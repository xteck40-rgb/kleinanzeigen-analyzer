"""
Stage-1 Trend-Hunter Agent.

Generates a list of products currently profitable to flip on Kleinanzeigen.
Two domains: "general" (electronics/consumer goods) and "cars".

Uses built-in WebSearch + WebFetch tools (server-side, provided by Claude Code
auth — no extra setup needed on the Pro plan).

Run:
    cd backend
    venv\\Scripts\\activate
    python -m agents.trend_hunter            # default: general
    python -m agents.trend_hunter cars
"""
import asyncio
import json
import sys
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query

from agents.tools.ebay_sold import ebay_sold

EventCb = Optional[Callable[[dict], Awaitable[None]]]


GENERAL_SYSTEM_PROMPT = """You are a Kleinanzeigen arbitrage trend-hunter for GENERAL (non-vehicle) products in the German market.

Your job: identify 5-8 products that are currently profitable to buy used on Kleinanzeigen and resell at a profit on eBay / Kleinanzeigen / similar.

Process:
1. Use WebSearch (multiple queries) to find candidate products:
   - Currently trending / sold-out / hyped consumer products in DE
   - Recent product drops (new iPhone, new console, new GPU, etc.)
   - r/Flipping or r/de threads about profitable second-hand items
   - AVOID hyper-niche collab drops released <14 days ago (e.g. limited sneaker collabs, NFT-adjacent items). KA inventory will be near zero — the flip is theoretical.
2. Optionally WebFetch a promising source for more detail.
3. For EACH candidate: call ebay_sold(query). Require ebay_sold.sold_sample >= 5 (proves a real resale market). Discard candidates below that.
4. Compute price_max with this EXACT formula: price_max = round(0.78 * ebay_sold.median_price_eur). No "10-20% below" hand-waving — the Stage-2 reviewer enforces price_max <= 0.85 * median, so 0.78 leaves a safety buffer to survive rounding and reviewer scoring.
5. Compile a JSON array of 5-8 products that passed validation.

Each product MUST follow this EXACT schema:
{
  "query": "<keyword to search on Kleinanzeigen — see CRITICAL rules below>",
  "category": "all",
  "price_min": <int — floor to skip €1 spam ads and accessories>,
  "price_max": <int — ceiling above realistic sell-price>,
  "exclude": "<comma-separated noise terms — keep TIGHT, see below>",
  "reasoning": "<one sentence: WHY this product right now (demand signal, est margin, source)>"
}

CRITICAL query rules (Kleinanzeigen does AND-match across ALL tokens — every extra token slashes hit count by ~50%):
- HARD MAX 3 tokens. 2 is better. Aim for the SHORTEST string that uniquely identifies the product family.
- NEVER include storage size (128GB, 256GB, 1TB), color, carrier, or year in the query — these tokens are written 5+ different ways by sellers and kill 70% of hits. Use price_min/price_max to separate storage tiers instead.
- NEVER quote the query.
  GOOD: "iPhone 16 Pro", "PS5 Pro", "Dyson V15", "RTX 4090", "WH-1000XM5"
  BAD:  "iPhone 16 Pro 128GB Titan Schwarz", "Sony WH-1000XM5 Headphones Wireless", "PlayStation 5 Pro 30th Anniversary 1TB"
- One product = one query. For variants (iPhone 16 vs 16 Pro vs 16 Pro Max) emit SEPARATE entries.

CRITICAL exclude rules (only filter UNAMBIGUOUS buyer-ads + parts, do NOT over-filter):
- Terms are matched as whole words (\\bterm\\b) AND skipped when preceded by a negation ("kein", "ohne", "nicht", "no"), so common false-positives like "kein Defekt" don't trigger.
- HARD MAX 5 terms total. Every additional term silently cuts more legit listings than it saves.
- Always-safe (sellers never use these): ankauf, suche, gesuch, ersatzteile
- Optional ONE category-specific noise term if obvious (e.g. "bastler" for electronics, "totalschaden" for cars).
- DO NOT include: kabel, ladegerät, case, hülle, defekt, kaputt, reparatur — they appear in legitimate descriptions ("inkl. Kabel und Ladegerät", "kein Defekt", "mit Originalhülle") and the regex+negation handler can't always rescue them.

CRITICAL: Output ONLY the JSON array. No prose, no markdown code fences, no commentary."""


CARS_SYSTEM_PROMPT = """You are a Kleinanzeigen arbitrage trend-hunter for CARS in the German market.

Your job: identify 5-8 used car models currently profitable to flip on Kleinanzeigen.

Process:
1. Use WebSearch (multiple queries) for:
   - "wertstabile Gebrauchtwagen 2026"
   - "günstige Gebrauchtwagen Wertsteigerung"
   - Enthusiast/youngtimer trends (Golf GTI, BMW M, Audi RS, etc.)
   - Models with high demand vs supply
2. Optionally WebFetch auto-blogs / motor-talk threads.
3. For EACH candidate model: call ebay_sold(query) (works for cars too — eBay Motors).
   Use median_price_eur as a sanity floor — set Kleinanzeigen price_max ~10-20% below it.
   Skip candidates with no eBay sample (low market = no clear resell anchor).
4. Compile a JSON array of 5-8 car models that passed eBay validation.

Each product MUST follow this EXACT schema:
{
  "query": "<model search, see CRITICAL rules below>",
  "category": "cars",
  "price_min": <int — sane min price>,
  "price_max": <int — 0 if no cap>,
  "year_from": <int — e.g. 2014>,
  "km_max": <int — e.g. 150000>,
  "ps_min": <int — 0 to skip, else min PS for performance variants>,
  "exclude": "totalschaden,unfall,bastler,ersatzteile",
  "reasoning": "<one sentence: WHY this model right now>"
}

CRITICAL query rules (Kleinanzeigen does AND-match — every extra token slashes hit count):
- HARD MAX 3 tokens. Pick the SHORTEST identifier that pins the model+generation.
- DO NOT include color, year, fuel type, transmission, mileage in the query — use the dedicated fields (year_from, km_max, ps_min) for that.
  GOOD: "Golf 7 GTI", "BMW M3 E92", "Audi RS3 8V", "Porsche 911 997"
  BAD:  "Golf 7 GTI Performance 2018 schwarz", "BMW M3 M4 Competition", "Audi A4 B8 Diesel 2.0 TDI"
- One model/generation = one query. For multiple generations emit SEPARATE entries.

CRITICAL: Output ONLY the JSON array. No prose, no markdown code fences."""


def build_options(system_prompt: str) -> ClaudeAgentOptions:
    ebay_server = create_sdk_mcp_server(
        name="ebay",
        version="1.0.0",
        tools=[ebay_sold],
    )
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={"ebay": ebay_server},
        allowed_tools=[
            "WebSearch",
            "WebFetch",
            "mcp__ebay__ebay_sold",
        ],
        max_turns=40,
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
        print(f"[parse] JSON error: {e}", flush=True)
        return []


async def run_trend_hunter(
    domain: str = "general",
    verbose: bool = True,
    event_cb: EventCb = None,
) -> list[dict]:
    if domain == "cars":
        prompt = "Find 5-8 profitable car models for Kleinanzeigen arbitrage right now. Use WebSearch with multiple queries before deciding."
        options = build_options(CARS_SYSTEM_PROMPT)
    else:
        prompt = "Find 5-8 profitable consumer products for Kleinanzeigen arbitrage right now. Use WebSearch with multiple queries before deciding."
        options = build_options(GENERAL_SYSTEM_PROMPT)

    async def emit(evt: dict):
        if event_cb:
            try:
                await event_cb(evt)
            except Exception:
                pass

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
                await emit({"type": "agent_text", "stage": "trend_hunter", "domain": domain, "text": text})
                continue
            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", None)
            if tool_name:
                if verbose:
                    print(f"[{cls}/{btype}] -> {tool_name}({str(tool_input)[:200]})", flush=True)
                await emit({"type": "tool_call", "stage": "trend_hunter", "domain": domain,
                            "tool": tool_name, "input": tool_input})
                continue
            tool_result = getattr(block, "content", None)
            if tool_result is not None and btype.endswith("ToolResultBlock"):
                preview = str(tool_result)[:200]
                if verbose:
                    print(f"[{cls}/{btype}] <- {preview}", flush=True)
                await emit({"type": "tool_result", "stage": "trend_hunter", "domain": domain,
                            "preview": preview})

    products = _parse_json_array(full_text)
    return products


async def main():
    domain = sys.argv[1] if len(sys.argv) > 1 else "general"
    print(f"\n=== Trend-Hunter ({domain}) ===")
    products = await run_trend_hunter(domain)
    print("\n=== PARSED PRODUCTS ===")
    print(json.dumps(products, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
