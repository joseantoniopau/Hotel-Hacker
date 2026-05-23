"""
fx.py — FX rates + currency conversion + cross-currency arbitrage detection.

Pure functions modulo the injectable `http_get` in `fetch_rates`. Rates are
cached on disk for 24h via common.cache_*; if the upstream API is unreachable,
we fall back to a tiny baked-in table so a search never crashes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

try:
    from .common import cache_get, cache_put, log_event
except ImportError:
    # Allow standalone import (e.g. `import fx` with `scripts/` on sys.path).
    from common import cache_get, cache_put, log_event  # type: ignore


# Last-resort offline table (approx mid-market, USD base). Used only when the
# live API is unreachable AND nothing is cached.
FALLBACK_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 156.0,
    "MXN": 17.0,
    "CHF": 0.90,
    "AED": 3.67,
    "CAD": 1.36,
    "AUD": 1.52,
}

_FX_CACHE_KEY = "fx_open_er_api_usd"
_FX_URL = "https://open.er-api.com/v6/latest/USD"
_FX_TTL_HOURS = 24


def fetch_rates(
    base_ccy: str = "USD",
    http_get: Optional[Callable[..., Any]] = None,
) -> Dict[str, float]:
    """Fetch a USD-base rate table from open.er-api.com (cached 24h on disk).

    `http_get` is injectable for tests; defaults to `requests.get`. Returns a
    dict like `{"USD": 1.0, "EUR": 0.92, ...}`. On any network or parse error
    we return FALLBACK_RATES so the caller can still produce a result.
    """
    # Honor disk cache first — avoids a network hop every search.
    cached = cache_get(_FX_CACHE_KEY)
    if cached and isinstance(cached.get("rates"), dict):
        rates = {k: float(v) for k, v in cached["rates"].items() if _is_number(v)}
        if rates:
            return rates

    if http_get is None:
        try:
            import requests  # type: ignore
            http_get = requests.get
        except Exception:
            log_event("fx_fallback", reason="requests_not_available")
            return dict(FALLBACK_RATES)

    try:
        resp = http_get(_FX_URL, timeout=10)
        # Duck-type both requests.Response and our test fakes.
        if hasattr(resp, "json"):
            payload = resp.json()
        else:
            payload = resp
    except Exception as e:
        log_event("fx_fallback", reason="http_error", error=str(e))
        return dict(FALLBACK_RATES)

    if not isinstance(payload, dict):
        log_event("fx_fallback", reason="bad_payload_type")
        return dict(FALLBACK_RATES)

    rates_raw = payload.get("rates")
    if not isinstance(rates_raw, dict) or not rates_raw:
        log_event("fx_fallback", reason="no_rates_field")
        return dict(FALLBACK_RATES)

    rates: Dict[str, float] = {}
    for k, v in rates_raw.items():
        if _is_number(v):
            rates[str(k).upper()] = float(v)
    if "USD" not in rates:
        rates["USD"] = 1.0

    cache_put(_FX_CACHE_KEY, {"rates": rates, "base": base_ccy.upper()}, ttl_hours=_FX_TTL_HOURS)
    return rates


def get_rate(
    from_ccy: str,
    to_ccy: str,
    rates: Optional[Dict[str, float]] = None,
) -> float:
    """Pure: return units of `to_ccy` per 1 unit of `from_ccy`, using USD as pivot.

    Returns 1.0 for an unknown pair or if rates is None — never raises.
    """
    if not isinstance(from_ccy, str) or not isinstance(to_ccy, str):
        return 1.0
    f = from_ccy.upper()
    t = to_ccy.upper()
    if f == t:
        return 1.0
    if rates is None:
        rates = dict(FALLBACK_RATES)
    f_rate = rates.get(f)
    t_rate = rates.get(t)
    if not _is_number(f_rate) or not _is_number(t_rate) or float(f_rate) == 0.0:
        return 1.0
    # Rates are units-of-X-per-USD. To go from F -> T, pivot through USD.
    return float(t_rate) / float(f_rate)


def convert(
    amount: float,
    from_ccy: str,
    to_ccy: str,
    rates: Optional[Dict[str, float]] = None,
) -> float:
    """Pure: convert `amount` from `from_ccy` to `to_ccy`. Never raises."""
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return 0.0
    return amt * get_rate(from_ccy, to_ccy, rates=rates)


def currency_arbitrage(
    amount_local: float,
    ccy_local: str,
    amount_query_usd: float,
    rates: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Detect a meaningful spread between paying-in-local vs paying-in-query-USD.

    Returns `{spread_pct, spread_usd, flag}`. `flag` is True iff
    `abs(spread_pct) >= 0.02` (2%). Both sign conventions are preserved:
    a POSITIVE spread means the local-currency conversion is MORE expensive
    in USD than the quoted USD price (home-ccy worse); negative means cheaper.
    """
    try:
        q_usd = float(amount_query_usd)
    except (TypeError, ValueError):
        q_usd = 0.0
    local_in_usd = convert(amount_local, ccy_local, "USD", rates=rates)
    if q_usd == 0.0:
        return {"spread_pct": 0.0, "spread_usd": 0.0, "flag": False}
    spread_usd = local_in_usd - q_usd
    spread_pct = spread_usd / q_usd
    return {
        "spread_pct": float(spread_pct),
        "spread_usd": float(spread_usd),
        "flag": bool(abs(spread_pct) >= 0.02),
    }


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float))


__all__ = [
    "FALLBACK_RATES",
    "fetch_rates",
    "get_rate",
    "convert",
    "currency_arbitrage",
]
