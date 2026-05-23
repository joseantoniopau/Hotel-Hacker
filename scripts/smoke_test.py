"""
smoke_test.py — three-phase end-to-end check for the hotel-hacker pipeline.

Phases:
  [1/3] golden       — pinned fixtures + rank_hotels, deterministic asserts.
  [2/3] resilience   — edge-case records survive ranking without exceptions.
  [3/3] live         — optional live SerpApi → rank.py round-trip
                       (skipped unless SMOKE_LIVE=1 AND SERPAPI_KEY is set).

Exit code 0 on PASS, non-zero on FAIL. Prints one human-readable line per
assertion so failures are easy to diagnose without rerunning under -v.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
FIXTURES = HERE / "tests" / "fixtures"
DATA_DIR = REPO_ROOT / "data"

# Make `scripts/` importable so `from rank import ...` works regardless of cwd.
for p in (str(HERE), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

_PASS_COUNT = 0
_FAIL_COUNT = 0


def _ok(msg: str) -> None:
    global _PASS_COUNT
    _PASS_COUNT += 1
    print(f"  PASS  {msg}")


def _fail(msg: str) -> None:
    global _FAIL_COUNT
    _FAIL_COUNT += 1
    print(f"  FAIL  {msg}")


def _info(msg: str) -> None:
    print(f"        {msg}")


def _assert(cond: bool, msg: str) -> None:
    if cond:
        _ok(msg)
    else:
        _fail(msg)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Phase 1 — golden
# ---------------------------------------------------------------------------

def phase_golden() -> None:
    """Run rank_hotels against pinned fixtures and assert top pick + format."""
    print("[1/3] golden")

    try:
        from rank import rank_hotels  # type: ignore
    except Exception as e:
        _fail(f"could not import rank.rank_hotels: {e}")
        return

    try:
        hotels = _load_json(FIXTURES / "sample_hotels.json")
        balances = _load_json(FIXTURES / "sample_balances.json")
        valuations = _load_json(DATA_DIR / "points_valuations.json")
        loyalty_programs = _load_json(DATA_DIR / "loyalty_programs.json")
        fhr_perk_values = _load_json(DATA_DIR / "fhr_perk_values.json")
        perk_rules = _load_json(DATA_DIR / "perk_rules.json")
    except Exception as e:
        _fail(f"could not load fixtures or data files: {e}")
        return

    try:
        ranked = rank_hotels(
            hotels=hotels,
            balances=balances,
            valuations=valuations,
            loyalty_programs=loyalty_programs,
            fhr_perk_values=fhr_perk_values,
            perk_rules=perk_rules,
            fhr_inputs=None,
        )
    except Exception as e:
        _fail(f"rank_hotels raised: {e}")
        return

    _assert(len(ranked) == len(hotels),
            f"ranked length matches input ({len(ranked)} == {len(hotels)})")

    if not ranked:
        return

    top = ranked[0]
    name = top.get("normalized", {}).get("name", "")
    eff = top.get("effective_usd")

    # Andaz Paris Opera is a Cat-6 World-of-Hyatt redemption at 25k/night for
    # 3 nights. With 120k WoH points on hand (sample_balances) and a 1.7 cpp
    # floor, the points value is 25_000 * 3 * 1.7 / 100 = $1,275 — leaving
    # effective_usd = $1,380 raw - $1,275 points = $105. That beats every
    # cash-only competitor in sample_hotels.json, including the cheapest cash
    # rate (Casa Oaxaca at $495 raw + $24.75 flex penalty = $519.75).
    expected_top = "Andaz Paris Opera"
    expected_eff = 1380.0 - (25_000 * 3 * 1.7 / 100.0)  # = $105.00
    _info(f"top pick: {name}  effective_usd={eff}")
    _assert(name == expected_top,
            f"top pick is '{expected_top}' (got '{name}')")
    if isinstance(eff, (int, float)):
        _assert(abs(eff - expected_eff) <= 1.0,
                f"top effective_usd within $1 of ${expected_eff:.2f} (got {eff})")
    else:
        _fail(f"top effective_usd is not a number: {eff!r}")

    # Each record must carry a non-empty explanation containing a $ sign.
    bad = [r for r in ranked
           if not isinstance(r.get("explanation"), str)
           or "$" not in r["explanation"]
           or not r["explanation"].strip()]
    _assert(not bad,
            f"all {len(ranked)} explanations are non-empty and contain '$'")

    # Score ranks must be strictly 1..N.
    ranks = [r.get("score_rank") for r in ranked]
    _assert(ranks == list(range(1, len(ranked) + 1)),
            "score_rank is 1..N in order")

    # effective_usd should be non-decreasing modulo the $5 tiebreaker band.
    threshold = float(perk_rules.get("tiebreaker_threshold_usd", 5))
    violation = None
    for a, b in zip(ranked, ranked[1:]):
        ea, eb = a.get("effective_usd", 0), b.get("effective_usd", 0)
        if eb < ea - threshold:
            violation = (ea, eb)
            break
    _assert(violation is None,
            f"effective_usd is monotonic within ${threshold:.0f} tiebreaker band")


# ---------------------------------------------------------------------------
# Phase 2 — resilience
# ---------------------------------------------------------------------------

def phase_resilience() -> None:
    """Feed garbled / null-field records and assert no crashes + valid numbers.

    Sentinel policy: rank.py must always return a finite number for
    effective_usd (raw_total falls back to 0.0 when missing). Any non-finite
    value is treated as a failure.
    """
    print("[2/3] resilience")

    try:
        from rank import rank_hotels  # type: ignore
    except Exception as e:
        _fail(f"could not import rank.rank_hotels: {e}")
        return

    try:
        edge = _load_json(FIXTURES / "edge_cases.json")
        valuations = _load_json(DATA_DIR / "points_valuations.json")
        loyalty_programs = _load_json(DATA_DIR / "loyalty_programs.json")
        fhr_perk_values = _load_json(DATA_DIR / "fhr_perk_values.json")
        perk_rules = _load_json(DATA_DIR / "perk_rules.json")
    except Exception as e:
        _fail(f"could not load fixtures or data files: {e}")
        return

    try:
        ranked = rank_hotels(
            hotels=edge,
            balances=None,
            valuations=valuations,
            loyalty_programs=loyalty_programs,
            fhr_perk_values=fhr_perk_values,
            perk_rules=perk_rules,
            fhr_inputs=None,
        )
    except Exception as e:
        _fail(f"rank_hotels raised on edge_cases: {e}")
        return

    _assert(len(ranked) == len(edge),
            f"edge-case ranked length matches input ({len(ranked)} == {len(edge)})")

    bad = []
    for r in ranked:
        eff = r.get("effective_usd")
        if not isinstance(eff, (int, float)) or not math.isfinite(eff):
            bad.append(r.get("normalized", {}).get("hotel_id", "?"))
    _assert(not bad,
            f"all edge records have finite numeric effective_usd "
            f"(bad: {bad if bad else 'none'})")


# ---------------------------------------------------------------------------
# Phase 3 — live (optional)
# ---------------------------------------------------------------------------

def phase_live() -> None:
    """Optionally hit the live SerpApi pipeline via search_hotels.py | rank.py."""
    print("[3/3] live")

    if os.environ.get("SMOKE_LIVE") != "1":
        _info("SMOKE_LIVE != 1 — skipping live phase.")
        return
    if not os.environ.get("SERPAPI_KEY"):
        # Also check .env in repo root before declaring it unset.
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text().splitlines():
                    if line.strip().startswith("SERPAPI_KEY"):
                        break
                else:
                    _info("SERPAPI_KEY not in env or .env — skipping live phase.")
                    return
            except Exception:
                _info("SERPAPI_KEY not set — skipping live phase.")
                return
        else:
            _info("SERPAPI_KEY not set — skipping live phase.")
            return

    search_script = HERE / "search_hotels.py"
    if not search_script.exists():
        _info("scripts/search_hotels.py missing — skipping live phase.")
        return

    today = dt.date.today()
    check_in = (today + dt.timedelta(days=60)).isoformat()
    check_out = (today + dt.timedelta(days=63)).isoformat()

    cmd_search = [
        sys.executable, str(search_script),
        "--q", "Tokyo",
        "--check-in", check_in,
        "--check-out", check_out,
        "--adults", "2",
        "--currency", "USD",
    ]
    cmd_rank = [sys.executable, str(HERE / "rank.py"), "--top", "5"]

    try:
        search_proc = subprocess.run(
            cmd_search, capture_output=True, text=True, timeout=60, check=False
        )
    except Exception as e:
        _fail(f"search_hotels.py launch failed: {e}")
        return
    if search_proc.returncode != 0:
        _fail(f"search_hotels.py exited {search_proc.returncode}: "
              f"{search_proc.stderr[:200]}")
        return

    try:
        rank_proc = subprocess.run(
            cmd_rank, input=search_proc.stdout,
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception as e:
        _fail(f"rank.py launch failed: {e}")
        return
    if rank_proc.returncode != 0:
        _fail(f"rank.py exited {rank_proc.returncode}: {rank_proc.stderr[:200]}")
        return

    try:
        ranked = json.loads(rank_proc.stdout)
    except json.JSONDecodeError as e:
        _fail(f"rank.py stdout was not JSON: {e}")
        return

    _assert(isinstance(ranked, list) and len(ranked) >= 3,
            f"live pipeline returned >= 3 records (got {len(ranked) if isinstance(ranked, list) else 'n/a'})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    phase_golden()
    phase_resilience()
    phase_live()
    print("")
    print(f"summary: {_PASS_COUNT} passed, {_FAIL_COUNT} failed")
    if _FAIL_COUNT:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
