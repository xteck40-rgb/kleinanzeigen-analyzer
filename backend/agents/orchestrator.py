"""
Stage-3 Orchestrator Agent.

Takes a product description + search params, drives the Kleinanzeigen scraper
via tools, and returns top deals. Runs against the local FastAPI scraper which
must be up on http://127.0.0.1:8000 (uvicorn main:app).

Auth: uses Claude Code subscription (Pro/Max) automatically when claude-code
CLI is installed and logged in. No API key required.

Run:
    cd backend
    venv\\Scripts\\activate
    python -m agents.orchestrator
"""
import asyncio
import json
import sys
from typing import Awaitable, Callable, Optional

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query

from agents.tools.ka_scraper import get_deals, start_search, wait_for_done

EventCb = Optional[Callable[[dict], Awaitable[None]]]


SYSTEM_PROMPT = """You are a Kleinanzeigen arbitrage scout.

For each product the user gives you:
1. Call start_search with the right filters (category="cars" for vehicles, else "all"). Forward year_from, km_max, ps_min, max_pages, plz, radius from the product config when present. Forward `price_min` ONLY for cars (to skip €1 parts ads). NEVER forward `price_max` and NEVER forward `price_min` for non-car products — the scrape must see the full market so the deal-detection (sub-median threshold) has real data; pre-filtering at scrape time hides exactly the listings that prove the market exists. Reviewer used the price band to validate margin economics; Stage-3's job is volume.
2. Call wait_for_done with the returned search_id.
3. Call get_deals with the search_id, deal_threshold=0.80, top_n=25, and exclude=<product.exclude> verbatim from the product config. This strips noise (accessories, repair, parts).

SELF-HEALING — Inspect both get_deals.raw_count (listings KA actually returned) and get_deals.count (post-exclude). Choose retry strategy from the diagnostic:

  CASE A — raw_count >= 20 but count < 5: The scrape worked, the exclude filter killed everything. Retry get_deals on the SAME search_id with exclude="" (no filter). Do NOT re-scrape.

  CASE B — raw_count < 5 (genuinely thin scrape): Broaden the scrape, in this order:
    B1: drop plz + radius (DE-wide). Same query, same exclude.
    B2 (only if B1 still raw_count<5): shorten query by dropping the last token (e.g. "Nigel Sylvester Jordan 4" -> "Nigel Sylvester Jordan"). Keep DE-wide.
    B3 (only if B2 still raw_count<5): drop the exclude filter entirely.
    Each B-retry is a NEW start_search -> wait_for_done -> get_deals cycle.

Stop after at most 3 total retries (A counts as 1; B chain up to 3). Use the final non-empty result for the JSON output.

4. Return a JSON object with:
   - product: the original product name
   - market: {median_price, avg_price, count, raw_count}
   - top_deals: list of ALL deals returned (up to 25) with title, price, url, brief reason (why a deal vs market). Do not truncate.
   - retries_used: integer 0-3 (how many self-healing retries you ran)
   - retry_notes: short string describing what you changed (e.g. "exclude killed 80% of raw 50 -> retried no-exclude" or "dropped plz; shortened query") or "" if none.

Be concise per-deal but include every deal from get_deals output. No commentary outside the JSON. Output only valid JSON."""


# Hardcoded test products — replace with Stage-1/2 output later.
# `exclude` is forwarded to /api/analyze to filter noise from deal ranking
# (accessories, repair, parts, buyback ads).
PRODUCTS = [
    {
        "query": "PlayStation 5 Slim",
        "category": "all",
        "max_pages": 5,
        "price_min": 150,
        "price_max": 450,
        "exclude": "ankauf,suche,gesuch,zubehör,controller,hülle,tasche,spiel,game,disc,ersatzteile,defekt,reparatur",
    },
    {
        "query": "iPhone 15 Pro",
        "category": "all",
        "max_pages": 5,
        "price_min": 250,
        "price_max": 900,
        "exclude": "ankauf,suche,gesuch,hülle,case,ersatzteile,defekt,akku,display,reparatur,gehäuse,zubehör,kabel,ladegerät",
    },
    {
        "query": "Golf 7 GTI",
        "category": "cars",
        "max_pages": 10,
        "price_min": 4500,
        "year_from": 2014,
        "km_max": 150000,
        "ps_min": 200,
        "exclude": "totalschaden,getriebeschaden,motorschaden,unfall,bastler,ersatzteile",
    },
]


def build_options() -> ClaudeAgentOptions:
    server = create_sdk_mcp_server(
        name="ka",
        version="1.0.0",
        tools=[start_search, wait_for_done, get_deals],
    )
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"ka": server},
        allowed_tools=[
            "mcp__ka__start_search",
            "mcp__ka__wait_for_done",
            "mcp__ka__get_deals",
        ],
        max_turns=25,
        model="claude-sonnet-4-6",
    )


async def run_for_product(product: dict, event_cb: EventCb = None) -> str:
    options = build_options()
    query_label = product.get("query", "<no query>")
    prompt = (
        "Find deals for this product on Kleinanzeigen.\n"
        f"Product config:\n{json.dumps(product, ensure_ascii=False, indent=2)}\n"
    )

    async def emit(evt: dict):
        if event_cb:
            try:
                await event_cb(evt)
            except Exception:
                pass

    parts: list[str] = []
    async for msg in query(prompt=prompt, options=options):
        cls = type(msg).__name__
        for block in getattr(msg, "content", []) or []:
            btype = type(block).__name__

            text = getattr(block, "text", None)
            if text:
                print(f"[{cls}] {text}", flush=True)
                parts.append(text)
                await emit({"type": "agent_text", "stage": "orchestrator",
                            "product_query": query_label, "text": text})
                continue

            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", None)
            if tool_name:
                print(f"[{cls}/{btype}] -> tool {tool_name}({tool_input})", flush=True)
                await emit({"type": "tool_call", "stage": "orchestrator",
                            "product_query": query_label, "tool": tool_name, "input": tool_input})
                continue

            tool_result = getattr(block, "content", None)
            if tool_result is not None and btype.endswith("ToolResultBlock"):
                preview = str(tool_result)[:300]
                print(f"[{cls}/{btype}] <- result: {preview}", flush=True)
                await emit({"type": "tool_result", "stage": "orchestrator",
                            "product_query": query_label, "preview": preview})
                continue

            print(f"[{cls}/{btype}] {block!r}", flush=True)

        if cls == "ResultMessage":
            usage = getattr(msg, "usage", None)
            cost = getattr(msg, "total_cost_usd", None)
            print(f"[ResultMessage] usage={usage} cost=${cost}", flush=True)

    return "\n".join(parts).strip()


async def main():
    selected = PRODUCTS
    if len(sys.argv) > 1:
        # Quick filter: python -m agents.orchestrator iphone
        needle = sys.argv[1].lower()
        selected = [p for p in PRODUCTS if needle in p["query"].lower()]

    for product in selected:
        print(f"\n========== {product['query']} ==========")
        try:
            result = await run_for_product(product)
            print(result)
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())
