import re
from typing import Dict, List, Sequence

DEFAULT_FEATURED_TYPES = ["Run", "Ride", "WeightTraining"]

DEFAULT_TYPE_LABELS = {
    "Run": "Run",
    "Ride": "Ride",
    "WeightTraining": "Weight Training",
    "WalkHike": "Walk / Hike",
    "Swim": "Swim",
    "WaterSports": "Water Sports",
    "WinterSports": "Winter Sports",
    "GymCardio": "Gym Cardio",
    "MindBody": "Mind & Body",
    "TeamSports": "Team Sports",
    "CourtSports": "Court Sports",
    "Climbing": "Climbing",
    "SkateSports": "Skate Sports",
    "AdaptiveSports": "Adaptive Sports",
    "OtherSports": "Other Sports",
}

TYPE_ACCENT_COLORS = {
    "Run": "#01cdfe",
    "Ride": "#05ffa1",
    "WeightTraining": "#ff71ce",
    "WalkHike": "#f9f871",
    "Swim": "#00e5ff",
    "WaterSports": "#2de2e6",
    "WinterSports": "#b8c0ff",
    "GymCardio": "#ff8fab",
    "MindBody": "#ffd166",
    "TeamSports": "#ff9f1c",
    "CourtSports": "#f15bb5",
    "Climbing": "#7afcff",
    "SkateSports": "#9ef01a",
    "AdaptiveSports": "#b967ff",
    "OtherSports": "#f5c2ff",
}

FALLBACK_VAPORWAVE_COLORS = [
    "#f15bb5",
    "#fee440",
    "#00bbf9",
    "#00f5d4",
    "#9b5de5",
    "#fb5607",
    "#ffbe0b",
    "#72efdd",
]

KNOWN_TYPE_GROUPS_BY_SLUG = {
    "walk": "WalkHike",
    "hike": "WalkHike",
    "swim": "Swim",
    "alpineski": "WinterSports",
    "backcountryski": "WinterSports",
    "nordicski": "WinterSports",
    "rollerski": "WinterSports",
    "snowboard": "WinterSports",
    "snowshoe": "WinterSports",
    "iceskate": "WinterSports",
    "canoeing": "WaterSports",
    "kayaking": "WaterSports",
    "kitesurf": "WaterSports",
    "sail": "WaterSports",
    "standuppaddling": "WaterSports",
    "surfing": "WaterSports",
    "windsurf": "WaterSports",
    "rowing": "WaterSports",
    "virtualrow": "WaterSports",
    "elliptical": "GymCardio",
    "stairstepper": "GymCardio",
    "workout": "GymCardio",
    "highintensityintervaltraining": "GymCardio",
    "crossfit": "GymCardio",
    "yoga": "MindBody",
    "pilates": "MindBody",
    "soccer": "TeamSports",
    "football": "TeamSports",
    "baseball": "TeamSports",
    "basketball": "TeamSports",
    "volleyball": "TeamSports",
    "hockey": "TeamSports",
    "rugby": "TeamSports",
    "cricket": "TeamSports",
    "lacrosse": "TeamSports",
    "softball": "TeamSports",
    "tennis": "CourtSports",
    "tabletennis": "CourtSports",
    "badminton": "CourtSports",
    "racquetball": "CourtSports",
    "squash": "CourtSports",
    "pickleball": "CourtSports",
    "padel": "CourtSports",
    "rockclimbing": "Climbing",
    "bouldering": "Climbing",
    "inlineskate": "SkateSports",
    "skateboard": "SkateSports",
    "wheelchair": "AdaptiveSports",
    "handcycle": "AdaptiveSports",
    "velomobile": "AdaptiveSports",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def featured_types_from_config(config_activities: Dict) -> List[str]:
    configured = config_activities.get("types", []) or []
    if configured:
        return [str(item) for item in configured]
    return list(DEFAULT_FEATURED_TYPES)


def normalize_activity_type(
    activity_type: str,
    featured_types: Sequence[str],
    group_other_types: bool,
    other_bucket: str,
    group_aliases: Dict[str, str],
) -> str:
    value = str(activity_type or "").strip() or other_bucket
    if value in featured_types:
        return value

    alias = group_aliases.get(value)
    if alias:
        return alias

    if not group_other_types:
        return value

    slug = _slug(value)

    if "run" in slug and "row" not in slug:
        return "Run"
    if any(token in slug for token in ("ride", "bike", "cycle")):
        return "Ride"
    if any(token in slug for token in ("weight", "strength")):
        return "WeightTraining"

    known_group = KNOWN_TYPE_GROUPS_BY_SLUG.get(slug)
    if known_group:
        return known_group

    return other_bucket


def type_label(activity_type: str) -> str:
    if activity_type in DEFAULT_TYPE_LABELS:
        return DEFAULT_TYPE_LABELS[activity_type]
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", activity_type or "")
    return spaced.replace("_", " ").strip() or "Other"


def _fallback_color(activity_type: str) -> str:
    if not activity_type:
        return FALLBACK_VAPORWAVE_COLORS[0]
    index = 0
    for i, ch in enumerate(activity_type):
        index += (i + 1) * ord(ch)
    return FALLBACK_VAPORWAVE_COLORS[index % len(FALLBACK_VAPORWAVE_COLORS)]


def type_accent(activity_type: str) -> str:
    return TYPE_ACCENT_COLORS.get(activity_type, _fallback_color(activity_type))


def ordered_types(type_counts: Dict[str, int], featured_types: Sequence[str]) -> List[str]:
    counts = {str(k): int(v) for k, v in (type_counts or {}).items() if int(v) > 0}
    featured_present = [activity_type for activity_type in featured_types if counts.get(activity_type, 0) > 0]
    remaining = [activity_type for activity_type in counts.keys() if activity_type not in featured_present]
    remaining.sort(key=lambda item: (-counts[item], type_label(item).lower()))

    ordered = featured_present + remaining
    if ordered:
        return ordered
    return list(featured_types)


def build_type_meta(types: Sequence[str]) -> Dict[str, Dict[str, str]]:
    meta: Dict[str, Dict[str, str]] = {}
    for activity_type in types:
        meta[activity_type] = {
            "label": type_label(activity_type),
            "accent": type_accent(activity_type),
        }
    return meta
