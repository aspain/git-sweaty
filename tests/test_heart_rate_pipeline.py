import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import yaml


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import aggregate  # noqa: E402
import generate_heatmaps  # noqa: E402
import normalize  # noqa: E402


STRAVA_FIXTURE = {
    "id": "100001",
    "start_date_local": "2026-06-15T07:00:00+00:00",
    "sport_type": "Run",
    "type": "Run",
    "name": "Morning Run",
    "distance": 5000,
    "moving_time": 1800,
    "total_elevation_gain": 50,
    "average_heartrate": 148.6,
}

GARMIN_FIXTURE = {
    "id": "200002",
    "start_date_local": "2026-06-15T07:00:00",
    "start_date": "2026-06-15T14:00:00",
    "type": "running",
    "sport_type": "running",
    "name": "Garmin Run",
    "distance": 5000,
    "moving_time": 1800,
    "total_elevation_gain": 50,
    "average_heartrate": 148.6,
    "provider": "garmin",
}


def _write_fixture(tmpdir: str, source: str, payload: dict) -> None:
    raw_dir = os.path.join(tmpdir, "activities", "raw", source)
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, f"{payload['id']}.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _write_config(tmpdir: str, source: str) -> None:
    config = {
        "source": source,
        "sync": {},
        "activities": {"include_all_types": True},
        "units": {"distance": "mi", "elevation": "ft"},
        "heatmaps": {"week_start": "sunday"},
    }
    with open(os.path.join(tmpdir, "config.yaml"), "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle)


def _run_pipeline_in_tmp(tmpdir: str) -> dict:
    previous_cwd = os.getcwd()
    os.chdir(tmpdir)
    try:
        normalize.ensure_dir("data")
        items = normalize.normalize()
        normalize.write_json(normalize.OUT_PATH, items)
        output = aggregate.aggregate()
        aggregate.ensure_dir("data")
        aggregate.write_json(aggregate.OUT_PATH, output)
        with mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None):
            generate_heatmaps.generate(write_svgs=False)
        with open(os.path.join(tmpdir, "site", "data.json"), "r", encoding="utf-8") as handle:
            return json.load(handle)
    finally:
        os.chdir(previous_cwd)


class HeartRatePipelineTests(unittest.TestCase):
    def test_strava_fixture_propagates_heart_rate_to_site_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, "strava")
            _write_fixture(tmpdir, "strava", STRAVA_FIXTURE)

            data = _run_pipeline_in_tmp(tmpdir)

        entry = data["aggregates"]["2026"]["Run"]["2026-06-15"]
        self.assertAlmostEqual(entry["heart_rate"], 148.6)
        self.assertAlmostEqual(entry["hr_weighted_sum"], 148.6 * 1800)
        self.assertEqual(entry["hr_time"], 1800.0)

    def test_garmin_fixture_propagates_heart_rate_to_site_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, "garmin")
            _write_fixture(tmpdir, "garmin", GARMIN_FIXTURE)

            data = _run_pipeline_in_tmp(tmpdir)

        entry = data["aggregates"]["2026"]["Run"]["2026-06-15"]
        self.assertAlmostEqual(entry["heart_rate"], 148.6)
        self.assertAlmostEqual(entry["hr_weighted_sum"], 148.6 * 1800)
        self.assertEqual(entry["hr_time"], 1800.0)

    def test_no_heart_rate_fixture_omits_hr_fields(self) -> None:
        no_hr_fixture = dict(STRAVA_FIXTURE)
        no_hr_fixture["id"] = "100003"
        del no_hr_fixture["average_heartrate"]
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, "strava")
            _write_fixture(tmpdir, "strava", no_hr_fixture)

            data = _run_pipeline_in_tmp(tmpdir)

        entry = data["aggregates"]["2026"]["Run"]["2026-06-15"]
        self.assertNotIn("heart_rate", entry)
        self.assertEqual(entry.get("hr_time", 0), 0)


if __name__ == "__main__":
    unittest.main()
