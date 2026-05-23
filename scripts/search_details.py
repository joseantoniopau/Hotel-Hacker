#!/usr/bin/env python3
"""
search_details.py - Per-property detail lookup via SerpApi `property_token`.

Outputs a single NormalizedHotel JSON object (enriched with fees_breakdown,
refundable, refund_deadline, rooms, prices) to stdout.

Counts as a separate SerpApi search against the monthly quota. Local cache TTL
is 12h (vs 24h for list searches).

Contract: see /tmp/hh-build-spec.md.
Owned by Agent D. Never log or print SERPAPI_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any

# Make sibling scripts importable when invoked directly.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Re-use the source adapter + helpers from search_hotels.
from search_hotels import (  # noqa: E402
    SerpApiSource,
    _LocalFriendly,
    _get_friendly_error_class,
    _maybe_convert_usd,
    _num,
    _redact,
    _safe,
    normalize_property,
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nights(check_in: str, check_out: str) -> int:
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    n = (co - ci).days
    return max(n, 1)


def _cache_key(*, property_token: str, check_in: str, check_out: str, adults: int, currency: str) -> str:
    blob = f"detail|{property_token}|{check_in}|{check_out}|{adults}|{currency.upper()}"
    return sha256(blob.encode("utf-8")).hexdigest()


def _try_log(event: str, **fields: Any) -> None:
    try:
        from common import log_event  # type: ignore
        log_event(event, **fields)
    except Exception:
        pass


def _try_cache_get(key: str) -> Any:
    try:
        from common import cache_get  # type: ignore
        return cache_get(key)
    except Exception:
        return None


def _try_cache_put(key: str, value: Any, ttl_hours: int = 12) -> None:
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


# ---------------------------------------------------------------------------
# Fees / refundability extraction
# ---------------------------------------------------------------------------


_FEE_LABEL_MAP = {
    "resort": "resort_fee_usd",
    "destination": "resort_fee_usd",
    "amenity": "resort_fee_usd",
    "parking": "parking_usd",
    "valet": "parking_usd",
    "wifi": "wifi_usd",
    "wi-fi": "wifi_usd",
    "internet": "wifi_usd",
}


def _extract_fees(detail: dict, currency: str) -> dict:
    """Walk SerpApi detail body for known fee categories.

    SerpApi detail surfaces fees in a handful of shapes — we try them all.
    """
    out = {
        "resort_fee_usd": None,
        "parking_usd": None,
        "wifi_usd": None,
        "other_usd": None,
    }

    candidates: list[dict] = []

    # 1) `rate_breakdown` (list of {"name": "Resort fee", "amount": ...})
    rb = detail.get("rate_breakdown")
    if isinstance(rb, list):
        candidates.extend(x for x in rb if isinstance(x, dict))

    # 2) `prices` -> per-source breakdown often contains `fees` arrays.
    prices = detail.get("prices") or detail.get("featured_prices")
    if isinstance(prices, list):
        for p in prices:
            if not isinstance(p, dict):
                continue
            for key in ("fees", "taxes_and_fees", "extra_charges", "breakdown"):
                v = p.get(key)
                if isinstance(v, list):
                    candidates.extend(x for x in v if isinstance(x, dict))

    # 3) `taxes_fees` or `fees` at top level.
    for key in ("fees", "taxes_fees", "extra_charges"):
        v = detail.get(key)
        if isinstance(v, list):
            candidates.extend(x for x in v if isinstance(x, dict))

    other_total = 0.0
    other_seen = False

    for item in candidates:
        label = (item.get("name") or item.get("label") or item.get("title") or "").lower()
        amount = _num(item.get("amount")) or _num(item.get("price")) or _num(item.get("value")) or _num(item)
        if amount is None:
            continue
        usd = _maybe_convert_usd(amount, currency)
        if usd is None:
            continue
        matched = False
        for token, slot in _FEE_LABEL_MAP.items():
            if token in label:
                # Sum multiple matches into the same slot defensively.
                prior = out[slot] or 0.0
                out[slot] = round(prior + usd, 2)
                matched = True
                break
        if not matched:
            other_total += usd
            other_seen = True

    if other_seen:
        out["other_usd"] = round(other_total, 2)

    return out


_NONREFUNDABLE_HINTS = (
    "non-refundable",
    "nonrefundable",
    "non refundable",
    "no refund",
    "not refundable",
    "prepaid",
    "pay now",
)
_REFUNDABLE_HINTS = (
    "free cancellation",
    "fully refundable",
    "refundable",
    "cancel for free",
)


def _extract_refundable(detail: dict) -> tuple[bool | None, str | None]:
    """Return (refundable, refund_deadline_iso_or_text)."""
    refundable: bool | None = None
    deadline: str | None = None

    # 1) explicit field
    cp = detail.get("cancellation_policy") or detail.get("cancellation")
    if isinstance(cp, dict):
        if "refundable" in cp:
            refundable = bool(cp.get("refundable"))
        deadline = cp.get("deadline") or cp.get("free_cancellation_until") or cp.get("cancel_by")
        text = (cp.get("text") or cp.get("description") or "").lower()
    elif isinstance(cp, str):
        text = cp.lower()
    else:
        text = ""

    # 2) scan prices entries
    prices = detail.get("prices") or detail.get("featured_prices") or []
    if isinstance(prices, list):
        for p in prices:
            if not isinstance(p, dict):
                continue
            for fld in ("free_cancellation_until", "cancel_by", "cancellation_deadline"):
                if p.get(fld) and not deadline:
                    deadline = p.get(fld)
            for fld in ("policy", "cancellation_policy", "details", "description", "label"):
                v = p.get(fld)
                if isinstance(v, str):
                    text += " " + v.lower()
            if "refundable" in p and refundable is None:
                try:
                    refundable = bool(p.get("refundable"))
                except Exception:
                    pass

    # 3) text heuristics
    if refundable is None and text:
        if any(h in text for h in _NONREFUNDABLE_HINTS):
            refundable = False
        elif any(h in text for h in _REFUNDABLE_HINTS):
            refundable = True

    return refundable, deadline


# ---------------------------------------------------------------------------
# Normalization (detail flavor)
# ---------------------------------------------------------------------------


def normalize_detail(
    detail: dict,
    *,
    property_token: str,
    check_in: str,
    check_out: str,
    adults: int,
    currency: str,
    cache_hit: bool = False,
) -> dict:
    """Map a SerpApi detail body to a NormalizedHotel dict (enriched)."""
    # Detail responses typically nest the property fields at the top level
    # (no `properties` wrapper). Some shapes use `property_details` —
    # accept either.
    base = detail.get("property_details") if isinstance(detail.get("property_details"), dict) else detail

    # Start from the list-mode normalizer so we share the heavy lifting.
    rec = normalize_property(
        base,
        q="",
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        currency=currency,
        cache_hit=cache_hit,
    )

    # Preserve / overwrite hotel_id with the explicit token we used.
    rec["hotel_id"] = str(property_token)

    # Fees breakdown.
    rec["fees_breakdown"] = _extract_fees(detail, currency)

    # Refundability.
    refundable, deadline = _extract_refundable(detail)
    rec["refundable"] = refundable
    rec["refund_deadline"] = deadline

    if refundable is True:
        rec["rate_type"] = "best_flexible"
    elif refundable is False:
        rec["rate_type"] = "non_refundable"

    # Enrich hints with detail-only data.
    hints = rec.get("_hints") or {}
    hints["rooms"] = detail.get("rooms")
    hints["featured_prices"] = detail.get("featured_prices")
    hints["images"] = detail.get("images")
    hints["reviews_breakdown"] = detail.get("reviews_breakdown")
    hints["amenities_detailed"] = detail.get("amenities") or hints.get("amenities")
    rec["_hints"] = hints

    # Strip any api_key-like keys from raw, just in case.
    raw_clean = {k: v for k, v in detail.items() if k.lower() not in ("api_key", "apikey", "serpapi_key")}
    rec["raw"] = raw_clean

    rec["fetched_at"] = _now_iso()
    return rec


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="search_details.py",
        description="Fetch enriched per-property detail from SerpApi by property_token.",
    )
    p.add_argument("--property-token", required=True, dest="property_token", help="SerpApi property_token.")
    p.add_argument("--check-in", required=True, dest="check_in", help="Check-in date (YYYY-MM-DD).")
    p.add_argument("--check-out", required=True, dest="check_out", help="Check-out date (YYYY-MM-DD).")
    p.add_argument("--adults", type=int, default=1, help="Number of adult guests (default 1).")
    p.add_argument("--currency", default="USD", help="Query currency, ISO-4217 (default USD).")
    p.add_argument("--gl", default="us", help="Google geo locale (default us).")
    p.add_argument("--hl", default="en", help="Google language (default en).")
    p.add_argument("--no-cache", action="store_true", help="Skip local cache; force a live call.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    _try_load_env()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()

    cache_key = _cache_key(
        property_token=args.property_token,
        check_in=args.check_in,
        check_out=args.check_out,
        adults=args.adults,
        currency=args.currency,
    )

    # 1) Warm cache.
    if not args.no_cache:
        cached = _try_cache_get(cache_key)
        if isinstance(cached, dict) and cached:
            cached["cache_hit"] = True
            _try_log("search_details.cache_hit", property_token=args.property_token)
            print(json.dumps(cached, default=str))
            return 0

    # 2) Quota.
    remaining = _try_account_remaining()
    if remaining is not None and remaining < 1:
        _try_log(
            "search_details.quota_exhausted",
            property_token=args.property_token,
            remaining=remaining,
        )
        stale = _try_cache_get(cache_key)
        if isinstance(stale, dict) and stale:
            stale["cache_hit"] = True
            stale["staleness_warning"] = (
                "SerpApi monthly quota exhausted; returning cached detail which may be out of date."
            )
            print(json.dumps(stale, default=str))
            return 0
        FE = _get_friendly_error_class()
        try:
            err = FE(
                "Monthly hotel-search quota is used up and we have no cached detail for this property.",
                code="quota_exhausted",
                hint="Wait until your SerpApi quota resets, or re-fetch later.",
            )
        except TypeError:
            err = FE("Monthly hotel-search quota is used up and we have no cached detail for this property.")
        _print_error_and_exit(err, code=1)

    # 3) Live call.
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

    source = SerpApiSource(api_key)

    try:
        detail_body = source.detail(
            property_token=args.property_token,
            check_in=args.check_in,
            check_out=args.check_out,
            adults=args.adults,
            currency=args.currency,
            gl=args.gl,
            hl=args.hl,
        )
    except Exception as e:
        _try_log(
            "search_details.api_error",
            property_token=args.property_token,
            error=_redact(str(e))[:240],
        )
        stale = _try_cache_get(cache_key)
        if isinstance(stale, dict) and stale:
            stale["cache_hit"] = True
            stale["staleness_warning"] = "Live detail call failed; returning cached detail."
            print(json.dumps(stale, default=str))
            return 0
        _print_error_and_exit(e, code=1)

    # 4) Normalize.
    try:
        rec = normalize_detail(
            detail_body,
            property_token=args.property_token,
            check_in=args.check_in,
            check_out=args.check_out,
            adults=args.adults,
            currency=args.currency,
            cache_hit=False,
        )
    except Exception as norm_err:
        _try_log(
            "search_details.normalize_error",
            property_token=args.property_token,
            error=_redact(str(norm_err))[:240],
        )
        _print_error_and_exit(norm_err, code=1)

    # 5) Optional schema validation.
    try:
        from common import NormalizedHotel  # type: ignore
        try:
            if hasattr(NormalizedHotel, "model_validate"):
                m = NormalizedHotel.model_validate(rec)
                rec = m.model_dump()
            else:
                m = NormalizedHotel(**{k: v for k, v in rec.items() if k != "_hints"})
                rec = {**(m.dict() if hasattr(m, "dict") else rec), "_hints": rec.get("_hints")}
        except Exception as ve:
            _try_log(
                "search_details.schema_warn",
                error=str(ve)[:200],
                hotel_id=rec.get("hotel_id"),
            )
    except Exception:
        pass

    # 6) Cache (12h) + decrement.
    _try_cache_put(cache_key, rec, ttl_hours=12)
    _try_account_decrement(1)
    _try_log("search_details.success", property_token=args.property_token)

    print(json.dumps(rec, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
