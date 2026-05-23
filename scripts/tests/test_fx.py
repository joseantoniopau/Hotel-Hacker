"""
test_fx.py — unit tests for fx.fetch_rates / fx.convert / fx.currency_arbitrage.

We inject a fake `http_get` into fetch_rates so tests are deterministic and
never hit the network. Pure helpers (convert, get_rate, currency_arbitrage)
all accept an explicit `rates=` dict so we can bypass the fetcher entirely.
"""

from __future__ import annotations

import math

import pytest


# Pinned reference rates (units per USD). Realistic 2026-ish numbers.
_FIXTURE_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 156.0,
    "MXN": 17.0,
    "AED": 3.67,
    "CAD": 1.36,
}


class _FakeResponse:
    """Minimal duck-type for fx.fetch_rates' `resp.json()` path."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_http_get_ok(url, timeout=None):
    return _FakeResponse({"rates": dict(_FIXTURE_RATES), "base": "USD"})


def _fake_http_get_boom(url, timeout=None):
    raise RuntimeError("network down")


# ---------------------------------------------------------------------------
# convert() — pure, takes explicit rates= dict
# ---------------------------------------------------------------------------

def test_convert_usd_to_usd_is_identity():
    from fx import convert
    assert convert(100.0, "USD", "USD") == 100.0


def test_convert_eur_to_usd_math():
    from fx import convert
    out = convert(100.0, "EUR", "USD", rates=_FIXTURE_RATES)
    # 100 EUR / 0.92 EUR-per-USD ≈ $108.70
    assert math.isclose(out, 100.0 / 0.92, rel_tol=1e-9)


def test_convert_jpy_to_usd_math():
    from fx import convert
    out = convert(10_000.0, "JPY", "USD", rates=_FIXTURE_RATES)
    # 10,000 JPY / 156 ≈ $64.10
    assert math.isclose(out, 10_000.0 / 156.0, rel_tol=1e-9)


def test_convert_unknown_ccy_returns_amount(monkeypatch):
    """Unknown currency -> rate=1.0 -> amount unchanged (never raises)."""
    from fx import convert
    out = convert(100.0, "ZZZ", "USD", rates=_FIXTURE_RATES)
    assert out == 100.0


def test_convert_handles_bad_amount():
    from fx import convert
    # Non-numeric amount should return 0.0, not raise.
    out = convert("not-a-number", "EUR", "USD", rates=_FIXTURE_RATES)  # type: ignore[arg-type]
    assert out == 0.0


# ---------------------------------------------------------------------------
# fetch_rates() — http_get is injectable
# ---------------------------------------------------------------------------

def test_fetch_rates_uses_injected_http_get(monkeypatch, tmp_path):
    """fetch_rates must honour the injected http_get and return its payload."""
    # Redirect the on-disk cache to a tmp dir so prior runs don't interfere.
    import common  # type: ignore
    monkeypatch.setattr(common, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(common, "EVENTS_LOG", tmp_path / "events.log")
    # fx.py imports cache_get/cache_put at module-load time, so we also patch
    # those re-exports directly.
    import fx  # type: ignore
    from common import cache_get, cache_put  # type: ignore
    monkeypatch.setattr(fx, "cache_get", lambda key: None)
    monkeypatch.setattr(fx, "cache_put", lambda *a, **k: None)

    rates = fx.fetch_rates(http_get=_fake_http_get_ok)
    assert isinstance(rates, dict)
    assert math.isclose(rates["EUR"], 0.92, rel_tol=1e-9)
    assert math.isclose(rates["JPY"], 156.0, rel_tol=1e-9)


def test_fetch_rates_falls_back_when_http_raises(monkeypatch, tmp_path):
    """fetch_rates must return FALLBACK_RATES when the fetcher raises."""
    import fx  # type: ignore
    monkeypatch.setattr(fx, "cache_get", lambda key: None)
    monkeypatch.setattr(fx, "cache_put", lambda *a, **k: None)

    rates = fx.fetch_rates(http_get=_fake_http_get_boom)
    # FALLBACK_RATES contents must include USD and EUR.
    assert isinstance(rates, dict)
    assert "USD" in rates and "EUR" in rates


# ---------------------------------------------------------------------------
# currency_arbitrage()
# ---------------------------------------------------------------------------

def test_currency_arbitrage_flags_at_2_1_pct():
    """A 2.1% spread should set flag=True."""
    from fx import currency_arbitrage
    # 1000 EUR @ 0.92 -> ~$1086.96 local-in-USD. If USD quote is $1064 then
    # spread = 1086.96 - 1064 = $22.96, ~2.16% -> flag.
    res = currency_arbitrage(1000.0, "EUR", 1064.0, rates=_FIXTURE_RATES)
    assert isinstance(res, dict)
    assert res["flag"] is True
    assert abs(res["spread_pct"]) >= 0.02
    assert math.isclose(res["spread_usd"], (1000.0 / 0.92) - 1064.0, rel_tol=1e-6)


def test_currency_arbitrage_no_flag_at_1_9_pct():
    """A 1.9% spread should set flag=False."""
    from fx import currency_arbitrage
    # 1000 EUR @ 0.92 -> ~$1086.96. Target ~1.9% spread -> $1066.76.
    res = currency_arbitrage(1000.0, "EUR", 1066.76, rates=_FIXTURE_RATES)
    assert res["flag"] is False
    assert abs(res["spread_pct"]) < 0.02


def test_currency_arbitrage_same_ccy_zero():
    from fx import currency_arbitrage
    res = currency_arbitrage(500.0, "USD", 500.0, rates=_FIXTURE_RATES)
    assert math.isclose(res["spread_usd"], 0.0, abs_tol=0.01)
    assert res["flag"] is False


def test_currency_arbitrage_zero_usd_quote_safe():
    """A 0 USD quote should not divide-by-zero."""
    from fx import currency_arbitrage
    res = currency_arbitrage(1000.0, "EUR", 0.0, rates=_FIXTURE_RATES)
    assert res["spread_pct"] == 0.0
    assert res["spread_usd"] == 0.0
    assert res["flag"] is False


def test_currency_arbitrage_sign_positive_when_usd_cheaper():
    """fx convention: positive spread_usd = local-in-USD > query-USD (USD quote is cheaper)."""
    from fx import currency_arbitrage
    res = currency_arbitrage(1000.0, "EUR", 1000.0, rates=_FIXTURE_RATES)
    # 1000 EUR -> $1086.96 in local mid. USD quote is $1000 -> spread positive.
    assert res["spread_usd"] > 0
