import argparse
import hashlib
import hmac
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from utils import ensure_dir, load_config, read_json, utc_now, write_json

TOKEN_CACHE = ".strava_token.json"
RAW_DIR = os.path.join("activities", "raw")
SUMMARY_JSON = os.path.join("data", "last_sync_summary.json")
SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")
STATE_PATH = os.path.join("data", "backfill_state.json")
ATHLETE_PATH = os.path.join("data", "athletes.json")


class RateLimitExceeded(RuntimeError):
    pass


class RateLimiter:
    def __init__(
        self,
        overall_15_limit: int,
        overall_day_limit: int,
        read_15_limit: int,
        read_day_limit: int,
        safety_buffer: int,
        min_interval_seconds: float,
    ) -> None:
        self.overall_15_limit = overall_15_limit
        self.overall_day_limit = overall_day_limit
        self.read_15_limit = read_15_limit
        self.read_day_limit = read_day_limit
        self.safety_buffer = max(0, safety_buffer)
        self.min_interval_seconds = max(0.0, min_interval_seconds)

        self.window_start = time.time()
        self.day_start = datetime.now(timezone.utc).date()

        self.overall_15 = 0
        self.overall_day = 0
        self.read_15 = 0
        self.read_day = 0
        self.last_request_at = 0.0

    def _reset_if_needed(self) -> None:
        now = time.time()
        if now - self.window_start >= 900:
            self.window_start = now
            self.overall_15 = 0
            self.read_15 = 0

        current_day = datetime.now(timezone.utc).date()
        if current_day != self.day_start:
            self.day_start = current_day
            self.overall_day = 0
            self.read_day = 0

    def _sleep_until_window_reset(self) -> None:
        now = time.time()
        remaining = 900 - (now - self.window_start)
        if remaining > 0:
            time.sleep(remaining)
        self._reset_if_needed()

    def before_request(self, kind: str) -> None:
        self._reset_if_needed()

        if self.min_interval_seconds > 0 and self.last_request_at:
            elapsed = time.time() - self.last_request_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
                self._reset_if_needed()

        if self.overall_15 >= self.overall_15_limit - self.safety_buffer:
            self._sleep_until_window_reset()

        if kind == "read" and self.read_15 >= self.read_15_limit - self.safety_buffer:
            self._sleep_until_window_reset()

        if self.overall_day >= self.overall_day_limit - self.safety_buffer:
            raise RateLimitExceeded("Overall daily limit reached; try again after UTC midnight.")

        if kind == "read" and self.read_day >= self.read_day_limit - self.safety_buffer:
            raise RateLimitExceeded("Read daily limit reached; try again after UTC midnight.")

    def record_request(self, kind: str) -> None:
        self._reset_if_needed()
        self.overall_15 += 1
        self.overall_day += 1
        if kind == "read":
            self.read_15 += 1
            self.read_day += 1
        self.last_request_at = time.time()

    def apply_headers(self, headers: Dict[str, str]) -> None:
        def _parse_pair(value: Optional[str]) -> Optional[Tuple[int, int]]:
            if not value:
                return None
            parts = [p.strip() for p in value.split(",")]
            if len(parts) < 2:
                return None
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                return None

        overall_limit = _parse_pair(headers.get("X-RateLimit-Limit"))
        overall_usage = _parse_pair(headers.get("X-RateLimit-Usage"))
        if overall_limit and overall_usage:
            limit_15, limit_day = overall_limit
            usage_15, usage_day = overall_usage
            self.overall_15_limit = limit_15
            self.overall_day_limit = limit_day
            self.overall_15 = max(self.overall_15, usage_15)
            self.overall_day = max(self.overall_day, usage_day)

        read_limit = _parse_pair(headers.get("X-ReadRateLimit-Limit"))
        read_usage = _parse_pair(headers.get("X-ReadRateLimit-Usage"))
        if read_limit and read_usage:
            limit_15, limit_day = read_limit
            usage_15, usage_day = read_usage
            self.read_15_limit = limit_15
            self.read_day_limit = limit_day
            self.read_15 = max(self.read_15, usage_15)
            self.read_day = max(self.read_day, usage_day)


def _load_token_cache() -> Dict:
    if not os.path.exists(TOKEN_CACHE):
        return {}
    try:
        return read_json(TOKEN_CACHE)
    except Exception:
        return {}


def _save_token_cache(payload: Dict) -> None:
    write_json(TOKEN_CACHE, payload)


def _load_athlete_fingerprint() -> Optional[str]:
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


def _write_athlete_fingerprint(fingerprint: str) -> None:
    ensure_dir("data")
    write_json(
        ATHLETE_PATH,
        {
            "fingerprint": fingerprint,
            "updated_utc": utc_now().isoformat(),
            "version": 1,
        },
    )


def _athlete_fingerprint(athlete_id: int, secret: str) -> str:
    key = (secret or "").encode("utf-8")
    msg = str(athlete_id).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _get_access_token(config: Dict, limiter: Optional[RateLimiter]) -> str:
    strava = config.get("strava", {})
    client_id = strava.get("client_id")
    client_secret = strava.get("client_secret")
    refresh_token = strava.get("refresh_token")
    if not client_id or not client_secret or not refresh_token:
        raise ValueError("Missing Strava credentials in config.yaml/config.local.yaml")

    cache = _load_token_cache()
    now = int(utc_now().timestamp())
    access_token = cache.get("access_token")
    expires_at = cache.get("expires_at", 0)

    if access_token and expires_at - 60 > now:
        return access_token

    if limiter:
        limiter.before_request("overall")
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if limiter:
        limiter.record_request("overall")
        limiter.apply_headers(resp.headers)
    resp.raise_for_status()
    payload = resp.json()
    _save_token_cache(payload)
    return payload["access_token"]


def _fetch_athlete(token: str, limiter: Optional[RateLimiter]) -> Dict:
    if limiter:
        limiter.before_request("read")
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if limiter:
        limiter.record_request("read")
        limiter.apply_headers(resp.headers)
    resp.raise_for_status()
    return resp.json()


def _lookback_after_ts(years: int) -> int:
    now = datetime.now(timezone.utc)
    try:
        start = now.replace(year=now.year - years)
    except ValueError:
        # handle Feb 29
        start = now.replace(month=2, day=28, year=now.year - years)
    return int(start.timestamp())


def _start_after_ts(config: Dict) -> int:
    sync_cfg = config.get("sync", {})
    start_date = sync_cfg.get("start_date")
    if start_date:
        dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    lookback_years = sync_cfg.get("lookback_years")
    if lookback_years in (None, ""):
        # Default: no lower bound, so Strava backfill can reach all available history.
        return 0
    return _lookback_after_ts(int(lookback_years))


def _activity_start_ts(activity: Dict) -> Optional[int]:
    value = activity.get("start_date") or activity.get("start_date_local")
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def _fetch_page(
    token: str,
    per_page: int,
    page: int,
    after: int,
    before: Optional[int],
    limiter: Optional[RateLimiter],
) -> List[Dict]:
    if limiter:
        limiter.before_request("read")
    params = {"per_page": per_page, "page": page, "after": after}
    if before is not None:
        params["before"] = before
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if limiter:
        limiter.record_request("read")
        limiter.apply_headers(resp.headers)
    resp.raise_for_status()
    return resp.json()


def _load_existing_activity_ids() -> set:
    path = os.path.join("data", "activities_normalized.json")
    if not os.path.exists(path):
        return set()
    try:
        items = read_json(path) or []
    except Exception:
        return set()
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        activity_id = item.get("id")
        if activity_id is None:
            continue
        ids.add(str(activity_id))
    return ids


def _has_existing_data() -> bool:
    candidates = [
        os.path.join("data", "activities_normalized.json"),
        os.path.join("data", "daily_aggregates.json"),
        os.path.join("data", "backfill_state.json"),
        os.path.join("data", "last_sync_summary.json"),
        os.path.join("data", "last_sync_summary.txt"),
        os.path.join("site", "data.json"),
        "heatmaps",
    ]
    for path in candidates:
        if os.path.exists(path):
            return True
    return False


def _reset_persisted_data() -> None:
    paths = [
        os.path.join("data", "activities_normalized.json"),
        os.path.join("data", "daily_aggregates.json"),
        os.path.join("data", "backfill_state.json"),
        os.path.join("data", "last_sync_summary.json"),
        os.path.join("data", "last_sync_summary.txt"),
        os.path.join("site", "data.json"),
    ]
    for path in paths:
        if os.path.exists(path):
            os.remove(path)

    for dir_path in ["heatmaps", RAW_DIR]:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)


def _fetch_recent_activity_ids(
    token: str, per_page: int, limiter: Optional[RateLimiter]
) -> Optional[List[str]]:
    try:
        activities = _fetch_page(token, min(per_page, 50), 1, 0, None, limiter)
    except Exception:
        return None
    activity_ids = []
    for activity in activities or []:
        activity_id = activity.get("id")
        if activity_id:
            activity_ids.append(str(activity_id))
    return activity_ids


def _maybe_reset_for_new_athlete(
    config: Dict, token: str, per_page: int, limiter: Optional[RateLimiter]
) -> None:
    strava = config.get("strava", {}) or {}
    secret = strava.get("client_secret") or strava.get("refresh_token") or ""
    if not secret:
        return

    try:
        athlete = _fetch_athlete(token, limiter)
    except Exception as exc:
        print(f"Warning: unable to fetch athlete profile; skipping reset ({exc})")
        return
    athlete_id = athlete.get("id")
    if athlete_id is None:
        print("Warning: athlete profile missing id; skipping reset")
        return

    current_fingerprint = _athlete_fingerprint(int(athlete_id), secret)
    stored_fingerprint = _load_athlete_fingerprint()

    if stored_fingerprint and stored_fingerprint == current_fingerprint:
        return

    if stored_fingerprint and stored_fingerprint != current_fingerprint:
        print("Detected different athlete; resetting persisted data.")
        _reset_persisted_data()
        _write_athlete_fingerprint(current_fingerprint)
        return

    if not _has_existing_data():
        _write_athlete_fingerprint(current_fingerprint)
        return

    recent_ids = _fetch_recent_activity_ids(token, per_page, limiter)
    if recent_ids is None:
        print("Warning: unable to verify recent activity overlap; skipping reset")
        return

    existing_ids = _load_existing_activity_ids()
    if recent_ids and any(activity_id in existing_ids for activity_id in recent_ids):
        _write_athlete_fingerprint(current_fingerprint)
        return

    print("No athlete fingerprint found and data does not match; resetting persisted data.")
    _reset_persisted_data()
    _write_athlete_fingerprint(current_fingerprint)


def _write_activity(activity: Dict) -> bool:
    activity_id = activity.get("id")
    if not activity_id:
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


def _load_state() -> Dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        return read_json(STATE_PATH)
    except Exception:
        return {}


def _save_state(state: Dict) -> None:
    ensure_dir("data")
    write_json(STATE_PATH, state)


def _sync_recent(
    token: str,
    per_page: int,
    recent_days: int,
    limiter: RateLimiter,
    dry_run: bool,
) -> Dict:
    if recent_days <= 0:
        return {
            "fetched": 0,
            "new_or_updated": 0,
            "oldest_ts": None,
            "newest_ts": None,
            "rate_limited": False,
            "rate_limit_message": "",
        }

    after = int((utc_now() - timedelta(days=recent_days)).timestamp())
    page = 1
    total = 0
    new_or_updated = 0
    oldest_ts = None
    newest_ts = None
    rate_limited = False
    rate_limit_message = ""
    activity_ids = set()

    while True:
        try:
            activities = _fetch_page(token, per_page, page, after, None, limiter)
        except RateLimitExceeded as exc:
            rate_limited = True
            rate_limit_message = str(exc)
            break
        if not activities:
            break
        for activity in activities:
            total += 1
            ts = _activity_start_ts(activity)
            if ts is not None:
                oldest_ts = ts if oldest_ts is None else min(oldest_ts, ts)
                newest_ts = ts if newest_ts is None else max(newest_ts, ts)
            activity_id = activity.get("id")
            if activity_id:
                activity_ids.add(str(activity_id))
            if dry_run:
                continue
            if _write_activity(activity):
                new_or_updated += 1
        page += 1

    return {
        "fetched": total,
        "new_or_updated": new_or_updated,
        "oldest_ts": oldest_ts,
        "newest_ts": newest_ts,
        "rate_limited": rate_limited,
        "rate_limit_message": rate_limit_message,
        "activity_ids": sorted(activity_ids),
    }


def sync_strava(dry_run: bool, prune_deleted: bool) -> Dict:
    config = load_config()
    rate_cfg = config.get("rate_limits", {}) or {}
    limiter = RateLimiter(
        overall_15_limit=int(rate_cfg.get("overall_15_min", 200)),
        overall_day_limit=int(rate_cfg.get("overall_daily", 2000)),
        read_15_limit=int(rate_cfg.get("read_15_min", 100)),
        read_day_limit=int(rate_cfg.get("read_daily", 1000)),
        safety_buffer=int(rate_cfg.get("safety_buffer", 2)),
        min_interval_seconds=float(rate_cfg.get("min_interval_seconds", 10)),
    )
    per_page = int(config.get("sync", {}).get("per_page", 200))
    after = _start_after_ts(config)
    recent_days = int(config.get("sync", {}).get("recent_days", 7))
    resume_backfill = bool(config.get("sync", {}).get("resume_backfill", True))

    token = _get_access_token(config, limiter)
    if not dry_run:
        _maybe_reset_for_new_athlete(config, token, per_page, limiter)

    ensure_dir(RAW_DIR)

    recent_summary = _sync_recent(token, per_page, recent_days, limiter, dry_run)

    page = 1
    total = 0
    new_or_updated = 0
    fetched_ids = set(recent_summary.get("activity_ids", []))
    min_ts = None
    max_ts = None
    exhausted = False
    before = None
    skip_backfill = False

    state = _load_state() if resume_backfill and not dry_run else {}
    if state:
        state_after = state.get("after")
        try:
            state_after = int(state_after)
        except (TypeError, ValueError):
            state_after = None
        if state_after != after:
            print("Backfill boundary changed; restarting cursor.")
            state = {}
    if state and state.get("completed"):
        skip_backfill = True
    elif state and state.get("after") == after and state.get("next_before") is not None:
        before = int(state["next_before"])

    if before is None and not skip_backfill:
        before = int(utc_now().timestamp())

    rate_limited = bool(recent_summary.get("rate_limited"))
    rate_limit_message = recent_summary.get("rate_limit_message", "")

    if not rate_limited and not skip_backfill:
        while True:
            try:
                activities = _fetch_page(token, per_page, page, after, before, limiter)
            except RateLimitExceeded as exc:
                rate_limited = True
                rate_limit_message = str(exc)
                break
            if not activities:
                exhausted = True
                break
            for activity in activities:
                total += 1
                activity_id = activity.get("id")
                if activity_id:
                    fetched_ids.add(str(activity_id))
                ts = _activity_start_ts(activity)
                if ts is not None:
                    min_ts = ts if min_ts is None else min(min_ts, ts)
                    max_ts = ts if max_ts is None else max(max_ts, ts)
                if dry_run:
                    continue
                if _write_activity(activity):
                    new_or_updated += 1
            page += 1

    deleted = 0
    if prune_deleted and not dry_run:
        for filename in os.listdir(RAW_DIR):
            if not filename.endswith(".json"):
                continue
            activity_id = filename[:-5]
            if activity_id not in fetched_ids:
                os.remove(os.path.join(RAW_DIR, filename))
                deleted += 1

    completed = True if skip_backfill else (exhausted and not rate_limited)
    next_before = None
    if not completed and min_ts is not None:
        next_before = int(min_ts + 1)

    if not dry_run:
        if skip_backfill and state:
            state_update = dict(state)
            state_update["completed"] = True
            state_update["rate_limited"] = rate_limited
            state_update["last_run_utc"] = utc_now().isoformat()
        elif rate_limited and min_ts is None and state:
            state_update = dict(state)
            state_update["rate_limited"] = True
            state_update["last_run_utc"] = utc_now().isoformat()
        else:
            state_update = {
                "after": after,
                "next_before": next_before,
                "completed": completed,
                "oldest_seen_ts": min_ts,
                "newest_seen_ts": max_ts,
                "rate_limited": rate_limited,
                "last_run_utc": utc_now().isoformat(),
            }
        _save_state(state_update)

    total_fetched = total + int(recent_summary.get("fetched", 0))
    total_new_or_updated = new_or_updated + int(recent_summary.get("new_or_updated", 0))

    summary = {
        "fetched": total_fetched,
        "new_or_updated": total_new_or_updated,
        "deleted": deleted,
        "lookback_start_ts": after,
        "timestamp_utc": utc_now().isoformat(),
        "rate_limited": rate_limited,
        "backfill_completed": completed,
        "backfill_next_before": next_before,
        "recent_sync": recent_summary,
    }
    if rate_limited:
        summary["rate_limit_message"] = rate_limit_message
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Strava activities")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prune-deleted",
        action="store_true",
        help="Remove local raw activities not returned by Strava",
    )
    args = parser.parse_args()

    config = load_config()
    prune_deleted = args.prune_deleted or bool(
        config.get("sync", {}).get("prune_deleted", False)
    )

    summary = sync_strava(args.dry_run, prune_deleted)

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
            f"Sync Strava: {summary['new_or_updated']} new/updated, "
            f"{summary['deleted']} deleted ({range_label})"
        )
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
