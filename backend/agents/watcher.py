"""
Watch agent: one autonomous "Suchrunde" for a watched product.

Round flow:
  1. Scrape Kleinanzeigen with the product's criteria (user criteria ALWAYS apply:
     plz/radius/price band/car filters). Query may be an agent-refined variant.
  2. Compute market metrics via the shared analysis module (median, distribution,
     sub-median deals) — the agent sees the same numbers as the Suche tab.
  3. SCOUT pass (LLM): review only listings never seen before. Per listing:
     relevant? (the actual product, not accessory/part/buy-ad), fake risk 0-100,
     deal score 0-100, short German reason. User's custom prompt is injected.
  4. VERIFY pass (LLM): skeptical second review of the shortlist (score >= 60).
     Final verdict per listing: top_deal | ok | reject + Begründung.
  5. LEARN pass (LLM): update the product's criteria notes (markdown list the
     agent maintains itself) and optionally suggest a better search query for
     the next round.

Everything is persisted: watch_runs (round results), watch_seen (per-listing
verdicts, dedup), watch_products.notes / current_query (agent memory).
"""
import asyncio
import concurrent.futures
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

from analysis import analyze_listings
from database import Database
from llm import DEFAULT_MODEL, LLMError, LLMNotConfigured, chat, extract_json_array, extract_json_object
from scraper import fetch_full_descriptions, parse_listing_date, scrape_kleinanzeigen

logger = logging.getLogger(__name__)

EventCb = Optional[Callable[[dict], Awaitable[None]]]

MAX_NEW_PER_ROUND = 40       # cap LLM cost per round
SHORTLIST_MIN_SCORE = 60     # scout score needed to reach the verify pass
MAX_DETAIL_FETCH = 15        # max full-description fetches per round (verify pass)
DESC_CHARS = 400             # listing snippet budget in the scout prompt
DESC_CHARS_FULL = 1800       # full-description budget in the verify prompt
MAX_QUERIES = 3              # base + up to 2 agent-suggested synonyms per round
ALIAS_MAX_PAGES = 3          # fewer pages per synonym query (cost/scrape control)


# ── Prompts ────────────────────────────────────────────────────────────────────

SCOUT_SYSTEM = """You are a buying scout reviewing kleinanzeigen.de listings for a user who wants to BUY a specific product. Listings are in German. You must answer with a single JSON array, nothing else.

For EVERY listing in the input decide:
- "relevant" (bool): Is this the actual, complete, WORKING product the user wants? false if it is only an accessory, controller, game, case, single part, repair service, rental, or a buyer's ad ("Suche", "Ankauf"). false also if the text mentions ANY defect or limitation that conflicts with the user's criteria — e.g. user wants the disc edition and the text says the drive does not read discs ("Laufwerk defekt", "liest keine Discs", "nur digital nutzbar"), or user wants a complete set and something is missing. Watch for softened defect phrasing: "Hinweis:", "kleiner Mangel", "funktioniert bis auf...", "Bastler". When the text is merely SILENT about a detail, set relevant=true but mention the doubt in reason. Note: descriptions here are truncated list-page snippets — a later verify step sees the full text.
- "fake_risk" (int 0-100): Scam probability. Strong signals: price far below market median for a sealed/new item, generic stock-photo style text, shipping-only insistence with prepayment, urgency pressure, contact outside the platform, brand-new at ~50% of median. Mild signals: very short description, no condition info.
- "score" (int 0-100): Deal quality for the user. Consider price vs. market median, stated condition, completeness (OVP, accessories included), seller plausibility. 90+ only for clearly underpriced, complete, plausible items.
- "reason" (string): ONE short German sentence justifying your verdict.

Apply the USER CRITERIA below strictly — listings violating them get relevant=false.
Output format: [{"i": <listing index>, "relevant": bool, "fake_risk": int, "score": int, "reason": "..."}] — one entry per input listing, same order."""

VERIFY_SYSTEM = """You are a SKEPTICAL second reviewer. A scout pre-selected kleinanzeigen.de listings as good deals for the user. Challenge each one. Listings are in German.

Where available you receive the FULL detail-page description (the scout only saw a snippet). Read it COMPLETELY before judging — sellers bury defect disclaimers at the end ("Hinweis zum Laufwerk: ...", "Verkauf als defekt", "ohne Zubehör", "Konto gesperrt"). Any defect, limitation or missing part that conflicts with the USER CRITERIA is an automatic "reject", no matter how good the price is.

For each listing output your FINAL verdict:
- "verdict": "top_deal" (clearly worth contacting the seller now), "ok" (decent, watch it), or "reject" (scam suspicion, wrong/incomplete/defective product, criteria conflict, or not actually a good price)
- "fake_risk" (int 0-100)
- "reason": 1-2 German sentences: WHY it is/isn't a real deal — name the price vs median, condition, risks.

Be strict about scams: a price that looks too good IS the most common scam pattern. But do not reject genuinely good deals just for low price if other signals are healthy (real description, local pickup possible, plausible wear).

Output ONLY a JSON array: [{"i": <index>, "verdict": "...", "fake_risk": int, "reason": "..."}]."""

LEARN_SYSTEM = """You maintain the long-term search strategy for an automated kleinanzeigen.de product watcher. You see the round summary (query used, hit counts, market stats, verdicts) and the current criteria notes.

Tasks:
1. Update the criteria notes: a German markdown bullet list (max 15 bullets) describing what makes a GOOD listing for this exact product (price ranges seen, common scam patterns observed, accessory noise terms, good search practice). Keep proven bullets, refine with this round's evidence, drop stale ones.
2. Optionally suggest a BETTER search query for the next round.

CRITICAL query rules (violating them DESTROYS results):
- Kleinanzeigen AND-matches EVERY token. Each extra word roughly halves the hit count. FEWER tokens = MORE listings. Default to the SHORTEST query that names the product family (often just the base query).
- NEVER add a variant/condition/feature token to the query to "filter": words like "Disc", "Digital", "OVP", "neu", "defektfrei", storage size, color, edition. Sellers phrase these 5 different ways ("Disc"/"Laufwerk"/"Blu-Ray"/"mit CD") or omit them, so such a token silently drops most good listings. These distinctions are the LLM REVIEWER's job (it reads each description), NOT the search query's job.
- Only suggest a NEW query to BROADEN/fix recall when raw_count is low: e.g. shorten to fewer tokens, or swap to a more common synonym of the SAME product (e.g. "PS5" instead of "Playstation 5"). Never to narrow.
- If raw_count is healthy (>= ~25) or the current query is already minimal, return null.
- Max 3 tokens.

3. Suggest SYNONYM ALIASES ("aliases"): up to 2 ALTERNATIVE search terms that would surface DIFFERENT relevant listings for the SAME product, because sellers name it differently. Examples: "Klimaanlage" -> ["Klimagerät", "mobile Klimaanlage"]; "Playstation 5" -> ["PS5"]; "Fahrrad" -> ["Bike", "Rad"]. These are run as SEPARATE searches and merged — so they should be genuine synonyms / common alternative spellings, NOT narrower variants and NOT unrelated accessories. Each <= 3 tokens. Keep good aliases stable across rounds; only change when evidence shows an alias finds nothing or a better synonym exists. If none make sense, return [].

Output ONLY a JSON object:
{"notes": "<updated markdown bullets>", "next_query": "<string or null>", "query_reason": "<short German reason or empty>", "aliases": ["<synonym1>", "<synonym2>"]}"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _listing_line(i: int, l: dict, include_desc: bool = True,
                  desc_override: str = None, desc_chars: int = DESC_CHARS) -> str:
    parts = [f'#{i} "{(l.get("title") or "")[:90]}"', f'{l.get("price_value") or l.get("price_text") or "?"}€']
    if l.get("km"):
        parts.append(f'{l["km"]}km')
    if l.get("year"):
        parts.append(str(l["year"]))
    if l.get("location"):
        parts.append(l["location"][:40])
    if l.get("date_posted"):
        parts.append(l["date_posted"][:20])
    line = " | ".join(parts)
    desc = (desc_override or l.get("description") or "").replace("\n", " ").strip()
    if include_desc and desc:
        label = "Volltext" if desc_override else "Beschreibung"
        line += f'\n   {label}: {desc[:desc_chars]}'
    return line


async def _fetch_full_descs(urls: list[str]) -> dict:
    """Playwright needs its own event loop — run in a worker thread like the scrape."""
    def run_in_thread():
        return asyncio.run(fetch_full_descriptions(urls))

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, run_in_thread)


def _criteria_text(product: dict) -> str:
    bits = [f'Produkt: {product["name"]} (Suchbegriff: {product["query"]})']
    if product.get("price_min") or product.get("price_max"):
        lo = product.get("price_min") or 0
        hi = product.get("price_max") or "∞"
        bits.append(f"Preisrahmen des Nutzers: {lo}–{hi} €")
    if product.get("plz"):
        bits.append(f'Region: PLZ {product["plz"]}, Umkreis {product.get("radius") or "DE-weit"} km')
    if product.get("category") == "cars":
        if product.get("year_from"):
            bits.append(f'Baujahr ab {product["year_from"]}')
        if product.get("km_max"):
            bits.append(f'max. {product["km_max"]} km')
        if product.get("ps_min"):
            bits.append(f'min. {product["ps_min"]} PS')
    if product.get("custom_prompt"):
        bits.append(f'ZUSÄTZLICHE ANWEISUNG DES NUTZERS (hohe Priorität): {product["custom_prompt"]}')
    return "\n".join(bits)


def _market_text(market: dict) -> str:
    return (
        f'Markt: {market.get("count")} Inserate (roh {market.get("raw_count")}), '
        f'Median {market.get("median_price")}€, Ø {market.get("avg_price")}€, '
        f'Spanne {market.get("min_price")}–{market.get("max_price")}€, '
        f'Deal-Schwelle {market.get("deal_threshold_value")}€'
    )


async def _scrape(product: dict, query: str, max_pages: int = None) -> list:
    """Run the playwright scraper in a worker thread (needs its own event loop)."""
    pages = max_pages if max_pages else (product.get("max_pages") or 3)
    def run_in_thread():
        return asyncio.run(scrape_kleinanzeigen(
            query=query,
            max_pages=pages,
            category=product.get("category") or "all",
            plz=product.get("plz") or "",
            radius=product.get("radius") or 0,
            year_from=product.get("year_from") or 0,
            year_to=product.get("year_to") or 0,
            km_max=product.get("km_max") or 0,
            price_min=product.get("price_min") or 0,
            price_max=product.get("price_max") or 0,
            ps_min=product.get("ps_min") or 0,
            ps_max=0,
            detail_scrape=False,
        ))

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, run_in_thread)


# ── Round ──────────────────────────────────────────────────────────────────────

async def run_watch_round(product_id: int, db: Database, event_cb: EventCb = None) -> dict:
    """Execute one full round for a product. Returns the finished run dict."""
    async def emit(evt: dict):
        if event_cb:
            try:
                await event_cb(evt)
            except Exception:
                pass

    product = await db.get_watch_product(product_id)
    if not product:
        raise ValueError(f"watch product {product_id} not found")

    api_key = await db.get_setting("openrouter_api_key")
    model = await db.get_setting("openrouter_model") or DEFAULT_MODEL

    base_query = (product.get("current_query") or "").strip() or product["query"]
    # Build the query set: base + agent-suggested synonyms (klimaanlage -> klimagerät,
    # mobile klima). Separate searches, results merged into one combined round.
    try:
        aliases = json.loads(product.get("query_aliases") or "[]")
        if not isinstance(aliases, list):
            aliases = []
    except Exception:
        aliases = []
    queries = [base_query]
    for a in aliases:
        a = str(a).strip()
        if a and a.lower() not in [q.lower() for q in queries]:
            queries.append(a)
    queries = queries[:MAX_QUERIES]
    query_label = " | ".join(queries)
    log_lines: list[str] = []

    def log(msg: str):
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        log_lines.append(line)
        logger.info("[watch %s] %s", product["name"], msg)

    search_id = str(uuid.uuid4())
    run_id = await db.create_watch_run(product_id, query_label, search_id)
    await emit({"type": "watch_round_start", "product_id": product_id, "run_id": run_id, "query": query_label})

    try:
        # 1) Scrape every query, merge + dedup by URL. User criteria always apply.
        merged: dict = {}
        for i, q in enumerate(queries):
            pages = (product.get("max_pages") or 3) if i == 0 else min(product.get("max_pages") or 3, ALIAS_MAX_PAGES)
            log(f"Scrape '{q}' ({pages} Seiten)")
            qls = await _scrape(product, q, max_pages=pages)
            new_here = 0
            for l in qls:
                u = l.get("url")
                if u and u not in merged:
                    merged[u] = l
                    new_here += 1
            log(f"  -> {len(qls)} Treffer ({new_here} neu im Merge)")
        listings = list(merged.values())
        log(f"Scrape fertig: {len(listings)} Inserate gesamt aus {len(queries)} Begriff(en)")

        # Drop listings older than the user's max age (default 60d). Unparseable
        # dates are kept (benefit of doubt). Stops year-old ads from showing up.
        max_age = int(product.get("max_age_days") or 0)
        if max_age > 0:
            cutoff = date.today() - timedelta(days=max_age)
            before = len(listings)
            listings = [l for l in listings
                        if (parse_listing_date(l.get("date_posted")) or cutoff) >= cutoff]
            if before - len(listings) > 0:
                log(f"Altersfilter: {before - len(listings)} Inserate aelter als {max_age} Tage entfernt")

        # Persist as a regular search so the Suche tab can open the raw round
        await db.save_search(search_id, f"[Agent] {product['name']}", product.get("category") or "all",
                             product.get("max_pages") or 3, user_id=product.get("user_id"))
        await db.save_listings(search_id, listings)
        listings = await db.get_listings(search_id)  # re-read for stable ids

        # 2) Metrics (same code path as the Suche tab)
        market = analyze_listings(listings, deal_threshold=0.80, exclude=product.get("exclude") or "")
        market_compact = {k: market.get(k) for k in (
            "count", "raw_count", "excluded_count", "with_price", "median_price", "avg_price",
            "min_price", "max_price", "deal_threshold_value", "price_distribution")}
        log(f"Analyse: Median {market.get('median_price')}€, {len(market.get('deals') or [])} Metrik-Deals")

        # 3) Dedup: only never-seen listings go to the LLM
        seen = await db.get_seen_urls(product_id)
        fresh = [l for l in market["listings"] if l.get("url") and l["url"] not in seen]
        # cheapest first — those are the deal candidates; cap for cost control
        fresh.sort(key=lambda l: (l.get("price_value") is None, l.get("price_value") or 0))
        candidates = fresh[:MAX_NEW_PER_ROUND]
        log(f"{len(fresh)} neue Inserate, {len(candidates)} gehen ins LLM-Review")

        deals_out: list[dict] = []
        reviewed_count = 0

        if candidates:
            criteria = _criteria_text(product)
            notes = (product.get("notes") or "").strip()

            # ── SCOUT pass
            scout_user = (
                f"USER CRITERIA:\n{criteria}\n\n"
                + (f"LEARNED CRITERIA NOTES (your own, from earlier rounds):\n{notes}\n\n" if notes else "")
                + f"{_market_text(market_compact)}\n\nLISTINGS:\n"
                + "\n".join(_listing_line(i, l) for i, l in enumerate(candidates))
            )
            await emit({"type": "watch_llm", "product_id": product_id, "pass": "scout",
                        "count": len(candidates)})
            scout_raw = await chat(api_key, model, [
                {"role": "system", "content": SCOUT_SYSTEM},
                {"role": "user", "content": scout_user},
            ], max_tokens=6000)
            scout = extract_json_array(scout_raw)
            reviewed_count = len(scout)
            log(f"Scout-Review: {reviewed_count} bewertet")
            if not scout:
                log("WARNUNG: Scout-Antwort nicht parsebar — Runde ohne LLM-Deals")

            by_idx = {}
            for s in scout:
                try:
                    by_idx[int(s.get("i"))] = s
                except (TypeError, ValueError):
                    continue

            shortlist = []
            for i, l in enumerate(candidates):
                s = by_idx.get(i)
                if not s:
                    continue
                if s.get("relevant") and int(s.get("score") or 0) >= SHORTLIST_MIN_SCORE \
                        and int(s.get("fake_risk") or 0) <= 70:
                    shortlist.append((i, l, s))
            log(f"Shortlist für Verifier: {len(shortlist)}")

            # ── VERIFY pass
            verified = {}
            if shortlist:
                # Fetch FULL detail descriptions — list snippets hide defect notes
                # ("Laufwerk liest keine Discs") that must veto the deal.
                full_descs = {}
                try:
                    fetch_urls = [l.get("url") for _i, l, _s in shortlist[:MAX_DETAIL_FETCH] if l.get("url")]
                    full_descs = await _fetch_full_descs(fetch_urls)
                    log(f"Volltext-Beschreibungen geladen: {len(full_descs)}/{len(fetch_urls)}")
                except Exception as e:
                    log(f"Volltext-Fetch fehlgeschlagen ({type(e).__name__}: {e}) — Verifier nutzt Snippets")

                verify_user = (
                    f"USER CRITERIA:\n{criteria}\n\n{_market_text(market_compact)}\n\n"
                    "SHORTLIST (scout score in brackets):\n"
                    + "\n".join(
                        f"{_listing_line(i, l, desc_override=full_descs.get(l.get('url')), desc_chars=DESC_CHARS_FULL)}"
                        f"\n   Scout: score {s.get('score')}, "
                        f"fake_risk {s.get('fake_risk')}, '{s.get('reason')}'"
                        for i, l, s in shortlist)
                )
                await emit({"type": "watch_llm", "product_id": product_id, "pass": "verify",
                            "count": len(shortlist)})
                verify_raw = await chat(api_key, model, [
                    {"role": "system", "content": VERIFY_SYSTEM},
                    {"role": "user", "content": verify_user},
                ], max_tokens=4000)
                for v in extract_json_array(verify_raw):
                    try:
                        verified[int(v.get("i"))] = v
                    except (TypeError, ValueError):
                        continue
                log(f"Verifier: {len(verified)} Final-Urteile")

            # ── Assemble results + seen entries
            seen_entries = []
            for i, l in enumerate(candidates):
                s = by_idx.get(i) or {}
                v = verified.get(i)
                if v:
                    verdict = v.get("verdict") or "reject"
                    reason = v.get("reason") or s.get("reason") or ""
                    fake_risk = v.get("fake_risk", s.get("fake_risk"))
                else:
                    verdict = "reject" if not s.get("relevant") else ("ok" if int(s.get("score") or 0) >= SHORTLIST_MIN_SCORE else "reject")
                    reason = s.get("reason") or ""
                    fake_risk = s.get("fake_risk")
                score = int(s.get("score") or 0)
                seen_entries.append({
                    "url": l.get("url"), "title": l.get("title"), "price": l.get("price_value"),
                    "verdict": verdict, "score": score, "reason": reason,
                })
                if verdict in ("top_deal", "ok"):
                    deals_out.append({
                        "title": l.get("title"), "price": l.get("price_value"),
                        "url": l.get("url"), "location": l.get("location"),
                        "date_posted": l.get("date_posted"),
                        "km": l.get("km"), "year": l.get("year"),
                        "verdict": verdict, "score": score,
                        "fake_risk": fake_risk, "reason": reason,
                    })
            await db.upsert_seen(product_id, seen_entries)
            deals_out.sort(key=lambda d: (d["verdict"] != "top_deal", -(d["score"] or 0)))
            log(f"Ergebnis: {len(deals_out)} gute Inserate ({sum(1 for d in deals_out if d['verdict']=='top_deal')} Top-Deals)")

            # ── LEARN pass (best effort — round still succeeds if this fails)
            try:
                verdict_summary = [
                    {"title": (e.get("title") or "")[:70], "price": e.get("price"),
                     "verdict": e.get("verdict"), "score": e.get("score"), "reason": e.get("reason")}
                    for e in seen_entries[:30]
                ]
                learn_user = (
                    f"PRODUCT: {product['name']} | base query: {product['query']} | "
                    f"queries used this round: {query_label}\n"
                    f"current synonyms (aliases): {json.dumps(aliases, ensure_ascii=False)}\n"
                    f"{_market_text(market_compact)}\n"
                    f"Round counts: raw {market_compact.get('raw_count')}, new {len(fresh)}, "
                    f"reviewed {reviewed_count}, good {len(deals_out)}\n\n"
                    f"CURRENT NOTES:\n{notes or '(noch keine)'}\n\n"
                    f"THIS ROUND'S VERDICTS:\n{json.dumps(verdict_summary, ensure_ascii=False)}"
                )
                learn_raw = await chat(api_key, model, [
                    {"role": "system", "content": LEARN_SYSTEM},
                    {"role": "user", "content": learn_user},
                ], max_tokens=2000)
                learned = extract_json_object(learn_raw)
                update = {}
                if learned.get("notes"):
                    update["notes"] = str(learned["notes"])[:6000]
                nq = learned.get("next_query")
                # Guard: a refined query may only BROADEN recall, never narrow it.
                # Reject anything with MORE tokens than the user's base query — that
                # means the agent added a restrictive token (e.g. "Disc"), which KA
                # AND-matches and which silently kills most good listings. Variant/
                # condition filtering is the LLM reviewer's job, not the query's.
                base_tokens = len(product["query"].split())
                if (nq and isinstance(nq, str) and nq.strip()
                        and 0 < len(nq.split()) <= max(3, base_tokens)
                        and len(nq.split()) <= base_tokens
                        and nq.strip().lower() != base_query.lower()):
                    update["current_query"] = nq.strip()
                    log(f"Query angepasst (breiter): '{base_query}' -> '{nq.strip()}' ({learned.get('query_reason', '')})")
                elif nq and len(str(nq).split()) > base_tokens:
                    log(f"Query-Vorschlag '{nq}' verworfen (verengt Treffer, mehr Tokens als Basis '{product['query']}')")

                # Synonym aliases: SEPARATE search terms that surface DIFFERENT good
                # listings (klimaanlage -> klimagerät, mobile klima). Each <=3 tokens,
                # distinct from base, max 2 kept. Merged into one combined round.
                new_aliases = learned.get("aliases")
                if isinstance(new_aliases, list):
                    clean = []
                    for a in new_aliases:
                        a = str(a).strip()
                        if (a and 0 < len(a.split()) <= 3
                                and a.lower() != product["query"].lower()
                                and a.lower() != base_query.lower()
                                and a.lower() not in [x.lower() for x in clean]):
                            clean.append(a)
                    clean = clean[:MAX_QUERIES - 1]
                    # store only if changed
                    if [c.lower() for c in clean] != [str(a).lower() for a in aliases]:
                        update["query_aliases"] = json.dumps(clean, ensure_ascii=False)
                        if clean:
                            log(f"Synonyme aktualisiert: {', '.join(clean)}")

                if update:
                    await db.update_watch_product(product_id, update)
                    log("Notizen aktualisiert")
            except (LLMError, LLMNotConfigured) as e:
                log(f"Learn-Pass übersprungen: {e}")

        now = datetime.now().isoformat()
        await db.update_watch_run(run_id, {
            "finished_at": now, "status": "done",
            "raw_count": market_compact.get("raw_count") or 0,
            "new_count": len(fresh),
            "reviewed_count": reviewed_count,
            "deal_count": len(deals_out),
            "market_json": json.dumps(market_compact, ensure_ascii=False),
            "deals_json": json.dumps(deals_out, ensure_ascii=False),
            "log": "\n".join(log_lines),
        })
        await db.update_watch_product(product_id, {"last_run_at": now})
        # Retention: cap stored rounds + dedup memory per product
        await db.prune_watch_runs(product_id)
        await db.prune_seen(product_id)
        await emit({"type": "watch_round_done", "product_id": product_id, "run_id": run_id,
                    "deal_count": len(deals_out)})
        return await db.get_watch_run(run_id)

    except Exception as e:
        logger.exception("watch round failed")
        msg = f"{type(e).__name__}: {e}"
        log(f"FEHLER: {msg}")
        await db.update_watch_run(run_id, {
            "finished_at": datetime.now().isoformat(), "status": "error",
            "error": msg, "log": "\n".join(log_lines),
        })
        await db.update_watch_product(product_id, {"last_run_at": datetime.now().isoformat()})
        await emit({"type": "watch_round_error", "product_id": product_id, "run_id": run_id,
                    "message": msg})
        return await db.get_watch_run(run_id)
