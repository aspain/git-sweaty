from datetime import datetime, timezone
from typing import Any, Dict, Optional

from activity_types import featured_types_from_config


def lookback_after_ts(years: int) -> int:
    now = datetime.now(timezone.utc)
    try:
        start = now.replace(year=now.year - years)
    except ValueError:
        # handle Feb 29
        start = now.replace(month=2, day=28, year=now.year - years)
    return int(start.timestamp())


def start_after_ts(config: Dict[str, Any]) -> int:
    sync_cfg = config.get("sync", {})
    start_date = sync_cfg.get("start_date")
    if start_date:
        dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    lookback_years = sync_cfg.get("lookback_years")
    if lookback_years in (None, ""):
        return 0
    return lookback_after_ts(int(lookback_years))


def activity_scope_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    activities_cfg = config.get("activities", {}) or {}
    include_all_types = bool(activities_cfg.get("include_all_types", True))
    exclude_types = sorted({str(item) for item in (activities_cfg.get("exclude_types", []) or [])})
    scope: Dict[str, Any] = {
        "include_all_types": include_all_types,
        "exclude_types": exclude_types,
    }
    if include_all_types:
        return scope

    featured_types = sorted({str(item) for item in featured_types_from_config(activities_cfg)})
    type_aliases = {
        str(source): str(target)
        for source, target in (activities_cfg.get("type_aliases", {}) or {}).items()
    }
    group_aliases = {
        str(source): str(target)
        for source, target in (activities_cfg.get("group_aliases", {}) or {}).items()
    }
    scope.update(
        {
            "featured_types": featured_types,
            "group_other_types": bool(activities_cfg.get("group_other_types", True)),
            "other_bucket": str(activities_cfg.get("other_bucket", "OtherSports")),
            "type_aliases": dict(sorted(type_aliases.items())),
            "group_aliases": dict(sorted(group_aliases.items())),
        }
    )
    return scope


def activity_start_ts(activity: Dict[str, Any]) -> Optional[int]:
    value = activity.get("start_date") or activity.get("start_date_local")
    if not value:
        return None
    value_str = str(value)
    if value_str.endswith("Z"):
        value_str = value_str[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(value_str).timestamp())
    except ValueError:
        return None
