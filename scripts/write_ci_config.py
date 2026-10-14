"""Write config.local.yaml for CI from workflow secrets/variables in the environment.

Values are serialized with yaml.safe_dump, so quotes, backslashes and other
special characters in secrets or variables cannot break the generated YAML.
"""

import argparse
import os
from typing import Any, Dict, Mapping

import yaml

from utils import CONFIG_LOCAL_PATH, normalize_source

TRUTHY_TEXT = {"1", "true", "yes", "y", "on"}

# source -> (config key -> environment variable) for credentials.
SOURCE_CREDENTIAL_ENV: Dict[str, Dict[str, str]] = {
    "strava": {
        "client_id": "STRAVA_CLIENT_ID",
        "client_secret": "STRAVA_CLIENT_SECRET",
        "refresh_token": "STRAVA_REFRESH_TOKEN",
    },
    "garmin": {
        "token_store_b64": "GARMIN_TOKENS_B64",
        "email": "GARMIN_EMAIL",
        "password": "GARMIN_PASSWORD",
    },
    "intervals": {
        "api_key": "INTERVALS_API_KEY",
        "athlete_id": "INTERVALS_ATHLETE_ID",
    },
}
SOURCE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "intervals": {"athlete_id": "0"},
}


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUTHY_TEXT


def build_ci_config(env: Mapping[str, str]) -> Dict[str, Any]:
    source = normalize_source(env.get("SYNC_SOURCE"))
    prefix = f"DASHBOARD_{source.upper()}"

    source_cfg: Dict[str, Any] = {}
    defaults = SOURCE_DEFAULTS.get(source, {})
    for key, env_name in SOURCE_CREDENTIAL_ENV[source].items():
        value = str(env.get(env_name) or "")
        if key in defaults:
            value = value.strip() or defaults[key]
        source_cfg[key] = value
    profile_url = str(env.get(f"{prefix}_PROFILE_URL") or "").strip()
    if profile_url:
        source_cfg["profile_url"] = profile_url
    if _is_truthy(env.get(f"{prefix}_ACTIVITY_LINKS")):
        source_cfg["include_activity_urls"] = True

    config: Dict[str, Any] = {"source": source, source: source_cfg}

    units = {
        key: str(env.get(env_name)).strip()
        for key, env_name in (("distance", "DASHBOARD_DISTANCE_UNIT"), ("elevation", "DASHBOARD_ELEVATION_UNIT"))
        if str(env.get(env_name) or "").strip()
    }
    if units:
        config["units"] = units
    week_start = str(env.get("DASHBOARD_WEEK_START") or "").strip()
    if week_start:
        config["heatmaps"] = {"week_start": week_start}
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Write config.local.yaml from CI environment variables")
    parser.add_argument("--output", default=CONFIG_LOCAL_PATH)
    args = parser.parse_args()

    config = build_ci_config(os.environ)
    with open(args.output, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, default_flow_style=False)
    print(f"Generated {args.output} for source={config['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
