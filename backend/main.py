import asyncio
import os
import sys

# Windows: force ProactorEventLoop so claude-agent-sdk can spawn the `claude` CLI
# subprocess. SelectorEventLoop (default in some uvicorn --reload setups) raises
# NotImplementedError on subprocess_exec.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Portable/frozen mode (PyInstaller .exe): the bundled Playwright browser and the
# built frontend live inside the package; the database is written next to the exe
# so it persists and travels with the folder. Must run BEFORE scraper import
# (which imports playwright and reads PLAYWRIGHT_BROWSERS_PATH).
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    _bundle = sys._MEIPASS  # PyInstaller data dir (onedir: the _internal folder)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(_bundle, "pw-browsers"))
    os.chdir(os.path.dirname(sys.executable))  # DB + writable files next to the exe

import concurrent.futures
import csv
import io
import json
import logging
import traceback
import uuid
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agents.pipeline import PipelineParams, run_pipeline
from agents.watch_scheduler import WatchScheduler
from analysis import analyze_listings
from database import Database
from llm import DEFAULT_MODEL
from scraper import scrape_kleinanzeigen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Kleinanzeigen Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    # Single-process mode serves the frontend same-origin; dev mode goes through
    # the vite proxy (also same-origin). allow_origin_regex covers any LAN/Tailscale
    # IP in case the frontend is ever hit cross-origin.
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
jobs: dict = {}
pipelines: dict = {}  # pipeline_id -> {status, queue, params, task, events_log}
watch_scheduler = WatchScheduler(db)

# ── Retention limits ───────────────────────────────────────────────────────────
MAX_SEARCHES_PER_USER = 50    # manual searches; oldest auto-deleted
MAX_AGENTS_PER_USER = 10      # scraper load cap
MAX_RUNS_PER_AGENT = 50       # rounds incl. their raw searches
MAX_SEEN_PER_AGENT = 2000     # dedup memory


def require_user(x_user_id: str = Header(default="")) -> int:
    """Lightweight name-only auth: the frontend sends X-User-Id after login."""
    try:
        uid = int(x_user_id)
        if uid > 0:
            return uid
    except (TypeError, ValueError):
        pass
    raise HTTPException(status_code=401, detail="Nicht angemeldet — bitte Namen wählen")


@app.on_event("startup")
async def startup():
    await db.init()
    watch_scheduler.start()


# ── Request model ──────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    max_pages: int = 3
    category: str = "all"
    plz: str = ""
    radius: int = 0
    year_from: int = 0
    year_to: int = 0
    km_max: int = 0
    price_min: int = 0
    price_max: int = 0
    ps_min: int = 0
    ps_max: int = 0
    detail_scrape: bool = False


# ── Background job ─────────────────────────────────────────────────────────────

async def run_scraping_job(search_id: str, req: SearchRequest):
    try:
        jobs[search_id] = {"status": "running", "progress": 0, "query": req.query}

        def on_progress(p: int):
            jobs[search_id]["progress"] = p

        def run_in_thread():
            return asyncio.run(scrape_kleinanzeigen(
                query=req.query,
                max_pages=req.max_pages,
                category=req.category,
                plz=req.plz,
                radius=req.radius,
                year_from=req.year_from,
                year_to=req.year_to,
                km_max=req.km_max,
                price_min=req.price_min,
                price_max=req.price_max,
                ps_min=req.ps_min,
                ps_max=req.ps_max,
                detail_scrape=req.detail_scrape,
                progress_callback=on_progress,
            ))

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            listings = await loop.run_in_executor(pool, run_in_thread)

        await db.save_listings(search_id, listings)
        jobs[search_id].update({"status": "done", "count": len(listings)})

    except Exception as exc:
        import traceback
        traceback.print_exc()
        err = str(exc)
        jobs[search_id].update({"status": "error", "error": err})
        await db.set_search_error(search_id, err)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/api/search")
async def start_search(req: SearchRequest, background_tasks: BackgroundTasks,
                       x_user_id: str = Header(default="")):
    user_id = require_user(x_user_id)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query darf nicht leer sein")

    search_id = str(uuid.uuid4())
    req.query = req.query.strip()

    await db.save_search(search_id, req.query, req.category, req.max_pages, user_id=user_id)
    await db.prune_user_searches(user_id, keep=MAX_SEARCHES_PER_USER)
    jobs[search_id] = {"status": "pending", "progress": 0, "query": req.query}
    background_tasks.add_task(run_scraping_job, search_id, req)

    return {"search_id": search_id}


@app.get("/api/status/{search_id}")
async def get_status(search_id: str):
    job = jobs.get(search_id)
    if job:
        return job
    # Fallback: check DB (after server restart)
    searches = await db.get_searches()
    for s in searches:
        if s["id"] == search_id:
            return {"status": s["status"], "progress": 100, "count": s["count"]}
    raise HTTPException(status_code=404, detail="Job nicht gefunden")


@app.get("/api/results/{search_id}")
async def get_results(search_id: str):
    listings = await db.get_listings(search_id)
    return {"listings": listings, "count": len(listings)}


@app.get("/api/analyze/{search_id}")
async def analyze(search_id: str, deal_threshold: float = 0.80, exclude: str = ""):
    listings = await db.get_listings(search_id)
    if not listings:
        raise HTTPException(status_code=404, detail="Keine Inserate gefunden")

    result = analyze_listings(listings, deal_threshold=deal_threshold, exclude=exclude)

    # MLR (cars with enough data)
    filtered = result["listings"]
    has_car_data = any(l.get("km") or l.get("year") for l in filtered)
    if has_car_data and len(filtered) >= 10:
        result["mlr"] = _run_mlr(filtered)

    return result


def _run_mlr(listings: list) -> Optional[dict]:
    try:
        rows = []
        for l in listings:
            price = l.get("price_value")
            if not price or price <= 0:
                continue
            rows.append({
                "price":       price,
                "km":          l.get("km"),
                "year":        l.get("year"),
                "power_hp":    l.get("power_hp"),
                "fuel_diesel": 1 if l.get("fuel") == "Diesel" else 0,
                "fuel_elektro":1 if l.get("fuel") == "Elektro" else 0,
                "gear_auto":   1 if l.get("gearbox") == "Automatik" else 0,
            })

        if len(rows) < 10:
            return None

        df = pd.DataFrame(rows).dropna(subset=["price"])

        features = []
        if df["km"].notna().sum() >= 8:       features.append("km")
        if df["year"].notna().sum() >= 8:      features.append("year")
        if df["power_hp"].notna().sum() >= 8:  features.append("power_hp")
        for col in ["fuel_diesel", "fuel_elektro", "gear_auto"]:
            if df[col].sum() >= 3:             features.append(col)

        if not features:
            return None

        df_c = df.dropna(subset=features + ["price"]).copy()
        if len(df_c) < 10:
            return None

        X = df_c[features].values.astype(float)
        y = df_c["price"].values.astype(float)

        X_mean = X.mean(axis=0)
        X_std  = X.std(axis=0)
        X_std[X_std == 0] = 1
        X_norm = (X - X_mean) / X_std
        X_b = np.c_[np.ones(len(X_norm)), X_norm]

        theta = np.linalg.lstsq(X_b, y, rcond=None)[0]
        y_pred = X_b @ theta
        ss_res = ((y - y_pred) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        labels = {
            "km": "Kilometerstand", "year": "Baujahr", "power_hp": "Leistung (PS)",
            "fuel_diesel": "Kraftstoff: Diesel", "fuel_elektro": "Kraftstoff: Elektro",
            "gear_auto": "Getriebe: Automatik",
        }
        # unit_mult: multiply de-normalized coef by this for a human-readable step
        # unit_label: the label shown in UI ("je 10.000 km", "je Jahr", …)
        units = {
            "km":          (10_000, "je 10.000 km"),
            "year":        (1,      "je Jahr"),
            "power_hp":    (10,     "je 10 PS"),
            "fuel_diesel": (1,      "wenn Diesel"),
            "fuel_elektro":(1,      "wenn Elektro"),
            "gear_auto":   (1,      "wenn Automatik"),
        }
        coefficients = []
        for i, feat in enumerate(features):
            coef_norm = float(theta[i + 1])          # per 1 std-dev (normalized scale)
            coef_unit = coef_norm / X_std[i]          # per 1 raw unit (de-normalized)
            unit_mult, unit_label = units.get(feat, (1, "je Einheit"))
            per_unit_value = coef_unit * unit_mult    # per meaningful unit
            coefficients.append({
                "feature":        labels.get(feat, feat),
                "direction":      "positiv" if coef_norm > 0 else "negativ",
                "impact":         abs(round(coef_norm, 2)),   # normalized — used for bar width
                "per_unit_value": round(per_unit_value),      # €/meaningful unit — displayed
                "per_unit_label": unit_label,
            })
        coefficients.sort(key=lambda x: x["impact"], reverse=True)

        top = coefficients[0] if coefficients else None
        quality = "gut" if r2 > 0.6 else "mäßig" if r2 > 0.35 else "schwach"
        interpretation = ""
        if top:
            direction = "erhöht" if top["direction"] == "positiv" else "senkt"
            interpretation = (
                f"Das Modell erklärt {round(r2*100,1)}% der Preisunterschiede ({quality}). "
                f"Wichtigster Preistreiber: '{top['feature']}' — ein höherer Wert {direction} den Preis am stärksten."
            )

        return {
            "r2": round(r2, 3), "r2_pct": round(r2 * 100, 1),
            "n_samples": len(df_c), "coefficients": coefficients,
            "interpretation": interpretation,
        }
    except Exception as e:
        logger.error(f"MLR error: {e}")
        return None


@app.get("/api/searches")
async def list_searches(x_user_id: str = Header(default="")):
    user_id = require_user(x_user_id)
    return {"searches": await db.get_searches(user_id)}


# ── Users (name-only login) ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    name: str


@app.post("/api/login")
async def login(req: LoginRequest):
    name = req.name.strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="Name muss 1-40 Zeichen lang sein")
    user = await db.login_user(name)
    return {"id": user["id"], "name": user["name"]}


@app.get("/api/users")
async def list_users():
    return {"users": await db.get_users()}


@app.delete("/api/searches/{search_id}")
async def delete_search(search_id: str):
    await db.delete_search(search_id)
    jobs.pop(search_id, None)
    return {"deleted": search_id}


@app.get("/api/export/{search_id}")
async def export_csv(search_id: str):
    listings = await db.get_listings(search_id)
    if not listings:
        raise HTTPException(status_code=404, detail="Keine Inserate gefunden")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=listings[0].keys())
    writer.writeheader()
    writer.writerows(listings)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=kleinanzeigen_{search_id[:8]}.csv"},
    )


@app.get("/api/arbitrage/runs")
async def list_arbitrage_runs(limit: int = 200):
    rows = await db.get_arbitrage_runs(limit)
    return {"runs": rows}


@app.get("/api/arbitrage/runs/{run_id}")
async def get_arbitrage_run(run_id: int):
    row = await db.get_arbitrage_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run nicht gefunden")
    return row


@app.delete("/api/arbitrage/runs/{run_id}")
async def delete_arbitrage_run(run_id: int):
    await db.delete_arbitrage_run(run_id)
    return {"deleted": run_id}


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Kleinanzeigen Analyzer API"}


# ── Arbitrage Pipeline (Stage 1+2+3 via API) ───────────────────────────────────

class PipelineStartRequest(BaseModel):
    domains: list[str] = ["general"]
    skip_review: bool = False
    stage3_max_pages: int = 15
    plz: str = ""
    radius: int = 0
    min_review_score: int = 50


SENTINEL = {"type": "__close__"}


async def _run_pipeline_task(pid: str, params: PipelineParams):
    state = pipelines[pid]
    queue: asyncio.Queue = state["queue"]

    async def event_cb(evt: dict):
        state["events_log"].append(evt)
        await queue.put(evt)

    state["status"] = "running"
    try:
        await run_pipeline(params, event_cb=event_cb, pipeline_id=pid)
        state["status"] = "done"
    except Exception as e:
        logger.exception("pipeline failed")
        msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        state["status"] = "error"
        state["error"] = msg
        await queue.put({"type": "error", "stage": "pipeline",
                         "message": msg, "traceback": traceback.format_exc()})
    finally:
        await queue.put(SENTINEL)


@app.post("/api/pipeline/start")
async def pipeline_start(req: PipelineStartRequest):
    if not req.domains:
        raise HTTPException(status_code=400, detail="domains darf nicht leer sein")
    pid = str(uuid.uuid4())
    params = PipelineParams(
        domains=req.domains,
        skip_review=req.skip_review,
        stage3_max_pages=req.stage3_max_pages,
        plz=req.plz,
        radius=req.radius,
        min_review_score=req.min_review_score,
    )
    pipelines[pid] = {
        "status": "pending",
        "queue": asyncio.Queue(),
        "params": req.model_dump(),
        "events_log": [],
        "task": None,
        "started_at": pd.Timestamp.now().isoformat(),
    }
    task = asyncio.create_task(_run_pipeline_task(pid, params))
    pipelines[pid]["task"] = task
    return {"pipeline_id": pid}


@app.get("/api/pipeline/status/{pipeline_id}")
async def pipeline_status(pipeline_id: str):
    p = pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline nicht gefunden")
    return {
        "status": p["status"],
        "params": p["params"],
        "event_count": len(p["events_log"]),
        "error": p.get("error"),
    }


@app.get("/api/pipeline/stream/{pipeline_id}")
async def pipeline_stream(pipeline_id: str):
    p = pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline nicht gefunden")

    async def gen():
        # First replay everything that already happened so a late-connecting client
        # doesn't miss early events.
        for evt in list(p["events_log"]):
            yield {"event": evt.get("type", "message"), "data": json.dumps(evt, ensure_ascii=False)}
        queue: asyncio.Queue = p["queue"]
        while True:
            evt = await queue.get()
            if evt is SENTINEL:
                yield {"event": "close", "data": "{}"}
                break
            yield {"event": evt.get("type", "message"), "data": json.dumps(evt, ensure_ascii=False)}

    return EventSourceResponse(gen())


@app.delete("/api/pipeline/{pipeline_id}")
async def pipeline_cancel(pipeline_id: str):
    p = pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline nicht gefunden")
    task = p.get("task")
    if task and not task.done():
        task.cancel()
    p["status"] = "cancelled"
    await p["queue"].put(SENTINEL)
    return {"cancelled": pipeline_id}


# ── Settings (OpenRouter) ──────────────────────────────────────────────────────

class SettingsRequest(BaseModel):
    openrouter_api_key: Optional[str] = None  # None = unverändert lassen
    openrouter_model: Optional[str] = None


@app.get("/api/settings")
async def get_settings():
    key = await db.get_setting("openrouter_api_key")
    model = await db.get_setting("openrouter_model")
    return {
        "openrouter_key_set": bool(key),
        "openrouter_key_preview": (key[:8] + "…" + key[-4:]) if len(key) > 14 else ("gesetzt" if key else ""),
        "openrouter_model": model or DEFAULT_MODEL,
        "default_model": DEFAULT_MODEL,
    }


@app.put("/api/settings")
async def put_settings(req: SettingsRequest):
    if req.openrouter_api_key is not None:
        await db.set_setting("openrouter_api_key", req.openrouter_api_key.strip())
    if req.openrouter_model is not None:
        await db.set_setting("openrouter_model", req.openrouter_model.strip())
    return await get_settings()


# ── Watch agents ───────────────────────────────────────────────────────────────

class WatchProductRequest(BaseModel):
    name: str
    query: str
    category: str = "all"
    plz: str = ""
    radius: int = 0
    price_min: int = 0
    price_max: int = 0
    year_from: int = 0
    year_to: int = 0
    km_max: int = 0
    ps_min: int = 0
    max_pages: int = 3
    interval_minutes: int = 20
    exclude: str = ""
    custom_prompt: str = ""
    active: bool = True
    max_age_days: int = 60


def _watch_payload(req: WatchProductRequest) -> dict:
    d = req.model_dump()
    d["active"] = 1 if d["active"] else 0
    d["name"] = d["name"].strip()
    d["query"] = d["query"].strip()
    d["current_query"] = ""
    d["interval_minutes"] = max(5, int(d["interval_minutes"]))
    d["max_age_days"] = max(0, int(d["max_age_days"]))  # 0 = kein Altersfilter
    return d


@app.get("/api/watch/products")
async def watch_list(x_user_id: str = Header(default="")):
    user_id = require_user(x_user_id)
    products = await db.get_watch_products(user_id)
    for p in products:
        p["is_running"] = p["id"] in watch_scheduler.running_ids
    return {"products": products}


@app.post("/api/watch/products")
async def watch_create(req: WatchProductRequest, x_user_id: str = Header(default="")):
    user_id = require_user(x_user_id)
    if not req.name.strip() or not req.query.strip():
        raise HTTPException(status_code=400, detail="Name und Suchbegriff dürfen nicht leer sein")
    if await db.count_watch_products(user_id) >= MAX_AGENTS_PER_USER:
        raise HTTPException(status_code=400,
                            detail=f"Maximal {MAX_AGENTS_PER_USER} Agenten pro Nutzer — lösche zuerst einen")
    pid = await db.create_watch_product(_watch_payload(req), user_id=user_id)
    return {"id": pid}


@app.put("/api/watch/products/{product_id}")
async def watch_update(product_id: int, req: WatchProductRequest):
    if not await db.get_watch_product(product_id):
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    payload = _watch_payload(req)
    payload.pop("current_query", None)  # editing must not wipe the agent's refined query
    await db.update_watch_product(product_id, payload)
    return {"updated": product_id}


@app.delete("/api/watch/products/{product_id}")
async def watch_delete(product_id: int):
    await db.delete_watch_product(product_id)
    return {"deleted": product_id}


@app.post("/api/watch/products/{product_id}/toggle")
async def watch_toggle(product_id: int):
    p = await db.get_watch_product(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    new_active = 0 if p.get("active") else 1
    update = {"active": new_active}
    if new_active:
        # reactivation: run soon instead of waiting out a stale next_run_at
        update["next_run_at"] = pd.Timestamp.now().isoformat()
    await db.update_watch_product(product_id, update)
    return {"id": product_id, "active": bool(new_active)}


@app.post("/api/watch/products/{product_id}/run-now")
async def watch_run_now(product_id: int):
    p = await db.get_watch_product(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    if not await db.get_setting("openrouter_api_key"):
        raise HTTPException(status_code=400, detail="Kein OpenRouter API-Key gesetzt (Einstellungen)")
    if product_id in watch_scheduler.running_ids:
        raise HTTPException(status_code=409, detail="Runde läuft bereits")
    await watch_scheduler.trigger_now(product_id)
    if not p.get("active"):
        await db.update_watch_product(product_id, {"active": 1})
    return {"triggered": product_id}


@app.post("/api/watch/products/{product_id}/reset-query")
async def watch_reset_query(product_id: int):
    """Discard the agent-refined query + synonyms, go back to the user's base query."""
    if not await db.get_watch_product(product_id):
        raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
    await db.update_watch_product(product_id, {"current_query": "", "query_aliases": ""})
    return {"reset": product_id}


@app.get("/api/watch/products/{product_id}/runs")
async def watch_runs(product_id: int, limit: int = 30):
    runs = await db.get_watch_runs(product_id, limit)
    return {"runs": runs}


@app.get("/api/watch/products/{product_id}/top")
async def watch_top(product_id: int, limit: int = 30):
    """Best listings across all rounds (agent-curated list)."""
    return {"top": await db.get_top_seen(product_id, limit)}


@app.get("/api/watch/runs/{run_id}")
async def watch_run_detail(run_id: int):
    run = await db.get_watch_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run nicht gefunden")
    return run


# ── Serve built frontend (single-process mode) ─────────────────────────────────
# Mounted LAST so all /api routes above take precedence. If the built frontend
# exists, the whole app is reachable on ONE port — no node, no vite, no second
# terminal. In dev you still use `npm run dev` + the vite proxy.
from fastapi.staticfiles import StaticFiles

if FROZEN:
    _DIST = os.path.join(sys._MEIPASS, "frontend_dist")
else:
    _DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
    logger.info("Serving built frontend from %s", os.path.abspath(_DIST))
else:
    logger.warning("frontend/dist not found — run setup.ps1 or `npm run build` to enable single-port mode")


# ── Entry point for the packaged .exe ──────────────────────────────────────────
def _run():
    import uvicorn
    print("\n=== Kleinanzeigen Analyzer ===")
    print("  Lokal:  http://localhost:8000")
    try:
        ts = r"C:\Program Files\Tailscale\tailscale.exe"
        if os.path.exists(ts):
            import subprocess
            ip = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
            if ip:
                print(f"  Netz:   http://{ip[0].strip()}:8000   (Tailscale)")
    except Exception:
        pass
    print("  Beenden: dieses Fenster schliessen\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    _run()
