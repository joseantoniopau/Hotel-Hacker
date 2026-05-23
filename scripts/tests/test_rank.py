"""
test_rank.py — unit tests for rank.rank_hotels and related helpers.

Covers:
  - Empty input -> [].
  - Pinned sort order over four refundable hotels at $500/$502/$510/$600.
  - $5 tiebreaker preferring refundable when two hotels tie at $500 effective.
  - top-N truncation via the CLI helper (we run rank_hotels and slice).
  - FHR input applied: a record with an FHR paste reorders past raw price.
  - score_rank is 1..N after sort.
  - All output records carry a non-empty explanation string with '$'.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(
    hotel_id: str,
    name: str,
    total_usd: float,
    *,
    refundable: bool = True,
    nights: int = 3,
    nightly: float | None = None,
    currency_local: str = "USD",
    brand: str = "independent",
) -> Dict[str, Any]:
    """Build a minimal-but-valid normalized hotel record for tests."""
    if nightly is None:
        nightly = total_usd / max(1, nights)
    return {
        "hotel_id": hotel_id,
        "name": name,
        "brand": brand,
        "location": {"city": "Testville", "country": "US"},
        "check_in": "2026-08-01",
        "check_out": "2026-08-04",
        "nights": nights,
        "guests": 2,
        "currency_local": currency_local,
        "currency_query": "USD",
        "nightly_rate_query_ccy": nightly,
        "total_after_fees_query_ccy": total_usd,
        "taxes_fees_query_ccy": 0.0,
        "nightly_rate_usd": nightly,
        "total_after_fees_usd": total_usd,
        "fees_breakdown": {},
        "refundable": refundable,
        "refund_deadline": "2026-07-30" if refundable else None,
        "rate_type": "best_flexible" if refundable else "non_refundable",
        "points_eligible": None,
        "free_night_eligible": None,
        "source": "serpapi",
        "fetched_at": "2026-05-23T12:00:00Z",
        "cache_hit": False,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# Basic shape & empty-input behaviour
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty_list(valuations, loyalty_programs,
                                        fhr_perk_values, perk_rules):
    from rank import rank_hotels
    out = rank_hotels(
        hotels=[],
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    assert out == []


def test_none_balances_is_accepted(valuations, loyalty_programs,
                                   fhr_perk_values, perk_rules):
    """None balances must be tolerated — points value falls to 0."""
    from rank import rank_hotels
    out = rank_hotels(
        hotels=[_h("a", "Alpha", 500.0)],
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    assert len(out) == 1
    assert out[0]["normalized"]["hotel_id"] == "a"
    assert out[0]["breakdown"]["points_value_usd"] == 0


# ---------------------------------------------------------------------------
# Pinned sort order — four refundable hotels at different prices
# ---------------------------------------------------------------------------

def test_pinned_sort_order_refundable(valuations, loyalty_programs,
                                      fhr_perk_values, perk_rules):
    from rank import rank_hotels
    # All refundable -> tiebreaker_priority is moot; effective_usd dominates.
    # Each hotel here also has currency_local == currency_query so currency_arb
    # is 0 — keeps effective == raw.
    hotels = [
        _h("c", "Cheap",   500.0),
        _h("b", "Bit More", 502.0),
        _h("d", "Mid",     510.0),
        _h("a", "Pricey",  600.0),
    ]
    out = rank_hotels(
        hotels=hotels,
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    ids = [r["normalized"]["hotel_id"] for r in out]
    # $500 and $502 are within the $5 tiebreaker band -> they share a bucket
    # and the tiebreaker order is moot (both refundable / neither FHR / neither
    # points). Within-bucket sort falls back to effective ascending, so c < b.
    # $510 is also within $5 of $502 but +$8 from $500 -> different bucket if
    # threshold is exactly $5 (integer floor on 500/5=100 vs 510/5=102).
    assert ids == ["c", "b", "d", "a"]
    assert [r["score_rank"] for r in out] == [1, 2, 3, 4]


def test_top_n_truncation(valuations, loyalty_programs,
                          fhr_perk_values, perk_rules):
    """When the caller asks for fewer than the full set, only top N is kept."""
    from rank import rank_hotels
    hotels = [_h(f"h{i}", f"Hotel {i}", 100.0 + i * 50.0) for i in range(8)]
    out = rank_hotels(
        hotels=hotels,
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    # rank_hotels returns ALL; CLI does the truncation. Verify caller can slice.
    assert len(out) == 8
    assert [r["normalized"]["hotel_id"] for r in out][:3] == ["h0", "h1", "h2"]


# ---------------------------------------------------------------------------
# Tiebreaker — refundable wins inside the $5 band
# ---------------------------------------------------------------------------

def test_refundable_wins_tiebreaker(valuations, loyalty_programs,
                                    fhr_perk_values, perk_rules):
    """Two hotels at $500 effective — the refundable one must rank first."""
    from rank import rank_hotels
    # Hotel A is refundable cash ($500 raw, refundable -> no penalty).
    # Hotel B is non-refundable at $500 raw -> +5% penalty = $525 effective.
    # That's a $25 gap -> the band would not even trigger. To force a true tie
    # we set B's raw to $476.19 so 1.05 * 476.19 ≈ $500.00.
    a = _h("a", "Refundable", 500.0, refundable=True)
    b = _h("b", "Non-refundable", 476.19, refundable=False)
    out = rank_hotels(
        hotels=[b, a],  # input order is non-refundable first to prove stable sort
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    ids = [r["normalized"]["hotel_id"] for r in out]
    # Both land in the same $5 bucket; tiebreaker_priority puts refundable first.
    assert ids[0] == "a", (
        f"Expected refundable 'a' first inside the $5 band, got {ids}. "
        f"effective: {[r['effective_usd'] for r in out]}"
    )


def test_score_rank_is_one_indexed(valuations, loyalty_programs,
                                   fhr_perk_values, perk_rules):
    from rank import rank_hotels
    hotels = [_h("x", "X", 700.0), _h("y", "Y", 300.0), _h("z", "Z", 400.0)]
    out = rank_hotels(
        hotels=hotels,
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    assert [r["score_rank"] for r in out] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Explanation string format
# ---------------------------------------------------------------------------

def test_explanation_nonempty_and_has_dollar_sign(valuations, loyalty_programs,
                                                  fhr_perk_values, perk_rules):
    from rank import rank_hotels
    hotels = [_h("a", "Alpha", 500.0), _h("b", "Beta", 600.0)]
    out = rank_hotels(
        hotels=hotels,
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    for r in out:
        exp = r.get("explanation", "")
        assert isinstance(exp, str) and exp.strip(), f"empty explanation: {r}"
        assert "$" in exp, f"explanation missing '$': {exp!r}"
        assert "=" in exp, f"explanation missing '=': {exp!r}"


# ---------------------------------------------------------------------------
# FHR input applied
# ---------------------------------------------------------------------------

def test_fhr_input_reduces_effective_cost(valuations, loyalty_programs,
                                          fhr_perk_values, perk_rules):
    """A property with an FHR paste should rank ahead of a slightly cheaper one."""
    from rank import rank_hotels
    # Park Hyatt at $840 raw with $100 F&B credit + breakfast ($60) ~ $160 perks.
    # In JPY folio the haircut is 5% -> net $152. Effective should drop to ~$688.
    # A competitor at $700 raw with no perks should now lose.
    fhr_hotel = _h("ph", "Park Hyatt", 840.0, refundable=True,
                   currency_local="JPY", brand="Park Hyatt")
    plain = _h("pp", "Plain Place", 700.0, refundable=True)
    fhr_inputs = [{
        "property_token": "ph",
        "paste_rate_usd": 840.0,
        "applicable_offer_credit_usd": 100.0,
        "perks": {"fb_credit": True, "breakfast": True},
    }]
    balances = {"cards": ["Amex Platinum"], "programs": {}, "currencies": {}}
    out = rank_hotels(
        hotels=[plain, fhr_hotel],
        balances=balances,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
        fhr_inputs=fhr_inputs,
    )
    ids = [r["normalized"]["hotel_id"] for r in out]
    assert ids[0] == "ph", (
        f"FHR-paste hotel should rank first; got {ids} with "
        f"effective={[r['effective_usd'] for r in out]}"
    )
    top = out[0]
    assert top["breakdown"]["fhr_value_usd"] > 0
    assert "FHR" in top["badges"]
    assert top["recommended_channel"] == "fhr"


def test_fhr_skipped_without_eligible_card(valuations, loyalty_programs,
                                           fhr_perk_values, perk_rules):
    """No Amex Platinum -> FHR value never applies even if pasted."""
    from rank import rank_hotels
    fhr_hotel = _h("ph", "Park Hyatt", 840.0, currency_local="JPY",
                   brand="Park Hyatt")
    fhr_inputs = [{
        "property_token": "ph",
        "paste_rate_usd": 840.0,
        "applicable_offer_credit_usd": 100.0,
        "perks": {"fb_credit": True, "breakfast": True},
    }]
    balances = {"cards": ["Capital One Venture X"], "programs": {}, "currencies": {}}
    out = rank_hotels(
        hotels=[fhr_hotel],
        balances=balances,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
        fhr_inputs=fhr_inputs,
    )
    assert out[0]["breakdown"]["fhr_value_usd"] == 0
    assert "FHR" not in out[0]["badges"]


# ---------------------------------------------------------------------------
# Defensive — bogus inputs do not crash
# ---------------------------------------------------------------------------

def test_non_dict_items_are_skipped(valuations, loyalty_programs,
                                    fhr_perk_values, perk_rules):
    from rank import rank_hotels
    out = rank_hotels(
        hotels=[None, "not a hotel", 42, _h("ok", "OK", 100.0)],
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    assert len(out) == 1
    assert out[0]["normalized"]["hotel_id"] == "ok"


def test_breakdown_keys_are_complete(valuations, loyalty_programs,
                                     fhr_perk_values, perk_rules):
    from rank import rank_hotels
    out = rank_hotels(
        hotels=[_h("a", "A", 250.0)],
        balances=None,
        valuations=valuations,
        loyalty_programs=loyalty_programs,
        fhr_perk_values=fhr_perk_values,
        perk_rules=perk_rules,
    )
    bk = out[0]["breakdown"]
    expected = {
        "raw_total_usd", "points_value_usd", "free_night_value_usd",
        "fhr_value_usd", "fhr_haircut_usd", "flexibility_penalty_usd",
        "currency_arb_usd",
    }
    assert expected <= set(bk.keys())
