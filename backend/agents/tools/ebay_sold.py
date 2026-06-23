"""
eBay.de Sold-Listings Lookup.

Scrapes the "sold + completed" search page on eBay.de and returns aggregated
price stats. Used by Stage 1 Trend-Hunter to validate resell-price estimates
with real market data instead of LLM guesses.

Anti-bot hardening:
- Browser-realistic headers (sec-ch-ua, sec-fetch-*, full Accept, Referer)
- Cookie-seeding GET to ebay.de homepage before the actual search
- One retry on empty result with a brief delay
- Fallback: try ebay.com (USD prices converted to EUR at fixed 0.92 rate)
  so trend-hunter still gets *some* anchor when ebay.de is blocked.

No API key required. If eBay continues to block, swap to the Browse API
(OAuth client credentials).
"""
import asyncio
import json
import re
from urllib.parse import quote_plus

import httpx
from claude_agent_sdk import tool

# Realistic Chrome 124 on Win10 fingerprint
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="124", "Not-A.Brand";v="99", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

USD_TO_EUR = 0.92


def _parse_money(s: str, currency: str = "EUR") -> float | None:
    if not s:
        return None
    s = s.replace("EUR", "").replace("€", "").replace("US", "").replace("$", "").strip()
    s = s.split("bis")[0].split("to")[0].strip()
    if currency == "EUR":
        # DE: "12.345,67"
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
    else:
        # US: "12,345.67"
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s and len(s.split(",")[-1]) == 3:
            s = s.replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        v = float(m.group(0))
        return v if 0 < v < 1_000_000 else None
    except ValueError:
        return None


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


PRICE_PATTERN = re.compile(r'class="[^"]*s-card__price[^"]*"[^>]*>([^<]+)<')
# Legacy fallback for older s-item__price layout (kept in case eBay flips back).
LEGACY_PRICE_PATTERN = re.compile(r'class="s-item__price"[^>]*>([^<]+)</span>')


def _extract_prices(html: str) -> list[float]:
    """Extract prices from eBay.de HTML. Handles mixed EUR + USD listings on
    the same page (cross-border sellers) by detecting the currency per match
    and converting USD to EUR."""
    raw = PRICE_PATTERN.findall(html) or LEGACY_PRICE_PATTERN.findall(html)
    if raw and "shop on ebay" in html[:5000].lower():
        raw = raw[1:]
    out: list[float] = []
    for s in raw:
        if "$" in s or s.strip().startswith("US "):
            v = _parse_money(s, "USD")
            if v is not None:
                out.append(v * USD_TO_EUR)
        else:
            v = _parse_money(s, "EUR")
            if v is not None:
                out.append(v)
    return out


def _extract_prices_usd(html: str) -> list[float]:
    raw = PRICE_PATTERN.findall(html) or LEGACY_PRICE_PATTERN.findall(html)
    if raw and "shop on ebay" in html[:5000].lower():
        raw = raw[1:]
    return [p * USD_TO_EUR for p in (_parse_money(s, "USD") for s in raw) if p is not None]


async def _fetch_with_session(client: httpx.AsyncClient, search_url: str, home_url: str) -> str:
    # Seed cookies: GET homepage first, then the search URL with Referer set.
    try:
        await client.get(home_url, headers=BROWSER_HEADERS)
        await asyncio.sleep(0.4)
    except Exception:
        pass
    headers = {**BROWSER_HEADERS, "Referer": home_url, "Sec-Fetch-Site": "same-origin"}
    r = await client.get(search_url, headers=headers)
    return r.text


@tool(
    "ebay_sold",
    "Fetch recently SOLD eBay.de listings for a search query. Returns price stats (median, avg, min, max) and parsed sample count. Use this BEFORE finalizing a product in the trend list to verify the resell price is real, not guessed.",
    {"query": str},
)
async def ebay_sold(args: dict) -> dict:
    query = args["query"]
    de_url = (
        f"https://www.ebay.de/sch/i.html"
        f"?_nkw={quote_plus(query)}"
        f"&LH_Sold=1&LH_Complete=1&_sop=13"
    )

    prices: list[float] = []
    source_used = "ebay.de"
    html_len = 0
    last_error = ""

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
        # Try 1: ebay.de with cookie-seeding
        try:
            html = await _fetch_with_session(c, de_url, "https://www.ebay.de/")
            html_len = len(html)
            prices = _extract_prices(html)
        except Exception as e:
            last_error = f"de_fetch_failed: {e}"

        # Try 2: retry ebay.de once after delay
        if not prices:
            await asyncio.sleep(1.2)
            try:
                html = await _fetch_with_session(c, de_url, "https://www.ebay.de/")
                html_len = len(html)
                prices = _extract_prices(html)
            except Exception as e:
                last_error = f"de_retry_failed: {e}"

        # Try 3: ebay.com fallback (USD -> EUR conversion)
        if not prices:
            com_url = (
                f"https://www.ebay.com/sch/i.html"
                f"?_nkw={quote_plus(query)}"
                f"&LH_Sold=1&LH_Complete=1&_sop=13"
            )
            try:
                html = await _fetch_with_session(c, com_url, "https://www.ebay.com/")
                html_len = len(html)
                prices = _extract_prices_usd(html)
                if prices:
                    source_used = "ebay.com (USD→EUR)"
            except Exception as e:
                last_error = f"com_fetch_failed: {e}"

    if not prices:
        return {"content": [{"type": "text", "text": json.dumps({
            "query": query,
            "error": "no_prices_parsed (anti-bot block on ebay.de + ebay.com)",
            "last_error": last_error,
            "html_len": html_len,
            "source_url": de_url,
        })}]}

    result = {
        "query": query,
        "sold_sample": len(prices),
        "median_price_eur": round(_median(prices), 2),
        "avg_price_eur": round(sum(prices) / len(prices), 2),
        "min_price_eur": round(min(prices), 2),
        "max_price_eur": round(max(prices), 2),
        "source": source_used,
        "note": "Active+sold mix possible if page layout differs. Verify large outliers manually.",
    }
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
