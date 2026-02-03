import argparse
import os
from datetime import datetime
from typing import Dict, List

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


def normalize() -> List[Dict]:
    config = load_config()
    type_aliases = config.get("activities", {}).get("type_aliases", {}) or {}
    allowed_types = set(config.get("activities", {}).get("types", []) or [])

    items: List[Dict] = []
    if not os.path.exists(RAW_DIR):
        return items

    for filename in sorted(os.listdir(RAW_DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(RAW_DIR, filename)
        activity = read_json(path)
        normalized = _normalize_activity(activity, type_aliases)
        if not normalized:
            continue
        if allowed_types and normalized["type"] not in allowed_types:
            continue
        items.append(normalized)

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
