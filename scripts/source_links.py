"""Per-source link rules shared by setup and dashboard generation."""

import re
import urllib.parse
from typing import Any, Dict, Optional

STRAVA_HOST_RE = re.compile(r"(^|\.)strava\.com$", re.IGNORECASE)
GARMIN_CONNECT_HOST_RE = re.compile(r"(^|\.)connect\.garmin\.com$", re.IGNORECASE)
INTERVALS_HOST_RE = re.compile(r"(^|\.)intervals\.icu$", re.IGNORECASE)

# Per-source link registry: profile host, optional profile path canonicalizer
# (regex capturing the profile id + normalized path template), and the
# individual activity URL template. intervals.icu has no public athlete pages,
# so its profile link may point at the site root.
SOURCE_LINK_SPECS: Dict[str, Dict[str, Any]] = {
    "strava": {
        "display_name": "Strava",
        "host_re": STRAVA_HOST_RE,
        "host_hint": "a strava.com hostname",
        "profile_path_re": None,
        "profile_path_template": None,
        "profile_path_hint": "/athletes/<id>",
        "allow_root_profile": False,
        "activity_url_template": "https://www.strava.com/activities/{id}",
    },
    "garmin": {
        "display_name": "Garmin",
        "host_re": GARMIN_CONNECT_HOST_RE,
        "host_hint": "a connect.garmin.com hostname",
        "profile_path_re": re.compile(r"^/(?:modern/)?profile/([^/]+)(?:/.*)?$", re.IGNORECASE),
        "profile_path_template": "/modern/profile/{id}",
        "profile_path_hint": "/modern/profile/<id>",
        "allow_root_profile": False,
        "activity_url_template": "https://connect.garmin.com/modern/activity/{id}",
    },
    "intervals": {
        "display_name": "intervals.icu",
        "host_re": INTERVALS_HOST_RE,
        "host_hint": "an intervals.icu hostname",
        "profile_path_re": None,
        "profile_path_template": None,
        "profile_path_hint": None,
        "allow_root_profile": True,
        "activity_url_template": "https://intervals.icu/activities/{id}",
    },
}


def normalize_profile_url(value: Optional[str], source: str) -> str:
    """Return the canonical profile URL for ``source`` ("" for empty input).

    Raises ValueError with a user-facing message when the URL does not match
    the source's host/path rules.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    spec = SOURCE_LINK_SPECS.get(str(source or "").strip().lower())
    if spec is None:
        raise ValueError(f"Unsupported source for profile URL normalization: {source!r}")
    label = spec["display_name"]

    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = f"https://{raw.lstrip('/')}"
    parsed = urllib.parse.urlparse(raw)
    host = str(parsed.hostname or "").lower()
    if not host or not spec["host_re"].search(host):
        raise ValueError(f"{label} profile URL must use {spec['host_hint']}.")

    path_error = (
        f"{label} profile URL must include a profile path "
        f"(for example {spec['profile_path_hint']})."
    )
    profile_path_re = spec["profile_path_re"]
    if profile_path_re is not None:
        match = profile_path_re.match(str(parsed.path or "").strip())
        if not match:
            raise ValueError(path_error)
        normalized_path = spec["profile_path_template"].format(id=match.group(1))
    else:
        normalized_path = str(parsed.path or "").strip().rstrip("/")
        if not normalized_path and not spec["allow_root_profile"]:
            raise ValueError(path_error)

    return urllib.parse.urlunparse(
        (parsed.scheme or "https", parsed.netloc, normalized_path, "", parsed.query, "")
    )
