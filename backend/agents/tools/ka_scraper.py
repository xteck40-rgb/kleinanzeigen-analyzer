import asyncio
import json

import httpx
from claude_agent_sdk import tool

BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 900  # 15 min max for one scrape


@tool(
    "start_search",
    "Start a Kleinanzeigen scrape with the given filters. Returns search_id (UUID string) to be passed to wait_for_done. Forward plz/radius/max_pages from the product config verbatim if present.",
    {
        "query": str,
        "category": str,
        "max_pages": int,
        "price_min": int,
        "price_max": int,
        "year_from": int,
        "km_max": int,
        "ps_min": int,
        "plz": str,
        "radius": int,
    },
)
async def start_search(args: dict) -> dict:
    payload = {
        "query": args["query"],
        "category": args.get("category", "all"),
        "max_pages": args.get("max_pages", 15),
        "price_min": args.get("price_min", 0),
        "price_max": args.get("price_max", 0),
        "year_from": args.get("year_from", 0),
        "year_to": 0,
        "km_max": args.get("km_max", 0),
        "ps_min": args.get("ps_min", 0),
        "ps_max": 0,
        "plz": args.get("plz", ""),
        "radius": args.get("radius", 0),
        "detail_scrape": False,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE_URL}/api/search", json=payload)
        r.raise_for_status()
        sid = r.json().get("search_id", "")
    return {"content": [{"type": "text", "text": sid}]}


@tool(
    "wait_for_done",
    "Block until the scrape finishes. Polls every few seconds. Returns final status JSON with count.",
    {"search_id": str},
)
async def wait_for_done(args: dict) -> dict:
    sid = args["search_id"]
    elapsed = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while elapsed < POLL_TIMEOUT_S:
            try:
                r = await client.get(f"{BASE_URL}/api/status/{sid}")
                data = r.json()
            except Exception as e:
                data = {"status": f"poll_error:{e}"}

            status = data.get("status", "")
            if status == "done" or status.startswith("error"):
                return {"content": [{"type": "text", "text": json.dumps(data)}]}

            await asyncio.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

    return {"content": [{"type": "text", "text": json.dumps({"status": "timeout"})}]}


@tool(
    "get_deals",
    "Get analyzed deals for a completed scrape. exclude is a comma-separated list of noise terms (e.g. 'ankauf,ersatzteile,hülle,defekt,zubehör') that filter out irrelevant listings before deal ranking.",
    {"search_id": str, "deal_threshold": float, "top_n": int, "exclude": str},
)
async def get_deals(args: dict) -> dict:
    sid = args["search_id"]
    thr = args.get("deal_threshold", 0.80)
    top_n = args.get("top_n", 25)
    exclude = args.get("exclude", "")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/api/analyze/{sid}",
            params={"deal_threshold": thr, "exclude": exclude},
        )
        data = r.json()

    compact = {
        "count": data.get("count"),
        "raw_count": data.get("raw_count"),
        "excluded_count": data.get("excluded_count"),
        "with_price": data.get("with_price"),
        "median_price": data.get("median_price"),
        "avg_price": data.get("avg_price"),
        "min_price": data.get("min_price"),
        "max_price": data.get("max_price"),
        "deal_threshold_value": data.get("deal_threshold_value"),
        "deal_threshold_effective": data.get("deal_threshold_effective"),
        "top_deals": [
            {
                "title": d.get("title"),
                "price": d.get("price_value"),
                "url": d.get("url"),
                "km": d.get("km"),
                "year": d.get("year"),
                "fuel": d.get("fuel"),
                "location": d.get("location"),
                "date_posted": d.get("date_posted"),
            }
            for d in (data.get("deals") or [])[:top_n]
        ],
    }
    return {"content": [{"type": "text", "text": json.dumps(compact, ensure_ascii=False)}]}
