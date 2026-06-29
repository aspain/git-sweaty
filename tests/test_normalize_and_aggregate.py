import os
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import aggregate  # noqa: E402
import normalize  # noqa: E402


class NormalizeAndAggregateTests(unittest.TestCase):
    def test_normalize_activity_extracts_fields_and_prefers_positive_duration(self) -> None:
        activity = {
            "id": 123,
            "start_date_local": "2026-02-13 08:15:30+00:00",
            "sport_type": "Running",
            "type": "Workout",
            "name": "Morning Session",
            "distance": "1609.344",
            "moving_time": 0,
            "duration": 95.0,
            "elapsed_time": 120.0,
            "totalElevationGain": "50",
            "average_heartrate": 158.2,
        }
        type_aliases = {"Run": "Jog"}

        normalized = normalize._normalize_activity(activity, type_aliases=type_aliases, source="strava")

        self.assertEqual(normalized["id"], "123")
        self.assertEqual(normalized["date"], "2026-02-13")
        self.assertEqual(normalized["year"], 2026)
        self.assertEqual(normalized["start_date_local"], "2026-02-13T08:15:30+00:00")
        self.assertEqual(normalized["raw_activity_type"], "Workout")
        self.assertEqual(normalized["raw_type"], "Running")
        self.assertEqual(normalized["type"], "Jog")
        self.assertEqual(normalized["distance"], 1609.344)
        self.assertEqual(normalized["moving_time"], 95.0)
        self.assertEqual(normalized["elevation_gain"], 50.0)
        self.assertEqual(normalized["name"], "Morning Session")
        self.assertAlmostEqual(normalized["heart_rate"], 158.2)

    def test_normalize_activity_extracts_garmin_heart_rate_from_summary_dto(self) -> None:
        activity = {
            "id": 456,
            "start_date_local": "2026-03-01T07:00:00+00:00",
            "activityType": {"typeKey": "running"},
            "distance": 5000,
            "duration": 1800,
            "summaryDTO": {"averageHR": 145, "movingDuration": 1750},
        }

        normalized = normalize._normalize_activity(activity, type_aliases={}, source="garmin")

        self.assertAlmostEqual(normalized["heart_rate"], 145.0)

    def test_normalize_activity_extracts_garmin_heart_rate_from_top_level(self) -> None:
        activity = {
            "id": 789,
            "start_date_local": "2026-03-02T07:00:00+00:00",
            "activityType": {"typeKey": "running"},
            "distance": 3000,
            "duration": 1200,
            "averageHR": 152,
        }

        normalized = normalize._normalize_activity(activity, type_aliases={}, source="garmin")

        self.assertAlmostEqual(normalized["heart_rate"], 152.0)

    def test_normalize_activity_omits_heart_rate_when_missing(self) -> None:
        activity = {
            "id": 321,
            "start_date_local": "2026-03-03T07:00:00+00:00",
            "sport_type": "Running",
            "distance": 1000,
            "moving_time": 300,
        }

        normalized = normalize._normalize_activity(activity, type_aliases={}, source="strava")

        self.assertNotIn("heart_rate", normalized)

    def test_normalize_activity_rejects_implausible_heart_rate(self) -> None:
        activity = {
            "id": 654,
            "start_date_local": "2026-03-04T07:00:00+00:00",
            "sport_type": "Running",
            "distance": 1000,
            "moving_time": 300,
            "average_heartrate": 300,
        }

        normalized = normalize._normalize_activity(activity, type_aliases={}, source="strava")

        self.assertNotIn("heart_rate", normalized)

    def test_normalize_activity_returns_empty_when_missing_required_fields(self) -> None:
        self.assertEqual(normalize._normalize_activity({}, {}, "strava"), {})
        self.assertEqual(normalize._normalize_activity({"id": "x"}, {}, "strava"), {})
        self.assertEqual(normalize._normalize_activity({"start_date_local": "2026-01-01T00:00:00Z"}, {}, "strava"), {})

    def test_aggregate_groups_by_day_and_filters_types(self) -> None:
        config = {
            "activities": {
                "include_all_types": False,
                "types": ["Run"],
                "exclude_types": ["Ride"],
            }
        }
        items = [
            {
                "id": "a",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Run",
                "distance": 1000,
                "moving_time": 100,
                "elevation_gain": 10,
            },
            {
                "id": "c",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Run",
                "distance": 250,
                "moving_time": 25,
                "elevation_gain": 5,
            },
            {
                "id": "b",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Ride",
                "distance": 9999,
                "moving_time": 999,
                "elevation_gain": 999,
            },
        ]

        with (
            mock.patch("aggregate.load_config", return_value=config),
            mock.patch("aggregate.os.path.exists", return_value=True),
            mock.patch("aggregate.read_json", return_value=items),
            mock.patch("aggregate.utc_now", return_value=datetime(2026, 2, 14, tzinfo=timezone.utc)),
        ):
            output = aggregate.aggregate()

        run_entry = output["years"]["2026"]["Run"]["2026-02-01"]
        self.assertEqual(run_entry["count"], 2)
        self.assertEqual(run_entry["distance"], 1250.0)
        self.assertEqual(run_entry["moving_time"], 125.0)
        self.assertEqual(run_entry["elevation_gain"], 15.0)
        self.assertEqual(run_entry["activity_ids"], ["a", "c"])
        self.assertNotIn("Ride", output["years"]["2026"])

    def test_aggregate_computes_time_weighted_heart_rate(self) -> None:
        config = {"activities": {"include_all_types": True}}
        items = [
            {
                "id": "a",
                "date": "2026-04-01",
                "year": 2026,
                "type": "Run",
                "distance": 5000,
                "moving_time": 1800,
                "elevation_gain": 0,
                "heart_rate": 160.0,
            },
            {
                "id": "b",
                "date": "2026-04-01",
                "year": 2026,
                "type": "Run",
                "distance": 8000,
                "moving_time": 3600,
                "elevation_gain": 0,
                "heart_rate": 140.0,
            },
        ]

        with (
            mock.patch("aggregate.load_config", return_value=config),
            mock.patch("aggregate.os.path.exists", return_value=True),
            mock.patch("aggregate.read_json", return_value=items),
            mock.patch("aggregate.utc_now", return_value=datetime(2026, 4, 14, tzinfo=timezone.utc)),
        ):
            output = aggregate.aggregate()

        entry = output["years"]["2026"]["Run"]["2026-04-01"]
        self.assertEqual(entry["hr_time"], 5400.0)
        self.assertEqual(entry["hr_weighted_sum"], 160.0 * 1800 + 140.0 * 3600)
        self.assertAlmostEqual(entry["heart_rate"], (160.0 * 1800 + 140.0 * 3600) / 5400.0)

    def test_aggregate_skips_heart_rate_when_no_data(self) -> None:
        config = {"activities": {"include_all_types": True}}
        items = [
            {
                "id": "a",
                "date": "2026-04-02",
                "year": 2026,
                "type": "Run",
                "distance": 5000,
                "moving_time": 1800,
                "elevation_gain": 0,
            },
        ]

        with (
            mock.patch("aggregate.load_config", return_value=config),
            mock.patch("aggregate.os.path.exists", return_value=True),
            mock.patch("aggregate.read_json", return_value=items),
            mock.patch("aggregate.utc_now", return_value=datetime(2026, 4, 14, tzinfo=timezone.utc)),
        ):
            output = aggregate.aggregate()

        entry = output["years"]["2026"]["Run"]["2026-04-02"]
        self.assertEqual(entry["hr_time"], 0.0)
        self.assertEqual(entry["hr_weighted_sum"], 0.0)
        self.assertNotIn("heart_rate", entry)

    def test_aggregate_drops_heart_rate_when_moving_time_zero(self) -> None:
        config = {"activities": {"include_all_types": True}}
        items = [
            {
                "id": "a",
                "date": "2026-04-03",
                "year": 2026,
                "type": "StrengthTraining",
                "distance": 0,
                "moving_time": 0,
                "elevation_gain": 0,
                "heart_rate": 125.0,
            },
        ]

        with (
            mock.patch("aggregate.load_config", return_value=config),
            mock.patch("aggregate.os.path.exists", return_value=True),
            mock.patch("aggregate.read_json", return_value=items),
            mock.patch("aggregate.utc_now", return_value=datetime(2026, 4, 14, tzinfo=timezone.utc)),
        ):
            output = aggregate.aggregate()

        entry = output["years"]["2026"]["StrengthTraining"]["2026-04-03"]
        self.assertEqual(entry["hr_time"], 0.0)
        self.assertNotIn("heart_rate", entry)


if __name__ == "__main__":
    unittest.main()
