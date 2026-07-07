"""
Sync activities from FIT files stored in a Dropbox folder (e.g. exported by
HealthFitExporter from Apple Health) into the same raw-activity format the
Strava/Garmin sync scripts produce, so the rest of the pipeline
(normalize.py, aggregate.py, generate_heatmaps.py) works unchanged.

Design notes:
- Dropbox access uses a long-lived refresh token (OAuth2 "offline" access),
  exchanged for a short-lived access token on every run. See
  scripts/get_dropbox_refresh_token.py (repo root: same folder as this
  script's sibling tools) for how to obtain the refresh token once.
- Rather than a stateful Dropbox cursor, this sync uses a simple rolling
  lookback window (dropbox.lookback_days, default 14): every run looks at
  files whose filename-encoded date falls within the last N days. This is
  cheap (folder listings for a personal export folder are small), avoids
  fragile cursor-resumption logic, and is self-healing if a file inside the
  window gets corrected/re-exported (e.g. a pool-swim FIT correction).
  Activities that scroll out of the window keep their already-synced raw
  JSON forever (normalize.py merges with existing history), so history is
  never lost - only the *new-file scan* is windowed.
- Expected filename convention (as produced by HealthFitExporter):
      YYYY-MM-DD-HHMMSS-<Aktivitaetsname>-<App>.fit
  e.g. "2026-07-07-075900-Rad outdoor-WorkOutDoors.fit"
  The date/time in the filename is used as a fallback and for the cheap
  windowing check; the authoritative start time and all summary metrics
  come from the FIT file's "session" message.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback, not expected in CI
    ZoneInfo = None

from utils import ensure_dir, load_config, raw_activity_dir, read_json, utc_now, write_json

RAW_DIR = raw_activity_dir("dropbox")
SUMMARY_JSON = os.path.join("data", "last_sync_summary.json")
SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")
STATE_PATH = os.path.join("data", "backfill_state_dropbox.json")
LOCAL_TZ_NAME = "Europe/Berlin"

TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
LIST_FOLDER_URL = "https://api.dropboxapi.com/2/files/list_folder"
LIST_FOLDER_CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"
DOWNLOAD_URL = "https://content.dropboxapi.com/2/files/download"

FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{6})-(?P<label>.+)\.fit$",
    re.IGNORECASE,
)

TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_REQUEST_ATTEMPTS = 5

# FIT "sport" / "sub_sport" enum values (as decoded by fitparse) mapped onto
# Strava's own activity-type vocabulary, so the rest of the pipeline (which
# already understands Strava's "type" strings) needs no changes.
FIT_SPORT_MAP: Dict[Tuple[str, str], str] = {
    ("running", ""): "Run",
    ("running", "generic"): "Run",
    ("running", "trail"): "TrailRun",
    ("running", "treadmill"): "VirtualRun",
    ("running", "indoor_running"): "VirtualRun",
    ("running", "virtual_activity"): "VirtualRun",
    ("walking", ""): "Walk",
    ("walking", "generic"): "Walk",
    ("hiking", ""): "Hike",
    ("hiking", "generic"): "Hike",
    ("cycling", ""): "Ride",
    ("cycling", "generic"): "Ride",
    ("cycling", "road"): "Ride",
    ("cycling", "gravel_cycling"): "GravelRide",
    ("cycling", "mountain"): "MountainBikeRide",
    ("cycling", "mountain_biking"): "MountainBikeRide",
    ("cycling", "indoor_cycling"): "VirtualRide",
    ("cycling", "virtual_activity"): "VirtualRide",
    ("cycling", "e_biking"): "EBikeRide",
    ("e_biking", ""): "EBikeRide",
    ("swimming", ""): "Swim",
    ("swimming", "lap_swimming"): "Swim",
    ("swimming", "open_water"): "Swim",
    ("rowing", ""): "Rowing",
    ("rowing", "indoor_rowing"): "VirtualRow",
    ("training", ""): "Workout",
    ("training", "strength_training"): "WeightTraining",
    ("training", "cardio_training"): "Workout",
    ("training", "crosstraining"): "Crossfit",
    ("fitness_equipment", ""): "Workout",
    ("fitness_equipment", "strength_training"): "WeightTraining",
    ("yoga", ""): "Yoga",
    ("golf", ""): "Golf",
    ("rock_climbing", ""): "RockClimbing",
    ("snowboarding", ""): "Snowboard",
    ("skiing", ""): "AlpineSki",
    ("skiing", "backcountry"): "BackcountrySki",
    ("cross_country_skiing", ""): "NordicSki",
    ("ice_skating", ""): "IceSkate",
    ("inline_skating", ""): "InlineSkate",
    ("kayaking", ""): "Kayaking",
    ("snowshoeing", ""): "Snowshoe",
    ("stand_up_paddleboarding", ""): "StandUpPaddling",
    ("surfing", ""): "Surfing",
    ("windsurfing", ""): "Windsurf",
    ("kitesurfing", ""): "Kitesurf",
    ("sailing", ""): "Sail",
    ("boxing", ""): "Workout",
    ("tennis", ""): "Tennis",
    ("generic", ""): "Workout",
    ("all", ""): "Workout",
}


class DropboxAuthError(RuntimeError):
    pass


def _local_tz():
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(LOCAL_TZ_NAME)
    except Exception:
        return timezone.utc


def _request_with_retry(method: str, url: str, **kwargs):
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            resp = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
            if resp.status_code in TRANSIENT_HTTP_STATUS_CODES and attempt < MAX_REQUEST_ATTEMPTS:
                retry_after = resp.headers.get("Retry-After")
                sleep_seconds = int(retry_after) if retry_after and retry_after.isdigit() else min(30, 2 ** (attempt - 1))
                print(f"Transient Dropbox API error ({resp.status_code}) on {url}; retrying in {sleep_seconds}s.")
                time.sleep(sleep_seconds)
                continue
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= MAX_REQUEST_ATTEMPTS:
                break
            sleep_seconds = min(30, 2 ** (attempt - 1))
            print(f"Network error on {url}: {exc}; retrying in {sleep_seconds}s.")
            time.sleep(sleep_seconds)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Request to {url} failed after {MAX_REQUEST_ATTEMPTS} attempts")


def _get_access_token(dropbox_cfg: Dict[str, Any]) -> str:
    app_key = str(dropbox_cfg.get("app_key", "")).strip()
    app_secret = str(dropbox_cfg.get("app_secret", "")).strip()
    refresh_token = str(dropbox_cfg.get("refresh_token", "")).strip()
    if not app_key or not app_secret or not refresh_token:
        raise DropboxAuthError(
            "Missing dropbox.app_key / dropbox.app_secret / dropbox.refresh_token "
            "(config.local.yaml or DROPBOX_* secrets)."
        )

    resp = _request_with_retry(
        "POST",
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": app_key,
            "client_secret": app_secret,
        },
    )
    if resp.status_code != 200:
        raise DropboxAuthError(f"Failed to refresh Dropbox access token: {resp.status_code} {resp.text}")
    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise DropboxAuthError(f"No access_token in Dropbox token response: {payload}")
    return access_token


def _list_folder(access_token: str, folder_path: str) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    entries: List[Dict[str, Any]] = []

    resp = _request_with_retry(
        "POST",
        LIST_FOLDER_URL,
        headers=headers,
        json={"path": folder_path, "recursive": False},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Dropbox list_folder failed: {resp.status_code} {resp.text}")
    payload = resp.json()
    entries.extend(payload.get("entries", []))
    has_more = bool(payload.get("has_more"))
    cursor = payload.get("cursor")

    while has_more and cursor:
        resp = _request_with_retry(
            "POST",
            LIST_FOLDER_CONTINUE_URL,
            headers=headers,
            json={"cursor": cursor},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Dropbox list_folder/continue failed: {resp.status_code} {resp.text}")
        payload = resp.json()
        entries.extend(payload.get("entries", []))
        has_more = bool(payload.get("has_more"))
        cursor = payload.get("cursor")

    return [e for e in entries if e.get(".tag") == "file" and str(e.get("name", "")).lower().endswith(".fit")]


def _download_file(access_token: str, path: str) -> bytes:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Dropbox-API-Arg": json.dumps({"path": path}),
    }
    resp = _request_with_retry("POST", DOWNLOAD_URL, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Dropbox download failed for {path}: {resp.status_code} {resp.text}")
    return resp.content


def _safe_id_from_filename(filename: str) -> str:
    stem = filename
    if stem.lower().endswith(".fit"):
        stem = stem[: -len(".fit")]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    return slug or "activity"


def _parse_filename(filename: str) -> Optional[Dict[str, Any]]:
    match = FILENAME_RE.match(filename)
    if not match:
        return None
    date_str = match.group("date")
    time_str = match.group("time")
    label = match.group("label")
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None
    local_dt = naive.replace(tzinfo=_local_tz())

    # Filenames end with "-<ExportingApp>" (e.g. "Rad outdoor-WorkOutDoors",
    # "Traditionelles Krafttraining-StrengthLog"). Split that off so the
    # dashboard shows just the activity name, not the app suffix.
    if "-" in label:
        activity_name, source_app = label.rsplit("-", 1)
    else:
        activity_name, source_app = label, ""

    return {
        "local_dt": local_dt,
        "label": label,
        "activity_name": activity_name.strip(),
        "source_app": source_app.strip(),
    }


def _map_fit_sport(sport: Any, sub_sport: Any) -> str:
    sport_key = str(sport or "").strip().lower()
    sub_sport_key = str(sub_sport or "").strip().lower()
    if sub_sport_key == "generic":
        sub_sport_key = ""
    mapped = FIT_SPORT_MAP.get((sport_key, sub_sport_key))
    if mapped:
        return mapped
    mapped = FIT_SPORT_MAP.get((sport_key, ""))
    if mapped:
        return mapped
    # Fall back to a title-cased version of the raw FIT sport so at least
    # something sensible shows up instead of silently dropping the activity.
    return sport_key.replace("_", " ").title().replace(" ", "") or "Workout"


def _parse_fit_session(fit_bytes: bytes) -> Optional[Dict[str, Any]]:
    import fitparse  # imported lazily so config-only dry-runs don't need it installed

    fitfile = fitparse.FitFile(fit_bytes)
    session = None
    for message in fitfile.get_messages("session"):
        session = message
        break  # personal single-activity FIT files: first session is authoritative
    if session is None:
        return None

    values = {field.name: field.value for field in session}

    start_time = values.get("start_time")  # fitparse returns a naive UTC datetime
    start_dt_utc = None
    if isinstance(start_time, datetime):
        start_dt_utc = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)

    return {
        "start_dt_utc": start_dt_utc,
        "sport": values.get("sport"),
        "sub_sport": values.get("sub_sport"),
        "total_distance": values.get("total_distance"),
        "total_timer_time": values.get("total_timer_time"),
        "total_elapsed_time": values.get("total_elapsed_time"),
        "total_ascent": values.get("total_ascent"),
    }


def _build_activity(entry: Dict[str, Any], fit_bytes: bytes) -> Optional[Dict[str, Any]]:
    filename = str(entry.get("name", ""))
    filename_info = _parse_filename(filename)

    session_info = None
    try:
        session_info = _parse_fit_session(fit_bytes)
    except Exception as exc:  # corrupt/partial FIT file: skip, don't crash the whole sync
        print(f"Warning: could not parse FIT session in '{filename}': {exc}")

    local_dt = None
    if session_info and session_info.get("start_dt_utc") is not None:
        local_dt = session_info["start_dt_utc"].astimezone(_local_tz())
    elif filename_info:
        local_dt = filename_info["local_dt"]

    if local_dt is None:
        print(f"Skipping '{filename}': no usable timestamp from FIT session or filename.")
        return None

    sport = (session_info or {}).get("sport")
    sub_sport = (session_info or {}).get("sub_sport")
    activity_type = _map_fit_sport(sport, sub_sport)

    distance = 0.0
    moving_time = 0.0
    elevation_gain = 0.0
    if session_info:
        distance = float(session_info.get("total_distance") or 0.0)
        moving_time = float(
            session_info.get("total_timer_time") or session_info.get("total_elapsed_time") or 0.0
        )
        elevation_gain = float(session_info.get("total_ascent") or 0.0)

    name = None
    source_app = None
    if filename_info:
        if filename_info.get("activity_name"):
            name = filename_info["activity_name"]
        source_app = filename_info.get("source_app") or None

    activity_id = _safe_id_from_filename(filename)

    activity: Dict[str, Any] = {
        "id": activity_id,
        "start_date_local": local_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": activity_type,
        "sport_type": activity_type,
        "distance": distance,
        "moving_time": moving_time,
        "total_elevation_gain": elevation_gain,
        "source_filename": filename,
        "content_hash": entry.get("content_hash"),
    }
    if name:
        activity["name"] = name
    if source_app:
        activity["source_app"] = source_app
    return activity


def _write_activity(activity: Dict[str, Any]) -> bool:
    activity_id = str(activity.get("id") or "").strip()
    if not activity_id or activity_id in {".", ".."} or "/" in activity_id or "\\" in activity_id:
        return False
    path = os.path.join(RAW_DIR, f"{activity_id}.json")
    if os.path.exists(path):
        try:
            existing = read_json(path)
            if existing == activity:
                return False
        except Exception:
            pass
    write_json(path, activity)
    return True


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        payload = read_json(STATE_PATH)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(state: Dict[str, Any]) -> None:
    ensure_dir("data")
    write_json(STATE_PATH, state)


def sync_dropbox(dry_run: bool, prune_deleted: bool) -> Dict[str, Any]:
    config = load_config()
    dropbox_cfg = config.get("dropbox", {}) or {}
    folder_path = str(dropbox_cfg.get("folder_path", "/Apps/HealthFitExporter") or "/Apps/HealthFitExporter")
    lookback_days = int(dropbox_cfg.get("lookback_days", 14))

    ensure_dir(RAW_DIR)
    state = _load_state()
    content_hashes: Dict[str, str] = dict(state.get("content_hashes", {}))

    access_token = _get_access_token(dropbox_cfg)
    entries = _list_folder(access_token, folder_path)

    now_local = utc_now().astimezone(_local_tz())
    cutoff = now_local - timedelta(days=lookback_days)

    fetched = 0
    new_or_updated = 0
    fetched_ids = set()
    skipped_outside_window = 0
    skipped_unchanged = 0
    errors = 0

    for entry in entries:
        filename = str(entry.get("name", ""))
        filename_info = _parse_filename(filename)
        if filename_info and filename_info["local_dt"] < cutoff:
            skipped_outside_window += 1
            continue
        # If the filename doesn't match the expected pattern, don't silently
        # skip it - better to attempt a download and let FIT parsing decide.

        activity_id = _safe_id_from_filename(filename)
        fetched_ids.add(activity_id)
        content_hash = entry.get("content_hash")
        if content_hash and content_hashes.get(activity_id) == content_hash:
            skipped_unchanged += 1
            continue

        fetched += 1
        if dry_run:
            continue

        try:
            fit_bytes = _download_file(access_token, entry.get("path_lower") or entry.get("path_display"))
            activity = _build_activity(entry, fit_bytes)
        except Exception as exc:
            errors += 1
            print(f"Warning: failed to sync '{filename}': {exc}")
            continue

        if activity is None:
            errors += 1
            continue

        if _write_activity(activity):
            new_or_updated += 1
        if content_hash:
            content_hashes[activity_id] = content_hash

    deleted = 0
    if prune_deleted and not dry_run:
        # Only prune raw activities whose id we would expect to see in the
        # current window scan (i.e. their filename-derived date is inside
        # the lookback window). Anything older is permanent history and is
        # left untouched even if it has since left the Dropbox folder.
        if os.path.isdir(RAW_DIR):
            for raw_filename in os.listdir(RAW_DIR):
                if not raw_filename.endswith(".json"):
                    continue
                raw_id = raw_filename[: -len(".json")]
                try:
                    existing = read_json(os.path.join(RAW_DIR, raw_filename))
                except Exception:
                    continue
                start_local = existing.get("start_date_local")
                try:
                    existing_dt = datetime.fromisoformat(str(start_local)).replace(tzinfo=_local_tz())
                except Exception:
                    continue
                if existing_dt < cutoff:
                    continue  # outside window: permanent history, don't touch
                if raw_id not in fetched_ids:
                    os.remove(os.path.join(RAW_DIR, raw_filename))
                    deleted += 1

    if not dry_run:
        _save_state(
            {
                "content_hashes": content_hashes,
                "lookback_days": lookback_days,
                "last_run_utc": utc_now().isoformat(),
            }
        )

    summary = {
        "source": "dropbox",
        "fetched": fetched,
        "new_or_updated": new_or_updated,
        "deleted": deleted,
        "skipped_outside_window": skipped_outside_window,
        "skipped_unchanged": skipped_unchanged,
        "errors": errors,
        "lookback_days": lookback_days,
        "timestamp_utc": utc_now().isoformat(),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync activities from Dropbox FIT files")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prune-deleted",
        action="store_true",
        help="Remove local raw activities (within the lookback window) no longer present in Dropbox",
    )
    args = parser.parse_args()

    config = load_config()
    prune_deleted = args.prune_deleted or bool(config.get("sync", {}).get("prune_deleted", False))

    summary = sync_dropbox(args.dry_run, prune_deleted)

    ensure_dir("data")
    if not args.dry_run:
        write_json(SUMMARY_JSON, summary)
        message = (
            f"Sync Dropbox: {summary['new_or_updated']} new/updated, "
            f"{summary['deleted']} deleted (lookback {summary['lookback_days']}d)"
        )
        if summary.get("errors"):
            message += f", {summary['errors']} errors"
        with open(SUMMARY_TXT, "w", encoding="utf-8") as f:
            f.write(message + "\n")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
