import asyncio
import json
import math
import os
import re
import sys
import logging
from typing import Callable, Optional
from datetime import date, datetime, timedelta
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# ── PLZ -> Koordinaten (offline Entfernungsberechnung) ──────────────────────────
def _data_path(name: str) -> str:
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(__file__)
    return os.path.join(base, name)

try:
    with open(_data_path("plz_coords.json"), encoding="utf-8") as _f:
        _PLZ_COORDS = json.load(_f)
except Exception as _e:  # noqa
    _PLZ_COORDS = {}
    logger.warning(f"plz_coords.json nicht geladen: {_e} — PLZ-Entfernungsfilter inaktiv")


def _haversine_km(a, b) -> float:
    R = 6371.0
    lat1, lon1 = a
    lat2, lon2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def plz_distance_km(from_plz: str, to_plz: str) -> Optional[float]:
    """Straight-line distance between two German PLZ via centroid lookup."""
    a = _PLZ_COORDS.get(str(from_plz).strip().zfill(5))
    b = _PLZ_COORDS.get(str(to_plz).strip().zfill(5))
    if not a or not b:
        return None
    return _haversine_km(a, b)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_price(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    s = price_str.strip().lower()
    if any(x in s for x in ["verschenken", "tausch", "auf anfrage", "n.a."]):
        return None
    m = re.search(r'([\d]{1,3}(?:\.[\d]{3})*(?:,[\d]{1,2})?)', s)
    if m:
        num_str = m.group(1).replace('.', '').replace(',', '.')
        try:
            val = float(num_str)
            return val if 0 < val < 10_000_000 else None
        except ValueError:
            pass
    return None


def parse_km(text: str) -> Optional[int]:
    m = re.search(r'([\d\.]+)\s*km', text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(".", ""))
        except ValueError:
            pass
    return None


def parse_listing_date(s: str) -> Optional[date]:
    """Parse Kleinanzeigen's listed posting date into a date.
    Handles 'Heute, 20:51', 'Gestern, ...', 'DD.MM.YYYY', 'vor X Tagen/Wochen/Monaten'.
    Returns None if unparseable (caller should keep such listings = benefit of doubt)."""
    if not s:
        return None
    t = s.strip().lower()
    today = date.today()
    if t.startswith("heute"):
        return today
    if t.startswith("gestern"):
        return today - timedelta(days=1)
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"vor\s+(\d+)\s+(tag|woche|monat)", t)
    if m:
        n = int(m.group(1))
        unit = {"tag": 1, "woche": 7, "monat": 30}[m.group(2)]
        return today - timedelta(days=n * unit)
    return None


def parse_distance_km(location: str) -> Optional[int]:
    """Kleinanzeigen prints distance from the searched PLZ as '(81 km)' in the
    location string. Returns the km value, or None if not present (= local)."""
    if not location:
        return None
    m = re.search(r"\((\d+)\s*km\)", location)
    return int(m.group(1)) if m else None


def parse_year(text: str) -> Optional[int]:
    current_year = datetime.now().year
    for m in re.finditer(r'\b(19\d{2}|20\d{2})\b', text):
        yr = int(m.group())
        if 1960 <= yr <= current_year:
            return yr
    return None


async def try_text(el, selector: str) -> str:
    node = await el.query_selector(selector)
    if node:
        return (await node.inner_text()).strip()
    return ""


# ── URL Builder ────────────────────────────────────────────────────────────────

def _slugify_query(query: str) -> str:
    """Kleinanzeigen URL slug: lowercase, umlauts expanded, non-word stripped, dashes."""
    s = query.strip().lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def build_search_url(
    query: str,
    page_num: int = 1,
    radius: int = 0,
    category: str = "all",
    price_min: int = 0,
    price_max: int = 0,
    year_from: int = 0,
    year_to: int = 0,
    km_max: int = 0,
    ps_min: int = 0,
    ps_max: int = 0,
    location_id: str = "",
) -> str:
    """
    Build a canonical kleinanzeigen.de search URL.

    Location filtering requires the internal numeric location_id resolved via
    resolve_location_id(). It is encoded as `l{id}r{radius}` in the k-segment.
    PLZ must NOT appear in the URL path — Kleinanzeigen treats it as a search
    keyword and ignores it as a location.
    """
    slug = _slugify_query(query)

    loc_token = ""
    if location_id and radius > 0:
        loc_token = f"l{location_id}r{radius}"
    elif location_id:
        loc_token = f"l{location_id}"

    if category == "cars":
        parts = ["s-autos"]
        if price_min > 0 or price_max > 0:
            lo = str(price_min) if price_min > 0 else ""
            hi = str(price_max) if price_max > 0 else ""
            parts.append(f"preis:{lo}:{hi}")
        if page_num > 1:
            parts.append(f"seite:{page_num}")
        if slug:
            parts.append(slug)

        k_segment = "k0c216" + loc_token
        attrs = []
        if year_from > 0 or year_to > 0:
            yf = str(year_from) if year_from > 0 else ""
            yt = str(year_to) if year_to > 0 else ""
            attrs.append(f"autos.ez_i:{yf}%2C{yt}")
        if km_max > 0:
            attrs.append(f"autos.km_i:%2C{km_max}")
        if ps_min > 0 or ps_max > 0:
            pf = str(ps_min) if ps_min > 0 else ""
            pt = str(ps_max) if ps_max > 0 else ""
            attrs.append(f"autos.power_i:{pf}%2C{pt}")
        if attrs:
            k_segment += "+" + "+".join(attrs)

        return "https://www.kleinanzeigen.de/" + "/".join(parts) + "/" + k_segment

    # General search (all categories)
    segments = []
    if price_min > 0 or price_max > 0:
        lo = str(price_min) if price_min > 0 else ""
        hi = str(price_max) if price_max > 0 else ""
        segments.append(f"preis:{lo}:{hi}")
    if page_num > 1:
        segments.append(f"seite:{page_num}")
    if slug:
        segments.append(slug)

    if not segments:
        return "https://www.kleinanzeigen.de/s/k0" + loc_token
    first = segments[0]
    rest = "/".join(segments[1:])
    url = f"https://www.kleinanzeigen.de/s-{first}"
    if rest:
        url += f"/{rest}"
    url += "/k0" + loc_token
    return url


# ── Location resolution ────────────────────────────────────────────────────────

async def resolve_location_id(page, plz: str, query_slug: str = "") -> Optional[str]:
    """
    Resolve PLZ to Kleinanzeigen's internal location ID via the search form autocomplete.

    Kleinanzeigen's JS populates the hidden input[name='locationId'] when the user
    selects a location suggestion. We simulate that interaction:
      1. Navigate to any search results page to get the form.
      2. Remove the GDPR banner from the DOM (it intercepts pointer events).
      3. Type PLZ into #site-search-area using press_sequentially (keeps focus).
      4. Wait for the .multiselectbox-option list, click the matching PLZ entry.
      5. Read the now-populated input[name='locationId'].
    """
    plz = (plz or "").strip()
    if not plz:
        return None

    slug = query_slug or "auto"
    try:
        await page.goto(
            f"https://www.kleinanzeigen.de/s-{slug}/k0",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
    except Exception as e:
        logger.warning(f"resolve_location_id: goto failed: {e}")
        return None

    # Accept cookies and remove the GDPR banner from DOM so it can't intercept clicks.
    await accept_cookies(page)

    loc_input = page.locator("#site-search-area")
    if await loc_input.count() == 0:
        logger.warning("resolve_location_id: #site-search-area not found")
        return None

    try:
        await loc_input.click()
        await asyncio.sleep(0.3)
        await loc_input.fill("")
        await loc_input.press_sequentially(plz, delay=120)
        await asyncio.sleep(1.8)

        # Find the autocomplete suggestion matching the PLZ.
        suggestion = None
        for sel in [".multiselectbox-option", "[class*='suggest'] li"]:
            els = await page.query_selector_all(sel)
            for el in els:
                if not await el.is_visible():
                    continue
                if plz in (await el.inner_text()):
                    suggestion = el
                    break
            if suggestion:
                break

        if suggestion:
            await suggestion.click(timeout=5_000)
            await asyncio.sleep(0.6)

        loc_id = await page.evaluate(
            "() => { const el = document.querySelector('input[name=\"locationId\"]'); "
            "return el ? el.value : null; }"
        )
        if loc_id:
            logger.info(f"Resolved PLZ {plz} -> location id {loc_id}")
            return str(loc_id)

    except Exception as e:
        logger.warning(f"resolve_location_id error for PLZ {plz}: {e}")
    return None


# ── Cookie banner ──────────────────────────────────────────────────────────────

async def accept_cookies(page):
    for sel in [
        "button#gdpr-banner-accept",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Akzeptieren')",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.5)
                break
        except Exception:
            pass
    # Remove GDPR container from DOM — even after clicking accept the overlay
    # div remains in the DOM and intercepts pointer events on elements below it.
    await page.evaluate(
        "() => { ['consentBanner','gdpr-banner'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); }); }"
    )


# ── Extract listing ────────────────────────────────────────────────────────────

async def extract_listing(item, category: str) -> Optional[dict]:
    try:
        listing: dict = {"scraped_at": datetime.now().isoformat()}

        # Full card text — used for price/location/date regex and fallbacks.
        try:
            card_text = await item.inner_text()
        except Exception:
            card_text = ""

        # Title + Description: prefer JSON-LD (clean, structured). KA switched to
        # Tailwind utility classes (mid-2026) so the old semantic selectors are gone;
        # each card now embeds a ld+json block with title + description.
        title, desc = "", ""
        ld = await item.query_selector('script[type="application/ld+json"]')
        if ld:
            try:
                data = json.loads((await ld.inner_text()).strip())
                if isinstance(data, dict):
                    title = (data.get("title") or "").strip()
                    desc = (data.get("description") or "").strip()
            except Exception:
                pass
        if not title:  # DOM fallback (old + new markup)
            for sel in ["h2 a", "h2.text-module-begin a", ".aditem-main--top--left a.ellipsis", "a[href^='/s-anzeige/']"]:
                el = await item.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    if title:
                        break

        # URL + id: new markup exposes them as attributes on the <article>.
        href = await item.get_attribute("data-href") or ""
        if not href:
            a = await item.query_selector("a[href^='/s-anzeige/']") or await item.query_selector("h2 a")
            if a:
                href = await a.get_attribute("href") or ""
        listing["url"] = f"https://www.kleinanzeigen.de{href}" if href.startswith("/") else href
        listing["title"] = title
        listing["description"] = desc

        # Price: rendered as a standalone "NNN €" / "NNN € VB" block. Match a line
        # that is only a price first, else the first € amount in the card.
        price_text = ""
        mp = re.search(r"(?m)^\s*(\d[\d.]*)\s*(?:€|EUR)(?:\s*VB)?\s*$", card_text)
        if not mp:
            mp = re.search(r"(\d[\d.]*)\s*(?:€|EUR)", card_text)
        if mp:
            price_text = mp.group(0).strip()
        if not price_text:  # DOM fallback
            for sel in ["[class*='price']", "p.aditem-main--top--right--price"]:
                price_text = await try_text(item, sel)
                if price_text:
                    break
        listing["price_text"] = price_text
        listing["price_value"] = parse_price(price_text)

        # Location & date — parse from full card text via regex; card-level
        # selectors are unreliable (shipping tags pollute .aditem-main--bottom--left
        # and the date moved out of .aditem-main--bottom--right in newer markup).
        try:
            card_text = await item.inner_text()
        except Exception:
            card_text = ""

        location = ""
        # First try: 5-digit PLZ on its own line, capture rest of line.
        m = re.search(r"(?m)^\s*(\d{5})\s+([^\n]{1,120}?)\s*$", card_text)
        if not m:
            # Inline fallback: PLZ followed by city until separator/date marker.
            m = re.search(
                r"\b(\d{5})\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9\.\-–/() ]{1,80}?)"
                r"(?=\s*(?:[·|\n]|Heute|Gestern|vor\s|\d{1,2}\.\d{1,2}\.|$))",
                card_text,
            )
        if m:
            tail = m.group(2).strip()
            # Strip trailing shipping/CTA tags that may leak into same line.
            tail = re.sub(
                r"\s*(Direkt kaufen|Versand möglich|Nur Abholung|Reserviert).*$",
                "", tail, flags=re.IGNORECASE,
            ).strip()
            location = f"{m.group(1)} {tail}".strip()

        date_posted = ""
        m = re.search(
            r"(Heute,?\s*\d{1,2}:\d{2}|Gestern,?\s*\d{1,2}:\d{2}|Heute|Gestern|vor\s+\d+\s+\w+|\d{1,2}\.\d{1,2}\.\d{4})",
            card_text,
        )
        if m:
            date_posted = m.group(1).strip()

        listing["location"] = location
        listing["date_posted"] = date_posted

        # Car-specific fields
        listing["km"] = None
        listing["year"] = None
        listing["fuel"] = None
        listing["gearbox"] = None
        listing["power_hp"] = None

        if category == "cars":
            combined = f"{title} {desc}"

            listing["km"] = parse_km(combined)
            listing["year"] = parse_year(combined)

            for fuel in ["Benzin", "Diesel", "Elektro", "Plug-in-Hybrid", "Hybrid", "Erdgas", "LPG"]:
                if fuel.lower() in combined.lower():
                    listing["fuel"] = fuel
                    break

            for gear in ["Automatik", "Schaltgetriebe", "Halbautomatik"]:
                if gear.lower() in combined.lower():
                    listing["gearbox"] = gear
                    break

            # Structured tag elements on the card
            tags = await item.query_selector_all(
                ".simpletag, [class*='simpletag'], [class*='tag'], .aditem-details span, "
                "[class*='attribute'], [data-testid*='tag']"
            )
            for tag in tags:
                tag_text = (await tag.inner_text()).strip()
                if not tag_text or len(tag_text) < 2:
                    continue

                if not listing["km"]:
                    km_val = parse_km(tag_text)
                    if km_val:
                        listing["km"] = km_val

                if not listing["year"]:
                    yr = parse_year(tag_text)
                    if yr:
                        listing["year"] = yr

                if not listing["power_hp"]:
                    hp = re.search(r'(\d{2,4})\s*PS', tag_text, re.IGNORECASE)
                    kw = re.search(r'(\d{2,4})\s*kW', tag_text, re.IGNORECASE)
                    if hp:
                        listing["power_hp"] = int(hp.group(1))
                    elif kw:
                        listing["power_hp"] = round(int(kw.group(1)) * 1.36)

                if not listing["fuel"]:
                    for fuel in ["Benzin", "Diesel", "Elektro", "Hybrid"]:
                        if fuel.lower() in tag_text.lower():
                            listing["fuel"] = fuel
                            break

                if not listing["gearbox"]:
                    for gear, label in [
                        ("Automatik", "Automatik"), ("DSG", "Automatik"), ("CVT", "Automatik"),
                        ("Schaltgetriebe", "Schaltgetriebe"), ("Halbautomatik", "Halbautomatik"),
                    ]:
                        if gear.lower() in tag_text.lower():
                            listing["gearbox"] = label
                            break

            # Also check EZ date in bottom for year if not found yet
            if not listing["year"]:
                bottom_el = await item.query_selector(".aditem-main--bottom")
                if bottom_el:
                    bottom_text = await bottom_el.inner_text()
                    ez_match = re.search(r'EZ\s+\d{1,2}/(\d{4})', bottom_text, re.IGNORECASE)
                    if ez_match:
                        listing["year"] = int(ez_match.group(1))

        return listing if listing.get("title") else None

    except Exception as exc:
        logger.warning(f"extract_listing error: {exc}")
        return None


# ── Detail page ────────────────────────────────────────────────────────────────

# Map (substring of) Kleinanzeigen attribute label → our field name.
# Order matters: more specific keys checked first.
_LABEL_MAP = [
    ("kilometerstand",          "km"),
    ("erstzulassung",           "year"),
    ("kraftstoffart",           "fuel"),
    ("kraftstoff",              "fuel"),
    ("leistung",                "power_hp"),
    ("getriebe",                "gearbox"),
    ("fahrzeugzustand",         "condition"),
    ("zustand",                 "condition"),
    ("farbe",                   "color"),
    ("türen",                   "doors"),
    ("anzahl sitzplätze",       "seats"),
    ("sitzplätze",              "seats"),
    ("anzahl der vorbesitzer",  "prev_owners"),
    ("vorbesitzer",             "prev_owners"),
    ("hu",                      "hu_until"),
    ("fahrzeugart",             "body_type"),
    ("art",                     "body_type"),
]


def _normalize_gearbox(v: str) -> str:
    lv = v.lower()
    if "auto" in lv or "dsg" in lv or "cvt" in lv:
        return "Automatik"
    if "halb" in lv:
        return "Halbautomatik"
    if "schalt" in lv or "manuell" in lv:
        return "Schaltgetriebe"
    return v.strip()


def _normalize_fuel(v: str) -> str:
    lv = v.lower()
    if "elektro" in lv and "hybrid" not in lv:
        return "Elektro"
    if "plug" in lv and "hybrid" in lv:
        return "Plug-in-Hybrid"
    if "hybrid" in lv:
        return "Hybrid"
    if "diesel" in lv:
        return "Diesel"
    if "benzin" in lv:
        return "Benzin"
    if "lpg" in lv or "autogas" in lv:
        return "LPG"
    if "erdgas" in lv or "cng" in lv:
        return "Erdgas"
    if "wasserstoff" in lv:
        return "Wasserstoff"
    return v.strip()


def _parse_attr_value(field: str, value: str):
    if not value:
        return None
    if field == "km":
        return parse_km(value)
    if field == "year":
        m = re.search(r"(\d{4})", value)
        return int(m.group(1)) if m else None
    if field == "power_hp":
        hp = re.search(r"(\d{2,4})\s*PS", value, re.IGNORECASE)
        if hp:
            return int(hp.group(1))
        kw = re.search(r"(\d{2,4})\s*kW", value, re.IGNORECASE)
        if kw:
            return round(int(kw.group(1)) * 1.36)
        return None
    if field in ("doors", "seats", "prev_owners"):
        m = re.search(r"(\d+)", value)
        return int(m.group(1)) if m else None
    if field == "gearbox":
        return _normalize_gearbox(value)
    if field == "fuel":
        return _normalize_fuel(value)
    return value.strip()


def _map_label(label: str) -> Optional[str]:
    for key, field in _LABEL_MAP:
        if key in label:
            return field
    return None


async def fetch_detail_page(page, url: str) -> dict:
    """
    Parse Kleinanzeigen detail page.
    Uses structured key/value rows (li.addetailslist--detail) — robust against
    text-position changes. Returns dict with only non-empty fields.
    """
    extra: dict = {}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        try:
            await page.wait_for_selector(
                "li.addetailslist--detail, #viewad-details, .checktag, #viewad-description-text",
                timeout=6_000,
            )
        except Exception:
            pass

        # Structured key/value rows
        items = await page.query_selector_all("li.addetailslist--detail")
        for li in items:
            value_el = await li.query_selector(".addetailslist--detail--value")
            if not value_el:
                value_el = await li.query_selector("span")
            if not value_el:
                continue
            value = (await value_el.inner_text()).strip()
            if not value:
                continue
            full = (await li.inner_text()).strip()
            label = full.replace(value, "", 1).strip().rstrip(":").lower()
            label = re.sub(r"\s+", " ", label)
            field = _map_label(label)
            if not field:
                continue
            parsed = _parse_attr_value(field, value)
            if parsed not in (None, ""):
                extra[field] = parsed

        # Equipment tags ("Ausstattung")
        feature_els = await page.query_selector_all(".checktag")
        features = []
        for fe in feature_els:
            t = (await fe.inner_text()).strip()
            if t:
                features.append(t)
        if features:
            extra["features"] = ", ".join(features[:40])

        # Full description (richer than card snippet)
        desc_el = await page.query_selector("#viewad-description-text")
        if desc_el:
            full_desc = (await desc_el.inner_text()).strip()
            if full_desc:
                extra["description"] = full_desc

        # Regex fallback for year/km/PS if attrs missed something
        if "year" not in extra or "km" not in extra or "power_hp" not in extra:
            try:
                body_text = await page.inner_text("body")
            except Exception:
                body_text = ""
            if body_text:
                if "year" not in extra:
                    for pat in (
                        r"Erstzulassung[:\s]*\d{1,2}[./](\d{4})",
                        r"EZ[:\s]*\d{1,2}[./](\d{4})",
                        r"Baujahr[:\s]*(\d{4})",
                    ):
                        m = re.search(pat, body_text, re.IGNORECASE)
                        if m:
                            extra["year"] = int(m.group(1))
                            break
                if "km" not in extra:
                    km = parse_km(body_text)
                    if km:
                        extra["km"] = km
                if "power_hp" not in extra:
                    hp = re.search(r"(\d{2,4})\s*PS", body_text, re.IGNORECASE)
                    if hp:
                        extra["power_hp"] = int(hp.group(1))

    except Exception as e:
        logger.warning(f"Detail page error for {url}: {e}")
    return extra


async def fetch_full_descriptions(urls: list[str]) -> dict:
    """Fetch the full description text for a small set of listing URLs.

    Used by the watch agent before the verify pass: list-page snippets hide
    defect disclaimers ("Laufwerk liest nicht", "ohne Controller") that often
    only appear deep in the detail description. Sequential on one page —
    intended for shortlists (<~15 URLs), not bulk scraping.
    Returns {url: description}; URLs that fail are simply missing.
    """
    out: dict = {}
    if not urls:
        return out
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )
        await context.route(
            "**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf,mp4,mp3,svg}",
            lambda r: r.abort(),
        )
        page = await context.new_page()
        cookies_accepted = False
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                if not cookies_accepted:
                    await accept_cookies(page)
                    cookies_accepted = True
                desc_el = await page.query_selector("#viewad-description-text")
                if desc_el:
                    desc = (await desc_el.inner_text()).strip()
                    if desc:
                        out[url] = desc
            except Exception as e:
                logger.warning(f"fetch_full_descriptions failed for {url}: {e}")
        await browser.close()
    return out


# ── Detail worker pool ─────────────────────────────────────────────────────────

async def _detail_worker(page, queue: asyncio.Queue):
    while True:
        listing = await queue.get()
        try:
            if listing is None:
                return
            try:
                extra = await asyncio.wait_for(
                    fetch_detail_page(page, listing["url"]), timeout=20.0
                )
                for k, v in extra.items():
                    if v not in (None, "", []):
                        listing[k] = v
            except Exception as e:
                logger.warning(f"Detail fetch failed for {listing.get('url')}: {e}")
        finally:
            queue.task_done()


# ── Main scraper ───────────────────────────────────────────────────────────────

async def scrape_kleinanzeigen(
    query: str,
    max_pages: int = 3,
    category: str = "all",
    plz: str = "",
    radius: int = 0,
    year_from: int = 0,
    year_to: int = 0,
    km_max: int = 0,
    price_min: int = 0,
    price_max: int = 0,
    ps_min: int = 0,
    ps_max: int = 0,
    detail_scrape: bool = False,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> list[dict]:

    results: list[dict] = []
    cookies_accepted = False
    do_detail = bool(detail_scrape and category == "cars")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )
        await context.route(
            "**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf,mp4,mp3,svg}",
            lambda r: r.abort(),
        )
        page = await context.new_page()

        # Resolve PLZ → internal location ID needed for l{id}r{radius} in k-segment.
        # PLZ must NOT appear in the URL path — Kleinanzeigen treats it as a search keyword.
        location_id = ""
        if plz:
            loc = await resolve_location_id(page, plz, _slugify_query(query))
            if loc:
                location_id = loc
                if not cookies_accepted:
                    await accept_cookies(page)
                    cookies_accepted = True
            else:
                logger.warning(f"Could not resolve PLZ {plz} — searches will be nationwide")

        # Detail-fetch worker pool (reused across all listings — much faster
        # than spinning up a new page per listing).
        detail_queue: Optional[asyncio.Queue] = None
        detail_pages: list = []
        detail_workers: list = []
        if do_detail:
            detail_queue = asyncio.Queue()
            pool_size = 5
            for _ in range(pool_size):
                dp = await context.new_page()
                detail_pages.append(dp)
                detail_workers.append(
                    asyncio.create_task(_detail_worker(dp, detail_queue))
                )

        try:
            for page_num in range(1, max_pages + 1):
                if progress_callback:
                    progress_callback(int((page_num - 1) / max_pages * 80))

                url = build_search_url(
                    query=query,
                    page_num=page_num,
                    radius=radius,
                    category=category,
                    price_min=price_min,
                    price_max=price_max,
                    year_from=year_from,
                    year_to=year_to,
                    km_max=km_max,
                    ps_min=ps_min,
                    ps_max=ps_max,
                    location_id=location_id,
                )
                logger.info(f"Page {page_num}: {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=40_000)
                    # KA markup (mid-2026): listings are <article data-adid>. Keep the
                    # old article.aditem as fallback in case of A/B markup.
                    ITEM_SEL = "article[data-adid], article.aditem"
                    try:
                        await page.wait_for_selector(ITEM_SEL, timeout=8_000)
                    except Exception:
                        logger.warning(f"wait_for listings timed out on page {page_num} (final URL: {page.url})")

                    if not cookies_accepted:
                        await accept_cookies(page)
                        cookies_accepted = True

                    items = await page.query_selector_all(ITEM_SEL)
                    logger.info(f"Page {page_num}: {len(items)} listing nodes on {page.url}")
                    if not items:
                        # Dump short HTML diagnostic so we know what kleinanzeigen returned.
                        try:
                            head = (await page.content())[:800]
                        except Exception:
                            head = "<failed>"
                        logger.warning(f"No items on page {page_num} — HTML head: {head!r}")
                        break

                    page_results = []
                    for item in items:
                        listing = await extract_listing(item, category)
                        if listing:
                            page_results.append(listing)

                    results.extend(page_results)
                    logger.info(f"Page {page_num}: {len(page_results)} listings scraped")

                    # Next page?
                    next_btn = page.locator(
                        "a.pagination-next, [data-testid='pagination-next'], a[aria-label='Nächste Seite']"
                    )
                    if await next_btn.count() == 0:
                        logger.info("No next page — done")
                        break

                except Exception as exc:
                    logger.error(f"Page {page_num} error: {exc}")
                    import traceback
                    traceback.print_exc()
                    break

            # Detail fetch runs AFTER all search pagination completes — running
            # detail workers in parallel with search-page navigation triggers
            # Kleinanzeigen anti-bot, causing later search pages to come back empty.
            if do_detail and detail_queue is not None and results:
                total = sum(1 for l in results if l.get("url"))
                logger.info(f"Detail fetch: {total} listings queued")
                for l in results:
                    if l.get("url"):
                        await detail_queue.put(l)

                # Poll progress; asyncio.Queue.unfinished_tasks is private in
                # Python <3.13, but the attribute is stable across versions.
                while detail_queue._unfinished_tasks > 0:
                    done = total - detail_queue._unfinished_tasks
                    if progress_callback:
                        progress_callback(min(99, int(80 + (done / max(total, 1)) * 20)))
                    logger.info(f"Detail progress: {done}/{total}")
                    await asyncio.sleep(2.0)

        finally:
            # Shut down detail-worker pool
            if detail_queue is not None:
                for _ in detail_workers:
                    await detail_queue.put(None)
                await asyncio.gather(*detail_workers, return_exceptions=True)
                for dp in detail_pages:
                    try:
                        await dp.close()
                    except Exception:
                        pass
            await browser.close()

    if progress_callback:
        progress_callback(100)

    # Hard-enforce the radius. Kleinanzeigen silently EXPANDS the radius when a
    # tight search has few local hits, returning nationwide results sorted by
    # distance. The distance is printed in each location string ("(81 km)").
    # Drop anything beyond the requested radius so the user's PLZ+radius filter
    # actually holds. Listings without a distance (same city / no "(NN km)") are
    # local and kept.
    if radius and plz:
        kept = []
        dropped = 0
        # 15% buffer: KA's radius is straight-line too, but PLZ centroids vs. the
        # exact address introduce a few km of slack — don't drop borderline-local.
        limit = radius * 1.15
        for l in results:
            loc = l.get("location", "")
            dist = parse_distance_km(loc)              # fast path: KA's "(NN km)"
            if dist is None:                            # fallback: compute from PLZ
                m = re.search(r"\b(\d{5})\b", loc)
                if m:
                    dist = plz_distance_km(plz, m.group(1))
            if dist is not None and dist > limit:
                dropped += 1
                continue
            kept.append(l)
        if dropped:
            logger.info(f"Radius filter: dropped {dropped} listings beyond {radius}km "
                        f"(KA auto-expanded), {len(kept)} remain")
        results = kept

    logger.info(f"Total: {len(results)} listings for '{query}'")
    return results
