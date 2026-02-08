import argparse
import os
from collections import defaultdict

from utils import ensure_dir, load_config, read_json, utc_now, write_json

IN_PATH = "data/activities_normalized.json"
OUT_PATH = "data/daily_aggregates.json"


def aggregate():
    config = load_config()
    activities_cfg = config.get("activities", {}) or {}
    include_all_types = bool(activities_cfg.get("include_all_types", True))
    featured_types = set(activities_cfg.get("types", []) or [])

    items = read_json(IN_PATH) if os.path.exists(IN_PATH) else []

    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for item in items:
        activity_type = item.get("type")
        if not include_all_types and featured_types and activity_type not in featured_types:
            continue
        date = item.get("date")
        year = str(item.get("year"))
        if not date or not year:
            continue

        entry = data[year][activity_type].get(date)
        if not entry:
            entry = {
                "count": 0,
                "distance": 0.0,
                "moving_time": 0.0,
                "elevation_gain": 0.0,
                "activity_ids": [],
            }
        entry["count"] += 1
        entry["distance"] += float(item.get("distance", 0.0))
        entry["moving_time"] += float(item.get("moving_time", 0.0))
        entry["elevation_gain"] += float(item.get("elevation_gain", 0.0))
        entry["activity_ids"].append(item.get("id"))
        data[year][activity_type][date] = entry

    for year_data in data.values():
        for type_data in year_data.values():
            for entry in type_data.values():
                entry["activity_ids"] = sorted(entry["activity_ids"])

    output = {
        "generated_at": utc_now().isoformat(),
        "years": data,
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate normalized activities by day/type/year")
    args = parser.parse_args()

    ensure_dir("data")
    output = aggregate()
    write_json(OUT_PATH, output)
    years = list(output["years"].keys())
    print(f"Aggregated years: {', '.join(sorted(years))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
