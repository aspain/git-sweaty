import re
from typing import Dict, List, Sequence

STRAVA_ACTIVITY_TYPES = [
    "AlpineSki",
    "BackcountrySki",
    "Canoeing",
    "Crossfit",
    "EBikeRide",
    "Elliptical",
    "Golf",
    "Handcycle",
    "Hike",
    "IceSkate",
    "InlineSkate",
    "Kayaking",
    "Kitesurf",
    "NordicSki",
    "Ride",
    "RockClimbing",
    "RollerSki",
    "Rowing",
    "Run",
    "Sail",
    "Skateboard",
    "Snowboard",
    "Snowshoe",
    "Soccer",
    "StairStepper",
    "StandUpPaddling",
    "Surfing",
    "Swim",
    "Velomobile",
    "VirtualRide",
    "VirtualRun",
    "Walk",
    "WeightTraining",
    "Wheelchair",
    "Windsurf",
    "Workout",
    "Yoga",
]

STRAVA_SPORT_TYPES = [
    "AlpineSki",
    "BackcountrySki",
    "Badminton",
    "Canoeing",
    "Crossfit",
    "EBikeRide",
    "Elliptical",
    "EMountainBikeRide",
    "Golf",
    "GravelRide",
    "Handcycle",
    "HighIntensityIntervalTraining",
    "Hike",
    "IceSkate",
    "InlineSkate",
    "Kayaking",
    "Kitesurf",
    "MountainBikeRide",
    "NordicSki",
    "Pickleball",
    "Pilates",
    "Racquetball",
    "Ride",
    "RockClimbing",
    "RollerSki",
    "Rowing",
    "Run",
    "Sail",
    "Skateboard",
    "Snowboard",
    "Snowshoe",
    "Soccer",
    "Squash",
    "StairStepper",
    "StandUpPaddling",
    "Surfing",
    "Swim",
    "TableTennis",
    "Tennis",
    "TrailRun",
    "Velomobile",
    "VirtualRide",
    "VirtualRow",
    "VirtualRun",
    "Walk",
    "WeightTraining",
    "Wheelchair",
    "Windsurf",
    "Workout",
    "Yoga",
]

STRAVA_ENUM_TYPES = set(STRAVA_ACTIVITY_TYPES) | set(STRAVA_SPORT_TYPES)

DEFAULT_FEATURED_TYPES = list(STRAVA_SPORT_TYPES)

DEFAULT_TYPE_LABELS = {
    "HighIntensityIntervalTraining": "HITT",
    "Workout": "Other Workout",
    "Run": "Run",
    "Ride": "Ride",
    "Hike": "Hike",
    "Walk": "Walk",
    "Golf": "Golf",
    "WeightTraining": "Weights",
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
    "Commute": "Commute",
}

TYPE_ACCENT_COLORS = {
    "Run": "#01cdfe",
    "Ride": "#05ffa1",
    "Walk": "#d6ff6b",
    "WeightTraining": "#ff71ce",
    "Hike": "#d6ff6b",
    "Golf": "#38b000",
    "WalkHike": "#d6ff6b",
    "Swim": "#3a86ff",
    "WaterSports": "#118ab2",
    "WinterSports": "#b8c0ff",
    "GymCardio": "#ff8a5b",
    "Workout": "#ff8a5b",
    "MindBody": "#ffd166",
    "TeamSports": "#fb5607",
    "CourtSports": "#c77dff",
    "Climbing": "#7ae582",
    "SkateSports": "#9ef01a",
    "AdaptiveSports": "#8338ec",
    "OtherSports": "#ff006e",
    "Commute": "#666666",
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
    "walk": "Walk",
    "hike": "Hike",
    "swim": "Swim",
    "golf": "Golf",
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

# Garmin Connect type keys vary across devices/apps. Map known variants into
# the same canonical sport names used by Strava-driven flows for parity.
GARMIN_TYPE_ALIASES_BY_SLUG = {
    "running": "Run",
    "run": "Run",
    "trailrunning": "TrailRun",
    "trailrun": "TrailRun",
    "ultrarun": "Run",
    "trackrunning": "Run",
    "virtualrun": "VirtualRun",
    "treadmillrunning": "VirtualRun",
    "walking": "Walk",
    "walk": "Walk",
    "hiking": "Hike",
    "hike": "Hike",
    "cycling": "Ride",
    "bike": "Ride",
    "biking": "Ride",
    "roadbiking": "Ride",
    "roadcycling": "Ride",
    "indoorcycling": "VirtualRide",
    "virtualcycling": "VirtualRide",
    "virtualride": "VirtualRide",
    "mountainbiking": "MountainBikeRide",
    "mountainbike": "MountainBikeRide",
    "gravelcycling": "GravelRide",
    "gravelbiking": "GravelRide",
    "ebiking": "EBikeRide",
    "ebikeride": "EBikeRide",
    "swimming": "Swim",
    "swim": "Swim",
    "poolswimming": "Swim",
    "openwaterswimming": "Swim",
    "rowing": "Rowing",
    "indoorrowing": "VirtualRow",
    "virtualrowing": "VirtualRow",
    "alpineskiing": "AlpineSki",
    "alpineski": "AlpineSki",
    "crosscountryskiing": "NordicSki",
    "crosscountryski": "NordicSki",
    "nordicskiing": "NordicSki",
    "nordicski": "NordicSki",
    "snowboarding": "Snowboard",
    "snowboard": "Snowboard",
    "snowshoeing": "Snowshoe",
    "snowshoe": "Snowshoe",
    "iceskating": "IceSkate",
    "iceskate": "IceSkate",
    "inlineskating": "InlineSkate",
    "inlineskate": "InlineSkate",
    "strengthtraining": "WeightTraining",
    "weighttraining": "WeightTraining",
    "functionalstrengthtraining": "WeightTraining",
    "cardio": "Workout",
    "indoorcardio": "Workout",
    "cardiotraining": "Workout",
    "other": "Workout",
    "fitness": "Workout",
    "fitnessequipment": "Workout",
    "workout": "Workout",
    "crossfit": "Crossfit",
    "hiit": "HighIntensityIntervalTraining",
    "highintensityintervaltraining": "HighIntensityIntervalTraining",
    "elliptical": "Elliptical",
    "stairstepper": "StairStepper",
    "stepper": "StairStepper",
    "yoga": "Yoga",
    "pilates": "Pilates",
    "golf": "Golf",
    "kayaking": "Kayaking",
    "canoeing": "Canoeing",
    "standuppaddleboarding": "StandUpPaddling",
    "standuppaddling": "StandUpPaddling",
    "paddleboarding": "StandUpPaddling",
    "surfing": "Surfing",
    "windsurfing": "Windsurf",
    "windsurf": "Windsurf",
    "kitesurfing": "Kitesurf",
    "kitesurf": "Kitesurf",
    "sailing": "Sail",
    "rockclimbing": "RockClimbing",
    "climbing": "RockClimbing",
    "bouldering": "RockClimbing",
    "soccer": "Soccer",
    "football": "Soccer",
    "tennis": "Tennis",
    "tabletennis": "TableTennis",
    "pickleball": "Pickleball",
    "badminton": "Badminton",
    "squash": "Squash",
    "racquetball": "Racquetball",
    "wheelchair": "Wheelchair",
    "handcycling": "Handcycle",
    "handcycle": "Handcycle",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _capitalize_label_start(label: str) -> str:
    value = str(label or "").strip()
    if not value:
        return "Other"
    first_letter_match = re.search(r"[A-Za-z]", value)
    if not first_letter_match:
        return value
    index = first_letter_match.start()
    return f"{value[:index]}{value[index].upper()}{value[index + 1:]}"


def _virtual_variant(slug: str) -> str:
    if "row" in slug:
        return "VirtualRow"
    if any(token in slug for token in ("ride", "bike", "cycle")):
        return "VirtualRide"
    if any(token in slug for token in ("run", "walk")):
        return "VirtualRun"
    return ""


def canonicalize_activity_type(activity_type: str, source: str = "strava") -> str:
    value = str(activity_type or "").strip()
    if not value:
        return "Unknown"
    if value in STRAVA_ENUM_TYPES:
        return value

    slug = _slug(value)
    if not slug:
        return "Unknown"

    # Convert case/spacing variants that already correspond to Strava values.
    for known in STRAVA_ENUM_TYPES:
        if _slug(known) == slug:
            return known

    if source == "garmin":
        garmin_match = GARMIN_TYPE_ALIASES_BY_SLUG.get(slug)
        if garmin_match:
            return garmin_match
        if "virtual" in slug:
            virtual = _virtual_variant(slug)
            if virtual:
                return virtual

    if any(token in slug for token in ("trail",)) and "run" in slug:
        return "TrailRun"
    if "run" in slug and "row" not in slug:
        return "Run"
    if any(token in slug for token in ("ride", "bike", "cycle")):
        return "Ride"
    if any(token in slug for token in ("weight", "strength")):
        return "WeightTraining"
    if "walk" in slug:
        return "Walk"
    if "hike" in slug:
        return "Hike"
    if "swim" in slug:
        return "Swim"

    return value


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
    featured_set = set(featured_types)

    # Resolve to a candidate group via slug heuristics or known mappings.
    candidate = None
    if "run" in slug and "row" not in slug:
        candidate = "Run"
    elif any(token in slug for token in ("ride", "bike", "cycle")):
        candidate = "Ride"
    elif any(token in slug for token in ("weight", "strength")):
        candidate = "WeightTraining"
    else:
        candidate = KNOWN_TYPE_GROUPS_BY_SLUG.get(slug)

    # Only use the candidate if it is actually a featured type;
    # otherwise collapse into the catch-all bucket.
    if candidate and candidate in featured_set:
        return candidate

    return other_bucket


def type_label(activity_type: str) -> str:
    if activity_type in DEFAULT_TYPE_LABELS:
        return _capitalize_label_start(DEFAULT_TYPE_LABELS[activity_type])
    if activity_type in STRAVA_ENUM_TYPES:
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", activity_type or "")
        return _capitalize_label_start(spaced.replace("_", " ").strip())
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", activity_type or "")
    return _capitalize_label_start(spaced.replace("_", " ").strip())


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
    featured_absent = [activity_type for activity_type in featured_types if counts.get(activity_type, 0) == 0]
    remaining = [activity_type for activity_type in counts.keys() if activity_type not in featured_present]
    remaining.sort(key=lambda item: (-counts[item], type_label(item).lower()))

    ordered = featured_present + featured_absent + remaining
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
