"""
Stage-2 Reviewer Agent.

Takes the Stage-1 Trend-Hunter output and runs a skeptical second LLM pass:
- Sanity-checks margin assumptions (KA buy price vs real resell anchor).
- Validates demand signal (re-checks via ebay_sold + optional WebSearch).
- Flags weak reasoning, thin samples, unrealistic price bands.
- Scores each product 0-100 and emits approve/reject verdict.

Output: filtered + scored product list, sorted by score desc. Only approved
products flow into Stage 3.

Run:
    cd backend
    venv\\Scripts\\activate
    python -m agents.reviewer        # reads sample products from stdin or runs trend_hunter
"""
import asyncio
import json
import sys
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query

from agents.tools.ebay_sold import ebay_sold

EventCb = Optional[Callable[[dict], Awaitable[None]]]


SYSTEM_PROMPT = """You are a SKEPTICAL arbitrage-deal reviewer for a Kleinanzeigen flipping pipeline.

You receive a JSON array of candidate products from a Stage-1 Trend-Hunter. Your job is to challenge each candidate and decide if it deserves to advance to Stage 3 (full Kleinanzeigen scrape + deal analysis), which is expensive.

For EVERY candidate:
1. Re-verify the resell anchor by calling ebay_sold(query). Compare median_price_eur against the candidate's price_max. A healthy flip needs:
   - eBay sold_sample >= 5 (proves liquidity)
   - candidate.price_max <= 0.85 * eBay median (leaves margin after fees + shipping + risk)
   - eBay median is a coherent number, not skewed by outliers (check min/max spread)
2. Optionally use WebSearch ONCE per candidate if the demand signal looks soft and you want a sanity-check. Skip if Stage-1 reasoning already cites strong evidence.
3. Judge the Stage-1 `reasoning` field skeptically:
   - Is the demand claim concrete (sold-out, hyped, post-launch shortage) or vague ("popular")?
   - Is the margin claim quantified or hand-waved?
   - Is the `exclude` filter thorough enough?

SOFT-FAIL POLICY — do NOT auto-reject. The Stage-3 orchestrator has self-healing retry logic (drops PLZ/shortens query) that can rescue thin-market candidates. Score honestly, but reserve `reject` for candidates that fail multiple criteria:
- Thin eBay sample alone (sold_sample 2-4) -> score 40-55, verdict still `approve` if reasoning is concrete. Stage-3 can still find something.
- Margin slightly tight (price_max between 0.85 and 0.92 * median) -> score 50-65, verdict `approve` if other signals strong. Note in `concerns`.
- Margin AND sample both weak -> score 30-45, verdict `reject`.
- Demand reasoning vague AND no eBay sample -> score 0-30, `reject`.
- Hyper-niche collab released <14 days ago with thin eBay history -> score 25-40, `reject` (Stage-3 retries won't help if market is genuinely empty).

For EACH candidate output an enriched object with EXACTLY these additional fields:
{
  ...all original Stage-1 fields preserved verbatim...,
  "score": <int 0-100 — your confidence this will yield real deals>,
  "verdict": "approve" | "reject",
  "concerns": "<1-2 sentences: biggest risks or weaknesses>",
  "verified_resell_eur": <int median from your ebay_sold call, or null if it failed>,
  "verified_sample": <int sold_sample count, or 0>
}

Scoring rubric:
- 80-100: strong demand + clear margin + thorough exclude + healthy eBay sample
- 60-79: decent but with one soft spot (thin sample OR vague reasoning OR tight margin)
- 40-59: marginal — approve only if the soft spot is rescuable by Stage-3 retry (e.g. thin sample for a non-niche product). Otherwise reject.
- 0-39: reject — fundamentally weak or genuinely empty market.

Verdict rule: approve unless score < 40 OR (score 40-59 AND the failure mode is structural, not retryable).

You MAY add new exclude terms to a candidate if you spot obvious noise gaps. Do not change query, category, price_max etc. — only enrich.

CRITICAL: Output ONLY a JSON array. No prose, no markdown fences, no commentary. Include ALL input candidates (rejected ones too — caller filters)."""


def build_options() -> ClaudeAgentOptions:
    ebay_server = create_sdk_mcp_server(
        name="ebay",
        version="1.0.0",
        tools=[ebay_sold],
    )
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"ebay": ebay_server},
        allowed_tools=[
            "WebSearch",
            "mcp__ebay__ebay_sold",
        ],
        max_turns=60,
        model="claude-sonnet-4-6",
    )


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.splitlines() if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(text[start:end + 1])
    except Exception as e:
        print(f"[reviewer/parse] JSON error: {e}", flush=True)
        return []


async def run_reviewer(
    candidates: list[dict],
    verbose: bool = True,
    event_cb: EventCb = None,
) -> list[dict]:
    """Review Stage-1 candidates. Returns the same list enriched with score/
    verdict/concerns/verified_* fields. Caller decides how to filter."""
    if not candidates:
        return []

    async def emit(evt: dict):
        if event_cb:
            try:
                await event_cb(evt)
            except Exception:
                pass

    options = build_options()
    prompt = (
        "Review the following Stage-1 candidates. For each one verify resell "
        "price via ebay_sold and apply the rubric.\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n"
    )

    full_text = ""
    async for msg in query(prompt=prompt, options=options):
        cls = type(msg).__name__
        for block in getattr(msg, "content", []) or []:
            btype = type(block).__name__
            text = getattr(block, "text", None)
            if text:
                if verbose:
                    print(f"[{cls}] {text[:250]}", flush=True)
                full_text += text + "\n"
                await emit({"type": "agent_text", "stage": "reviewer", "text": text})
                continue
            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", None)
            if tool_name:
                if verbose:
                    print(f"[{cls}/{btype}] -> {tool_name}({str(tool_input)[:200]})", flush=True)
                await emit({"type": "tool_call", "stage": "reviewer", "tool": tool_name, "input": tool_input})
                continue
            tool_result = getattr(block, "content", None)
            if tool_result is not None and btype.endswith("ToolResultBlock"):
                preview = str(tool_result)[:200]
                if verbose:
                    print(f"[{cls}/{btype}] <- {preview}", flush=True)
                await emit({"type": "tool_result", "stage": "reviewer", "preview": preview})

    reviewed = _parse_json_array(full_text)
    if not reviewed:
        print("[reviewer] WARNING: parser returned 0 items — falling back to raw candidates with score=50/reject")
        return [
            {**c, "score": 50, "verdict": "reject", "concerns": "reviewer parse failure",
             "verified_resell_eur": None, "verified_sample": 0}
            for c in candidates
        ]
    return reviewed


def filter_approved(reviewed: list[dict], min_score: int = 60) -> list[dict]:
    """Keep only approved + score>=min_score, sorted by score desc."""
    approved = [
        r for r in reviewed
        if r.get("verdict") == "approve" and int(r.get("score", 0)) >= min_score
    ]
    approved.sort(key=lambda r: int(r.get("score", 0)), reverse=True)
    return approved


async def main():
    """Standalone: reads candidates from stdin as JSON array, prints reviewed JSON."""
    raw = sys.stdin.read().strip()
    if not raw:
        print("Usage: cat candidates.json | python -m agents.reviewer", file=sys.stderr)
        sys.exit(1)
    candidates = json.loads(raw)
    reviewed = await run_reviewer(candidates)
    approved = filter_approved(reviewed)
    print("\n=== REVIEWED (all) ===")
    print(json.dumps(reviewed, ensure_ascii=False, indent=2))
    print(f"\n=== APPROVED ({len(approved)}/{len(reviewed)}) ===")
    print(json.dumps(approved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
