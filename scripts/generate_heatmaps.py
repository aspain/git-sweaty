import argparse
import os
from datetime import date, timedelta
from typing import Dict, List

from utils import (
    ensure_dir,
    format_distance,
    format_duration,
    format_elevation,
    load_config,
    read_json,
    utc_now,
    write_json,
)

AGG_PATH = os.path.join("data", "daily_aggregates.json")
README_PATH = "README.md"
SITE_DATA_PATH = os.path.join("site", "data.json")

CELL = 12
GAP = 2
PADDING = 16
LABEL_LEFT = 36
LABEL_TOP = 20

DEFAULT_COLORS = ["#1f2937", "#374151", "#4b5563", "#6b7280", "#9ca3af"]
TYPE_COLORS = {
    "Run": ["#1f2937", "#0a3d4d", "#0e5c6e", "#128a9e", "#01cdfe"],
    "Ride": ["#1f2937", "#0a3d2d", "#0e5c45", "#12a06a", "#05ffa1"],
    "WeightTraining": ["#1f2937", "#4d1a3d", "#7a2960", "#b84090", "#ff71ce"],
}
LABEL_COLOR = "#cbd5e1"
TEXT_COLOR = "#e5e7eb"
BG_COLOR = "#0f172a"
STROKE_COLOR = "#0f172a"


def _year_range_from_config(config: Dict) -> List[int]:
    sync_cfg = config.get("sync", {})
    current_year = utc_now().year
    start_date = sync_cfg.get("start_date")
    if start_date:
        try:
            start_year = int(start_date.split("-")[0])
        except (ValueError, IndexError):
            start_year = current_year
    else:
        lookback_years = int(sync_cfg.get("lookback_years", 5))
        start_year = current_year - lookback_years + 1
    return list(range(start_year, current_year + 1))


def _monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _sunday_on_or_after(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()))


def _distance_to_level(distance_meters: float, thresholds: Dict, unit: str) -> int:
    if not thresholds or all(v == 0 for v in thresholds.values()):
        return 4 if distance_meters > 0 else 0

    if unit == "km":
        distance = distance_meters / 1000.0
    else:
        distance = distance_meters / 1609.344

    level_1 = thresholds.get("level_1", 0)
    level_2 = thresholds.get("level_2", 0)
    level_3 = thresholds.get("level_3", 0)
    level_4 = thresholds.get("level_4", 0)

    if distance >= level_4:
        return 4
    elif distance >= level_3:
        return 3
    elif distance >= level_2:
        return 2
    elif distance >= level_1:
        return 1
    elif distance > 0:
        return 1
    return 0


def _level(count: int, distance: float, thresholds: Dict, unit: str) -> int:
    if count == 0:
        return 0
    return _distance_to_level(distance, thresholds, unit)


def _build_title(date_str: str, entry: Dict, units: Dict[str, str]) -> str:
    count = entry.get("count", 0)
    distance = format_distance(entry.get("distance", 0.0), units["distance"])
    duration = format_duration(entry.get("moving_time", 0.0))
    elevation = format_elevation(entry.get("elevation_gain", 0.0), units["elevation"])

    return (
        f"{date_str}\n"
        f"{count} workout{'s' if count != 1 else ''}\n"
        f"Distance: {distance}\n"
        f"Duration: {duration}\n"
        f"Elevation: {elevation}"
    )


def _svg_for_year(
    activity_type: str,
    year: int,
    entries: Dict[str, Dict],
    units: Dict[str, str],
    distance_thresholds: Dict,
) -> str:
    start = _monday_on_or_before(date(year, 1, 1))
    end = _sunday_on_or_after(date(year, 12, 31))

    weeks = ((end - start).days // 7) + 1
    width = weeks * (CELL + GAP) + PADDING * 2 + LABEL_LEFT
    height = 7 * (CELL + GAP) + PADDING * 2 + LABEL_TOP

    grid_x = PADDING + LABEL_LEFT
    grid_y = PADDING + LABEL_TOP

    colors = TYPE_COLORS.get(activity_type, DEFAULT_COLORS)

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'  # noqa: E501
    )
    lines.append(
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>'
    )
    lines.append(
        f'<text x="{PADDING}" y="{PADDING + 12}" font-size="12" fill="{TEXT_COLOR}" font-family="Arial, sans-serif">{year}</text>'
    )

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for month in range(1, 13):
        first_day = date(year, month, 1)
        week_index = (first_day - start).days // 7
        x = grid_x + week_index * (CELL + GAP)
        lines.append(
            f'<text x="{x}" y="{PADDING + 12}" font-size="10" fill="{LABEL_COLOR}" font-family="Arial, sans-serif">{month_labels[month - 1]}</text>'
        )

    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for row, label in enumerate(day_labels):
        y = grid_y + row * (CELL + GAP) + CELL - 2
        x = PADDING + LABEL_LEFT - 6
        lines.append(
            f'<text x="{x}" y="{y}" font-size="9" fill="{LABEL_COLOR}" font-family="Arial, sans-serif" text-anchor="end">{label}</text>'
        )

    lines.append(f'<g transform="translate({grid_x},{grid_y})">')

    current = start
    while current <= end:
        week_index = (current - start).days // 7
        row = current.weekday()  # Monday=0
        x = week_index * (CELL + GAP)
        y = row * (CELL + GAP)

        in_year = current.year == year
        date_str = current.isoformat()

        if in_year:
            entry = entries.get(date_str, {
                "count": 0,
                "distance": 0.0,
                "moving_time": 0.0,
                "elevation_gain": 0.0,
                "activity_ids": [],
            })
            count = int(entry.get("count", 0))
            distance = float(entry.get("distance", 0.0))
            level = _level(count, distance, distance_thresholds, units["distance"])
            color = colors[level]
            title = _build_title(date_str, entry, units)
        else:
            color = BG_COLOR
            title = None

        rect = (
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'fill="{color}" stroke="{STROKE_COLOR}" stroke-width="1"/>'
        )

        if title:
            rect = rect[:-2] + f' data-date="{date_str}"><title>{title}</title></rect>'

        lines.append(rect)
        current += timedelta(days=1)

    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _readme_section(types: List[str], years_desc: List[int]) -> str:
    lines = []
    lines.append("![Run 2025](heatmaps/Run/2025.svg)")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _update_readme(types: List[str], years_desc: List[int]) -> None:
    if not os.path.exists(README_PATH):
        return
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = "<!-- HEATMAPS:START -->"
    end_tag = "<!-- HEATMAPS:END -->"
    section = _readme_section(types, years_desc)

    if start_tag in content and end_tag in content:
        before, rest = content.split(start_tag, 1)
        _, after = rest.split(end_tag, 1)
        new_content = before + start_tag + "\n" + section + end_tag + after
    else:
        new_content = content.rstrip() + "\n\n" + start_tag + "\n" + section + end_tag + "\n"

    updated_tag_start = "<!-- UPDATED:START -->"
    updated_tag_end = "<!-- UPDATED:END -->"
    updated_value = utc_now().strftime("%Y-%m-%d %H:%M UTC")
    if updated_tag_start in new_content and updated_tag_end in new_content:
        before, rest = new_content.split(updated_tag_start, 1)
        _, after = rest.split(updated_tag_end, 1)
        new_content = before + updated_tag_start + updated_value + updated_tag_end + after

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


def _write_site_data(payload: Dict) -> None:
    ensure_dir("site")
    write_json(SITE_DATA_PATH, payload)


def generate():
    config = load_config()
    activities_cfg = config.get("activities", {})
    types = activities_cfg.get("types", []) or []
    distance_levels = activities_cfg.get("distance_levels", {})

    units = config.get("units", {})
    units = {
        "distance": units.get("distance", "mi"),
        "elevation": units.get("elevation", "ft"),
    }

    aggregates = read_json(AGG_PATH)
    years = _year_range_from_config(config)

    for activity_type in types:
        type_dir = os.path.join("heatmaps", activity_type)
        ensure_dir(type_dir)
        thresholds = distance_levels.get(activity_type, {})
        for year in years:
            year_entries = (
                aggregates.get("years", {})
                .get(str(year), {})
                .get(activity_type, {})
            )
            svg = _svg_for_year(activity_type, year, year_entries, units, thresholds)
            path = os.path.join(type_dir, f"{year}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)

    years_desc = list(reversed(years))
    _update_readme(types, years_desc)

    site_payload = {
        "generated_at": utc_now().isoformat(),
        "years": years,
        "types": types,
        "aggregates": aggregates.get("years", {}),
        "units": units,
        "distance_levels": distance_levels,
    }
    _write_site_data(site_payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SVG heatmaps and README section")
    args = parser.parse_args()
    generate()
    print("Generated heatmaps and README section")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
