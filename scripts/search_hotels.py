#!/usr/bin/env python3
"""
search_hotels.py - Hotel search via SerpApi Google Hotels engine.

Outputs a JSON (or JSONL) list of NormalizedHotel records to stdout.
Source-adapter pattern so we can later swap in Amadeus / RapidAPI.

Contract: see /tmp/hh-build-spec.md (SERPAPI CONTRACT + Normalized record).
Owned by Agent D. Never log or print SERPAPI_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any

import requests

# Make sibling scripts importable when invoked directly.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Agent C's common module. We import lazily inside main() so this file can be
# imported (and unit-tested) even before common.py exists. The spec guarantees
# the names below will be available on common.py.
#   load_env, cache_get, cache_put, account_decrement, account_remaining,
#   log_event, FriendlyError, NormalizedHotel
# Agent C's fx module:
#   fx.convert(amount, from_ccy, to_ccy) -> float

# ---------------------------------------------------------------------------
# Source-adapter interface
# ---------------------------------------------------------------------------


class HotelSource(ABC):
    """Pluggable hotel-search backend."""

    @abstractmethod
    def search(
        self,
        q: str,
        check_in: str,
        check_out: str,
        adults: int,
        currency: str,
        **kwargs: Any,
    ) -> list[dict]:
        """Return raw provider 'properties' list (un-normalized)."""

    @abstractmethod
    def detail(
        self,
        property_token: str,
        check_in: str,
        check_out: str,
        adults: int,
        currency: str,
        **kwargs: Any,
    ) -> dict:
        """Return raw provider detail dict for a single property."""


class SerpApiSource(HotelSource):
    BASE = "https://serpapi.com/search.json"
    TIMEOUT_S = 30

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("SERPAPI_KEY is required for SerpApiSource")
        self._api_key = api_key

    def _params(
        self,
        q: str,
        check_in: str,
        check_out: str,
        adults: int,
        currency: str,
        gl: str = "us",
        hl: str = "en",
    ) -> dict[str, Any]:
        return {
            "engine": "google_hotels",
            "q": q,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "adults": adults,
            "currency": currency,
            "gl": gl,
            "hl": hl,
            "api_key": self._api_key,
        }

    def search(
        self,
        q: str,
        check_in: str,
        check_out: str,
        adults: int,
        currency: str,
        **kwargs: Any,
    ) -> list[dict]:
        params = self._params(
            q=q,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            currency=currency,
            gl=kwargs.get("gl", "us"),
            hl=kwargs.get("hl", "en"),
        )
        resp = requests.get(self.BASE, params=params, timeout=self.TIMEOUT_S)
        if resp.status_code != 200:
            # Surface body without leaking api_key (requests never echoes it
            # back, but be defensive on the message).
            raise _http_error(resp.status_code, _redact(resp.text))
        body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            raise _provider_error(str(body.get("error")))
        props = body.get("properties") or []
        if not isinstance(props, list):
            return []
        return props

    def detail(
        self,
        property_token: str,
        check_in: str,
        check_out: str,
        adults: int,
        currency: str,
        **kwargs: Any,
    ) -> dict:
        params = self._params(
            q=kwargs.get("q", ""),
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            currency=currency,
            gl=kwargs.get("gl", "us"),
            hl=kwargs.get("hl", "en"),
        )
        params["property_token"] = property_token
        # `q` is optional when property_token is provided; drop empty.
        if not params.get("q"):
            params.pop("q", None)
        resp = requests.get(self.BASE, params=params, timeout=self.TIMEOUT_S)
        if resp.status_code != 200:
            raise _http_error(resp.status_code, _redact(resp.text))
        body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            raise _provider_error(str(body.get("error")))
        return body if isinstance(body, dict) else {}


class AmadeusSource(HotelSource):
    """Placeholder — wired up later for cross-checking."""

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def search(self, *_: Any, **__: Any) -> list[dict]:
        raise NotImplementedError("AmadeusSource not implemented yet")

    def detail(self, *_: Any, **__: Any) -> dict:
        raise NotImplementedError("AmadeusSource not implemented yet")


class RapidApiSource(HotelSource):
    """Placeholder — alternate Booking.com/Hotels.com adapter."""

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def search(self, *_: Any, **__: Any) -> list[dict]:
        raise NotImplementedError("RapidApiSource not implemented yet")

    def detail(self, *_: Any, **__: Any) -> dict:
        raise NotImplementedError("RapidApiSource not implemented yet")


# ---------------------------------------------------------------------------
# Helpers (kept local so module imports without common.py)
# ---------------------------------------------------------------------------


class _LocalFriendly(Exception):
    """Fallback if common.FriendlyError isn't importable yet."""

    def __init__(self, message: str, *, code: str = "error", hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint

    def to_dict(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "hint": self.hint}}


def _get_friendly_error_class():
    try:
        from common import FriendlyError  # type: ignore
        return FriendlyError
    except Exception:
        return _LocalFriendly


def _http_error(status: int, body_snippet: str) -> Exception:
    FE = _get_friendly_error_class()
    msg = f"Hotel search service returned HTTP {status}."
    hint = "We'll try cached results if available. Try again in a minute."
    snippet = (body_snippet or "")[:240]
    try:
        return FE(msg, code=f"http_{status}", hint=hint + (f" Details: {snippet}" if snippet else ""))
    except TypeError:
        return FE(msg)


def _provider_error(detail: str) -> Exception:
    FE = _get_friendly_error_class()
    msg = "Hotel search service reported an error."
    try:
        return FE(msg, code="provider_error", hint=_redact(detail)[:240])
    except TypeError:
        return FE(msg)


_SECRET_HINT_KEYS = ("api_key", "apikey", "serpapi_key")


def _redact(s: str | None) -> str:
    if not s:
        return ""
    out = s
    for k in _SECRET_HINT_KEYS:
        # crude but safe: replace any ?api_key=... or &api_key=... up to next & or whitespace
        for sep in ("?", "&"):
            needle = f"{sep}{k}="
            idx = out.lower().find(needle)
            while idx != -1:
                end = len(out)
                for stop in ("&", " ", "\n", "\t", "\"", "'"):
                    j = out.find(stop, idx + len(needle))
                    if j != -1 and j < end:
                        end = j
                out = out[: idx + len(needle)] + "REDACTED" + out[end:]
                idx = out.lower().find(needle, idx + len(needle) + len("REDACTED"))
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nights(check_in: str, check_out: str) -> int:
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    n = (co - ci).days
    return max(n, 1)


def _cache_key(*, q: str, check_in: str, check_out: str, adults: int, currency: str, extra: str = "") -> str:
    blob = f"{q.strip().lower()}|{check_in}|{check_out}|{adults}|{currency.upper()}|{extra}"
    return sha256(blob.encode("utf-8")).hexdigest()


def _safe(d: dict | None, *keys, default=None):
    """Walk nested keys defensively."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _num(v: Any) -> float | None:
    """Best-effort numeric coercion. SerpApi often gives '$1,234' or {'lowest': '$1,234'}."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        # common SerpApi shape: {"lowest": "$1,234", "extracted_lowest": 1234}
        for k in ("extracted_lowest", "extracted", "value", "lowest"):
            if k in v:
                got = _num(v[k])
                if got is not None:
                    return got
        return None
    if isinstance(v, str):
        cleaned = v.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
        # strip any letters
        cleaned = "".join(c for c in cleaned if (c.isdigit() or c == "."))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


_FREE_NIGHT_HINTS = (
    "5th night free",
    "fifth night free",
    "4th night free",
    "fourth night free",
    "free night",
    "stay 5",
    "stay 4",
)


def _has_free_night_hint(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(h in t for h in _FREE_NIGHT_HINTS)


_BRAND_TOKENS = {
    "marriott": "Marriott",
    "ritz-carlton": "Marriott",
    "ritz carlton": "Marriott",
    "st. regis": "Marriott",
    "st regis": "Marriott",
    "w hotel": "Marriott",
    "westin": "Marriott",
    "sheraton": "Marriott",
    "le meridien": "Marriott",
    "courtyard": "Marriott",
    "renaissance": "Marriott",
    "hilton": "Hilton",
    "conrad": "Hilton",
    "waldorf": "Hilton",
    "doubletree": "Hilton",
    "embassy suites": "Hilton",
    "hampton": "Hilton",
    "hyatt": "Hyatt",
    "park hyatt": "Hyatt",
    "andaz": "Hyatt",
    "grand hyatt": "Hyatt",
    "ihg": "IHG",
    "intercontinental": "IHG",
    "kimpton": "IHG",
    "holiday inn": "IHG",
    "crowne plaza": "IHG",
    "accor": "Accor",
    "sofitel": "Accor",
    "fairmont": "Accor",
    "raffles": "Accor",
    "wyndham": "Wyndham",
    "ramada": "Wyndham",
    "days inn": "Wyndham",
    "choice": "Choice",
    "comfort inn": "Choice",
    "quality inn": "Choice",
    "best western": "Best Western",
    "four seasons": "Four Seasons",
    "aman": "Aman",
    "rosewood": "Rosewood",
    "mandarin oriental": "Mandarin Oriental",
    "belmond": "Belmond",
    "auberge": "Auberge",
}


def _guess_brand(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower()
    for token, brand in _BRAND_TOKENS.items():
        if token in n:
            return brand
    return None


def _maybe_convert_usd(amount: float | None, from_ccy: str) -> float | None:
    if amount is None:
        return None
    if (from_ccy or "USD").upper() == "USD":
        return float(amount)
    try:
        from fx import convert  # type: ignore
        return float(convert(amount, from_ccy, "USD"))
    except Exception:
        # Last-resort: if fx is unavailable, leave as-is so downstream still works.
        return float(amount)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_property(
    prop: dict,
    *,
    q: str,
    check_in: str,
    check_out: str,
    adults: int,
    currency: str,
    cache_hit: bool = False,
) -> dict:
    """Map a SerpApi `properties[i]` entry to a NormalizedHotel dict."""
    name = prop.get("name")
    nights = _nights(check_in, check_out)

    nightly = _num(prop.get("rate_per_night")) or _num(_safe(prop, "rate_per_night", "lowest"))
    if nightly is None:
        nightly = _num(_safe(prop, "rate_per_night", "extracted_lowest"))

    total = _num(prop.get("total_rate")) or _num(_safe(prop, "total_rate", "lowest"))
    if total is None:
        total = _num(_safe(prop, "total_rate", "extracted_lowest"))

    if total is None and nightly is not None:
        total = round(nightly * nights, 2)
    if nightly is None and total is not None and nights > 0:
        nightly = round(total / nights, 2)

    taxes_fees = None
    if total is not None and nightly is not None:
        taxes_fees = round(max(total - nightly * nights, 0.0), 2)

    lat = _safe(prop, "gps_coordinates", "latitude")
    lon = _safe(prop, "gps_coordinates", "longitude")
    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon = None

    property_token = prop.get("property_token") or prop.get("token") or prop.get("serpapi_property_details_link")

    # `raw` keeps the original entry for debugging; SerpApi never echoes our
    # api_key inside a property record, but strip any field that looks like one.
    raw_clean = {k: v for k, v in prop.items() if k.lower() not in _SECRET_HINT_KEYS}

    nightly_usd = _maybe_convert_usd(nightly, currency)
    total_usd = _maybe_convert_usd(total, currency)

    description = prop.get("description") or ""
    rate_type = "best_flexible"  # SerpApi rarely surfaces; refined by search_details.

    return {
        "hotel_id": str(property_token) if property_token else f"unknown:{sha256((name or '').encode()).hexdigest()[:12]}",
        "name": name,
        "brand": _guess_brand(name),
        "location": {
            "city": q,
            "country": None,
            "lat": lat,
            "lon": lon,
            "address": prop.get("address") or prop.get("location"),
        },
        "check_in": check_in,
        "check_out": check_out,
        "nights": nights,
        "guests": adults,
        "currency_local": currency.upper(),
        "currency_query": currency.upper(),
        "nightly_rate_query_ccy": nightly,
        "total_after_fees_query_ccy": total,
        "taxes_fees_query_ccy": taxes_fees,
        "nightly_rate_usd": nightly_usd,
        "total_after_fees_usd": total_usd,
        "fees_breakdown": {
            "resort_fee_usd": None,
            "parking_usd": None,
            "wifi_usd": None,
            "other_usd": None,
        },
        "refundable": None,
        "refund_deadline": None,
        "rate_type": rate_type,
        "source": "serpapi",
        "source_url": prop.get("link"),
        "fetched_at": _now_iso(),
        "cache_hit": cache_hit,
        "raw": raw_clean,
        # Internal hints — rank.py overwrites with authoritative logic.
        "_hints": {
            "free_night_hint": _has_free_night_hint(description) or _has_free_night_hint(prop.get("deal_description")),
            "deal": prop.get("deal"),
            "deal_description": prop.get("deal_description"),
            "hotel_class": prop.get("hotel_class"),
            "overall_rating": prop.get("overall_rating"),
            "reviews": prop.get("reviews"),
            "amenities": prop.get("amenities"),
            "eco_certified": prop.get("eco_certified"),
            "location_rating": prop.get("location_rating"),
            "nearby_places": prop.get("nearby_places"),
            "type": prop.get("type"),
            "check_in_time": prop.get("check_in_time"),
            "check_out_time": prop.get("check_out_time"),
            "prices": prop.get("prices"),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print_error_and_exit(err: Exception, *, code: int = 1) -> None:
    payload = {}
    if hasattr(err, "to_dict"):
        try:
            payload = err.to_dict()  # type: ignore[attr-defined]
        except Exception:
            payload = {}
    if not payload:
        payload = {
            "ok": False,
            "error": {
                "code": getattr(err, "code", "error"),
                "message": str(err),
                "hint": getattr(err, "hint", ""),
            },
        }
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def _try_log(event: str, **fields: Any) -> None:
    try:
        from common import log_event  # type: ignore
        log_event(event, **fields)
    except Exception:
        # Silent: never crash on logging.
        pass


def _try_cache_get(key: str) -> Any:
    try:
        from common import cache_get  # type: ignore
        return cache_get(key)
    except Exception:
        return None


def _try_cache_put(key: str, value: Any, ttl_hours: int = 24) -> None:
    try:
        from common import cache_put  # type: ignore
        cache_put(key, value, ttl_hours=ttl_hours)
    except Exception:
        pass


def _try_account_remaining() -> int | None:
    try:
        from common import account_remaining  # type: ignore
        return int(account_remaining())
    except Exception:
        return None


def _try_account_decrement(n: int = 1) -> None:
    try:
        from common import account_decrement  # type: ignore
        account_decrement(n)
    except Exception:
        pass


def _try_load_env() -> None:
    try:
        from common import load_env  # type: ignore
        env = load_env() or {}
        for k, v in env.items():
            os.environ.setdefault(k, v)
    except Exception:
        pass


def _emit(records: list[dict], output: str, top: int) -> None:
    sliced = records[: max(top, 0)]
    if output == "jsonl":
        for r in sliced:
            print(json.dumps(r, default=str))
    else:
        print(json.dumps(sliced, default=str))


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="search_hotels.py",
        description="Search hotels via SerpApi (Google Hotels) and emit normalized JSON.",
    )
    p.add_argument("--q", required=True, help="Destination query (city, area, or hotel name).")
    p.add_argument("--check-in", required=True, dest="check_in", help="Check-in date (YYYY-MM-DD).")
    p.add_argument("--check-out", required=True, dest="check_out", help="Check-out date (YYYY-MM-DD).")
    p.add_argument("--adults", type=int, default=1, help="Number of adult guests (default 1).")
    p.add_argument("--currency", default="USD", help="Query currency, ISO-4217 (default USD).")
    p.add_argument("--gl", default="us", help="Google geo locale (default us).")
    p.add_argument("--hl", default="en", help="Google language (default en).")
    p.add_argument("--no-cache", action="store_true", help="Skip local cache; force a live call.")
    p.add_argument("--top", type=int, default=100, help="Maximum records to emit (default 100).")
    p.add_argument(
        "--output",
        choices=("json", "jsonl"),
        default="json",
        help="Output format (default json).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    _try_load_env()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()

    # Cache key — DOES NOT include api_key.
    cache_key = _cache_key(
        q=args.q,
        check_in=args.check_in,
        check_out=args.check_out,
        adults=args.adults,
        currency=args.currency,
    )

    # 1) Cache hit (warm).
    if not args.no_cache:
        cached = _try_cache_get(cache_key)
        if isinstance(cached, list) and cached:
            for r in cached:
                if isinstance(r, dict):
                    r["cache_hit"] = True
            _try_log("search_hotels.cache_hit", q=args.q, count=len(cached))
            _emit(cached, args.output, args.top)
            return 0

    # 2) Quota check.
    remaining = _try_account_remaining()
    if remaining is not None and remaining < 1:
        _try_log("search_hotels.quota_exhausted", q=args.q, remaining=remaining)
        stale = _try_cache_get(cache_key)
        if isinstance(stale, list) and stale:
            for r in stale:
                if isinstance(r, dict):
                    r["cache_hit"] = True
                    r["staleness_warning"] = (
                        "SerpApi monthly quota exhausted; returning cached results which may be out of date."
                    )
            _emit(stale, args.output, args.top)
            return 0
        FE = _get_friendly_error_class()
        _print_error_and_exit(
            FE(
                "Monthly hotel-search quota is used up and we have no cached results for this trip.",
                code="quota_exhausted",
                hint="Wait until your SerpApi quota resets, or set --no-cache=false and re-run a known trip.",
            )
            if FE is not _LocalFriendly
            else _LocalFriendly(
                "Monthly hotel-search quota is used up and we have no cached results for this trip.",
                code="quota_exhausted",
                hint="Wait until your SerpApi quota resets, or re-run a previously cached trip.",
            ),
            code=1,
        )

    # 3) Live SerpApi call.
    if not api_key:
        FE = _get_friendly_error_class()
        try:
            err = FE(
                "Missing SERPAPI_KEY.",
                code="missing_key",
                hint="Add SERPAPI_KEY to your .env file (see .env.example).",
            )
        except TypeError:
            err = FE("Missing SERPAPI_KEY.")
        _print_error_and_exit(err, code=2)

    source: HotelSource = SerpApiSource(api_key)

    try:
        raw_props = source.search(
            q=args.q,
            check_in=args.check_in,
            check_out=args.check_out,
            adults=args.adults,
            currency=args.currency,
            gl=args.gl,
            hl=args.hl,
        )
    except Exception as e:
        _try_log(
            "search_hotels.api_error",
            q=args.q,
            error=_redact(str(e))[:240],
        )
        # 4) Fall back to any cached result, even if --no-cache was set.
        stale = _try_cache_get(cache_key)
        if isinstance(stale, list) and stale:
            for r in stale:
                if isinstance(r, dict):
                    r["cache_hit"] = True
                    r["staleness_warning"] = (
                        "Live hotel-search call failed; returning cached results."
                    )
            _emit(stale, args.output, args.top)
            return 0
        _print_error_and_exit(e, code=1)

    # 5) Normalize.
    records: list[dict] = []
    missing_rate_count = 0
    for prop in raw_props:
        if not isinstance(prop, dict):
            continue
        try:
            rec = normalize_property(
                prop,
                q=args.q,
                check_in=args.check_in,
                check_out=args.check_out,
                adults=args.adults,
                currency=args.currency,
                cache_hit=False,
            )
        except Exception as norm_err:
            _try_log(
                "search_hotels.normalize_error",
                q=args.q,
                error=_redact(str(norm_err))[:240],
                name=prop.get("name"),
            )
            continue
        if rec.get("nightly_rate_query_ccy") is None and rec.get("total_after_fees_query_ccy") is None:
            missing_rate_count += 1
            _try_log(
                "search_hotels.missing_rate",
                q=args.q,
                name=rec.get("name"),
                hotel_id=rec.get("hotel_id"),
            )
            # Keep record with None rates so rank.py can deprioritize.
        records.append(rec)

    # Validate against NormalizedHotel pydantic model if available — but never block.
    try:
        from common import NormalizedHotel  # type: ignore
        validated: list[dict] = []
        for r in records:
            try:
                # pydantic v2 model_validate / fallback to constructor
                if hasattr(NormalizedHotel, "model_validate"):
                    m = NormalizedHotel.model_validate(r)
                    validated.append(m.model_dump())
                else:
                    m = NormalizedHotel(**{k: v for k, v in r.items() if k != "_hints"})
                    validated.append({**(m.dict() if hasattr(m, "dict") else r), "_hints": r.get("_hints")})
            except Exception as ve:
                _try_log("search_hotels.schema_warn", error=str(ve)[:200], hotel_id=r.get("hotel_id"))
                validated.append(r)
        records = validated
    except Exception:
        pass

    # 6) Cache + decrement.
    _try_cache_put(cache_key, records, ttl_hours=24)
    _try_account_decrement(1)
    _try_log(
        "search_hotels.success",
        q=args.q,
        count=len(records),
        missing_rate=missing_rate_count,
    )

    _emit(records, args.output, args.top)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
