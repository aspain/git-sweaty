import argparse
import os
from datetime import datetime
from typing import Dict, List

from activity_types import featured_types_from_config, normalize_activity_type
from utils import ensure_dir, load_config, read_json, write_json

RAW_DIR = os.path.join("activities", "raw")
OUT_PATH = os.path.join("data", "activities_normalized.json")


def _parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        # fallback: strip fractional seconds
        if "." in value:
            base, rest = value.split(".", 1)
            if "+" in rest:
                tz = "+" + rest.split("+", 1)[1]
            elif "-" in rest:
                tz = "-" + rest.split("-", 1)[1]
            else:
                tz = ""
            return datetime.fromisoformat(base + tz)
        raise


def _normalize_activity(activity: Dict, type_aliases: Dict[str, str]) -> Dict:
    activity_id = activity.get("id")
    start_date_local = activity.get("start_date_local") or activity.get("start_date")
    if not activity_id or not start_date_local:
        return {}

    dt = _parse_datetime(start_date_local)
    date_str = dt.strftime("%Y-%m-%d")
    year = dt.year

    raw_type = activity.get("type") or "Unknown"
    activity_type = type_aliases.get(raw_type, raw_type)

    return {
        "id": activity_id,
        "start_date_local": start_date_local,
        "date": date_str,
        "year": year,
        "type": activity_type,
        "distance": float(activity.get("distance", 0.0)),
        "moving_time": float(activity.get("moving_time", 0.0)),
        "elevation_gain": float(activity.get("total_elevation_gain", 0.0)),
    }


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
    activities_cfg = config.get("activities", {}) or {}
    type_aliases = activities_cfg.get("type_aliases", {}) or {}
    featured_types = featured_types_from_config(activities_cfg)
    include_all_types = bool(activities_cfg.get("include_all_types", True))
    group_other_types = bool(activities_cfg.get("group_other_types", True))
    other_bucket = str(activities_cfg.get("other_bucket", "OtherSports"))
    group_aliases = activities_cfg.get("group_aliases", {}) or {}
    featured_set = set(featured_types)

<<<<<<< HEAD
=======
    # In CI, activities/raw is ephemeral per run, so keep persisted normalized
    # history and overlay any newly fetched raw activities.
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
    existing = _load_existing()

    if os.path.exists(RAW_DIR):
        for filename in sorted(os.listdir(RAW_DIR)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(RAW_DIR, filename)
            activity = read_json(path)
            normalized = _normalize_activity(activity, type_aliases)
            if not normalized:
                continue
<<<<<<< HEAD
            if allowed_types and normalized["type"] not in allowed_types:
=======
            normalized_type = normalize_activity_type(
                normalized.get("type"),
                featured_types=featured_types,
                group_other_types=group_other_types,
                other_bucket=other_bucket,
                group_aliases=group_aliases,
            )
            normalized["type"] = normalized_type
            if not include_all_types and normalized_type not in featured_set:
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
                continue
            existing[str(normalized["id"])] = normalized

    items = [
        item
        for item in existing.values()
        if item.get("id") is not None and item.get("date")
    ]
<<<<<<< HEAD
    if allowed_types:
        items = [item for item in items if item.get("type") in allowed_types]
=======
    for item in items:
        item["type"] = normalize_activity_type(
            item.get("type"),
            featured_types=featured_types,
            group_other_types=group_other_types,
            other_bucket=other_bucket,
            group_aliases=group_aliases,
        )
    if not include_all_types:
        items = [item for item in items if item.get("type") in featured_set]
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
    items.sort(key=lambda x: (x["date"], x["id"]))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize raw Strava activities")
    args = parser.parse_args()

    ensure_dir("data")
    items = normalize()
    write_json(OUT_PATH, items)
    print(f"Wrote {len(items)} normalized activities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
