"""
Shared listing analysis: exclude filtering, IQR outlier removal, deal detection,
price distribution. Used by the /api/analyze endpoint AND the watch agents so
both always compute identical metrics.
"""
import re
from typing import Optional

import numpy as np
import pandas as pd

_NEGATION = re.compile(r"\b(kein|keine|keinen|ohne|nicht|no)\s+$", re.IGNORECASE)


def build_exclude_matchers(terms: list[str]):
    """Compile each exclude term into a word-boundary regex. Suppresses obvious
    negations like "kein Defekt", "ohne Reparatur", "no damage" right before
    the term — these are legit listings the substring filter wrongly killed."""
    matchers = []
    for t in terms:
        t = t.strip().lower()
        if not t:
            continue
        # Word boundary on both sides so "defekt" doesn't match "defektfrei".
        matchers.append((t, re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)))
    return matchers


def is_excluded(listing: dict, matchers) -> bool:
    text = f"{listing.get('title') or ''} {listing.get('description') or ''}".lower()
    for _term, rx in matchers:
        for m in rx.finditer(text):
            # Check 12-char window before the match for a negation; skip if found.
            lo = max(0, m.start() - 12)
            if _NEGATION.search(text[lo:m.start()]):
                continue
            return True
    return False


# Auto-exclude only the unambiguous "buy ad" markers — sellers never use these.
AUTO_EXCLUDE = ["suche", "gesuch", "looking for", "ankauf"]


def analyze_listings(listings: list, deal_threshold: float = 0.80, exclude: str = "") -> dict:
    raw_count = len(listings)

    exclude_terms = [t.strip().lower() for t in exclude.split(",") if t.strip()]
    all_terms = list(dict.fromkeys(exclude_terms + AUTO_EXCLUDE))  # dedupe, preserve order
    matchers = build_exclude_matchers(all_terms)

    filtered = [l for l in listings if not is_excluded(l, matchers)]
    excluded_count = raw_count - len(filtered)

    prices = [
        l["price_value"] for l in filtered
        if l.get("price_value") and l["price_value"] > 0
    ]

    if not prices:
        return {
            "count": len(filtered), "raw_count": raw_count, "excluded_count": excluded_count,
            "with_price": 0, "avg_price": None, "median_price": None,
            "min_price": None, "max_price": None, "std_dev": None,
            "deals": [], "deal_threshold_value": None,
            "deal_threshold_pct": deal_threshold,
            "price_distribution": [], "listings": filtered, "mlr": None,
        }

    # Remove outliers with IQR
    s = pd.Series(prices)
    q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
    iqr = q3 - q1
    if iqr > 0:
        clean_prices = [p for p in prices if (q1 - 1.5 * iqr) <= p <= (q3 + 1.5 * iqr)]
    else:
        clean_prices = prices
    if not clean_prices:
        clean_prices = prices

    cs = pd.Series(clean_prices)
    avg    = float(cs.mean())
    median = float(cs.median())
    std    = float(cs.std()) if len(clean_prices) > 1 else 0.0

    # Adaptive threshold: small samples have noisy medians, so loosen the cut
    # to surface anything meaningfully below market instead of returning empty.
    effective_threshold = deal_threshold
    sample_size = len(clean_prices)
    if sample_size < 10:
        effective_threshold = min(0.95, deal_threshold + 0.15)
    elif sample_size < 20:
        effective_threshold = min(0.90, deal_threshold + 0.10)
    threshold_value = median * effective_threshold

    deals = sorted(
        [l for l in filtered if l.get("price_value") and 0 < l["price_value"] < threshold_value],
        key=lambda x: x["price_value"]
    )

    return {
        "count": len(filtered),
        "raw_count": raw_count,
        "excluded_count": excluded_count,
        "with_price": len(prices),
        "clean_prices_count": len(clean_prices),
        "avg_price": round(avg, 2),
        "median_price": round(median, 2),
        "min_price": round(min(clean_prices), 2),
        "max_price": round(max(clean_prices), 2),
        "std_dev": round(std, 2),
        "deals": deals,
        "deal_threshold_value": round(threshold_value, 2),
        "deal_threshold_pct": deal_threshold,
        "deal_threshold_effective": round(effective_threshold, 3),
        "price_distribution": price_distribution(clean_prices),
        "listings": filtered,
        "mlr": None,  # caller may fill via run_mlr
    }


def price_distribution(prices: list, bins: int = 12) -> list:
    if len(prices) < 2:
        return []
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return [{"range": f"{int(lo)}€", "count": len(prices)}]
    step = (hi - lo) / bins
    result = []
    for i in range(bins):
        low  = lo + i * step
        high = lo + (i + 1) * step
        count = sum(1 for p in prices if low <= p < high)
        if i == bins - 1:
            count += sum(1 for p in prices if p == high)
        result.append({"range": f"{int(low)}–{int(high)}", "count": count})
    return result
