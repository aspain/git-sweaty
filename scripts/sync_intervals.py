import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import intervals_api
from intervals_api import IntervalsAuthError, IntervalsRateLimitError
from sync_scope import activity_scope_from_config, activity_start_ts, start_after_ts
from utils import (
    ensure_dir,
    load_config,
    raw_activity_dir,
    read_json,
    utc_now,
    write_json,
)

API_BASE = intervals_api.API_BASE
RAW_DIR = raw_activity_dir("intervals")
SUMMARY_JSON = os.path.join("data", "last_sync_summary.json")
SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")
STATE_PATH = os.path.join("data", "backfill_state_intervals.json")
ATHLETE_PATH = os.path.join("data", "athletes_intervals.json")
# Generated outputs wiped (with raw files and backfill state) when the synced account changes.
PERSISTED_OUTPUT_PATHS = (
    os.path.join("data", "activities_normalized.json"),
    os.path.join("data", "daily_aggregates.json"),
    SUMMARY_JSON,
    SUMMARY_TXT,
    os.path.join("site", "data.json"),
)
WINDOW_DAYS = 180
# Hard lower bound for the backfill walk when no start_date/lookback_years is configured.
FLOOR_DATE = date(1990, 1, 1)
# Without a configured lower bound, the backfill walk stops after this many consecutive
# empty windows (~2 years with no activities) instead of walking all the way to FLOOR_DATE.
MAX_EMPTY_WINDOWS = 4
MAX_REQUEST_ATTEMPTS = intervals_api.DEFAULT_MAX_ATTEMPTS
MAX_RETRY_WAIT_SECONDS = intervals_api.DEFAULT_MAX_RETRY_WAIT
# Native intervals.icu fields kept in raw files: the ones normalize.py consumes plus
# scalar metrics the dashboard can use later. Large stream/zone arrays are dropped.
NATIVE_FIELDS = (
    "id",
    "start_date_local",
    "start_date",
    "timezone",
    "type",
    "name",
    "source",
    "device_name",
    "trainer",
    "commute",
    "distance",
    "moving_time",
    "elapsed_time",
    "total_elevation_gain",
    "total_elevation_loss",
    "average_speed",
    "max_speed",
    "average_heartrate",
    "max_heartrate",
    "average_cadence",
    "calories",
    "icu_training_load",
    "icu_intensity",
    "icu_average_watts",
    "icu_weighted_avg_watts",
    "icu_ftp",
    "icu_efficiency_factor",
    "trimp",
    "hr_load",
    "pace_load",
    "power_load",
)
STRAVA_STUB_HINT = (
    "Note: {count} intervals.icu activities were imported from Strava and cannot be "
    "re-exported via the intervals.icu API; connect Garmin/Wahoo/etc. directly to "
    "intervals.icu or upload the files to include them."
)


class RateLimitExceeded(RuntimeError):
    pass


def _credentials(config: Dict[str, Any]) -> Tuple[str, str]:
    intervals_cfg = config.get("intervals", {}) or {}
    api_key = str(intervals_cfg.get("api_key") or "").strip()
    if not api_key:
        raise ValueError(
            "Missing intervals.icu API key (intervals.api_key) in config.yaml/config.local.yaml. "
            "Create one on intervals.icu under Settings -> Developer Settings."
        )
    athlete_id = str(intervals_cfg.get("athlete_id") or "0").strip() or "0"
    return api_key, athlete_id


def _request_json(api_key: str, path: str, params: Optional[Dict[str, str]] = None) -> Any:
    try:
        return intervals_api.get_json(
            api_key,
            path,
            params,
            max_attempts=MAX_REQUEST_ATTEMPTS,
            max_retry_wait=MAX_RETRY_WAIT_SECONDS,
        )
    except IntervalsRateLimitError as exc:
        raise RateLimitExceeded(str(exc)) from exc
    except IntervalsAuthError as exc:
        raise RuntimeError(
            f"intervals.icu rejected the request (HTTP {exc.status}). Check that "
            "intervals.api_key is valid and that intervals.athlete_id belongs to that key "
            "(use \"0\" for the key's own athlete)."
        ) from exc


def _athlete_path(athlete_id: str) -> str:
    return f"/athlete/{urllib.parse.quote(athlete_id, safe='')}"


def _fetch_window(api_key: str, athlete_id: str, oldest: date, newest: date) -> List[Dict[str, Any]]:
    payload = _request_json(
        api_key,
        f"{_athlete_path(athlete_id)}/activities",
        {"oldest": oldest.isoformat(), "newest": newest.isoformat()},
    )
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _is_strava_stub(activity: Dict[str, Any]) -> bool:
    # intervals.icu never returns the data of Strava-imported activities via the API, so any
    # Strava-sourced or annotated entry is a placeholder, even when it carries a type.
    return bool(activity.get("_note")) or str(activity.get("source") or "").upper() == "STRAVA"


def _normalize_activity(activity: Dict[str, Any]) -> Dict[str, Any]:
    if not activity.get("id") or not activity.get("start_date_local"):
        return {}
    normalized = {key: activity[key] for key in NATIVE_FIELDS if activity.get(key) is not None}
    normalized["id"] = str(activity["id"])
    normalized["provider"] = "intervals"
    return normalized


def _write_activity(activity: Dict[str, Any]) -> bool:
    activity_id = str(activity.get("id") or "").strip()
    if not activity_id or activity_id in {".", ".."}:
        return False
    if "/" in activity_id or "\\" in activity_id or ".." in activity_id:
        return False

    path = os.path.join(RAW_DIR, f"{activity_id}.json")
    if os.path.exists(path):
        try:
            if read_json(path) == activity:
                return False
        except Exception:
            pass
    write_json(path, activity)
    return True


def _empty_range(next_newest: Optional[date] = None) -> Dict[str, Any]:
    return {
        "fetched": 0,
        "new_or_updated": 0,
        "skipped_strava_stubs": 0,
        "oldest_ts": None,
        "newest_ts": None,
        "rate_limited": False,
        "rate_limit_message": "",
        "activity_ids": [],
        "strava_stub_ids": [],
        "exhausted": False,
        "next_newest": next_newest.isoformat() if next_newest else None,
    }


def _sync_range(
    api_key: str,
    athlete_id: str,
    oldest: date,
    newest: date,
    after: int,
    dry_run: bool,
    stop_after_empty: int = 0,
    walk_at_least_to: Optional[date] = None,
) -> Dict[str, Any]:
    """Walk [oldest, newest] backwards in WINDOW_DAYS chunks, writing activities.

    With `stop_after_empty`, the walk ends (as exhausted) after that many consecutive
    windows returned nothing, once it has gone at least as far back as `walk_at_least_to`.
    """
    new_or_updated = 0
    strava_stub_ids = set()
    oldest_ts = None
    newest_ts = None
    activity_ids = set()
    rate_limited = False
    rate_limit_message = ""
    empty_streak = 0

    cursor: Optional[date] = newest
    while cursor is not None and cursor >= oldest:
        window_oldest = max(oldest, cursor - timedelta(days=WINDOW_DAYS - 1))
        try:
            activities = _fetch_window(api_key, athlete_id, window_oldest, cursor)
        except RateLimitExceeded as exc:
            rate_limited = True
            rate_limit_message = str(exc)
            break
        empty_streak = 0 if activities else empty_streak + 1
        for raw_activity in activities:
            if _is_strava_stub(raw_activity):
                strava_stub_ids.add(str(raw_activity.get("id") or raw_activity.get("start_date_local")))
                continue
            activity = _normalize_activity(raw_activity)
            if not activity:
                continue
            ts = activity_start_ts(activity)
            if ts is not None and ts < after:
                continue
            activity_ids.add(activity["id"])
            if ts is not None:
                oldest_ts = ts if oldest_ts is None else min(oldest_ts, ts)
                newest_ts = ts if newest_ts is None else max(newest_ts, ts)
            if not dry_run and _write_activity(activity):
                new_or_updated += 1
        cursor = window_oldest - timedelta(days=1)
        if (
            stop_after_empty
            and empty_streak >= stop_after_empty
            and (walk_at_least_to is None or window_oldest <= walk_at_least_to)
        ):
            break

    exhausted = not rate_limited
    return {
        "fetched": len(activity_ids),
        "new_or_updated": new_or_updated,
        "skipped_strava_stubs": len(strava_stub_ids),
        "oldest_ts": oldest_ts,
        "newest_ts": newest_ts,
        "rate_limited": rate_limited,
        "rate_limit_message": rate_limit_message,
        "activity_ids": sorted(activity_ids),
        "strava_stub_ids": sorted(strava_stub_ids),
        "exhausted": exhausted,
        "next_newest": None if exhausted else cursor.isoformat(),
    }


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


def _fetch_athlete(api_key: str, athlete_id: str) -> Dict[str, Any]:
    payload = _request_json(api_key, _athlete_path(athlete_id))
    if not isinstance(payload, dict) or not payload.get("id"):
        raise RuntimeError("intervals.icu athlete profile response is missing an athlete id.")
    return payload


def _raw_activity_files() -> List[str]:
    if not os.path.isdir(RAW_DIR):
        return []
    return [name for name in os.listdir(RAW_DIR) if name.endswith(".json")]


def _has_intervals_history() -> bool:
    """True when intervals.icu-specific data (raw activities or backfill state) exists."""
    return os.path.exists(STATE_PATH) or bool(_raw_activity_files())


def _oldest_local_activity_date() -> Optional[date]:
    oldest: Optional[int] = None
    for filename in _raw_activity_files():
        try:
            ts = activity_start_ts(read_json(os.path.join(RAW_DIR, filename)))
        except Exception:
            continue
        if ts is not None:
            oldest = ts if oldest is None else min(oldest, ts)
    if oldest is None:
        return None
    return datetime.fromtimestamp(oldest, tz=timezone.utc).date()


def _account_fingerprint(athlete_id: str) -> str:
    # Keyed on the resolved athlete id (not the API key) so rotating the key keeps history.
    return hashlib.sha256(f"intervals:{athlete_id}".encode("utf-8")).hexdigest()


def _load_account_fingerprint() -> Optional[str]:
    if not os.path.exists(ATHLETE_PATH):
        return None
    try:
        payload = read_json(ATHLETE_PATH)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("fingerprint")
    return value if isinstance(value, str) and value else None


def _write_athlete_cache(athlete: Dict[str, Any]) -> None:
    ensure_dir("data")
    athlete_id = str(athlete["id"])
    write_json(
        ATHLETE_PATH,
        {
            "fingerprint": _account_fingerprint(athlete_id),
            "athlete_id": athlete_id,
            "name": str(athlete.get("name") or "").strip(),
            "updated_utc": utc_now().isoformat(),
            "version": 1,
        },
    )


def _reset_persisted_data() -> None:
    for path in (*PERSISTED_OUTPUT_PATHS, STATE_PATH):
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(RAW_DIR):
        shutil.rmtree(RAW_DIR)


def _maybe_reset_for_new_account(athlete: Dict[str, Any]) -> None:
    stored = _load_account_fingerprint()
    if stored and stored != _account_fingerprint(str(athlete["id"])):
        print("Detected different intervals.icu account; resetting persisted data.")
    elif not stored and _has_intervals_history():
        # Only intervals.icu raw data/state can belong to an unknown account. Derived outputs
        # alone (e.g. written after a rate-limited first run, or left by another source, which
        # run_pipeline already resets on a source switch) are adopted by this account.
        print("No intervals.icu account fingerprint found with existing data; resetting persisted data.")
    else:
        _write_athlete_cache(athlete)
        return
    _reset_persisted_data()
    _write_athlete_cache(athlete)


def _boundary_still_covered(state_after: Any, after: int) -> bool:
    # sync.lookback_years recomputes `after` from now() on every run, so the bound creeps
    # later over time. History already walked still covers it; only an earlier bound
    # (more history wanted) or a missing/invalid saved bound needs a fresh walk.
    try:
        return int(state_after) <= after
    except (TypeError, ValueError):
        return False


def _parse_cursor(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _saved_progress_ahead(state: Dict[str, Any], next_newest: Any) -> bool:
    """True when the saved backfill progress is further along than this run's walk."""
    if state.get("completed"):
        return True
    saved = _parse_cursor(state.get("next_newest"))
    current = _parse_cursor(next_newest)
    return saved is not None and (current is None or saved <= current)


# Internal _sync_range bookkeeping that is not part of the published recent_sync summary.
_INTERNAL_RANGE_KEYS = ("exhausted", "next_newest", "strava_stub_ids")


def _build_summary(
    *,
    after: int,
    recent: Dict[str, Any],
    fetched: int = 0,
    new_or_updated: int = 0,
    deleted: int = 0,
    rate_limited: bool = False,
    rate_limit_message: str = "",
    backfill_completed: bool = False,
    backfill_next_newest: Optional[str] = None,
    skipped_strava_stubs: int = 0,
) -> Dict[str, Any]:
    """Single source of truth for the sync summary shape (normal and early-exit paths)."""
    return {
        "source": "intervals",
        "fetched": fetched,
        "new_or_updated": new_or_updated,
        "deleted": deleted,
        "lookback_start_ts": after,
        "timestamp_utc": utc_now().isoformat(),
        "rate_limited": rate_limited,
        "rate_limit_message": rate_limit_message if rate_limited else "",
        "backfill_completed": backfill_completed,
        "backfill_next_newest": backfill_next_newest,
        "skipped_strava_stubs": skipped_strava_stubs,
        "recent_sync": {k: v for k, v in recent.items() if k not in _INTERNAL_RANGE_KEYS},
    }


def _rate_limited_summary(after: int, message: str) -> Dict[str, Any]:
    state = _load_state()
    return _build_summary(
        after=after,
        recent=_empty_range(),
        rate_limited=True,
        rate_limit_message=message,
        backfill_completed=bool(state.get("completed")),
        backfill_next_newest=state.get("next_newest"),
    )


def sync_intervals(dry_run: bool, prune_deleted: bool) -> Dict[str, Any]:
    config = load_config()
    sync_cfg = config.get("sync", {}) or {}
    after = start_after_ts(config)
    activity_scope = activity_scope_from_config(config)
    recent_days = int(sync_cfg.get("recent_days", 7))
    resume_backfill = bool(sync_cfg.get("resume_backfill", True))
    api_key, athlete_id = _credentials(config)

    # One profile request per run: validates the key, resolves athlete id "0" and
    # identifies the account for the reset check and athlete cache.
    try:
        athlete = _fetch_athlete(api_key, athlete_id)
    except RateLimitExceeded as exc:
        # Syncing without the account check would write data with no fingerprint, which the
        # next run treats as foreign and wipes. Stop before touching anything.
        print(f"Warning: unable to fetch intervals.icu athlete profile; skipping sync ({exc})")
        return _rate_limited_summary(after, str(exc))
    athlete_id = str(athlete["id"])

    if not dry_run:
        _maybe_reset_for_new_account(athlete)
        ensure_dir(RAW_DIR)

    # Upper bound is tomorrow so activities whose local date is ahead of UTC are included.
    newest = utc_now().date() + timedelta(days=1)
    lower = FLOOR_DATE
    if after:
        lower = datetime.fromtimestamp(after, tz=timezone.utc).date() - timedelta(days=1)

    saved_state = _load_state()
    last_success = _parse_cursor(saved_state.get("last_success_date"))

    recent_summary = _empty_range()
    backfill_start = newest
    if recent_days > 0:
        recent_oldest = utc_now().date() - timedelta(days=recent_days)
        if last_success is not None:
            # Catch up on gaps longer than recent_days (e.g. the workflow was broken for weeks).
            recent_oldest = min(recent_oldest, last_success - timedelta(days=1))
        recent_oldest = max(lower, recent_oldest)
        recent_summary = _sync_range(api_key, athlete_id, recent_oldest, newest, after, dry_run)
        # Backfill only runs when the recent window completed, so it can start below it.
        backfill_start = recent_oldest - timedelta(days=1)

    state = dict(saved_state) if resume_backfill and not dry_run else {}
    if state:
        if not _boundary_still_covered(state.get("after"), after):
            print("Backfill boundary changed; restarting intervals.icu cursor.")
            state = {}
        elif state.get("activity_scope") != activity_scope:
            print("Activity scope changed; restarting intervals.icu backfill cursor.")
            state = {}
    # prune_deleted needs every activity id in scope, so it walks the whole range even when
    # the backfill is already completed or has a resume cursor.
    full_scan = prune_deleted and not dry_run
    skip_backfill = bool(state.get("completed")) and not full_scan
    resume_cursor = None if skip_backfill or full_scan else _parse_cursor(state.get("next_newest"))

    rate_limited = bool(recent_summary["rate_limited"])
    rate_limit_message = str(recent_summary["rate_limit_message"])
    backfill = _empty_range(resume_cursor)
    if not rate_limited and not skip_backfill:
        backfill_newest = min(resume_cursor, backfill_start) if resume_cursor else backfill_start
        stop_after_empty = 0
        walk_at_least_to = None
        if not after:
            # No configured lower bound: stop once a long stretch has no activities. A prune
            # scan must still reach the oldest local activity so it is not pruned by mistake.
            stop_after_empty = MAX_EMPTY_WINDOWS
            if full_scan:
                walk_at_least_to = _oldest_local_activity_date()
        backfill = _sync_range(
            api_key,
            athlete_id,
            lower,
            backfill_newest,
            after,
            dry_run,
            stop_after_empty=stop_after_empty,
            walk_at_least_to=walk_at_least_to,
        )
        if backfill["rate_limited"]:
            rate_limited = True
            rate_limit_message = backfill["rate_limit_message"]
    walk_completed = bool(backfill["exhausted"]) and not rate_limited

    fetched_ids = set(recent_summary["activity_ids"]) | set(backfill["activity_ids"])
    deleted = 0
    if full_scan and walk_completed:
        for filename in _raw_activity_files():
            if filename[:-5] not in fetched_ids:
                os.remove(os.path.join(RAW_DIR, filename))
                deleted += 1
    elif prune_deleted and not dry_run:
        print(
            "Skipping prune_deleted for intervals.icu: pruning requires a full backfill scan in this run."
        )

    # Keep saved progress when this run's walk did not get as far (e.g. a rate-limited prune scan).
    keep_state = skip_backfill or (
        not walk_completed and bool(state) and _saved_progress_ahead(state, backfill["next_newest"])
    )
    if keep_state:
        completed = bool(state.get("completed"))
        next_newest = None if completed else state.get("next_newest")
    else:
        completed = walk_completed
        next_newest = None if completed else backfill["next_newest"]

    if not dry_run:
        if keep_state:
            state_update = dict(state)
            state_update["rate_limited"] = rate_limited
            state_update["last_run_utc"] = utc_now().isoformat()
        else:
            state_update = {
                "after": after,
                "next_newest": next_newest,
                "completed": completed,
                "oldest_seen_ts": backfill["oldest_ts"],
                "newest_seen_ts": backfill["newest_ts"],
                "rate_limited": rate_limited,
                "last_run_utc": utc_now().isoformat(),
            }
        state_update["activity_scope"] = activity_scope
        if recent_days > 0 and not recent_summary["rate_limited"]:
            state_update["last_success_date"] = utc_now().date().isoformat()
        elif last_success is not None:
            state_update["last_success_date"] = last_success.isoformat()
        else:
            state_update.pop("last_success_date", None)
        _save_state(state_update)

    # The recent window and a resumed cursor can overlap; count each activity once.
    skipped_strava_stubs = len(set(recent_summary["strava_stub_ids"]) | set(backfill["strava_stub_ids"]))
    if skipped_strava_stubs:
        print(STRAVA_STUB_HINT.format(count=skipped_strava_stubs))

    return _build_summary(
        after=after,
        recent=recent_summary,
        fetched=len(fetched_ids),
        new_or_updated=backfill["new_or_updated"] + recent_summary["new_or_updated"],
        deleted=deleted,
        rate_limited=rate_limited,
        rate_limit_message=rate_limit_message,
        backfill_completed=completed,
        backfill_next_newest=next_newest,
        skipped_strava_stubs=skipped_strava_stubs,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync intervals.icu activities")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prune-deleted",
        action="store_true",
        help="Remove local raw activities not returned by intervals.icu",
    )
    args = parser.parse_args()

    config = load_config()
    prune_deleted = args.prune_deleted or bool(config.get("sync", {}).get("prune_deleted", False))

    summary = sync_intervals(args.dry_run, prune_deleted)

    if not args.dry_run:
        ensure_dir("data")
        write_json(SUMMARY_JSON, summary)
        start_ts = summary.get("lookback_start_ts")
        if start_ts:
            start_label = datetime.fromtimestamp(start_ts, tz=timezone.utc).date().isoformat()
            range_label = f"start {start_label}"
        else:
            range_label = "start unknown"
        message = (
            f"Sync intervals.icu: {summary['new_or_updated']} new/updated, "
            f"{summary['deleted']} deleted ({range_label})"
        )
        if summary.get("skipped_strava_stubs"):
            message += f", {summary['skipped_strava_stubs']} Strava imports skipped"
        if summary.get("rate_limited"):
            message += " [rate limited]"
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
