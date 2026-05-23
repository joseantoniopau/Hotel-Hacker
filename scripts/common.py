"""
common.py — shared primitives for the hotel-hacker scripts package.

Responsibilities:
  - Repo path resolution.
  - .env loading (NEVER prints values).
  - Static data loading from data/*.json with friendly errors.
  - On-disk SHA256-keyed JSON cache with TTL.
  - account.json bookkeeping (SerpApi quota tracking).
  - Structured JSONL event logging with secret redaction.
  - Pydantic models for the normalized + ranked hotel record schemas.

Everything here is designed to degrade gracefully — missing files, missing
fields, and partial data should never crash a search.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = REPO_ROOT / "data"
CACHE_DIR: Path = REPO_ROOT / "cache"
ACCOUNT_PATH: Path = REPO_ROOT / "account.json"
ENV_PATH: Path = REPO_ROOT / ".env"
EVENTS_LOG: Path = CACHE_DIR / "events.log"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FriendlyError(Exception):
    """An error with a layperson-readable message in `.human_message`.

    Raise this whenever a missing config / file / network problem should be
    surfaced to the user in plain English instead of a stack trace.
    """

    def __init__(self, human_message: str, *args: Any) -> None:
        super().__init__(human_message, *args)
        self.human_message = human_message


# ---------------------------------------------------------------------------
# .env loader (never logs values)
# ---------------------------------------------------------------------------

def load_env() -> Dict[str, str]:
    """Parse `.env` at repo root into a dict. Returns {} if the file is missing.

    Format: KEY=VALUE per line; blank lines and `# ...` comments ignored.
    Values may be optionally wrapped in single or double quotes.
    This function NEVER prints values.
    """
    env: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    try:
        text = ENV_PATH.read_text(encoding="utf-8")
    except Exception:
        return env
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key:
            env[key] = value
    return env


# ---------------------------------------------------------------------------
# Static data loader
# ---------------------------------------------------------------------------

def load_data(name: str) -> dict:
    """Load `data/<name>.json` as a dict; raise FriendlyError if missing/broken.

    `name` may be passed with or without the trailing `.json`.
    """
    stem = name[:-5] if name.endswith(".json") else name
    path = DATA_DIR / f"{stem}.json"
    if not path.exists():
        raise FriendlyError(
            f"Missing settings file: {path.name}. "
            f"Make sure the data/ folder contains {path.name} — try re-running install.sh."
        )
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise FriendlyError(
            f"The settings file {path.name} has a formatting error "
            f"(line {e.lineno}). Try restoring it from the example file."
        )
    except Exception as e:
        raise FriendlyError(
            f"Could not read settings file {path.name}: {e}"
        )
    if not isinstance(data, dict):
        raise FriendlyError(
            f"Settings file {path.name} should contain a JSON object at the top level."
        )
    return data


# ---------------------------------------------------------------------------
# Cache — sha256 key, TTL stored in payload
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Best effort — caller will see the failure on write.
        pass


def cache_key(*parts: Any) -> str:
    """sha256 of pipe-joined string parts. Order-sensitive."""
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def cache_get(key: str) -> Optional[dict]:
    """Return cached `data` payload if present and not expired, else None.

    Expiry uses file mtime + the `_meta.ttl_hours` stored inside the payload.
    Any read/parse error is treated as a cache miss (returns None).
    """
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    meta = payload.get("_meta") or {}
    ttl_hours = meta.get("ttl_hours")
    try:
        ttl_seconds = float(ttl_hours) * 3600.0
    except (TypeError, ValueError):
        # No TTL — treat as already-expired to be safe.
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if (time.time() - mtime) > ttl_seconds:
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        if set(data.keys()) == {"value"}:
            return data["value"]
        return data
    return data


def cache_put(key: str, value: dict, ttl_hours: int = 24) -> None:
    """Write `value` under cache `key` with the given TTL.

    Payload shape: {"_meta": {"ttl_hours": N, "stored_at": <iso>}, "data": value}
    Best effort — write failures are swallowed (logged via log_event upstream).
    """
    _ensure_cache_dir()
    path = _cache_path(key)
    payload = {
        "_meta": {
            "ttl_hours": ttl_hours,
            "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "data": value if isinstance(value, dict) else {"value": value},
    }
    try:
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        # Cache is non-critical; do not raise.
        pass


# ---------------------------------------------------------------------------
# account.json — SerpApi quota tracking
# ---------------------------------------------------------------------------

_ACCOUNT_DEFAULT: Dict[str, Any] = {
    "searches_used_this_month": 0,
    "searches_remaining": 250,
    "plan_searches_left": 250,
    "last_checked": None,
}


def account_load() -> dict:
    """Load account.json, returning sensible defaults if missing or broken."""
    if not ACCOUNT_PATH.exists():
        return dict(_ACCOUNT_DEFAULT)
    try:
        with ACCOUNT_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(_ACCOUNT_DEFAULT)
        merged = dict(_ACCOUNT_DEFAULT)
        merged.update(data)
        return merged
    except Exception:
        return dict(_ACCOUNT_DEFAULT)


def account_save(d: dict) -> None:
    """Write account.json atomically. Silently ignores write errors."""
    if not isinstance(d, dict):
        return
    try:
        tmp = ACCOUNT_PATH.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ACCOUNT_PATH)
    except Exception:
        pass


def account_decrement(n: int = 1) -> None:
    """Decrement the remaining-search counter by `n` and bump used-count."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    d = account_load()
    remaining = d.get("searches_remaining", 250)
    used = d.get("searches_used_this_month", 0)
    try:
        d["searches_remaining"] = max(0, int(remaining) - n)
    except (TypeError, ValueError):
        d["searches_remaining"] = max(0, 250 - n)
    try:
        d["searches_used_this_month"] = int(used) + n
    except (TypeError, ValueError):
        d["searches_used_this_month"] = n
    account_save(d)


def account_remaining() -> int:
    """Return the current `searches_remaining` value, default 250."""
    d = account_load()
    val = d.get("searches_remaining", 250)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 250


# ---------------------------------------------------------------------------
# Event log (JSONL, secret-redacted)
# ---------------------------------------------------------------------------

_REDACT_PATTERN = re.compile(r"^SERPAPI_KEY$|api_key|token|password", re.IGNORECASE)


def _redact_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(k, str) and _REDACT_PATTERN.search(k):
            safe[k] = "***"
        else:
            safe[k] = v
    return safe


def log_event(kind: str, **fields: Any) -> None:
    """Append a JSONL event line to cache/events.log.

    Any field whose key matches SERPAPI_KEY / api_key / token / password is
    redacted to "***" before writing. Errors are swallowed so logging never
    breaks the calling code path.
    """
    _ensure_cache_dir()
    safe_fields = _redact_fields(fields)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        **safe_fields,
    }
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
    except Exception:
        try:
            line = json.dumps(
                {"ts": record["ts"], "kind": kind, "_warn": "unserializable fields"},
                ensure_ascii=False,
            )
        except Exception:
            return
    try:
        with EVENTS_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pydantic models — normalized + ranked hotel records
# ---------------------------------------------------------------------------

class HotelLocation(BaseModel):
    """Sub-record for hotel geography. All fields optional/defaulted."""

    city: str = ""
    country: str = ""           # ISO-2 (e.g. "US", "MX")
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None


class FeesBreakdown(BaseModel):
    """Sub-record breaking out common itemized fees in USD."""

    resort_fee_usd: Optional[float] = None
    parking_usd: Optional[float] = None
    wifi_usd: Optional[float] = None
    other_usd: Optional[float] = None


class PointsEligible(BaseModel):
    """Optional eligibility info for a points redemption on this stay."""

    program: Optional[str] = None
    points_per_night: Optional[int] = None
    cents_per_point: Optional[float] = None
    award_chart_category: Optional[str] = None


class FreeNightEligible(BaseModel):
    """Optional eligibility info for a free-night perk (5th-free, 4th-free)."""

    program: Optional[str] = None
    rule: Optional[str] = None
    threshold_nights: Optional[int] = None
    qualifies: bool = False


class NormalizedHotel(BaseModel):
    """Normalized hotel record — the canonical shape after search/details.

    All numeric fields default to 0 / None so missing API data never crashes
    downstream consumers (rank.py, the UI, tests).
    """

    hotel_id: str = ""
    name: str = ""
    brand: Optional[str] = None
    location: HotelLocation = Field(default_factory=HotelLocation)

    check_in: str = ""           # YYYY-MM-DD
    check_out: str = ""          # YYYY-MM-DD
    nights: int = 0
    guests: int = 1

    currency_local: str = "USD"
    currency_query: str = "USD"

    nightly_rate_query_ccy: float = 0.0
    total_after_fees_query_ccy: float = 0.0
    taxes_fees_query_ccy: float = 0.0

    nightly_rate_usd: float = 0.0
    total_after_fees_usd: float = 0.0

    fees_breakdown: FeesBreakdown = Field(default_factory=FeesBreakdown)

    refundable: Optional[bool] = None
    refund_deadline: Optional[str] = None
    rate_type: str = ""

    points_eligible: Optional[PointsEligible] = None
    free_night_eligible: Optional[FreeNightEligible] = None

    source: str = "serpapi"
    source_url: Optional[str] = None
    fetched_at: str = ""
    cache_hit: bool = False

    raw: Dict[str, Any] = Field(default_factory=dict)


class RankBreakdown(BaseModel):
    """Itemized breakdown of effective_cost_usd. All components default to 0."""

    raw_total_usd: float = 0.0
    points_value_usd: float = 0.0
    free_night_value_usd: float = 0.0
    fhr_value_usd: float = 0.0
    fhr_haircut_usd: float = 0.0
    flexibility_penalty_usd: float = 0.0
    currency_arb_usd: float = 0.0


class RankedRecord(BaseModel):
    """A NormalizedHotel + ranking breakdown, channel recommendation, badges."""

    normalized: NormalizedHotel = Field(default_factory=NormalizedHotel)
    raw_usd: float = 0.0
    effective_usd: float = 0.0
    breakdown: RankBreakdown = Field(default_factory=RankBreakdown)

    recommended_channel: str = "direct"   # direct | fhr | ota | points-portal
    channel_reason: str = ""
    badges: List[str] = Field(default_factory=list)
    explanation: str = ""
    score_rank: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # paths
    "REPO_ROOT",
    "DATA_DIR",
    "CACHE_DIR",
    "ACCOUNT_PATH",
    "ENV_PATH",
    "EVENTS_LOG",
    # errors
    "FriendlyError",
    # env / data / cache / account / log
    "load_env",
    "load_data",
    "cache_key",
    "cache_get",
    "cache_put",
    "account_load",
    "account_save",
    "account_decrement",
    "account_remaining",
    "log_event",
    # models
    "HotelLocation",
    "FeesBreakdown",
    "PointsEligible",
    "FreeNightEligible",
    "NormalizedHotel",
    "RankBreakdown",
    "RankedRecord",
]
