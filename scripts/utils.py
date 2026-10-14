import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

import yaml

CONFIG_PATH = "config.yaml"
CONFIG_LOCAL_PATH = "config.local.yaml"
DEFAULT_SOURCE = "strava"
SUPPORTED_SOURCES = {"strava", "garmin", "intervals"}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Missing {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}
    if os.path.exists(CONFIG_LOCAL_PATH):
        with open(CONFIG_LOCAL_PATH, "r", encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        return _deep_merge(base, override)
    return base


def normalize_source(value: Any) -> str:
    source = str(value or DEFAULT_SOURCE).strip().lower()
    if source not in SUPPORTED_SOURCES:
        allowed = ", ".join(sorted(SUPPORTED_SOURCES))
        raise ValueError(f"Unsupported source '{source}'. Supported values: {allowed}.")
    return source


def raw_activity_dir(source: str) -> str:
    return os.path.join("activities", "raw", normalize_source(source))


# Generated outputs shared by every source; wiped when the synced account changes.
PERSISTED_OUTPUT_PATHS = (
    os.path.join("data", "activities_normalized.json"),
    os.path.join("data", "daily_aggregates.json"),
    os.path.join("data", "last_sync_summary.json"),
    os.path.join("data", "last_sync_summary.txt"),
    os.path.join("site", "data.json"),
)


def has_existing_persisted_data(extra_paths: Iterable[str] = ()) -> bool:
    return any(os.path.exists(path) for path in (*PERSISTED_OUTPUT_PATHS, *extra_paths))


def reset_persisted_data(raw_dir: str, extra_paths: Iterable[str] = ()) -> None:
    for path in (*PERSISTED_OUTPUT_PATHS, *extra_paths):
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(raw_dir):
        shutil.rmtree(raw_dir)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("Missing datetime")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        # fallback: strip fractional seconds when offset parsing fails
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


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_distance(meters: float, unit: str) -> str:
    if unit == "km":
        val = meters / 1000.0
        return f"{val:.2f} km"
    miles = meters / 1609.344
    return f"{miles:.2f} mi"


def format_elevation(meters: float, unit: str) -> str:
    if unit == "m":
        return f"{meters:.0f} m"
    feet = meters * 3.28084
    return f"{feet:.0f} ft"
