import json
import os
import subprocess
import sys
import tempfile
import types
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import write_ci_config  # noqa: E402


class BuildCiConfigTests(unittest.TestCase):
    def test_strava_config(self) -> None:
        config = write_ci_config.build_ci_config(
            {
                "SYNC_SOURCE": "strava",
                "STRAVA_CLIENT_ID": "123",
                "STRAVA_CLIENT_SECRET": "secret",
                "STRAVA_REFRESH_TOKEN": "refresh",
                "DASHBOARD_STRAVA_PROFILE_URL": " https://www.strava.com/athletes/1 ",
                "DASHBOARD_STRAVA_ACTIVITY_LINKS": " Yes ",
                "DASHBOARD_DISTANCE_UNIT": "km",
                "DASHBOARD_WEEK_START": "monday",
            }
        )
        self.assertEqual(
            config,
            {
                "source": "strava",
                "strava": {
                    "client_id": "123",
                    "client_secret": "secret",
                    "refresh_token": "refresh",
                    "profile_url": "https://www.strava.com/athletes/1",
                    "include_activity_urls": True,
                },
                "units": {"distance": "km"},
                "heatmaps": {"week_start": "monday"},
            },
        )

    def test_garmin_config_omits_optional_fields(self) -> None:
        config = write_ci_config.build_ci_config(
            {"SYNC_SOURCE": "garmin", "GARMIN_TOKENS_B64": "abc", "DASHBOARD_GARMIN_ACTIVITY_LINKS": "off"}
        )
        self.assertEqual(
            config,
            {"source": "garmin", "garmin": {"token_store_b64": "abc", "email": "", "password": ""}},
        )

    def test_intervals_athlete_id_defaults_to_key_owner(self) -> None:
        config = write_ci_config.build_ci_config({"SYNC_SOURCE": "intervals", "INTERVALS_API_KEY": "k"})
        self.assertEqual(config["intervals"], {"api_key": "k", "athlete_id": "0"})

        config = write_ci_config.build_ci_config(
            {"SYNC_SOURCE": "Intervals", "INTERVALS_API_KEY": "k", "INTERVALS_ATHLETE_ID": " i42 "}
        )
        self.assertEqual(config["source"], "intervals")
        self.assertEqual(config["intervals"]["athlete_id"], "i42")

    def test_unknown_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            write_ci_config.build_ci_config({"SYNC_SOURCE": "fitbit"})


class WriteCiConfigScriptTests(unittest.TestCase):
    def test_special_characters_round_trip_through_yaml(self) -> None:
        # Run in a subprocess so the real PyYAML is used (other tests stub it).
        tricky = 'k"ey\\with: #yaml\nstuff'
        env = dict(
            os.environ,
            SYNC_SOURCE="intervals",
            INTERVALS_API_KEY=tricky,
            DASHBOARD_INTERVALS_PROFILE_URL='https://intervals.icu/"x"',
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "config.local.yaml")
            subprocess.run(
                [sys.executable, os.path.join(SCRIPTS_DIR, "write_ci_config.py"), "--output", output],
                check=True,
                capture_output=True,
                env=env,
            )
            loaded = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
                    output,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        config = json.loads(loaded.stdout)
        self.assertEqual(config["intervals"]["api_key"], tricky)
        self.assertEqual(config["intervals"]["profile_url"], 'https://intervals.icu/"x"')


if __name__ == "__main__":
    unittest.main()
