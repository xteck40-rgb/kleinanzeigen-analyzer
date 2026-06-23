"""
End-to-end pipeline: Stage 1 (Trend-Hunter) -> Stage 2 (Reviewer) -> Stage 3 (Orchestrator).

Persists every stage result to the `arbitrage_runs` table so the frontend can
show history. All rows from the same pipeline invocation share a
`pipeline_run_id` UUID.

Backend must be running on http://127.0.0.1:8000 (uvicorn main:app).

CLI:
    cd backend
    venv\\Scripts\\activate
    python -m agents.pipeline                  # both domains: general + cars
    python -m agents.pipeline general          # only general
    python -m agents.pipeline cars             # only cars
    python -m agents.pipeline general --no-review   # skip Stage 2 (debug)

Programmatic:
    from agents.pipeline import run_pipeline, PipelineParams
    await run_pipeline(PipelineParams(domains=["general"], stage3_max_pages=15),
                      event_cb=async_callback, pipeline_id="...")
"""
import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional

from agents.orchestrator import run_for_product
from agents.reviewer import filter_approved, run_reviewer
from agents.trend_hunter import run_trend_hunter
from database import Database

EventCb = Optional[Callable[[dict], Awaitable[None]]]


@dataclass
class PipelineParams:
    domains: list[str] = field(default_factory=lambda: ["general", "cars"])
    skip_review: bool = False
    stage3_max_pages: int = 15
    plz: str = ""
    radius: int = 0
    min_review_score: int = 50


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        candidate = cleaned[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return {}


async def _emit(cb: EventCb, evt: dict):
    if cb:
        try:
            await cb(evt)
        except Exception:
            pass


async def run_pipeline(
    params: PipelineParams,
    event_cb: EventCb = None,
    pipeline_id: Optional[str] = None,
) -> str:
    """Run full 3-stage pipeline. Returns pipeline_id."""
    pid = pipeline_id or str(uuid.uuid4())
    db = Database()
    await db.init()

    await _emit(event_cb, {"type": "pipeline_start", "pipeline_id": pid,
                           "params": {"domains": params.domains,
                                      "skip_review": params.skip_review,
                                      "stage3_max_pages": params.stage3_max_pages,
                                      "plz": params.plz, "radius": params.radius}})

    all_products: list[dict] = []
    for domain in params.domains:
        print(f"\n########## STAGE 1: Trend-Hunter ({domain}) ##########")
        await _emit(event_cb, {"type": "stage_start", "stage": "trend_hunter", "domain": domain})
        try:
            products = await run_trend_hunter(domain, event_cb=event_cb)
        except Exception as e:
            print(f"Trend-Hunter ({domain}) ERROR: {e}")
            await _emit(event_cb, {"type": "error", "stage": "trend_hunter",
                                   "domain": domain, "message": (f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)})
            continue

        print(f"\n>>> {len(products)} products from {domain}")
        await db.save_arbitrage_run(
            ran_at=datetime.now().isoformat(),
            stage="trend_hunter",
            domain=domain,
            products_json=json.dumps(products, ensure_ascii=False),
            pipeline_run_id=pid,
        )
        await _emit(event_cb, {"type": "stage_done", "stage": "trend_hunter",
                               "domain": domain, "products": products})
        for p in products:
            p.setdefault("_domain", domain)
        all_products.extend(products)

    if not all_products:
        await _emit(event_cb, {"type": "pipeline_done", "pipeline_id": pid,
                               "reason": "no_products"})
        return pid

    if params.skip_review:
        print("\n########## STAGE 2: Reviewer SKIPPED ##########")
        await _emit(event_cb, {"type": "stage_skipped", "stage": "reviewer"})
        approved = all_products
    else:
        print(f"\n########## STAGE 2: Reviewer ({len(all_products)} candidates) ##########")
        await _emit(event_cb, {"type": "stage_start", "stage": "reviewer",
                               "candidate_count": len(all_products)})
        try:
            reviewed = await run_reviewer(all_products, event_cb=event_cb)
        except Exception as e:
            print(f"Reviewer ERROR: {e} — falling back to all candidates")
            await _emit(event_cb, {"type": "error", "stage": "reviewer", "message": (f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)})
            reviewed = []

        if reviewed:
            await db.save_arbitrage_run(
                ran_at=datetime.now().isoformat(),
                stage="reviewer",
                products_json=json.dumps(reviewed, ensure_ascii=False),
                pipeline_run_id=pid,
            )
            approved = filter_approved(reviewed, min_score=params.min_review_score)
            print(f"\n>>> {len(approved)}/{len(reviewed)} approved (score>={params.min_review_score})")
            await _emit(event_cb, {"type": "stage_done", "stage": "reviewer",
                                   "reviewed": reviewed, "approved_count": len(approved)})
        else:
            print("Reviewer produced no output — falling back to all candidates")
            await _emit(event_cb, {"type": "stage_done", "stage": "reviewer",
                                   "reviewed": [], "approved_count": len(all_products),
                                   "warning": "parse_failure_fallback"})
            approved = all_products

    if not approved:
        await _emit(event_cb, {"type": "pipeline_done", "pipeline_id": pid,
                               "reason": "no_approved"})
        return pid

    # Inject Stage-3 overrides + strip price-band for non-cars.
    # Rationale: passing price_min/price_max to the scraper applies them as URL
    # filters → KA returns ONLY listings inside the band → tiny dataset, no way
    # to spot underpriced deals because the median itself is biased by the cap.
    # For cars we keep price_min (to skip €1 parts ads) but still drop price_max.
    for p in approved:
        p["max_pages"] = params.stage3_max_pages
        if params.plz:
            p["plz"] = params.plz
        if params.radius:
            p["radius"] = params.radius
        if p.get("category") != "cars":
            p["price_min"] = 0
            p["price_max"] = 0
        else:
            p["price_max"] = 0

    print(f"\n########## STAGE 3: Orchestrator ({len(approved)} products) ##########")
    await _emit(event_cb, {"type": "stage_start", "stage": "orchestrator",
                           "approved_count": len(approved)})

    for p in approved:
        query = p.get("query", "<no query>")
        print(f"\n========== {query} ==========")
        await _emit(event_cb, {"type": "product_start", "stage": "orchestrator",
                               "product_query": query, "config": p})
        try:
            result = await run_for_product(p, event_cb=event_cb)
            print(result)
            parsed = _extract_json_object(result)
            market = parsed.get("market") if parsed else None
            deals = parsed.get("top_deals") if parsed else None
            await db.save_arbitrage_run(
                ran_at=datetime.now().isoformat(),
                stage="orchestrator",
                product_query=query,
                market_json=json.dumps(market, ensure_ascii=False) if market else None,
                deals_json=json.dumps(deals, ensure_ascii=False) if deals else None,
                raw_text=result,
                pipeline_run_id=pid,
            )
            await _emit(event_cb, {"type": "product_done", "stage": "orchestrator",
                                   "product_query": query, "market": market, "deals": deals})
        except Exception as e:
            print(f"ERROR for {query}: {e}")
            await db.save_arbitrage_run(
                ran_at=datetime.now().isoformat(),
                stage="orchestrator",
                product_query=query,
                raw_text=f"ERROR: {e}",
                pipeline_run_id=pid,
            )
            await _emit(event_cb, {"type": "error", "stage": "orchestrator",
                                   "product_query": query, "message": (f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)})

    await _emit(event_cb, {"type": "stage_done", "stage": "orchestrator"})
    await _emit(event_cb, {"type": "pipeline_done", "pipeline_id": pid})
    print(f"\nPipeline complete. pipeline_run_id={pid}")
    return pid


async def main():
    args = sys.argv[1:]
    skip_review = "--no-review" in args
    domains = [a for a in args if not a.startswith("--")] or ["general", "cars"]
    await run_pipeline(PipelineParams(domains=domains, skip_review=skip_review))


if __name__ == "__main__":
    asyncio.run(main())
