import argparse
import hashlib
import hmac
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from garmin_token_store import (
    decode_token_store_b64,
    token_store_ready,
    write_token_store_bytes,
)
from provider_fields import (
    coalesce as _shared_coalesce,
    get_nested as _shared_get_nested,
    pick_duration_seconds as _shared_pick_duration_seconds,
)
from sync_scope import (
    activity_scope_from_config,
    activity_start_ts as _shared_activity_start_ts,
    start_after_ts as _shared_start_after_ts,
)
from utils import ensure_dir, load_config, raw_activity_dir, read_json, utc_now, write_json

RAW_DIR = raw_activity_dir("garmin")
SUMMARY_JSON = os.path.join("data", "last_sync_summary.json")
SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")
STATE_PATH = os.path.join("data", "backfill_state_garmin.json")
ATHLETE_PATH = os.path.join("data", "athletes_garmin.json")
TOKEN_STORE_PATH = ".garmin_token_store"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _strict_token_only(config: Dict[str, Any]) -> bool:
    env_value = os.getenv("GARMIN_STRICT_TOKEN_ONLY")
    if env_value is not None:
        return _to_bool(env_value)
    garmin_cfg = config.get("garmin", {}) or {}
    return _to_bool(garmin_cfg.get("strict_token_only"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coalesce(*values: Any) -> Any:
    return _shared_coalesce(*values)


def _duration_candidates(payload: Dict[str, Any]) -> List[Any]:
    return [
        payload.get("movingDuration"),
        payload.get("duration"),
        payload.get("elapsedDuration"),
        payload.get("moving_time"),
        payload.get("elapsed_time"),
        _get_nested(payload, ["summaryDTO", "movingDuration"]),
        _get_nested(payload, ["summaryDTO", "duration"]),
        _get_nested(payload, ["summaryDTO", "elapsedDuration"]),
        _get_nested(payload, ["activitySummary", "movingDuration"]),
        _get_nested(payload, ["activitySummary", "duration"]),
        _get_nested(payload, ["activitySummary", "elapsedDuration"]),
    ]


def _pick_duration_seconds(*values: Any) -> float:
    return _shared_pick_duration_seconds(*values)


def _get_nested(payload: Dict[str, Any], keys: List[str]) -> Any:
    return _shared_get_nested(payload, keys)


def _activity_type_key(activity: Dict[str, Any]) -> str:
    value = _coalesce(
        _get_nested(activity, ["activityType", "typeKey"]),
        _get_nested(activity, ["activityTypeDTO", "typeKey"]),
        _get_nested(activity, ["activityType", "type"]),
        activity.get("type"),
        activity.get("activityType"),
        "Unknown",
    )
    return str(value)


def _normalize_activity(activity: Dict[str, Any]) -> Dict[str, Any]:
    activity_id = _coalesce(activity.get("activityId"), activity.get("id"))
    if activity_id is None:
        return {}

    start_local = _coalesce(
        activity.get("startTimeLocal"),
        activity.get("startTimeGMT"),
        activity.get("startTimeGmt"),
        activity.get("startDate"),
    )
    if not start_local:
        return {}
    start_local_str = str(start_local).replace(" ", "T")

    type_key = _activity_type_key(activity)
    moving_time = _pick_duration_seconds(*_duration_candidates(activity))
    elevation_gain = _coalesce(
        activity.get("elevationGain"),
        activity.get("totalElevationGain"),
        activity.get("total_elevation_gain"),
    )
    distance = _coalesce(activity.get("distance"), activity.get("totalDistance"), 0.0)
    activity_name = str(
        _coalesce(
            activity.get("activityName"),
            activity.get("activity_name"),
            activity.get("name"),
            _get_nested(activity, ["summaryDTO", "activityName"]),
        )
        or ""
    ).strip()

    normalized = {
        "id": str(activity_id),
        "start_date_local": start_local_str,
        "start_date": str(
            _coalesce(
                activity.get("startTimeGMT"),
                activity.get("startTimeGmt"),
                activity.get("startTimeLocal"),
                start_local_str,
            )
        ).replace(" ", "T"),
        "type": type_key,
        "sport_type": type_key,
        "distance": _safe_float(distance, 0.0),
        "moving_time": _safe_float(moving_time, 0.0),
        "total_elevation_gain": _safe_float(elevation_gain, 0.0),
        "provider": "garmin",
    }
    if activity_name:
        normalized["name"] = activity_name
    return normalized


def _fetch_activity_duration_from_summary(client: Any, activity_id: str) -> Optional[float]:
    methods = [
        ("get_activity", (activity_id,), {}),
        ("getActivity", (activity_id,), {}),
        ("get_activity_details", (activity_id,), {}),
        ("getActivityDetails", (activity_id,), {}),
    ]
    for method_name, args, kwargs in methods:
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            payload = method(*args, **kwargs)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        value = _pick_duration_seconds(*_duration_candidates(payload))
        if value > 0:
            return value
    return None


def _enrich_missing_duration(
    client: Any,
    normalized: Dict[str, Any],
    stats: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    if _safe_float(normalized.get("moving_time"), 0.0) > 0:
        return normalized
    activity_id = str(normalized.get("id") or "").strip()
    if not activity_id:
        return normalized
    resolved = _fetch_activity_duration_from_summary(client, activity_id)
    if not resolved or resolved <= 0:
        return normalized
    enriched = dict(normalized)
    enriched["moving_time"] = resolved
    if stats is not None:
        stats["duration_enriched"] = int(stats.get("duration_enriched", 0)) + 1
    return enriched


def _activity_start_ts(activity: Dict[str, Any]) -> Optional[int]:
    return _shared_activity_start_ts(activity)


def _start_after_ts(config: Dict[str, Any]) -> int:
    return _shared_start_after_ts(config)


def _activity_scope(config: Dict[str, Any]) -> Dict[str, Any]:
    return activity_scope_from_config(config)


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


def _write_account_fingerprint(fingerprint: str) -> None:
    ensure_dir("data")
    write_json(
        ATHLETE_PATH,
        {
            "fingerprint": fingerprint,
            "updated_utc": utc_now().isoformat(),
            "version": 1,
        },
    )


def _account_fingerprint(config: Dict[str, Any]) -> Optional[str]:
    garmin_cfg = config.get("garmin", {}) or {}
    email = str(garmin_cfg.get("email") or "").strip().lower()
    password = str(garmin_cfg.get("password") or "")
    token_store_b64 = str(garmin_cfg.get("token_store_b64") or "")

    # Prefer stable account identity when email is available.
    if email:
        secret = password or token_store_b64
        if not secret:
            return None
        return hmac.new(secret.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()

    # Fallback for token-only setups (common in manual secret configuration).
    # This still lets us detect that restored persisted data belongs to a different account.
    if token_store_b64:
        return hashlib.sha256(token_store_b64.encode("utf-8")).hexdigest()

    return None


def _has_existing_data() -> bool:
    candidates = [
        os.path.join("data", "activities_normalized.json"),
        os.path.join("data", "daily_aggregates.json"),
        os.path.join("data", "last_sync_summary.json"),
        os.path.join("data", "last_sync_summary.txt"),
        os.path.join("site", "data.json"),
    ]
    return any(os.path.exists(path) for path in candidates)


def _reset_persisted_data() -> None:
    paths = [
        os.path.join("data", "activities_normalized.json"),
        os.path.join("data", "daily_aggregates.json"),
        os.path.join("data", "last_sync_summary.json"),
        os.path.join("data", "last_sync_summary.txt"),
        os.path.join("site", "data.json"),
    ]
    for path in paths:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(RAW_DIR):
        shutil.rmtree(RAW_DIR)


def _maybe_reset_for_new_account(config: Dict[str, Any]) -> None:
    fingerprint = _account_fingerprint(config)
    if not fingerprint:
        return
    stored = _load_account_fingerprint()
    if stored == fingerprint:
        return
    if stored and stored != fingerprint:
        print("Detected different Garmin account; resetting persisted data.")
        _reset_persisted_data()
    elif not stored and _has_existing_data():
        print("No Garmin account fingerprint found with existing data; resetting persisted data.")
        _reset_persisted_data()
    _write_account_fingerprint(fingerprint)


def _load_token_store_bytes(config: Dict[str, Any]) -> Optional[bytes]:
    garmin_cfg = config.get("garmin", {}) or {}
    encoded = str(garmin_cfg.get("token_store_b64") or "").strip()
    if not encoded:
        return None
    return decode_token_store_b64(encoded)


def _write_token_store(token_bytes: bytes) -> str:
    return write_token_store_bytes(token_bytes, TOKEN_STORE_PATH)


def _local_token_store_path() -> Optional[str]:
    return TOKEN_STORE_PATH if token_store_ready(TOKEN_STORE_PATH) else None


def _candidate_clients(
    garmin_cls: Any, email: str, password: str, allow_credentials: bool
) -> List[Any]:
    factories = []
    if allow_credentials and email and password:
        factories.extend(
            [
                lambda: garmin_cls(email=email, password=password),
                lambda: garmin_cls(email, password),
            ]
        )
    factories.append(lambda: garmin_cls())
    clients: List[Any] = []
    for factory in factories:
        try:
            clients.append(factory())
        except Exception:
            continue
    return clients


def _login_variants(
    client: Any,
    email: str,
    password: str,
    token_store: Optional[str],
    allow_credentials: bool,
    allow_default_login: bool,
) -> bool:
    attempts = []
    if token_store:
        attempts.extend(
            [
                lambda: client.login(tokenstore=token_store),
                lambda: client.login(token_store=token_store),
                lambda: client.login(token_store),
            ]
        )
    if allow_credentials and email and password:
        attempts.extend(
            [
                lambda: client.login(),
                lambda: client.login(email, password),
                lambda: client.login(email=email, password=password),
            ]
        )
    if allow_default_login and not (allow_credentials and email and password):
        attempts.append(lambda: client.login())

    for attempt in attempts:
        try:
            attempt()
            return True
        except TypeError:
            continue
        except Exception:
            continue
    return False


def _load_garmin_client(config: Dict[str, Any]) -> Any:
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'garminconnect'. Install requirements before using source=garmin."
        ) from exc

    garmin_cfg = config.get("garmin", {}) or {}
    email = str(garmin_cfg.get("email") or "").strip()
    password = str(garmin_cfg.get("password") or "").strip()
    strict_token_mode = _strict_token_only(config)

    token_store: Optional[str] = None
    token_bytes = _load_token_store_bytes(config)
    if token_bytes:
        token_store = _write_token_store(token_bytes)
    elif strict_token_mode:
        raise RuntimeError(
            "Garmin strict token-only mode is enabled, but no garmin.token_store_b64 is configured."
        )
    elif email and password:
        token_store = _local_token_store_path() or TOKEN_STORE_PATH

    clients = _candidate_clients(
        Garmin,
        email,
        password,
        allow_credentials=not strict_token_mode,
    )
    if not clients:
        raise RuntimeError("Unable to initialize Garmin API client.")

    for client in clients:
        if _login_variants(
            client,
            email,
            password,
            token_store,
            allow_credentials=not strict_token_mode,
            allow_default_login=not strict_token_mode,
        ):
            return client

    if strict_token_mode:
        raise RuntimeError(
            "Garmin authentication failed in strict token-only mode. "
            "Provide a valid garmin.token_store_b64 (or disable strict token-only mode)."
        )
    raise RuntimeError(
        "Garmin authentication failed. Provide valid garmin.token_store_b64 or garmin.email/password."
    )


def _fetch_page(client: Any, start: int, limit: int) -> List[Dict[str, Any]]:
    errors = []
    variants = [
        ("get_activities", (start, limit), {}),
        ("getActivities", (start, limit), {}),
    ]
    for method_name, args, kwargs in variants:
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            payload = method(*args, **kwargs)
        except Exception as exc:
            errors.append(f"{method_name}: {exc}")
            continue
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("activities")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            return []
        return []
    detail = "; ".join(errors) if errors else "no supported activities API method found"
    raise RuntimeError(f"Unable to fetch Garmin activities ({detail}).")


def _is_rate_limited_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    return "toomanyrequests" in name or "429" in text or "rate limit" in text


def _write_activity(activity: Dict[str, Any]) -> bool:
    activity_id = str(activity.get("id") or "").strip()
    if not activity_id:
        return False
    if activity_id in {".", ".."}:
        return False
    if "/" in activity_id or "\\" in activity_id or ".." in activity_id:
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


def _sync_recent(
    client: Any,
    per_page: int,
    recent_days: int,
    dry_run: bool,
    enrich_stats: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    if recent_days <= 0:
        return {
            "fetched": 0,
            "new_or_updated": 0,
            "oldest_ts": None,
            "newest_ts": None,
            "rate_limited": False,
            "rate_limit_message": "",
            "activity_ids": [],
        }

    after = int((utc_now() - timedelta(days=recent_days)).timestamp())
    offset = 0
    total = 0
    new_or_updated = 0
    oldest_ts = None
    newest_ts = None
    fetched_ids = set()
    rate_limited = False
    rate_limit_message = ""

    while True:
        try:
            activities = _fetch_page(client, offset, per_page)
        except Exception as exc:
            if _is_rate_limited_error(exc):
                rate_limited = True
                rate_limit_message = str(exc)
                break
            raise
        if not activities:
            break

        reached_boundary = False
        for raw_activity in activities:
            activity = _normalize_activity(raw_activity)
            if not activity:
                continue
            activity = _enrich_missing_duration(client, activity, enrich_stats)
            ts = _activity_start_ts(activity)
            if ts is not None and ts < after:
                reached_boundary = True
                continue
            total += 1
            if ts is not None:
                oldest_ts = ts if oldest_ts is None else min(oldest_ts, ts)
                newest_ts = ts if newest_ts is None else max(newest_ts, ts)
            fetched_ids.add(str(activity["id"]))
            if not dry_run and _write_activity(activity):
                new_or_updated += 1

        if reached_boundary or len(activities) < per_page:
            break
        offset += len(activities)

    return {
        "fetched": total,
        "new_or_updated": new_or_updated,
        "oldest_ts": oldest_ts,
        "newest_ts": newest_ts,
        "rate_limited": rate_limited,
        "rate_limit_message": rate_limit_message,
        "activity_ids": sorted(fetched_ids),
    }


def sync_garmin(dry_run: bool, prune_deleted: bool) -> Dict[str, Any]:
    config = load_config()
    sync_cfg = config.get("sync", {}) or {}
    per_page = int(sync_cfg.get("per_page", 200))
    after = _start_after_ts(config)
    activity_scope = _activity_scope(config)
    recent_days = int(sync_cfg.get("recent_days", 7))
    resume_backfill = bool(sync_cfg.get("resume_backfill", True))

    if not dry_run:
        _maybe_reset_for_new_account(config)

    client = _load_garmin_client(config)
    ensure_dir(RAW_DIR)

    enrich_stats: Dict[str, int] = {"duration_enriched": 0}
    recent_summary = _sync_recent(client, per_page, recent_days, dry_run, enrich_stats)

    total = 0
    new_or_updated = 0
    fetched_ids = set(recent_summary.get("activity_ids", []))
    min_ts = None
    max_ts = None
    exhausted = False
    skip_backfill = False
    rate_limited = bool(recent_summary.get("rate_limited"))
    rate_limit_message = str(recent_summary.get("rate_limit_message", ""))

    state = _load_state() if resume_backfill and not dry_run else {}
    if state:
        state_after = _safe_int(state.get("after"))
        if state_after != after:
            print("Backfill boundary changed; restarting Garmin cursor.")
            state = {}
        elif state.get("activity_scope") != activity_scope:
            print("Activity scope changed; restarting Garmin backfill cursor.")
            state = {}
        elif state.get("completed"):
            skip_backfill = True

    next_offset = _safe_int(state.get("next_offset")) if state else None
    if next_offset is None:
        next_offset = 0

    if not rate_limited and not skip_backfill:
        offset = next_offset
        while True:
            try:
                activities = _fetch_page(client, offset, per_page)
            except Exception as exc:
                if _is_rate_limited_error(exc):
                    rate_limited = True
                    rate_limit_message = str(exc)
                    break
                raise
            if not activities:
                exhausted = True
                break

            reached_boundary = False
            for raw_activity in activities:
                activity = _normalize_activity(raw_activity)
                if not activity:
                    continue
                activity = _enrich_missing_duration(client, activity, enrich_stats)
                ts = _activity_start_ts(activity)
                if ts is not None and ts < after:
                    reached_boundary = True
                    continue
                total += 1
                fetched_ids.add(str(activity["id"]))
                if ts is not None:
                    min_ts = ts if min_ts is None else min(min_ts, ts)
                    max_ts = ts if max_ts is None else max(max_ts, ts)
                if not dry_run and _write_activity(activity):
                    new_or_updated += 1

            offset += len(activities)
            next_offset = offset
            if reached_boundary or len(activities) < per_page:
                exhausted = True
                break

    can_prune_deleted = (
        prune_deleted
        and not dry_run
        and not skip_backfill
        and exhausted
        and not rate_limited
    )
    deleted = 0
    if can_prune_deleted:
        for filename in os.listdir(RAW_DIR):
            if not filename.endswith(".json"):
                continue
            activity_id = filename[:-5]
            if activity_id not in fetched_ids:
                os.remove(os.path.join(RAW_DIR, filename))
                deleted += 1
    elif prune_deleted and not dry_run:
        print(
            "Skipping prune_deleted for Garmin: pruning requires a full backfill scan in this run."
        )

    completed = True if skip_backfill else (exhausted and not rate_limited)
    if completed:
        next_offset = None

    if not dry_run:
        if skip_backfill and state:
            state_update = dict(state)
            state_update["completed"] = True
            state_update["rate_limited"] = rate_limited
            state_update["last_run_utc"] = utc_now().isoformat()
        else:
            state_update = {
                "after": after,
                "next_offset": next_offset,
                "completed": completed,
                "oldest_seen_ts": min_ts,
                "newest_seen_ts": max_ts,
                "rate_limited": rate_limited,
                "last_run_utc": utc_now().isoformat(),
            }
        state_update["activity_scope"] = activity_scope
        _save_state(state_update)

    total_fetched = total + int(recent_summary.get("fetched", 0))
    total_new_or_updated = new_or_updated + int(recent_summary.get("new_or_updated", 0))

    summary: Dict[str, Any] = {
        "source": "garmin",
        "fetched": total_fetched,
        "new_or_updated": total_new_or_updated,
        "deleted": deleted,
        "lookback_start_ts": after,
        "timestamp_utc": utc_now().isoformat(),
        "rate_limited": rate_limited,
        "backfill_completed": completed,
        "backfill_next_offset": next_offset,
        "duration_enriched": int(enrich_stats.get("duration_enriched", 0)),
        "recent_sync": recent_summary,
    }
    if rate_limited:
        summary["rate_limit_message"] = rate_limit_message
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Garmin activities")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prune-deleted",
        action="store_true",
        help="Remove local raw activities not returned by Garmin",
    )
    args = parser.parse_args()

    config = load_config()
    prune_deleted = args.prune_deleted or bool(config.get("sync", {}).get("prune_deleted", False))

    summary = sync_garmin(args.dry_run, prune_deleted)

    ensure_dir("data")
    if not args.dry_run:
        write_json(SUMMARY_JSON, summary)
        start_ts = summary.get("lookback_start_ts")
        if start_ts:
            start_label = datetime.fromtimestamp(start_ts, tz=timezone.utc).date().isoformat()
            range_label = f"start {start_label}"
        else:
            range_label = "start unknown"
        message = (
            f"Sync Garmin: {summary['new_or_updated']} new/updated, "
            f"{summary['deleted']} deleted ({range_label})"
        )
        if summary.get("duration_enriched"):
            message += f", {summary['duration_enriched']} durations enriched"
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
