"""
test_value.py — unit tests for the pure valuation helpers in value.py.

Covers (>=10 cases):
  - value_points: known program / unknown program fallback / zero nights
                  / zero points / bogus inputs.
  - value_free_night: Marriott 5n exact, Marriott 4n no-trigger, IHG 4n,
                     Hilton 5n, Hyatt always 0, unknown program 0.
  - value_fhr: all-perks USD vs EUR haircut math; empty perks;
              unknown currency uses _default haircut.
  - flexibility_penalty: refundable True / False / None / "maybe".

Pinned to data/*.json defaults via conftest fixtures so any future tweak to
the data table must update these tests.
"""

from __future__ import annotations

import math

import pytest


# ---------------------------------------------------------------------------
# value_points — signature: (program, points_per_night, nights, valuations)
# ---------------------------------------------------------------------------

def test_value_points_known_program(valuations):
    from value import value_points
    # Marriott Bonvoy floor cpp = 0.8 -> 60k * 5 * 0.8 / 100 = $2,400.
    out = value_points("Marriott Bonvoy", 60_000, 5, valuations)
    assert math.isclose(out, 2400.0, abs_tol=0.01)


def test_value_points_hyatt_floor(valuations):
    from value import value_points
    # World of Hyatt floor cpp = 1.7 -> 25k * 3 * 1.7 / 100 = $1,275.
    out = value_points("World of Hyatt", 25_000, 3, valuations)
    assert math.isclose(out, 1275.0, abs_tol=0.01)


def test_value_points_unknown_program_uses_conservative_floor(valuations):
    """Unknown programs should NOT inflate value — conservative 0.5 cpp floor."""
    from value import value_points
    out = value_points("Imaginary Rewards", 10_000, 2, valuations)
    # 10_000 * 2 * 0.5 / 100 = $100 — at most this conservative amount.
    assert out <= 100.0 + 1e-6


def test_value_points_zero_nights(valuations):
    from value import value_points
    assert value_points("Marriott Bonvoy", 60_000, 0, valuations) == 0


def test_value_points_zero_points(valuations):
    from value import value_points
    assert value_points("Marriott Bonvoy", 0, 5, valuations) == 0


def test_value_points_bogus_inputs(valuations):
    from value import value_points
    out = value_points("Marriott Bonvoy", "not-a-number", 5, valuations)  # type: ignore[arg-type]
    assert out == 0


# ---------------------------------------------------------------------------
# value_free_night — signature: (program, nightly_rate_usd, nights, loyalty_programs)
# ---------------------------------------------------------------------------

def test_value_free_night_marriott_5_nights(loyalty_programs):
    from value import value_free_night
    out = value_free_night("Marriott Bonvoy", 380.0, 5, loyalty_programs)
    assert math.isclose(out, 380.0, abs_tol=0.01)


def test_value_free_night_marriott_4_nights_no_trigger(loyalty_programs):
    from value import value_free_night
    out = value_free_night("Marriott Bonvoy", 380.0, 4, loyalty_programs)
    assert out == 0


def test_value_free_night_ihg_4_nights(loyalty_programs):
    from value import value_free_night
    out = value_free_night("IHG One Rewards", 540.0, 4, loyalty_programs)
    assert math.isclose(out, 540.0, abs_tol=0.01)


def test_value_free_night_hilton_5_nights(loyalty_programs):
    from value import value_free_night
    out = value_free_night("Hilton Honors", 220.0, 5, loyalty_programs)
    assert math.isclose(out, 220.0, abs_tol=0.01)


def test_value_free_night_hyatt_always_zero(loyalty_programs):
    """Hyatt has no free-night-on-N-nights mechanic -> always 0."""
    from value import value_free_night
    for n in (1, 3, 5, 7):
        out = value_free_night("World of Hyatt", 460.0, n, loyalty_programs)
        assert out == 0, f"Hyatt should be 0 at {n} nights, got {out}"


def test_value_free_night_unknown_program_zero(loyalty_programs):
    from value import value_free_night
    assert value_free_night("Made Up Program", 200.0, 5, loyalty_programs) == 0


# ---------------------------------------------------------------------------
# value_fhr — signature: (perk_selection, fhr_perk_values, folio_currency)
# Returns (gross_usd, haircut_usd).
# ---------------------------------------------------------------------------

def test_value_fhr_all_perks_usd_zero_haircut(fhr_perk_values):
    from value import value_fhr
    # Keys must match data/fhr_perk_values.json canonical names.
    perk_selection = {
        "fb_credit_usd_property": True,
        "daily_breakfast_2pax_usd": True,
        "late_checkout_4pm_usd": True,
        "noon_check_in_usd": True,
        "room_upgrade_usd_uncertain": True,
        "complimentary_wifi_usd": True,
    }
    val, hair = value_fhr(perk_selection, fhr_perk_values, "USD")
    # 100 + 60 + 40 + 25 + 50 + 15 = 290
    assert math.isclose(val, 290.0, abs_tol=0.01)
    assert math.isclose(hair, 0.0, abs_tol=0.01)


def test_value_fhr_eur_haircut_six_pct(fhr_perk_values):
    from value import value_fhr
    perk_selection = {
        "fb_credit_usd_property": True,
        "daily_breakfast_2pax_usd": True,
    }
    val, hair = value_fhr(perk_selection, fhr_perk_values, "EUR")
    assert math.isclose(val, 160.0, abs_tol=0.01)
    assert math.isclose(hair, 160.0 * 0.06, abs_tol=0.01)


def test_value_fhr_jpy_haircut_five_pct(fhr_perk_values):
    from value import value_fhr
    perk_selection = {"fb_credit_usd_property": True}
    val, hair = value_fhr(perk_selection, fhr_perk_values, "JPY")
    assert math.isclose(val, 100.0, abs_tol=0.01)
    assert math.isclose(hair, 5.0, abs_tol=0.01)


def test_value_fhr_unknown_currency_default_haircut(fhr_perk_values):
    from value import value_fhr
    perk_selection = {"fb_credit_usd_property": True}
    val, hair = value_fhr(perk_selection, fhr_perk_values, "XYZ")
    # _default haircut is 5%.
    assert math.isclose(val, 100.0, abs_tol=0.01)
    assert math.isclose(hair, 5.0, abs_tol=0.01)


def test_value_fhr_no_perks_zero(fhr_perk_values):
    from value import value_fhr
    val, hair = value_fhr({}, fhr_perk_values, "USD")
    assert val == 0
    assert hair == 0


def test_value_fhr_unselected_perks_excluded(fhr_perk_values):
    """Only perks with truthy values count toward the total."""
    from value import value_fhr
    perk_selection = {
        "fb_credit_usd_property": True,
        "daily_breakfast_2pax_usd": False,    # not selected
        "late_checkout_4pm_usd": None,        # falsy
    }
    val, _ = value_fhr(perk_selection, fhr_perk_values, "USD")
    assert math.isclose(val, 100.0, abs_tol=0.01)


# ---------------------------------------------------------------------------
# flexibility_penalty(refundable, raw_total_usd)
# ---------------------------------------------------------------------------

def test_flexibility_penalty_refundable_zero():
    from value import flexibility_penalty
    assert flexibility_penalty(True, 1_000.0) == 0


def test_flexibility_penalty_non_refundable_five_pct():
    from value import flexibility_penalty
    assert math.isclose(
        flexibility_penalty(False, 1_000.0), 50.0, abs_tol=0.01
    )


def test_flexibility_penalty_none_zero():
    """Unknown refundability -> no penalty (presume innocent until proven non-refundable)."""
    from value import flexibility_penalty
    assert flexibility_penalty(None, 1_000.0) == 0


def test_flexibility_penalty_garbled_string_zero():
    """A garbled refundable value ('maybe') should not trigger the penalty."""
    from value import flexibility_penalty
    # value.py treats anything other than False as no-penalty.
    assert flexibility_penalty("maybe", 1_000.0) == 0
