"""
value.py — pure valuation primitives for the effective-cost formula.

No I/O, no globals, no side effects. Every function is unit-testable in
isolation and returns 0.0 (never None, never raises) on degenerate input —
the ranking layer is allowed to assume these never blow up.

GATING CONTRACT
---------------
These functions TRUST THEIR INPUTS. They do not check whether the caller's
user actually holds the points, has the qualifying card, or is otherwise
eligible to realize the value being computed. Every balance / card / FHR /
free-night gate lives one layer up in scripts/rank.py
(_compute_points_value, _compute_free_night_value, _compute_fhr). The
guarantee here is purely arithmetic: "given these inputs, this is the USD
value of the redemption". The caller is responsible for deciding whether
to apply that value at all.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


def value_points(
    program: str,
    points_per_night: int,
    nights: int,
    valuations: Dict[str, Any],
) -> float:
    """Convert a points redemption to USD using user-overridable cents-per-point.

    Conservative fallback of 0.5 cpp when a program is unknown — better to
    under-credit points value than to oversell a stay.

    NOTE: trusts inputs. Does NOT check whether the user has enough points
    to actually book this award — that gate lives in
    rank._compute_points_value.
    """
    try:
        ppn = float(points_per_night)
    except (TypeError, ValueError):
        ppn = 0.0
    try:
        n = float(nights)
    except (TypeError, ValueError):
        n = 0.0
    if not isinstance(valuations, dict):
        valuations = {}
    raw_cpp = valuations.get(program, 0.5) if isinstance(program, str) else 0.5
    try:
        cpp = float(raw_cpp)
    except (TypeError, ValueError):
        cpp = 0.5
    return (ppn * n * cpp) / 100.0


def value_free_night(
    program: str,
    nightly_rate_usd: float,
    nights: int,
    loyalty_programs: Dict[str, Any],
) -> float:
    """Apply free-night rules (Marriott 5th-free, IHG 4th-free, Hilton 5th-free).

    Worth one nightly rate in USD when the rule fires; otherwise 0.0. We model
    only the canonical patterns we encode in data/loyalty_programs.json.

    NOTE: trusts inputs. Does NOT check whether the user has a positive
    program balance — free-night benefits stack onto award redemptions, so
    the ranker (rank._compute_free_night_value) gates this on a non-zero
    direct program balance.
    """
    try:
        rate = float(nightly_rate_usd)
    except (TypeError, ValueError):
        return 0.0
    try:
        n = int(nights)
    except (TypeError, ValueError):
        return 0.0
    if not isinstance(loyalty_programs, dict) or not isinstance(program, str):
        return 0.0
    entry = loyalty_programs.get(program) or {}
    if not isinstance(entry, dict):
        return 0.0
    rule = entry.get("free_night_rule")
    if not rule:
        return 0.0
    if rule == "5th_free_on_5_night_redemption" and n >= 5:
        return rate
    if rule == "4th_free_on_4_consecutive_nights_award" and n >= 4:
        return rate
    if rule == "5th_free_on_5_night_award_diamond_gold" and n >= 5:
        return rate
    return 0.0


def value_fhr(
    perk_selection: Dict[str, Any],
    fhr_perk_values: Dict[str, Any],
    folio_currency: str = "USD",
) -> Tuple[float, float]:
    """Total FHR perk value + the regional FX haircut on that total.

    Sums USD values for every perk flagged True in `perk_selection`, then
    applies the folio-currency-specific haircut from
    `fhr_perk_values['_meta']['regional_haircut_pct']` (because an FHR USD
    credit converts at folio FX which typically clips 3-6% vs market mid).

    NOTE: trusts inputs. Does NOT check whether the user holds an
    FHR-qualifying Amex card (Platinum / Centurion / Business Platinum) or
    whether the property is FHR-eligible — both gates live in
    rank._compute_fhr.
    """
    if not isinstance(perk_selection, dict) or not isinstance(fhr_perk_values, dict):
        return (0.0, 0.0)

    gross_usd = 0.0
    for key, selected in perk_selection.items():
        if not selected:
            continue
        raw = fhr_perk_values.get(key)
        try:
            gross_usd += float(raw)
        except (TypeError, ValueError):
            continue

    meta = fhr_perk_values.get("_meta") or {}
    haircuts = meta.get("regional_haircut_pct") if isinstance(meta, dict) else None
    if not isinstance(haircuts, dict):
        haircuts = {}
    ccy = folio_currency.upper() if isinstance(folio_currency, str) else "USD"
    pct = haircuts.get(ccy, haircuts.get("_default", 0.05))
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.05

    haircut_usd = gross_usd * pct
    return (float(gross_usd), float(haircut_usd))


def flexibility_penalty(
    refundable: Any,
    raw_total_usd: float,
    pct: float = 0.05,
) -> float:
    """Non-refundable rates carry real downside risk; we tax 5% as a flexibility premium.

    Only False (explicitly non-refundable) triggers the penalty. True and None
    (unknown) both return 0.0 — we don't punish missing data.
    """
    if refundable is not False:
        return 0.0
    try:
        raw = float(raw_total_usd)
    except (TypeError, ValueError):
        return 0.0
    try:
        p = float(pct)
    except (TypeError, ValueError):
        p = 0.05
    return p * raw


__all__ = [
    "value_points",
    "value_free_night",
    "value_fhr",
    "flexibility_penalty",
]
