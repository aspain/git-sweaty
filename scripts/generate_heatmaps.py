import argparse
import os
import re
import subprocess
import urllib.parse
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from activity_types import build_type_meta, featured_types_from_config, ordered_types
from repo_helpers import choose_repo_slug_from_env, normalize_repo_slug
from utils import (
    ensure_dir,
    format_distance,
    format_duration,
    format_elevation,
    format_heart_rate,
    load_config,
    normalize_source,
    parse_iso_datetime,
    read_json,
    utc_now,
    write_json,
)

AGG_PATH = os.path.join("data", "daily_aggregates.json")
ACTIVITIES_PATH = os.path.join("data", "activities_normalized.json")
SITE_DATA_PATH = os.path.join("site", "data.json")

CELL = 12
GAP = 2
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
DEFAULT_WEEK_START = "sunday"
WEEK_START_CHOICES = {"sunday", "monday"}
DAY_LABELS_BY_WEEK_START = {
    "sunday": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    "monday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
STRAVA_HOST_RE = re.compile(r"(^|\.)strava\.com$", re.IGNORECASE)
GARMIN_CONNECT_HOST_RE = re.compile(r"(^|\.)connect\.garmin\.com$", re.IGNORECASE)


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


def _normalize_week_start(value: object) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "sun": "sunday",
        "sunday": "sunday",
        "mon": "monday",
        "monday": "monday",
    }
    resolved = aliases.get(normalized)
    if resolved:
        return resolved
    return DEFAULT_WEEK_START


def _day_row_index(d: date, week_start: str) -> int:
    if week_start == "monday":
        return d.weekday()  # Monday=0
    return (d.weekday() + 1) % 7  # Sunday=0


def _week_start_on_or_before(d: date, week_start: str) -> date:
    return d - timedelta(days=_day_row_index(d, week_start))


def _week_end_on_or_after(d: date, week_start: str) -> date:
    return d + timedelta(days=(6 - _day_row_index(d, week_start)))


def _level(count: int) -> int:
    return 4 if count > 0 else 0


def _build_title(date_str: str, entry: Dict, units: Dict[str, str]) -> str:
    count = entry.get("count", 0)
    distance = format_distance(entry.get("distance", 0.0), units["distance"])
    duration = format_duration(entry.get("moving_time", 0.0))
    elevation = format_elevation(entry.get("elevation_gain", 0.0), units["elevation"])
    lines = [
        f"{date_str}",
        f"{count} workout{'s' if count != 1 else ''}",
        f"Distance: {distance}",
        f"Duration: {duration}",
        f"Elevation: {elevation}",
    ]
    if float(entry.get("hr_time", 0.0) or 0.0) > 0.0:
        lines.append(f"Heart rate: {format_heart_rate(entry.get('heart_rate', 0.0))}")
    return "\n".join(lines)


def _color_scale(accent: str) -> List[str]:
    return [DEFAULT_COLORS[0], DEFAULT_COLORS[1], DEFAULT_COLORS[2], DEFAULT_COLORS[3], accent]


def _load_activities(
    *,
    source: str = "strava",
    include_activity_urls: bool = False,
    include_strava_activity_urls: bool = False,
    include_garmin_activity_urls: bool = False,
) -> List[Dict]:
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
        subtype = item.get("raw_type") or activity_type
        start_date_local = item.get("start_date_local")
        if not date_str or year is None or not activity_type or not subtype or not start_date_local:
            continue
        try:
            hour = parse_iso_datetime(start_date_local).hour
        except Exception:
            hour = None
        activity = {
            "date": date_str,
            "year": int(year),
            "type": activity_type,
            "subtype": str(subtype),
            "hour": hour,
        }
        include_provider_activity_urls = include_activity_urls
        if source == "strava" and include_strava_activity_urls:
            include_provider_activity_urls = True
        if source == "garmin" and include_garmin_activity_urls:
            include_provider_activity_urls = True

        if include_provider_activity_urls:
            url = _activity_url_from_id(source, item.get("id"))
            if url:
                activity["url"] = url
                activity_name = str(item.get("name") or "").strip()
                if activity_name:
                    activity["name"] = activity_name
        activities.append(activity)
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


def _repo_slug_from_git() -> Optional[str]:
    env_slug = choose_repo_slug_from_env(
        dashboard_repo=os.environ.get("DASHBOARD_REPO", ""),
        github_repository=os.environ.get("GITHUB_REPOSITORY", ""),
        github_actions=os.environ.get("GITHUB_ACTIONS", ""),
    )
    if env_slug:
        return env_slug

    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    return normalize_repo_slug(result.stdout.strip())


def _host_regex_for_source(source: str) -> Optional[re.Pattern]:
    if source == "strava":
        return STRAVA_HOST_RE
    if source == "garmin":
        return GARMIN_CONNECT_HOST_RE
    return None


def _profile_url_from_config(config: Dict, source: str) -> Optional[str]:
    raw = str((config.get(source, {}) or {}).get("profile_url", "")).strip()
    if not raw:
        return None
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = f"https://{raw.lstrip('/')}"
    parsed = urllib.parse.urlparse(raw)
    host = str(parsed.hostname or "").lower()
    host_regex = _host_regex_for_source(source)
    if not host or host_regex is None or not host_regex.search(host):
        return None
    if source == "garmin":
        path = str(parsed.path or "").strip()
        match = re.match(r"^/(?:modern/)?profile/([^/]+)(?:/.*)?$", path, flags=re.IGNORECASE)
        if not match:
            return None
        normalized_path = f"/modern/profile/{match.group(1)}"
    else:
        normalized_path = str(parsed.path or "").strip().rstrip("/")
        if not normalized_path:
            return None
    return urllib.parse.urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            normalized_path,
            "",
            parsed.query,
            "",
        )
    )


def _activity_links_enabled_from_config(config: Dict, source: str) -> bool:
    value = (config.get(source, {}) or {}).get("include_activity_urls", False)
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _activity_url_from_id(source: str, activity_id: object) -> Optional[str]:
    raw = str(activity_id or "").strip()
    if not raw:
        return None
    if "/" in raw or "\\" in raw:
        return None
    encoded = urllib.parse.quote(raw, safe="")
    if not encoded:
        return None
    if source == "strava":
        return f"https://www.strava.com/activities/{encoded}"
    if source == "garmin":
        return f"https://connect.garmin.com/modern/activity/{encoded}"
    return None


def _strava_profile_url_from_config(config: Dict) -> Optional[str]:
    return _profile_url_from_config(config, "strava")


def _strava_activity_links_enabled_from_config(config: Dict) -> bool:
    return _activity_links_enabled_from_config(config, "strava")


def _strava_activity_url_from_id(activity_id: object) -> Optional[str]:
    return _activity_url_from_id("strava", activity_id)


def _svg_for_year(
    year: int,
    entries: Dict[str, Dict],
    units: Dict[str, str],
    colors: List[str],
    color_for_entry: Optional[Callable[[Dict], str]] = None,
    week_start: str = DEFAULT_WEEK_START,
) -> str:
    normalized_week_start = _normalize_week_start(week_start)
    start = _week_start_on_or_before(date(year, 1, 1), normalized_week_start)
    end = _week_end_on_or_after(date(year, 12, 31), normalized_week_start)

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

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'  # noqa: E501
    )
    lines.append(
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>'
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

    day_labels = DAY_LABELS_BY_WEEK_START[normalized_week_start]
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

    current = start
    while current <= end:
        week_index = (current - start).days // 7
        row = _day_row_index(current, normalized_week_start)
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
                "hr_weighted_sum": 0.0,
                "hr_time": 0.0,
                "activity_ids": [],
            })
            count = int(entry.get("count", 0))
            level = _level(count)
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
        current += timedelta(days=1)

    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _write_site_data(payload: Dict) -> None:
    ensure_dir("site")
    write_json(SITE_DATA_PATH, payload)


def generate(write_svgs: bool = True):
    config = load_config()
    activities_cfg = config.get("activities", {}) or {}
    featured_types = featured_types_from_config(activities_cfg)
    other_bucket = str(activities_cfg.get("other_bucket", "OtherSports"))
    heatmaps_cfg = config.get("heatmaps", {}) or {}
    week_start = _normalize_week_start(heatmaps_cfg.get("week_start") or config.get("week_start"))

    units = config.get("units", {})
    units = {
        "distance": units.get("distance", "mi"),
        "elevation": units.get("elevation", "ft"),
    }

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

    if write_svgs:
        for activity_type in types:
            type_dir = os.path.join("heatmaps", activity_type)
            ensure_dir(type_dir)
            for year in years:
                year_entries = (
                    aggregate_years
                    .get(str(year), {})
                    .get(activity_type, {})
                )
                svg = _svg_for_year(
                    year,
                    year_entries,
                    units,
                    type_colors.get(activity_type, DEFAULT_COLORS),
                    week_start=week_start,
                )
                path = os.path.join(type_dir, f"{year}.svg")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(svg)

    source = normalize_source(config.get("source", "strava"))
    include_activity_urls = _activity_links_enabled_from_config(config, source)
    load_activities_kwargs = {"source": source}
    if source == "strava":
        load_activities_kwargs["include_strava_activity_urls"] = include_activity_urls
    elif source == "garmin":
        load_activities_kwargs["include_garmin_activity_urls"] = include_activity_urls
    site_payload = {
        "source": source,
        "generated_at": utc_now().isoformat(),
        "years": years,
        "types": types,
        "other_bucket": other_bucket,
        "type_meta": type_meta,
        "aggregates": aggregate_years,
        "units": units,
        "week_start": week_start,
        "activities": _load_activities(**load_activities_kwargs),
    }
    profile_url = _profile_url_from_config(config, source)
    if profile_url:
        site_payload["profile_url"] = profile_url
        if source == "strava":
            site_payload["strava_profile_url"] = profile_url
        elif source == "garmin":
            site_payload["garmin_profile_url"] = profile_url
    repo_slug = _repo_slug_from_git()
    if repo_slug:
        site_payload["repo"] = repo_slug
    _write_site_data(site_payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SVG heatmaps")
    parser.add_argument(
        "--no-write-svgs",
        action="store_true",
        help="Skip writing heatmaps/<type>/<year>.svg exports and only refresh site/data.json.",
    )
    args = parser.parse_args()
    generate(write_svgs=not args.no_write_svgs)
    print("Generated heatmaps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
