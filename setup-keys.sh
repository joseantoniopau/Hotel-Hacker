#!/usr/bin/env bash
# setup-keys.sh — one-time setup of your free SerpApi login.

set -euo pipefail

AMBER=$'\033[38;5;214m'
DIM=$'\033[2m'
RESET=$'\033[0m'
TICK="▍"
say()  { printf "%s%s [hotel-hacker]%s %s\n" "$AMBER" "$TICK" "$RESET" "$1"; }
note() { printf "%s   %s%s\n" "$DIM" "$1" "$RESET"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"

say "This sets up your free SerpApi login. You'll only do this once."
echo ""
note "SerpApi is the service Hotel-Hacker uses to look up real hotel prices."
note "Their free plan gives you 250 hotel searches per month — plenty."
note "If you don't have a key yet, sign up here (free, takes 30 seconds):"
note "  https://serpapi.com/"
echo ""

# ---- check for an existing .env ----------------------------------------
if [ -f "$ENV_FILE" ]; then
  say "Heads up: a settings file already exists at .env"
  printf "   Overwrite it with a new key? (y/N): "
  read -r confirm
  case "$confirm" in
    y|Y|yes|YES)
      note "OK — we'll replace it."
      ;;
    *)
      note "Leaving the existing .env alone. Nothing changed."
      exit 0
      ;;
  esac
  echo ""
fi

# ---- prompt for the key ------------------------------------------------
read -r -p "Paste your SerpApi key and press Enter: " key

# strip surrounding whitespace
key="${key#"${key%%[![:space:]]*}"}"
key="${key%"${key##*[![:space:]]}"}"

if [ -z "$key" ]; then
  printf "%s%s [hotel-hacker]%s That looked empty. Nothing was saved.\n" "$AMBER" "$TICK" "$RESET" >&2
  echo "   Run ./setup-keys.sh again when you have the key handy."
  exit 1
fi

if [ "${#key}" -le 20 ]; then
  printf "%s%s [hotel-hacker]%s That key looks too short.\n" "$AMBER" "$TICK" "$RESET" >&2
  echo "   SerpApi keys are usually 40+ characters of letters and numbers."
  echo "   Double-check you copied the whole thing, then run this again."
  exit 1
fi

if ! printf '%s' "$key" | grep -qE '^[A-Za-z0-9_-]+$'; then
  printf "%s%s [hotel-hacker]%s That key has unexpected characters.\n" "$AMBER" "$TICK" "$RESET" >&2
  echo "   SerpApi keys only contain letters, numbers, dashes, and underscores."
  echo "   Try copying it again — maybe a stray space sneaked in."
  exit 1
fi

# ---- prompt for an OPTIONAL Google Maps key (removes the watermark) ---
echo ""
say "OPTIONAL — add a free Google Maps key to remove the \"for development purposes only\" watermark."
note "Hotel-Hacker shows every result on a Google Map. Without a key, Google overlays"
note "a faded \"For development purposes only\" banner. Adding a key (free, ~3 minutes)"
note "removes it. To get one:"
note "  1) Go to  https://console.cloud.google.com/google/maps-apis/start"
note "  2) Create a project (any name)."
note "  3) Enable these three APIs:  Maps JavaScript API,  Maps Embed API,  Street View Static API."
note "  4) Open APIs & Services → Credentials → Create credentials → API key."
note "  5) Copy the key. (You can restrict it to HTTP referrer \"http://127.0.0.1:8788/*\")."
note "Press Enter to skip — the app still works, just with the watermark."
echo ""
read -r -p "Paste your Google Maps key (or press Enter to skip): " gkey
gkey="${gkey#"${gkey%%[![:space:]]*}"}"
gkey="${gkey%"${gkey##*[![:space:]]}"}"

# ---- write the .env safely --------------------------------------------
umask 077
{
  printf 'SERPAPI_KEY=%s\n' "$key"
  if [ -n "$gkey" ]; then
    printf 'GOOGLE_MAPS_API_KEY=%s\n' "$gkey"
  fi
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo ""
if [ -n "$gkey" ]; then
  say "Saved both keys to .env (locked so only you can read it)."
else
  say "Saved your SerpApi key to .env (locked so only you can read it)."
  note "No Google Maps key — the map will work with the watermark."
  note "Add one later by re-running ./setup-keys.sh."
fi
echo ""
echo "  You're done with setup. To launch the app, run:"
echo ""
echo "      python3 ui/server.py"
echo ""
echo "  Then open http://127.0.0.1:8788 in your web browser."
echo ""
