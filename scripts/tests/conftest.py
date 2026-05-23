"""
conftest.py — shared pytest configuration for the hotel-hacker test suite.

Ensures `scripts/` is importable as a top-level package source so tests can do
`from common import ...`, `from value import ...`, `from fx import ...`,
`from rank import ...` without sys.path gymnastics.

Also exposes a handful of canonical fixtures (valuations, loyalty_programs,
fhr_perk_values, perk_rules) loaded from data/*.json so tests stay pinned to
real defaults.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# Make scripts/ importable as the top of the path so unqualified imports work.
TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
REPO_ROOT = SCRIPTS_DIR.parent
DATA_DIR = REPO_ROOT / "data"
FIXTURES_DIR = TESTS_DIR / "fixtures"

for p in (str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Data-file fixtures — loaded from data/*.json
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def valuations() -> dict:
    """data/points_valuations.json — cents per point per program."""
    return _load_json(DATA_DIR / "points_valuations.json")


@pytest.fixture(scope="session")
def loyalty_programs() -> dict:
    """data/loyalty_programs.json — free-night mechanics and stack rules."""
    return _load_json(DATA_DIR / "loyalty_programs.json")


@pytest.fixture(scope="session")
def fhr_perk_values() -> dict:
    """data/fhr_perk_values.json — FHR perk default USD valuations + haircuts."""
    return _load_json(DATA_DIR / "fhr_perk_values.json")


@pytest.fixture(scope="session")
def perk_rules() -> dict:
    """data/perk_rules.json — applicability tables (min nights, tiebreaker)."""
    return _load_json(DATA_DIR / "perk_rules.json")


@pytest.fixture(scope="session")
def fhr_eligible_brands() -> dict:
    """data/fhr_eligible_brands.json — curated FHR brand list."""
    return _load_json(DATA_DIR / "fhr_eligible_brands.json")


# ---------------------------------------------------------------------------
# Fixture-file loaders — pinned sample inputs/outputs
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_hotels() -> list:
    """tests/fixtures/sample_hotels.json — golden normalized hotel records."""
    return _load_json(FIXTURES_DIR / "sample_hotels.json")


@pytest.fixture(scope="session")
def sample_balances() -> dict:
    """tests/fixtures/sample_balances.json — realistic user balances."""
    return _load_json(FIXTURES_DIR / "sample_balances.json")


@pytest.fixture(scope="session")
def edge_cases() -> list:
    """tests/fixtures/edge_cases.json — malformed / partial records."""
    return _load_json(FIXTURES_DIR / "edge_cases.json")
