"""
server.py — FastAPI backend for the hotel-hacker brutalist UI.

Wires the UI views to the search/rank pipeline and the static data files in
/data. Runs on 127.0.0.1:8788 (sibling-distinct from flight_hacker's 8721).

Run:
    python3 ui/server.py
    # or
    python -m uvicorn ui.server:app --host 127.0.0.1 --port 8788
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import uvicorn


# ---------------------------------------------------------------------------
# Paths + module wiring
# ---------------------------------------------------------------------------

UI_DIR = Path(__file__).resolve().parent
REPO_ROOT = UI_DIR.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR = REPO_ROOT / "data"
ACCOUNT_PATH = REPO_ROOT / "account.json"
SEARCH_SCRIPT = SCRIPTS_DIR / "search_hotels.py"
USER_BAL_PATH = DATA_DIR / "user_balances.json"
USER_BAL_EXAMPLE = DATA_DIR / "user_balances.example.json"

for p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# common — always available (Agent C deliverable)
try:
    from common import log_event, load_data, account_load, load_env  # type: ignore
    _HAS_COMMON = True
except Exception as _e:
    _HAS_COMMON = False

    def log_event(kind: str, **fields: Any) -> None:  # type: ignore
        return None

    def load_data(name: str) -> dict:  # type: ignore
        path = DATA_DIR / (name if name.endswith(".json") else f"{name}.json")
        if not path.exists():
            raise FileNotFoundError(str(path))
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def account_load() -> dict:  # type: ignore
        if ACCOUNT_PATH.exists():
            try:
                return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {
            "searches_used_this_month": 0,
            "searches_remaining": 250,
            "plan_searches_left": 250,
            "last_checked": None,
        }

    def load_env() -> dict:  # type: ignore
        """Minimal .env parser fallback (no deps)."""
        env_path = REPO_ROOT / ".env"
        out: dict = {}
        if not env_path.exists():
            return out
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or \
                   (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                if k:
                    out[k] = v
        except Exception:
            return out
        return out


def _ensure_env_loaded() -> None:
    """Make sure .env values are visible via os.environ. Safe to call repeatedly."""
    try:
        env = load_env() or {}
    except Exception:
        env = {}
    for k, v in env.items():
        # Don't overwrite existing process env (operator may have already set it).
        if k and (k not in os.environ or not os.environ.get(k)):
            os.environ[k] = v


# Optional ranker — Agent E deliverable. Graceful fallback if missing.
try:
    import rank as rank_mod  # type: ignore
    _HAS_RANK = True
except Exception as _re:
    rank_mod = None  # type: ignore
    _HAS_RANK = False
    log_event("import_fallback", module="rank", error=str(_re))


# ---------------------------------------------------------------------------
# Errors helper
# ---------------------------------------------------------------------------

def _err(message: str, code: str = "internal_error", status: int = 500) -> JSONResponse:
    """Friendly error envelope: {"error": "...", "code": "..."}."""
    return JSONResponse({"error": message, "code": code}, status_code=status)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SearchBody(BaseModel):
    q: str = Field(..., min_length=1, description="Destination, e.g. 'Tokyo'")
    check_in: str = Field(..., description="YYYY-MM-DD")
    check_out: str = Field(..., description="YYYY-MM-DD")
    adults: int = Field(2, ge=1, le=8)
    currency: str = Field("USD", min_length=3, max_length=3)


class FhrInput(BaseModel):
    hotel_id: Optional[str] = None
    property_name: Optional[str] = None
    best_flexible_rate_usd: Optional[float] = None
    applicable_offer_credit_usd: Optional[float] = None
    property_currency: Optional[str] = "USD"
    perks: dict = Field(default_factory=dict)


class RankBody(BaseModel):
    hotels: list[dict] = Field(default_factory=list)
    balances: Optional[dict] = None
    fhr_inputs: Optional[list[FhrInput]] = None


class BalancesBody(BaseModel):
    currencies: dict = Field(default_factory=dict)
    programs: dict = Field(default_factory=dict)
    cards: list[str] = Field(default_factory=list)


class UpgradeEmailBody(BaseModel):
    hotel_name: str
    arrival_date: str
    status: Optional[str] = None
    special_occasion: Optional[str] = None


# ---------------------------------------------------------------------------
# Allowed data names (whitelist for /api/data/{name})
# ---------------------------------------------------------------------------

ALLOWED_DATA_NAMES = {
    "points_valuations",
    "loyalty_programs",
    "fhr_perk_values",
    "perk_rules",
    "fhr_eligible_brands",
}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="hotel-hacker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8788"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """Log each request (path + method only — no bodies, no secrets)."""
    try:
        log_event(
            "http_request",
            method=request.method,
            path=request.url.path,
        )
    except Exception:
        pass
    return await call_next(request)


# ---------------------------------------------------------------------------
# Static + index
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    """Serve index.html at root."""
    return FileResponse(UI_DIR / "index.html", media_type="text/html")


# Mount the ui/ directory for static assets (styles.css, app.js).
# Routed AFTER explicit endpoints so /api/* never collides.
app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


@app.get("/styles.css")
def styles_css() -> FileResponse:
    return FileResponse(UI_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
def app_js() -> FileResponse:
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript")


# ---------------------------------------------------------------------------
# /api/search — invoke search_hotels.py via subprocess
# ---------------------------------------------------------------------------

@app.post("/api/search")
def api_search(body: SearchBody) -> JSONResponse:
    """Run scripts/search_hotels.py and return its JSON stdout verbatim.

    The script is invoked as a subprocess so this server doesn't take a
    hard import-time dependency on Agent D's module. stdout is expected to
    be a JSON array (list) or object — we pass it through unchanged.
    """
    if not SEARCH_SCRIPT.exists():
        return _err(
            "The search helper isn't installed yet. "
            "Make sure scripts/search_hotels.py exists.",
            code="search_script_missing",
            status=503,
        )

    cmd = [
        sys.executable,
        str(SEARCH_SCRIPT),
        "--q", body.q,
        "--check-in", body.check_in,
        "--check-out", body.check_out,
        "--adults", str(body.adults),
        "--currency", body.currency,
        "--output", "json",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        log_event("search_timeout", q=body.q)
        return _err(
            "The hotel search took too long and was cancelled. "
            "Please try again in a moment.",
            code="timeout",
            status=504,
        )
    except Exception as e:
        log_event("search_subprocess_error", error=str(e))
        return _err(
            f"Could not run the hotel search: {e}",
            code="subprocess_error",
        )

    if proc.returncode != 0:
        log_event(
            "search_nonzero_exit",
            code=proc.returncode,
            stderr_tail=(proc.stderr or "")[-400:],
        )
        return _err(
            "The hotel search reported an error. "
            "Check that your SerpApi key is set in .env.",
            code="search_failed",
            status=502,
        )

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return _err(
            "The hotel search returned an empty response.",
            code="empty_response",
            status=502,
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        log_event("search_bad_json", error=str(e))
        return _err(
            "The hotel search returned an unreadable response.",
            code="bad_json",
            status=502,
        )

    # Normalize to {"hotels": [...]} envelope for the UI.
    if isinstance(payload, list):
        envelope = {"hotels": payload, "count": len(payload)}
    elif isinstance(payload, dict):
        if "hotels" in payload:
            envelope = payload
        else:
            envelope = {"hotels": [payload], "count": 1}
    else:
        envelope = {"hotels": [], "count": 0}

    log_event("search_ok", q=body.q, count=envelope.get("count", 0))
    return JSONResponse(envelope)


# ---------------------------------------------------------------------------
# /api/rank — call rank module with preloaded data files
# ---------------------------------------------------------------------------

def _identity_rank(hotels: list[dict]) -> list[dict]:
    """Minimal fallback ranker — uses total_after_fees_usd as effective_usd."""
    ranked: list[dict] = []
    for i, h in enumerate(sorted(
        hotels,
        key=lambda x: (x.get("total_after_fees_usd") is None,
                       x.get("total_after_fees_usd") or float("inf")),
    )):
        raw = float(h.get("total_after_fees_usd") or 0.0)
        ranked.append({
            "normalized": h,
            "raw_usd": raw,
            "effective_usd": raw,
            "breakdown": {
                "raw_total_usd": raw,
                "points_value_usd": 0.0,
                "free_night_value_usd": 0.0,
                "fhr_value_usd": 0.0,
                "fhr_haircut_usd": 0.0,
                "flexibility_penalty_usd": 0.0,
                "currency_arb_usd": 0.0,
            },
            "recommended_channel": "direct",
            "channel_reason": "Identity fallback — rank.py not loaded.",
            "badges": [],
            "explanation": f"${raw:.0f} raw total via direct booking.",
            "score_rank": i + 1,
        })
    return ranked


def _load_preloaded_data() -> dict:
    """Load all the static reference files rank_hotels expects."""
    out: dict = {}
    for name in (
        "points_valuations",
        "loyalty_programs",
        "fhr_perk_values",
        "perk_rules",
        "fhr_eligible_brands",
    ):
        try:
            out[name] = load_data(name)
        except Exception as e:
            log_event("data_load_warning", name=name, error=str(e))
            out[name] = {}
    return out


@app.post("/api/rank")
def api_rank(body: RankBody) -> JSONResponse:
    """Rank a list of hotels using scripts/rank.py (or a safe fallback).

    The data files (points_valuations, loyalty_programs, fhr_perk_values,
    perk_rules, fhr_eligible_brands) are loaded once here and passed in so
    rank.py stays pure (no file I/O).
    """
    hotels = body.hotels or []
    if not isinstance(hotels, list):
        return _err("The 'hotels' field must be a list.", code="bad_request", status=400)

    balances = body.balances
    if balances is None:
        balances = _load_user_balances()

    fhr_inputs = [fi.model_dump() if hasattr(fi, "model_dump") else dict(fi)
                  for fi in (body.fhr_inputs or [])]

    if _HAS_RANK and rank_mod is not None and hasattr(rank_mod, "rank_hotels"):
        try:
            preloaded = _load_preloaded_data()
            result = rank_mod.rank_hotels(  # type: ignore[attr-defined]
                hotels,
                balances=balances,
                valuations=preloaded.get("points_valuations") or {},
                loyalty_programs=preloaded.get("loyalty_programs") or {},
                fhr_perk_values=preloaded.get("fhr_perk_values") or {},
                perk_rules=preloaded.get("perk_rules") or {},
                fhr_inputs=fhr_inputs,
            )
            if not isinstance(result, list):
                # Some implementations wrap in {"ranked": [...]}
                if isinstance(result, dict) and "ranked" in result:
                    result = result["ranked"]
                else:
                    result = []
            log_event("rank_ok", count=len(result))
            return JSONResponse({"ranked": result, "count": len(result)})
        except TypeError:
            # Older signature — try positional
            try:
                result = rank_mod.rank_hotels(hotels)  # type: ignore[attr-defined]
                if not isinstance(result, list):
                    result = []
                log_event("rank_ok_legacy", count=len(result))
                return JSONResponse({"ranked": result, "count": len(result)})
            except Exception as e:
                log_event("rank_error_fallback", error=str(e))
        except Exception as e:
            log_event("rank_error_fallback", error=str(e))

    # Fallback path
    result = _identity_rank(hotels)
    log_event("rank_fallback", count=len(result))
    return JSONResponse({
        "ranked": result,
        "count": len(result),
        "fallback": True,
    })


# ---------------------------------------------------------------------------
# /api/account — read account.json
# ---------------------------------------------------------------------------

@app.get("/api/account")
def api_account() -> JSONResponse:
    """Return the SerpApi quota snapshot from account.json."""
    try:
        data = account_load()
        return JSONResponse(data)
    except Exception as e:
        log_event("account_read_error", error=str(e))
        return _err(
            "Could not read the account file.",
            code="account_unreadable",
        )


# ---------------------------------------------------------------------------
# /api/map-key — return Google Maps JS API key (or null) for the UI to embed
# ---------------------------------------------------------------------------

@app.get("/api/map-key")
async def get_map_key() -> JSONResponse:
    """Expose GOOGLE_MAPS_API_KEY (or null) so the UI can load Maps JS.

    Without a key, Maps still renders (watermarked "for development purposes
    only") and Street View falls back to the legacy keyless svembed URL.
    The key is read from .env via common.load_env() and merged into os.environ.
    """
    _ensure_env_loaded()
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    return JSONResponse({"key": k or None})


# ---------------------------------------------------------------------------
# /api/data/{name} — whitelisted static data
# ---------------------------------------------------------------------------

@app.get("/api/data/{name}")
def api_data(name: str) -> JSONResponse:
    """Serve a static data file by short name. Whitelisted to a fixed set."""
    if name not in ALLOWED_DATA_NAMES:
        return _err(
            f"Unknown data file '{name}'.",
            code="data_forbidden",
            status=403,
        )
    try:
        return JSONResponse(load_data(name))
    except FileNotFoundError:
        return _err(
            f"The data file '{name}.json' is missing.",
            code="data_missing",
            status=404,
        )
    except Exception as e:
        log_event("data_read_error", name=name, error=str(e))
        return _err(
            f"Could not read '{name}.json'.",
            code="data_unreadable",
        )


# ---------------------------------------------------------------------------
# /api/balances — read + write user_balances.json
# ---------------------------------------------------------------------------

def _load_user_balances() -> dict:
    """Load user_balances.json (falls back to example)."""
    for path in (USER_BAL_PATH, USER_BAL_EXAMPLE):
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                log_event("balances_read_error", error=str(e), path=str(path))
    return {"currencies": {}, "programs": {}, "cards": []}


@app.get("/api/balances")
def api_balances_get() -> JSONResponse:
    return JSONResponse(_load_user_balances())


@app.post("/api/balances")
def api_balances_post(body: BalancesBody) -> JSONResponse:
    """Write user_balances.json after a basic shape check."""
    payload = body.model_dump()
    # Validate shape: dict of dicts of numbers + list of strings.
    if not isinstance(payload.get("currencies"), dict) \
            or not isinstance(payload.get("programs"), dict) \
            or not isinstance(payload.get("cards"), list):
        return _err(
            "Balances must have currencies (dict), programs (dict), cards (list).",
            code="bad_balances_shape",
            status=400,
        )
    for k, v in payload["currencies"].items():
        if not isinstance(v, (int, float)):
            return _err(
                f"Currency balance '{k}' must be a number.",
                code="bad_balance_value",
                status=400,
            )
    for k, v in payload["programs"].items():
        if not isinstance(v, (int, float)):
            return _err(
                f"Program balance '{k}' must be a number.",
                code="bad_balance_value",
                status=400,
            )
    try:
        USER_BAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = USER_BAL_PATH.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(USER_BAL_PATH)
    except Exception as e:
        log_event("balances_write_error", error=str(e))
        return _err(
            f"Could not save your balances: {e}",
            code="balances_unwritable",
        )
    log_event("balances_saved",
              currencies=len(payload["currencies"]),
              programs=len(payload["programs"]),
              cards=len(payload["cards"]))
    return JSONResponse({"saved": True})


# ---------------------------------------------------------------------------
# /api/draft-upgrade-email — return a templated draft (never sends)
# ---------------------------------------------------------------------------

@app.post("/api/draft-upgrade-email")
def api_draft_upgrade_email(body: UpgradeEmailBody) -> JSONResponse:
    """Return a polite, four-sentence draft email body. Does NOT send."""
    hotel = (body.hotel_name or "the hotel").strip()
    arrival = (body.arrival_date or "my upcoming stay").strip()
    status = (body.status or "").strip()
    occasion = (body.special_occasion or "").strip()

    status_clause = (
        f" As a {status} member" if status else ""
    )
    occasion_clause = (
        f" We are celebrating {occasion} during this stay, so any thoughtful touch would be especially meaningful."
        if occasion else ""
    )

    sentence_1 = (
        f"Hello {hotel} team,"
    )
    sentence_2 = (
        f"I'm writing ahead of my arrival on {arrival} to thank you in advance "
        f"for your hospitality."
    )
    sentence_3 = (
        f"{status_clause + ', I' if status else 'I'} would be very grateful if "
        f"you could consider a complimentary room upgrade or any other thoughtful "
        f"touches you feel are appropriate.{occasion_clause}"
    ).strip()
    sentence_4 = (
        "Thank you so much for your time, and I look forward to staying with you."
    )

    body_text = "\n\n".join([sentence_1, sentence_2, sentence_3, sentence_4])
    subject = f"Looking forward to my stay at {hotel} on {arrival}"

    log_event("upgrade_email_drafted", hotel=hotel)
    return JSONResponse({
        "subject": subject,
        "body": body_text,
        "sent": False,
        "note": "This is a draft only. The tool never sends email.",
    })


# ---------------------------------------------------------------------------
# Generic error handlers — friendly envelope
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        {"error": str(exc.detail), "code": f"http_{exc.status_code}"},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def _generic_exception_handler(request: Request, exc: Exception):
    log_event("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        {"error": "Something went wrong on the server.", "code": "internal_error"},
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

_BANNER = r"""
   _           _       _        _                _
  | |__   ___ | |_ ___| |      | |__   __ _  ___| | _____ _ __
  | '_ \ / _ \| __/ _ \ |  ___ | '_ \ / _` |/ __| |/ / _ \ '__|
  | | | | (_) | ||  __/ | |___|| | | | (_| | (__|   <  __/ |
  |_| |_|\___/ \__\___|_|      |_| |_|\__,_|\___|_|\_\___|_|

  find the true cheapest stay — brutalist minimal, layperson-friendly
  ----------------------------------------------------------------
  serving on  ->  http://127.0.0.1:8788
  press Ctrl-C to stop.
"""


def main() -> None:
    print(_BANNER)
    uvicorn.run(
        "ui.server:app" if __package__ else app,
        host="127.0.0.1",
        port=8788,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
