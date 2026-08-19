from typing import Any, Dict, List


def coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def get_nested(payload: Dict[str, Any], keys: List[str]) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def pick_duration_seconds(*values: Any) -> float:
    """Prefer a positive duration value when multiple provider fields are present."""
    first_numeric = None
    for value in values:
        if value in (None, "", []):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if first_numeric is None:
            first_numeric = number
        if number > 0:
            return number
    return first_numeric if first_numeric is not None else 0.0


def pick_heart_rate(*values: Any) -> float:
    """Return the first plausible resting/active HR value (0 < hr <= 255)."""
    for value in values:
        if value in (None, "", []):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if 0.0 < number <= 255.0:
            return number
    return 0.0
