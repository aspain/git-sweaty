#!/usr/bin/env bash
set -Eeuo pipefail

PORT=4173
RUN_SYNC=0
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Usage: ./scripts/dev_dashboard.sh [options]

Starts a local dashboard server from ./site.
By default, it refreshes site/data.json first using local data only.

Options:
  --port <number>   Port for local server (default: 4173)
  --sync            Run provider sync before build (slower, hits API)
  --skip-build      Skip running the pipeline before serving
  -h, --help        Show this help text
EOF
}

check_sync_credentials() {
  "$PYTHON_BIN" - <<'PY'
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from utils import load_config, normalize_source


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


config = load_config()
source = normalize_source(config.get("source", "strava"))

if source == "strava":
    strava = config.get("strava") or {}
    missing = [
        name
        for name in ("client_id", "client_secret", "refresh_token")
        if not has_text(strava.get(name))
    ]
    if missing:
        print(
            "Sync preflight failed: missing Strava credentials in config.local.yaml "
            f"({', '.join(missing)})."
        )
        raise SystemExit(2)
elif source == "garmin":
    garmin = config.get("garmin") or {}
    token = has_text(garmin.get("token_store_b64"))
    email = has_text(garmin.get("email"))
    password = has_text(garmin.get("password"))
    strict_token_only = bool(garmin.get("strict_token_only"))

    if strict_token_only and not token:
        print(
            "Sync preflight failed: garmin.strict_token_only=true but garmin.token_store_b64 is missing in config.local.yaml."
        )
        raise SystemExit(2)
    if not token and not (email and password):
        print(
            "Sync preflight failed: missing Garmin auth in config.local.yaml "
            "(set garmin.token_store_b64 or garmin.email+garmin.password)."
        )
        raise SystemExit(2)
elif source == "intervals":
    intervals = config.get("intervals") or {}
    if not has_text(intervals.get("api_key")):
        print(
            "Sync preflight failed: missing intervals.icu API key in config.local.yaml "
            "(set intervals.api_key)."
        )
        raise SystemExit(2)

print(source)
PY
}

read_local_activity_count() {
  "$PYTHON_BIN" - <<'PY'
import json
import os

path = os.path.join("site", "data.json")
if not os.path.exists(path):
    print(0)
    raise SystemExit(0)

try:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    print(0)
    raise SystemExit(0)

activities = payload.get("activities", [])
print(len(activities) if isinstance(activities, list) else 0)
PY
}

restore_from_dashboard_data_branch() {
  if ! git rev-parse --verify --quiet origin/dashboard-data >/dev/null; then
    if git remote get-url origin >/dev/null 2>&1; then
      git fetch origin dashboard-data >/dev/null 2>&1 || true
    fi
  fi

  if ! git rev-parse --verify --quiet origin/dashboard-data >/dev/null; then
    return 1
  fi

  if git archive --format=tar origin/dashboard-data data site/data.json | tar -xf -; then
    return 0
  fi
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --port requires a value." >&2; exit 1; }
      PORT="$1"
      ;;
    --sync)
      RUN_SYNC=1
      ;;
    --skip-build)
      SKIP_BUILD=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [[ "$PORT" -lt 1 ]] || [[ "$PORT" -gt 65535 ]]; then
  echo "ERROR: Invalid port '$PORT'. Use a number between 1 and 65535." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=""
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "ERROR: python3 is required." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import yaml" >/dev/null 2>&1; then
  echo "ERROR: Missing Python dependencies." >&2
  echo "Run: $PYTHON_BIN -m pip install -r requirements.txt" >&2
  exit 1
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "Refreshing dashboard data..."
  if [[ "$RUN_SYNC" -eq 0 ]]; then
    "$PYTHON_BIN" scripts/run_pipeline.py --skip-sync
  else
    if sync_source="$(check_sync_credentials)"; then
      echo "Sync source: $sync_source"
      if ! "$PYTHON_BIN" scripts/run_pipeline.py; then
        echo "WARN: Provider sync failed; continuing with local cached data only." >&2
        "$PYTHON_BIN" scripts/run_pipeline.py --skip-sync
      fi
    else
      echo "WARN: Provider sync is not configured yet; continuing with local cached data only." >&2
      echo "Run ./scripts/bootstrap.sh once to set up provider credentials, then retry --sync." >&2
      "$PYTHON_BIN" scripts/run_pipeline.py --skip-sync
    fi
  fi
  activity_count="$(read_local_activity_count)"
  if [[ "$activity_count" -eq 0 ]]; then
    echo "WARN: Local site/data.json has 0 activities." >&2
    if restore_from_dashboard_data_branch; then
      activity_count="$(read_local_activity_count)"
      echo "Restored local data snapshot from origin/dashboard-data (activities: ${activity_count})."
    else
      echo "No local dashboard-data snapshot available. Run ./scripts/bootstrap.sh to configure sync credentials." >&2
    fi
  fi

  echo "Local activity count: ${activity_count}"
  echo ""
fi

echo "Starting local dashboard at: http://localhost:${PORT}"
echo "Edit files in site/ and refresh your browser to test changes instantly."
echo "For data/pipeline changes, rerun: $PYTHON_BIN scripts/run_pipeline.py --skip-sync"
echo ""

exec "$PYTHON_BIN" -m http.server "$PORT" --directory site
