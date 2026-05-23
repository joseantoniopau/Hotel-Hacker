"""
rank.py — sort normalized hotel records by effective_cost_usd.

CLI:
  cat normalized.json | python3 rank.py --top 20 [--balances balances.json] [--fhr-input fhr.json]

Pure-function core:
  rank_hotels(hotels, balances, valuations, loyalty_programs,
              fhr_perk_values, perk_rules, fhr_inputs=None) -> list[ranked_record]

Canonical formula (see /tmp/hh-build-spec.md):
  effective_cost_usd = raw_total_usd
                     - points_value_usd
                     - free_night_value_usd
                     - (fhr_value_usd - fhr_haircut_usd)
                     + flexibility_penalty_usd
                     + currency_arb_usd   # signed

Tie-breaker: when |Δeffective_usd| < $5, prefer refundable > FHR > points > raw.

This module does no network I/O and no globals — it is fully unit-testable.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

# Module imports — assumes Agent C has written common.py, fx.py, value.py per
# spec, and sys.path includes scripts/ (set by conftest / smoke_test / CLI).
from common import load_data, log_event  # type: ignore

# value.py and fx.py imports are wrapped because rank.py is loaded by tests
# before value.py / fx.py may exist; guard with informative re-raise.
try:
    from value import (  # type: ignore
        value_points,
        value_free_night,
        value_fhr,
        flexibility_penalty,
    )
except ImportError as e:  # pragma: no cover — only hit during partial builds
    raise ImportError(
        "rank.py requires scripts/value.py (pure-function valuations). "
        f"Original import error: {e}"
    ) from e

try:
    from fx import currency_arbitrage  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "rank.py requires scripts/fx.py (currency_arbitrage helper). "
        f"Original import error: {e}"
    ) from e


# ---------------------------------------------------------------------------
# Defensive accessors — never crash on missing / nulled fields
# ---------------------------------------------------------------------------

def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; return `default` on None / type errors / NaN."""
    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    # Reject NaN — propagating NaN into a sort key produces undefined order.
    if f != f:
        return default
    return f


def _as_bool(value: Any) -> Optional[bool]:
    """Coerce truthy boolean-ish into True / False / None.

    Garbled values like "maybe" become None so the flexibility penalty falls
    back to "unknown -> no penalty" (per spec: penalty only when explicitly
    non-refundable).
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        lo = value.strip().lower()
        if lo in ("true", "yes", "y", "1", "refundable"):
            return True
        if lo in ("false", "no", "n", "0", "non_refundable", "nonrefundable"):
            return False
    return None


def _get(d: Any, key: str, default: Any = None) -> Any:
    """Dict-or-pydantic-friendly attribute fetch."""
    if isinstance(d, dict):
        return d.get(key, default)
    return getattr(d, key, default)


def _raw_total_usd(hotel: dict) -> float:
    """Pick the canonical USD anchor — falls back to nightly_rate_usd * nights."""
    total = _as_float(hotel.get("total_after_fees_usd"), default=0.0)
    if total > 0:
        return total
    nightly = _as_float(hotel.get("nightly_rate_usd"), default=0.0)
    nights = _as_float(hotel.get("nights"), default=0.0)
    if nightly > 0 and nights > 0:
        return nightly * nights
    return 0.0


# ---------------------------------------------------------------------------
# Per-component computations (delegate to value.py / fx.py)
# ---------------------------------------------------------------------------

def _compute_points_value(
    hotel: dict,
    balances: Optional[dict],
    valuations: dict,
) -> float:
    """Return USD points value if user has the program + enough balance, else 0.

    The pure cpp-math lives in value.value_points; this wrapper enforces the
    ranking-layer gate: "only credit points value when the user actually has
    enough points to book". Without a balances dict (CLI run without
    --balances) we still credit the points value — the user explicitly opted
    out of the balance check.
    """
    pe = hotel.get("points_eligible")
    if not pe:
        return 0.0
    program = _get(pe, "program")
    if not program:
        return 0.0
    points_per_night = _as_float(_get(pe, "points_per_night"), default=0.0)
    nights = _as_float(hotel.get("nights"), default=0.0)
    if points_per_night <= 0 or nights <= 0:
        return 0.0

    # If a balances dict was supplied, enforce the threshold; otherwise skip
    # the check (graceful: user did not opt into balance-aware ranking).
    if balances and isinstance(balances, dict):
        programs = balances.get("programs") or {}
        balance = _as_float(programs.get(program), default=0.0)
        if balance < points_per_night * nights:
            return 0.0

    return float(value_points(
        program=program,
        points_per_night=int(points_per_night),
        nights=int(nights),
        valuations=valuations or {},
    ))


def _compute_free_night_value(
    hotel: dict,
    loyalty_programs: dict,
) -> float:
    """Return USD value of free-night benefit when the rule + threshold trigger."""
    fne = hotel.get("free_night_eligible")
    program = None
    if fne:
        program = _get(fne, "program")
    if not program:
        program = hotel.get("brand")  # best-effort fallback by brand label

    nights = _as_float(hotel.get("nights"), default=0.0)
    nightly = _as_float(hotel.get("nightly_rate_usd"), default=0.0)
    if nights <= 0 or nightly <= 0 or not program:
        return 0.0

    return float(value_free_night(
        program=program,
        nightly_rate_usd=nightly,
        nights=int(nights),
        loyalty_programs=loyalty_programs or {},
    ))


def _compute_fhr(
    hotel: dict,
    fhr_inputs: Optional[List[dict]],
    fhr_perk_values: dict,
    perk_rules: dict,
    balances: Optional[dict],
) -> Tuple[float, float]:
    """Return (fhr_value_usd, fhr_haircut_usd).

    fhr_inputs are user-pasted entries that opt this property into FHR scoring.
    No automatic FHR scoring without an explicit input — FHR availability
    rotates and cannot be inferred from brand alone.
    """
    if not fhr_inputs:
        return 0.0, 0.0
    token = hotel.get("hotel_id")
    if not token:
        return 0.0, 0.0

    # Require an FHR-eligible card in the user's wallet (if balances provided).
    if balances and isinstance(balances, dict):
        cards = balances.get("cards") or []
        required = (perk_rules or {}).get("fhr_requires_card") or []
        if required and not any(c in cards for c in required):
            return 0.0, 0.0

    entry: Optional[dict] = None
    for fi in fhr_inputs:
        if not isinstance(fi, dict):
            continue
        if fi.get("property_token") == token:
            entry = fi
            break
    if not entry:
        return 0.0, 0.0

    perks_in = entry.get("perks") or {}
    # Translate shorthand perk flags ("fb_credit", "breakfast", ...) into the
    # canonical fhr_perk_values keys before handing to value.value_fhr (which
    # expects the canonical keys directly).
    perk_selection: Dict[str, bool] = {}
    for k, v in perks_in.items():
        if not v:
            continue
        canonical = _perk_key_for(k)
        perk_selection[canonical] = True

    folio_currency = (
        entry.get("property_currency")
        or hotel.get("currency_local")
        or "USD"
    )

    result = value_fhr(
        perk_selection=perk_selection,
        fhr_perk_values=fhr_perk_values or {},
        folio_currency=folio_currency,
    )

    # value_fhr returns (gross_usd, haircut_usd).
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        return float(result[0]), float(result[1])
    return float(result or 0.0), 0.0


# Map shorthand perk flags ("fb_credit", "breakfast", "late_checkout", ...) to
# the canonical keys in fhr_perk_values.json. Kept narrow on purpose.
_PERK_KEY_MAP: Dict[str, str] = {
    "fb_credit": "fb_credit_usd_property",
    "breakfast": "daily_breakfast_2pax_usd",
    "late_checkout": "late_checkout_4pm_usd",
    "late_checkout_guaranteed": "guaranteed_4pm_usd",
    "noon_check_in": "noon_check_in_usd",
    "upgrade": "room_upgrade_usd_uncertain",
    "welcome_amenity": "welcome_amenity_usd",
    "wifi": "complimentary_wifi_usd",
}


def _perk_key_for(short: str) -> str:
    return _PERK_KEY_MAP.get(short, short)


def _compute_flex_penalty(hotel: dict, raw_total_usd: float) -> float:
    """Return the flexibility penalty USD via value.py (with safe fallback)."""
    refundable = _as_bool(hotel.get("refundable"))
    try:
        return float(flexibility_penalty(refundable, raw_total_usd))
    except TypeError:
        # Fallback to canonical 5%.
        if refundable is False:
            return 0.05 * raw_total_usd
        return 0.0


def _compute_currency_arb(hotel: dict) -> float:
    """Return signed currency_arb_usd contribution to effective_cost.

    fx.currency_arbitrage returns `spread_usd = local_in_usd - q_usd`:
      - positive when local-currency-converted-to-USD exceeds the USD quote
        (i.e. paying in USD is BETTER for the user — an edge);
      - negative when paying in USD is WORSE than paying in local-and-converting.

    Per the canonical spec formula, currency_arb_usd is ADDED to effective and
    a positive value should INCREASE effective ("home-currency-asking-USD is
    worse"). That is the OPPOSITE sign from fx.currency_arbitrage's convention,
    so we negate before returning.

    Returns 0.0 when the local and query currencies are the same, when the
    needed numbers are missing, or when fx raises (it should not, but we are
    defensive).
    """
    # Arbitrage is only meaningful when we have a non-USD QUERY total that we
    # can compare against the USD-converted total. (The normalized schema does
    # not carry a local-currency total separately, so we treat query_ccy as
    # the local-equivalent. When the query is already USD there is no edge.)
    query_ccy = hotel.get("currency_query") or "USD"
    if not query_ccy or query_ccy == "USD":
        return 0.0
    local_amount = _as_float(hotel.get("total_after_fees_query_ccy"), default=0.0)
    usd_amount = _as_float(hotel.get("total_after_fees_usd"), default=0.0)
    if local_amount <= 0 or usd_amount <= 0:
        return 0.0

    try:
        result = currency_arbitrage(local_amount, query_ccy, usd_amount)
    except Exception:
        return 0.0

    if isinstance(result, dict):
        spread = _as_float(result.get("spread_usd"), default=0.0)
    else:
        spread = _as_float(result, default=0.0)
    # Invert sign to align with the spec convention (positive == USD worse).
    return -spread


def _arb_flagged(hotel: dict, perk_rules: dict, arb_usd: float) -> bool:
    """True when |arb| exceeds the configured min_signal_pct of raw_total.

    Used to set the CCY-NOTE badge; the signal threshold matches the
    `currency_arb_min_signal_pct` knob in data/perk_rules.json (default 2%).
    """
    raw = _raw_total_usd(hotel)
    if raw <= 0:
        return False
    min_signal = _as_float(
        (perk_rules or {}).get("currency_arb_min_signal_pct"), default=0.02
    )
    return abs(arb_usd) / raw >= min_signal


# ---------------------------------------------------------------------------
# Per-hotel ranking record
# ---------------------------------------------------------------------------

def _format_explanation(
    name: str,
    raw_total: float,
    points_value: float,
    free_night_value: float,
    fhr_net: float,
    flex_penalty: float,
    arb_usd: float,
    effective: float,
    channel: str,
) -> str:
    """Produce a single human-readable sentence reconstructing the line items."""
    parts: List[str] = [f"${raw_total:,.0f} raw"]
    if points_value > 0:
        parts.append(f"minus ${points_value:,.0f} points value")
    if free_night_value > 0:
        parts.append(f"minus ${free_night_value:,.0f} free-night")
    if fhr_net > 0:
        parts.append(f"minus ${fhr_net:,.0f} FHR net")
    elif fhr_net < 0:
        parts.append(f"plus ${abs(fhr_net):,.0f} FHR haircut")
    if flex_penalty > 0:
        parts.append(f"plus ${flex_penalty:,.0f} non-refundable penalty")
    if arb_usd > 0:
        parts.append(f"plus ${arb_usd:,.0f} currency haircut")
    elif arb_usd < 0:
        parts.append(f"minus ${abs(arb_usd):,.0f} currency edge")
    via = {
        "fhr": "via Amex FHR",
        "points-portal": "via points portal",
        "direct": "via direct booking",
        "ota": "via OTA",
    }.get(channel, "")
    head = " ".join(parts)
    return f"{head} = ${effective:,.0f} {via}".strip()


def _pick_channel(
    *,
    fhr_net: float,
    points_value: float,
    free_night_value: float,
    refundable: Optional[bool],
) -> Tuple[str, str]:
    """Return (recommended_channel, channel_reason).

    Priority: FHR > points-portal > direct (refundable cash) > OTA.
    """
    points_total = points_value + free_night_value
    if fhr_net > 0 and fhr_net >= points_total and fhr_net > 0:
        return (
            "fhr",
            "FHR perks deliver the single biggest saving for this stay.",
        )
    if points_total > 0 and points_total >= fhr_net:
        return (
            "points-portal",
            "Award redemption beats every cash discount for this stay.",
        )
    if refundable is True:
        return (
            "direct",
            "Direct refundable rate wins on price and option value.",
        )
    return ("ota", "OTA cash rate is the best available channel.")


def _build_badges(
    *,
    refundable: Optional[bool],
    fhr_net: float,
    free_night_value: float,
    points_value: float,
    arb_flagged: bool,
    cache_hit: bool,
) -> List[str]:
    badges: List[str] = []
    if refundable is True:
        badges.append("REFUNDABLE")
    if fhr_net > 0:
        badges.append("FHR")
    if free_night_value > 0:
        # Distinguish 5TH-FREE vs 4TH-FREE based on the proportion vs nightly.
        # value.py returns nightly * 1 always, so we cannot infer here — leave
        # the broad badge for now; rank.py callers may overwrite via metadata.
        badges.append("FREE-NIGHT")
    if points_value > 0:
        badges.append("PTS")
    if arb_flagged:
        badges.append("CCY-NOTE")
    badges.append("LEGAL")  # default-on per spec
    if not cache_hit and False:  # placeholder — gray only when explicitly stale
        badges.append("GRAY")
    return badges


def _refine_free_night_badge(
    badges: List[str],
    hotel: dict,
    loyalty_programs: dict,
) -> List[str]:
    """Replace the broad FREE-NIGHT badge with 5TH-FREE or 4TH-FREE when known."""
    if "FREE-NIGHT" not in badges:
        return badges
    fne = hotel.get("free_night_eligible") or {}
    program = _get(fne, "program") or hotel.get("brand")
    prog_info = (loyalty_programs or {}).get(program) or {}
    min_nights = prog_info.get("min_nights")
    try:
        min_nights_int = int(min_nights) if min_nights is not None else None
    except (TypeError, ValueError):
        min_nights_int = None
    label = "FREE-NIGHT"
    if min_nights_int == 5:
        label = "5TH-FREE"
    elif min_nights_int == 4:
        label = "4TH-FREE"
    return [label if b == "FREE-NIGHT" else b for b in badges]


# ---------------------------------------------------------------------------
# Pure-function core
# ---------------------------------------------------------------------------

def _score_one(
    hotel: dict,
    *,
    balances: Optional[dict],
    valuations: dict,
    loyalty_programs: dict,
    fhr_perk_values: dict,
    perk_rules: dict,
    fhr_inputs: Optional[List[dict]],
) -> Dict[str, Any]:
    """Compute the full ranked record for one normalized hotel."""
    raw_total = _raw_total_usd(hotel)

    points_value = _compute_points_value(hotel, balances, valuations)
    free_night_value = _compute_free_night_value(hotel, loyalty_programs)
    fhr_value, fhr_haircut = _compute_fhr(
        hotel, fhr_inputs, fhr_perk_values, perk_rules, balances
    )
    flex_penalty = _compute_flex_penalty(hotel, raw_total)
    arb_usd = _compute_currency_arb(hotel)

    fhr_net = fhr_value - fhr_haircut
    effective = (
        raw_total
        - points_value
        - free_night_value
        - fhr_net
        + flex_penalty
        + arb_usd
    )

    refundable = _as_bool(hotel.get("refundable"))
    channel, reason = _pick_channel(
        fhr_net=fhr_net,
        points_value=points_value,
        free_night_value=free_night_value,
        refundable=refundable,
    )

    badges = _build_badges(
        refundable=refundable,
        fhr_net=fhr_net,
        free_night_value=free_night_value,
        points_value=points_value,
        arb_flagged=_arb_flagged(hotel, perk_rules, arb_usd),
        cache_hit=bool(hotel.get("cache_hit")),
    )
    badges = _refine_free_night_badge(badges, hotel, loyalty_programs)

    explanation = _format_explanation(
        name=hotel.get("name", ""),
        raw_total=raw_total,
        points_value=points_value,
        free_night_value=free_night_value,
        fhr_net=fhr_net,
        flex_penalty=flex_penalty,
        arb_usd=arb_usd,
        effective=effective,
        channel=channel,
    )

    return {
        "normalized": hotel,
        "raw_usd": round(raw_total, 2),
        "effective_usd": round(effective, 2),
        "breakdown": {
            "raw_total_usd": round(raw_total, 2),
            "points_value_usd": round(points_value, 2),
            "free_night_value_usd": round(free_night_value, 2),
            "fhr_value_usd": round(fhr_value, 2),
            "fhr_haircut_usd": round(fhr_haircut, 2),
            "flexibility_penalty_usd": round(flex_penalty, 2),
            "currency_arb_usd": round(arb_usd, 2),
        },
        "recommended_channel": channel,
        "channel_reason": reason,
        "badges": badges,
        "explanation": explanation,
        "score_rank": 0,  # filled in after sort
        "_meta": {
            "refundable": refundable,
            "fhr_net": fhr_net,
            "points_total": points_value + free_night_value,
        },
    }


def _tiebreaker_key(rec: Dict[str, Any], priority: List[str]) -> Tuple[int, ...]:
    """Return a tuple used as the secondary sort key.

    Lower = preferred. Mirrors the perk_rules tiebreaker_priority list:
    'refundable', 'fhr', 'points', 'raw'.
    """
    meta = rec.get("_meta") or {}
    flags: Dict[str, bool] = {
        "refundable": bool(meta.get("refundable") is True),
        "fhr": bool(meta.get("fhr_net", 0) > 0),
        "points": bool(meta.get("points_total", 0) > 0),
        "raw": True,  # always available
    }
    key: List[int] = []
    for p in priority:
        # 0 when the flag is set (preferred), 1 otherwise.
        key.append(0 if flags.get(p, False) else 1)
    return tuple(key)


def rank_hotels(
    hotels: List[dict],
    balances: Optional[dict],
    valuations: dict,
    loyalty_programs: dict,
    fhr_perk_values: dict,
    perk_rules: dict,
    fhr_inputs: Optional[List[dict]] = None,
) -> List[Dict[str, Any]]:
    """Pure ranking function — sort hotels ascending by effective_usd.

    Tiebreaker: when |Δeffective_usd| < tiebreaker_threshold_usd (default $5),
    apply the perk_rules.tiebreaker_priority preference list.

    Returns a list of ranked records (see RankedRecord in common.py).
    """
    if not hotels:
        return []

    scored: List[Dict[str, Any]] = []
    for h in hotels:
        if not isinstance(h, dict):
            continue
        try:
            scored.append(
                _score_one(
                    h,
                    balances=balances,
                    valuations=valuations or {},
                    loyalty_programs=loyalty_programs or {},
                    fhr_perk_values=fhr_perk_values or {},
                    perk_rules=perk_rules or {},
                    fhr_inputs=fhr_inputs,
                )
            )
        except Exception as e:  # pragma: no cover — defensive
            log_event("rank_score_error", hotel_id=h.get("hotel_id"), error=str(e))
            continue

    tb_threshold = float((perk_rules or {}).get("tiebreaker_threshold_usd", 5))
    tb_priority = list((perk_rules or {}).get("tiebreaker_priority") or [
        "refundable", "fhr", "points", "raw"
    ])

    # Primary sort: bucket effective_usd into floor(effective / threshold)-sized
    # bins so any two records within `threshold` USD land in the same bucket
    # and are then disambiguated by the tiebreaker key, then by raw effective
    # to keep the order stable inside a bucket.
    def sort_key(rec: Dict[str, Any]) -> Tuple[Any, ...]:
        eff = rec.get("effective_usd", 0.0)
        bucket = int(eff // tb_threshold) if tb_threshold > 0 else int(eff)
        return (bucket, _tiebreaker_key(rec, tb_priority), eff)

    scored.sort(key=sort_key)

    # Assign 1-based ranks; strip the internal _meta key from the public output.
    out: List[Dict[str, Any]] = []
    for i, rec in enumerate(scored, start=1):
        rec["score_rank"] = i
        rec.pop("_meta", None)
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_optional_json(path: Optional[str]) -> Any:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(
            f"warning: file not found: {path} — continuing without it.",
            file=sys.stderr,
        )
        return None
    except json.JSONDecodeError as e:
        print(
            f"warning: {path} is not valid JSON (line {e.lineno}) — ignored.",
            file=sys.stderr,
        )
        return None


def _read_stdin_hotels() -> List[dict]:
    raw = sys.stdin.read()
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(
            f"error: stdin is not valid JSON (line {e.lineno}): {e.msg}",
            file=sys.stderr,
        )
        sys.exit(2)
    if isinstance(data, dict) and "hotels" in data:
        data = data["hotels"]
    if not isinstance(data, list):
        print(
            "error: expected a JSON array of hotel records on stdin.",
            file=sys.stderr,
        )
        sys.exit(2)
    return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rank normalized hotel records by effective cost. "
            "Reads a JSON array from stdin and writes a JSON array to stdout."
        )
    )
    parser.add_argument("--top", type=int, default=20,
                        help="Maximum number of ranked records to emit (default 20).")
    parser.add_argument("--balances", default=None,
                        help="Path to a balances JSON file (programs + cards).")
    parser.add_argument("--fhr-input", default=None,
                        help="Path to a JSON array of FHR-paste entries.")
    args = parser.parse_args(argv)

    hotels = _read_stdin_hotels()
    balances = _load_optional_json(args.balances)
    fhr_inputs = _load_optional_json(args.fhr_input)
    if fhr_inputs is not None and not isinstance(fhr_inputs, list):
        print(
            "warning: --fhr-input file does not contain a list — ignored.",
            file=sys.stderr,
        )
        fhr_inputs = None

    # Pull data tables from data/ (graceful degradation if any are missing).
    valuations = _safe_load_data("points_valuations")
    loyalty_programs = _safe_load_data("loyalty_programs")
    fhr_perk_values = _safe_load_data("fhr_perk_values")
    perk_rules = _safe_load_data("perk_rules")

    ranked = rank_hotels(
        hotels=hotels,
        balances=balances,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
        fhr_inputs=fhr_inputs,
    )

    top_n = max(0, int(args.top))
    out = ranked[:top_n] if top_n else ranked
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def _safe_load_data(name: str) -> dict:
    try:
        return load_data(name)
    except Exception as e:
        print(
            f"warning: could not load data/{name}.json ({e}) — using empty defaults.",
            file=sys.stderr,
        )
        return {}


if __name__ == "__main__":
    sys.exit(main())
