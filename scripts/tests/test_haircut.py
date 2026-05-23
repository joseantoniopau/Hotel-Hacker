"""
test_haircut.py — pinned haircut percentages from data/fhr_perk_values.json.

Asserts the canonical FHR folio-currency haircut table:
  USD = 0%, EUR = 6%, GBP = 6%, JPY = 5%, MXN = 4%, AED = 3%,
  unknown -> _default 5%.

These values are loaded from data/fhr_perk_values.json via the conftest
fixture so any future tweak to the data file must update these tests.
"""

from __future__ import annotations

import math

import pytest


def _haircut_pct(fhr_perk_values: dict, currency: str) -> float:
    """Mirror the lookup rank.py / value.py performs on the data table."""
    meta = (fhr_perk_values or {}).get("_meta") or {}
    haircuts = meta.get("regional_haircut_pct") or {}
    if currency in haircuts:
        return float(haircuts[currency])
    return float(haircuts.get("_default", 0.0))


@pytest.mark.parametrize("ccy,expected_pct", [
    ("USD", 0.00),
    ("EUR", 0.06),
    ("GBP", 0.06),
    ("JPY", 0.05),
    ("MXN", 0.04),
    ("AED", 0.03),
])
def test_known_haircut_percentages(fhr_perk_values, ccy, expected_pct):
    actual = _haircut_pct(fhr_perk_values, ccy)
    assert math.isclose(actual, expected_pct, abs_tol=1e-9), (
        f"{ccy}: expected {expected_pct:.4f}, got {actual:.4f}"
    )


def test_unknown_currency_uses_default(fhr_perk_values):
    """An unknown ISO code should fall back to the _default entry (5%)."""
    actual = _haircut_pct(fhr_perk_values, "ZZZ")
    assert math.isclose(actual, 0.05, abs_tol=1e-9), (
        f"_default expected 0.05, got {actual:.4f}"
    )


def test_haircut_pct_table_has_default_key(fhr_perk_values):
    """Schema sanity: the table must always have a _default entry."""
    meta = fhr_perk_values.get("_meta") or {}
    haircuts = meta.get("regional_haircut_pct") or {}
    assert "_default" in haircuts


# ---------------------------------------------------------------------------
# When value.py exposes a regional_haircut helper, ensure it agrees with the
# table. We import lazily so the test file remains importable while Agent C
# is still wiring up value.py.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ccy,expected_pct", [
    ("USD", 0.00),
    ("EUR", 0.06),
    ("GBP", 0.06),
    ("JPY", 0.05),
    ("MXN", 0.04),
    ("AED", 0.03),
    ("ZZZ", 0.05),  # default
])
def test_value_regional_haircut_helper_matches_table(
    fhr_perk_values, ccy, expected_pct
):
    """If value.py exposes regional_haircut(), it must match the data file."""
    try:
        from value import regional_haircut  # type: ignore
    except ImportError:
        pytest.skip("value.regional_haircut not exported")
    actual = regional_haircut(ccy, fhr_perk_values)
    assert math.isclose(actual, expected_pct, abs_tol=1e-9), (
        f"{ccy}: expected {expected_pct:.4f}, got {actual:.4f}"
    )
