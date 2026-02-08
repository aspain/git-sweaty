import argparse
import os
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

from activity_types import build_type_meta, featured_types_from_config, ordered_types
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
<<<<<<< HEAD
=======
ACTIVITIES_PATH = os.path.join("data", "activities_normalized.json")
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
README_PATH = "README.md"
SITE_DATA_PATH = os.path.join("site", "data.json")
README_PREVIEW_IMAGE_PATH = os.path.join("site", "readme-preview.png")

CELL = 12
GAP = 2
<<<<<<< HEAD
PADDING = 16
LABEL_LEFT = 36
LABEL_TOP = 20

DEFAULT_COLORS = ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#1f2937"]
TYPE_COLORS = {
    "Run": ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#01cdfe"],
    "Ride": ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#05ffa1"],
    "WeightTraining": ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#ff71ce"],
}
LABEL_COLOR = "#cbd5e1"
TEXT_COLOR = "#e5e7eb"
BG_COLOR = "#0f172a"
STROKE_COLOR = "#0f172a"
=======
OUTER_PAD = 16
AXIS_WIDTH = 36
AXIS_GAP = 8
LABEL_ROW_HEIGHT = 18
GRID_PAD_TOP = 6
GRID_PAD_RIGHT = 4
GRID_PAD_BOTTOM = 6
GRID_PAD_LEFT = 6

DEFAULT_COLORS = ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#1f2937"]
YEAR_LABEL_COLOR = "#e5e7eb"
LABEL_COLOR = "#f1f5f9"
BG_COLOR = "#0f172a"
GRID_BG_COLOR = "rgba(15, 23, 42, 0.8)"
LABEL_FONT = "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a


def _year_range_from_config(config: Dict, aggregate_years: Dict) -> List[int]:
    sync_cfg = config.get("sync", {})
    current_year = utc_now().year
    start_date = sync_cfg.get("start_date")
    if start_date:
        try:
            start_year = int(start_date.split("-")[0])
        except (ValueError, IndexError):
            start_year = current_year
    else:
        lookback_years = sync_cfg.get("lookback_years")
        if lookback_years not in (None, ""):
            start_year = current_year - int(lookback_years) + 1
        else:
            data_years: List[int] = []
            for raw_year in (aggregate_years or {}).keys():
                try:
                    data_years.append(int(raw_year))
                except (TypeError, ValueError):
                    continue
            start_year = min(data_years) if data_years else current_year
    return list(range(start_year, current_year + 1))


def _sunday_on_or_before(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _saturday_on_or_after(d: date) -> date:
    return d + timedelta(days=(5 - d.weekday()) % 7)


def _level(count: int) -> int:
    return 4 if count > 0 else 0


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


<<<<<<< HEAD
def _svg_for_year(
    activity_type: str,
    year: int,
    entries: Dict[str, Dict],
    units: Dict[str, str],
) -> str:
    start = _monday_on_or_before(date(year, 1, 1))
    end = _sunday_on_or_after(date(year, 12, 31))

    weeks = ((end - start).days // 7) + 1
    width = weeks * (CELL + GAP) + PADDING * 2 + LABEL_LEFT
    height = 7 * (CELL + GAP) + PADDING * 2 + LABEL_TOP

    grid_x = PADDING + LABEL_LEFT
    grid_y = PADDING + LABEL_TOP

    colors = TYPE_COLORS.get(activity_type, DEFAULT_COLORS)
=======
def _color_scale(accent: str) -> List[str]:
    return [DEFAULT_COLORS[0], DEFAULT_COLORS[1], DEFAULT_COLORS[2], DEFAULT_COLORS[3], accent]


def _parse_hour(value: str) -> int:
    if not value:
        raise ValueError("Missing datetime")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        if "." in value:
            base, rest = value.split(".", 1)
            if "+" in rest:
                tz = "+" + rest.split("+", 1)[1]
            elif "-" in rest:
                tz = "-" + rest.split("-", 1)[1]
            else:
                tz = ""
            dt = datetime.fromisoformat(base + tz)
        else:
            raise
    return dt.hour


def _load_activities() -> List[Dict]:
    if not os.path.exists(ACTIVITIES_PATH):
        return []
    items = read_json(ACTIVITIES_PATH) or []
    activities: List[Dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date_str = item.get("date")
        year = item.get("year")
        activity_type = item.get("type")
        start_date_local = item.get("start_date_local")
        if not date_str or year is None or not activity_type or not start_date_local:
            continue
        try:
            hour = _parse_hour(start_date_local)
        except Exception:
            continue
        activities.append({
            "date": date_str,
            "year": int(year),
            "type": activity_type,
            "hour": hour,
        })
    return activities


def _type_totals(aggregates_years: Dict) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for year_data in (aggregates_years or {}).values():
        for activity_type, entries in (year_data or {}).items():
            for entry in (entries or {}).values():
                count = int(entry.get("count", 0))
                if count <= 0:
                    continue
                totals[activity_type] = totals.get(activity_type, 0) + count
    return totals


def _svg_for_year(
    year: int,
    entries: Dict[str, Dict],
    units: Dict[str, str],
    colors: List[str],
    color_for_entry: Optional[Callable[[Dict], str]] = None,
) -> str:
    start = _sunday_on_or_before(date(year, 1, 1))
    end = _saturday_on_or_after(date(year, 12, 31))

    weeks = ((end - start).days // 7) + 1
    grid_rows = 7
    grid_inner_width = weeks * CELL + (weeks - 1) * GAP
    grid_inner_height = grid_rows * CELL + (grid_rows - 1) * GAP
    grid_width = GRID_PAD_LEFT + grid_inner_width + GRID_PAD_RIGHT
    grid_height = GRID_PAD_TOP + grid_inner_height + GRID_PAD_BOTTOM

    width = OUTER_PAD * 2 + AXIS_WIDTH + AXIS_GAP + grid_width
    height = OUTER_PAD * 2 + LABEL_ROW_HEIGHT + grid_height

    heatmap_x = OUTER_PAD
    heatmap_y = OUTER_PAD
    month_row_x = heatmap_x + AXIS_WIDTH + AXIS_GAP + GRID_PAD_LEFT
    month_row_y = heatmap_y
    day_col_x = heatmap_x + AXIS_WIDTH
    day_col_y = heatmap_y + LABEL_ROW_HEIGHT + GRID_PAD_TOP
    grid_bg_x = heatmap_x + AXIS_WIDTH + AXIS_GAP
    grid_bg_y = heatmap_y + LABEL_ROW_HEIGHT
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'  # noqa: E501
    )
    lines.append(
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>'
<<<<<<< HEAD
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
=======
    )
    lines.append(
        f'<rect x="{grid_bg_x}" y="{grid_bg_y}" width="{grid_width}" height="{grid_height}" '
        f'rx="12" ry="12" fill="{GRID_BG_COLOR}"/>'
    )
    lines.append(
        f'<text x="{heatmap_x}" y="{heatmap_y + LABEL_ROW_HEIGHT - 2}" font-size="12" '
        f'fill="{YEAR_LABEL_COLOR}" font-family="{LABEL_FONT}">{year}</text>'
    )

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for month in range(1, 13):
        first_day = date(year, month, 1)
        week_index = (first_day - start).days // 7
        x = month_row_x + week_index * (CELL + GAP)
        lines.append(
            f'<text x="{x}" y="{month_row_y + 2}" font-size="10" fill="{LABEL_COLOR}" '
            f'font-family="{LABEL_FONT}" dominant-baseline="hanging">{month_labels[month - 1]}</text>'
        )

    day_labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for row, label in enumerate(day_labels):
        y = day_col_y + row * (CELL + GAP) + (CELL / 2)
        x = day_col_x
        lines.append(
            f'<text x="{x}" y="{y}" font-size="10" fill="{LABEL_COLOR}" font-family="{LABEL_FONT}" '
            f'text-anchor="end" dominant-baseline="middle">{label}</text>'
        )

    lines.append(
        f'<g transform="translate({month_row_x},{day_col_y})">'
    )
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a

    current = start
    while current <= end:
        week_index = (current - start).days // 7
        row = (current.weekday() + 1) % 7  # Sunday=0
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
            level = _level(count)
<<<<<<< HEAD
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
=======
            if color_for_entry:
                color = color_for_entry(entry)
            else:
                color = colors[level]
            title = _build_title(date_str, entry, units)
        else:
            current += timedelta(days=1)
            continue

        rect_attrs = (
            f'x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'rx="3" ry="3" fill="{color}"'
        )
        lines.append(
            f'<rect {rect_attrs} data-date="{date_str}"><title>{title}</title></rect>'
        )
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
        current += timedelta(days=1)

    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


<<<<<<< HEAD
def _readme_section(types: List[str], years_desc: List[int]) -> str:
    lines = []
    lines.append("![Run 2025](heatmaps/Run/2025.svg)")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
=======
def _readme_section() -> str:
    return (
        "Preview:\n\n"
        "![Dashboard Preview]"
        f"({README_PREVIEW_IMAGE_PATH})\n"
    )
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a


def _update_readme() -> None:
    if not os.path.exists(README_PATH):
        return
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = "<!-- HEATMAPS:START -->"
    end_tag = "<!-- HEATMAPS:END -->"
    section = _readme_section()

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
    activities_cfg = config.get("activities", {}) or {}
    featured_types = featured_types_from_config(activities_cfg)

    units = config.get("units", {})
    units = {
        "distance": units.get("distance", "mi"),
        "elevation": units.get("elevation", "ft"),
    }

<<<<<<< HEAD
    aggregates = read_json(AGG_PATH)
    years = _year_range_from_config(config)
=======
    aggregates = read_json(AGG_PATH) if os.path.exists(AGG_PATH) else {"years": {}}
    aggregate_years = aggregates.get("years", {}) or {}
    type_counts = _type_totals(aggregate_years)
    types = ordered_types(type_counts, featured_types)
    type_meta = build_type_meta(types)
    type_colors = {
        activity_type: _color_scale(type_meta.get(activity_type, {}).get("accent", DEFAULT_COLORS[4]))
        for activity_type in types
    }
    years = _year_range_from_config(config, aggregate_years)
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a

    for activity_type in types:
        type_dir = os.path.join("heatmaps", activity_type)
        ensure_dir(type_dir)
        for year in years:
            year_entries = (
                aggregate_years
                .get(str(year), {})
                .get(activity_type, {})
            )
<<<<<<< HEAD
            svg = _svg_for_year(activity_type, year, year_entries, units)
=======
            svg = _svg_for_year(
                year,
                year_entries,
                units,
                type_colors.get(activity_type, DEFAULT_COLORS),
            )
>>>>>>> 13dce35b0ad5e6078d660d724f50518d4f38191a
            path = os.path.join(type_dir, f"{year}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)

    _update_readme()

    site_payload = {
        "generated_at": utc_now().isoformat(),
        "years": years,
        "types": types,
        "type_meta": type_meta,
        "aggregates": aggregate_years,
        "units": units,
        "activities": _load_activities(),
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
