import argparse
import os
from typing import Any, Dict, List

from activity_types import canonicalize_activity_type, featured_types_from_config, normalize_activity_type
from provider_fields import (
    coalesce as _shared_coalesce,
    get_nested as _shared_get_nested,
    pick_duration_seconds as _shared_pick_duration_seconds,
)
from utils import ensure_dir, load_config, normalize_source, parse_iso_datetime, raw_activity_dir, read_json, write_json

OUT_PATH = os.path.join("data", "activities_normalized.json")


def _coalesce(*values: Any) -> Any:
    return _shared_coalesce(*values)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pick_duration_seconds(*values: Any) -> float:
    return _shared_pick_duration_seconds(*values)


def _duration_candidates(activity: Dict[str, Any]) -> List[Any]:
    return [
        activity.get("moving_time"),
        activity.get("movingDuration"),
        activity.get("duration"),
        activity.get("elapsedDuration"),
        activity.get("elapsed_time"),
        activity.get("elapsedTime"),
        _get_nested(activity, ["summaryDTO", "movingDuration"]),
        _get_nested(activity, ["summaryDTO", "duration"]),
        _get_nested(activity, ["summaryDTO", "elapsedDuration"]),
        _get_nested(activity, ["activitySummary", "movingDuration"]),
        _get_nested(activity, ["activitySummary", "duration"]),
        _get_nested(activity, ["activitySummary", "elapsedDuration"]),
    ]


def _get_nested(payload: Dict[str, Any], keys: List[str]) -> Any:
    return _shared_get_nested(payload, keys)


def _resolve_canonical_type(raw_value: str, source: str) -> str:
    return canonicalize_activity_type(raw_value, source=source)


def _normalize_activity(activity: Dict, type_aliases: Dict[str, str], source: str) -> Dict:
    activity_id = _coalesce(activity.get("id"), activity.get("activityId"))
    start_date_local = activity.get("start_date_local") or activity.get("start_date")
    if not activity_id or not start_date_local:
        return {}

    dt = parse_iso_datetime(str(start_date_local).replace(" ", "T"))
    date_str = dt.strftime("%Y-%m-%d")
    year = dt.year

    raw_activity_type = str(
        _coalesce(
            activity.get("type"),
            _get_nested(activity, ["activityType", "typeKey"]),
            _get_nested(activity, ["activityTypeDTO", "typeKey"]),
            activity.get("activityType"),
            "Unknown",
        )
    )
    raw_type = str(activity.get("sport_type") or raw_activity_type or "Unknown")
    canonical_raw_type = _resolve_canonical_type(raw_type, source)
    activity_type = type_aliases.get(raw_type, type_aliases.get(canonical_raw_type, canonical_raw_type))

    # Override type to Commute if marked as commute
    if activity.get("commute"):
        activity_type = "Commute"

    distance = _coalesce(activity.get("distance"), activity.get("totalDistance"))
    moving_time = _pick_duration_seconds(*_duration_candidates(activity))
    elevation_gain = _coalesce(
        activity.get("total_elevation_gain"),
        activity.get("elevationGain"),
        activity.get("totalElevationGain"),
    )
    activity_name = str(_coalesce(activity.get("name"), activity.get("activityName"), "") or "").strip()

    normalized = {
        "id": str(activity_id),
        "start_date_local": str(start_date_local).replace(" ", "T"),
        "date": date_str,
        "year": year,
        "raw_activity_type": raw_activity_type,
        "raw_type": raw_type,
        "type": activity_type,
        "is_commute": bool(activity.get("commute")),
        "distance": _safe_float(distance),
        "moving_time": _safe_float(moving_time),
        "elevation_gain": _safe_float(elevation_gain),
    }
    if activity_name:
        normalized["name"] = activity_name
    return normalized


def _load_existing() -> Dict[str, Dict]:
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        existing_items = read_json(OUT_PATH)
    except Exception:
        return {}
    existing: Dict[str, Dict] = {}
    for item in existing_items or []:
        if not isinstance(item, dict):
            continue
        activity_id = item.get("id")
        if activity_id is None:
            continue
        existing[str(activity_id)] = item
    return existing


def normalize() -> List[Dict]:
    config = load_config()
    source = normalize_source(config.get("source", "strava"))
    activities_cfg = config.get("activities", {}) or {}
    type_aliases = activities_cfg.get("type_aliases", {}) or {}
    featured_types = featured_types_from_config(activities_cfg)
    include_all_types = bool(activities_cfg.get("include_all_types", True))
    exclude_types = {str(item) for item in (activities_cfg.get("exclude_types", []) or [])}
    group_other_types = bool(activities_cfg.get("group_other_types", True))
    other_bucket = str(activities_cfg.get("other_bucket", "OtherSports"))
    group_aliases = activities_cfg.get("group_aliases", {}) or {}
    featured_set = set(featured_types)

    # In CI, activities/raw is ephemeral per run, so keep persisted normalized
    # history and overlay any newly fetched raw activities.
    existing = _load_existing()

    raw_dirs = [raw_activity_dir(source)]
    # Backward compatibility for old Strava layout (activities/raw/*.json).
    legacy_raw_dir = os.path.join("activities", "raw")
    if source == "strava" and os.path.isdir(legacy_raw_dir):
        raw_dirs.append(legacy_raw_dir)

    for current_raw_dir in raw_dirs:
        if not os.path.exists(current_raw_dir):
            continue
        for filename in sorted(os.listdir(current_raw_dir)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(current_raw_dir, filename)
            if not os.path.isfile(path):
                continue
            activity = read_json(path)
            normalized = _normalize_activity(activity, type_aliases, source)
            if not normalized:
                continue
            normalized_type = normalize_activity_type(
                normalized.get("type"),
                featured_types=featured_types,
                group_other_types=group_other_types,
                other_bucket=other_bucket,
                group_aliases=group_aliases,
            )
            normalized["type"] = normalized_type
            if normalized_type in exclude_types:
                continue
            if not include_all_types and normalized_type not in featured_set:
                continue
            existing[str(normalized["id"])] = normalized

    items = [
        item
        for item in existing.values()
        if item.get("id") is not None and item.get("date")
    ]
    for item in items:
        raw_activity_type = str(item.get("raw_activity_type") or item.get("raw_type") or item.get("type") or other_bucket)
        raw_type = str(item.get("raw_type") or raw_activity_type or other_bucket)
        item["raw_activity_type"] = raw_activity_type
        item["raw_type"] = raw_type

        # Preserve commute override: commute is a flag, not a sport type
        if item.get("is_commute") and "Commute" in featured_set:
            item["type"] = "Commute"
            continue

        canonical_raw_type = _resolve_canonical_type(raw_type, source)
        source_type = type_aliases.get(raw_type, type_aliases.get(canonical_raw_type, canonical_raw_type))
        item["type"] = normalize_activity_type(
            source_type,
            featured_types=featured_types,
            group_other_types=group_other_types,
            other_bucket=other_bucket,
            group_aliases=group_aliases,
        )
    if exclude_types:
        items = [item for item in items if item.get("type") not in exclude_types]
    if not include_all_types:
        items = [item for item in items if item.get("type") in featured_set]
    items.sort(key=lambda x: (x["date"], x["id"]))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize raw activities")
    parser.parse_args()

    ensure_dir("data")
    items = normalize()
    write_json(OUT_PATH, items)
    print(f"Wrote {len(items)} normalized activities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
