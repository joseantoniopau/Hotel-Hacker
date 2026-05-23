#!/usr/bin/env bash
# install.sh — set up everything Hotel-Hacker needs to run on your Mac.
# Safe to run more than once. Takes about 30 seconds on a warm pip cache.

set -euo pipefail

# ---- pretty output -------------------------------------------------------
AMBER=$'\033[38;5;214m'
DIM=$'\033[2m'
RESET=$'\033[0m'
TICK="▍"
say()   { printf "%s%s [hotel-hacker]%s %s\n" "$AMBER" "$TICK" "$RESET" "$1"; }
note()  { printf "%s   %s%s\n" "$DIM" "$1" "$RESET"; }
fail()  { printf "%s%s [hotel-hacker] %s%s\n" "$AMBER" "$TICK" "$1" "$RESET" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say "Welcome. This sets up Hotel-Hacker on your computer."
note "Working folder: $ROOT"
echo ""

# ---- 1. Python check -----------------------------------------------------
say "Step 1 of 5: Checking that Python is installed."
note "Hotel-Hacker needs Python version 3.10 or newer to run."

if ! command -v python3 >/dev/null 2>&1; then
  fail "Python 3 is not installed on this computer."
  echo ""
  echo "  Don't worry — you can fix this in two minutes."
  echo "  Open this page in your web browser and click the big yellow"
  echo "  'Download Python' button:"
  echo ""
  echo "      https://www.python.org/downloads/macos/"
  echo ""
  echo "  After it finishes installing, come back here and run"
  echo "  ./install.sh again."
  exit 1
fi

PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')"
if [ "$PY_OK" != "1" ]; then
  fail "Your Python is version $PY_VER, which is too old."
  echo ""
  echo "  Hotel-Hacker needs Python 3.10 or newer. To upgrade,"
  echo "  open this page and download the latest installer:"
  echo ""
  echo "      https://www.python.org/downloads/macos/"
  echo ""
  echo "  Then run ./install.sh again."
  exit 1
fi
note "Found Python $PY_VER — that works."
echo ""

# ---- 2. Virtual environment ---------------------------------------------
say "Step 2 of 5: Making a private workspace for Hotel-Hacker's helper files."
note "This keeps them tidy and separate from the rest of your computer."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  note "Workspace created at .venv/"
else
  note "Workspace already exists — reusing it."
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo ""

# ---- 3. Dependencies -----------------------------------------------------
say "Step 3 of 5: Downloading the helper files Hotel-Hacker needs to run."
note "This is the slowest step — usually 10 to 30 seconds. Sit tight."

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet \
  requests \
  fastapi \
  'uvicorn[standard]' \
  python-dotenv \
  pydantic \
  pytest
note "All helper files are in place."
echo ""

# ---- 4. Folders and starter files ---------------------------------------
say "Step 4 of 5: Setting up folders and starter settings."

mkdir -p cache
touch cache/.gitkeep
note "Cache folder ready (this is where searches get remembered for 24 hours)."

if [ ! -f "account.json" ]; then
  cat > account.json <<'JSON'
{
  "searches_remaining": 250,
  "searches_used_this_month": 0,
  "last_checked": null,
  "_note": "SerpApi free-tier defaults; refreshed lazily"
}
JSON
  note "Created account.json (tracks your free 250 monthly hotel searches)."
else
  note "account.json already exists — leaving it alone."
fi

if [ ! -f "data/user_balances.json" ]; then
  if [ -f "data/user_balances.example.json" ]; then
    cp data/user_balances.example.json data/user_balances.json
    note "Created your personal points-and-miles balances file."
    note "Edit data/user_balances.json later to add your real numbers."
  else
    note "Skipping balances file — data/user_balances.example.json not found yet."
  fi
else
  note "Your balances file already exists — leaving it alone."
fi
echo ""

# ---- 5. Done -------------------------------------------------------------
say "Step 5 of 5: All set."
echo ""
printf "%s%s [hotel-hacker]%s Install complete.\n" "$AMBER" "$TICK" "$RESET"
echo ""
echo "  Next step: connect Hotel-Hacker to its free hotel-search service."
echo "  Run this command:"
echo ""
echo "      ./setup-keys.sh"
echo ""
echo "  After that, you'll be able to launch the app with:"
echo ""
echo "      python3 ui/server.py"
echo ""
