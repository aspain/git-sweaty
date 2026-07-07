import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import sync_dropbox as sd  # noqa: E402


class FilenameParsingTests(unittest.TestCase):
    def test_parses_expected_healthfitexporter_pattern(self):
        info = sd._parse_filename("2026-07-07-075900-Rad outdoor-WorkOutDoors.fit")
        self.assertIsNotNone(info)
        self.assertEqual(info["local_dt"].year, 2026)
        self.assertEqual(info["local_dt"].month, 7)
        self.assertEqual(info["local_dt"].day, 7)
        self.assertEqual(info["local_dt"].hour, 7)
        self.assertEqual(info["local_dt"].minute, 59)
        self.assertEqual(info["activity_name"], "Rad outdoor")
        self.assertEqual(info["source_app"], "WorkOutDoors")

    def test_splits_multi_hyphen_activity_names(self):
        info = sd._parse_filename("2026-07-05-214557-Traditionelles Krafttraining-StrengthLog.fit")
        self.assertEqual(info["activity_name"], "Traditionelles Krafttraining")
        self.assertEqual(info["source_app"], "StrengthLog")

    def test_returns_none_for_unrecognized_filename(self):
        self.assertIsNone(sd._parse_filename("random_export.fit"))
        self.assertIsNone(sd._parse_filename("not-a-fit-file.txt"))

    def test_case_insensitive_extension(self):
        info = sd._parse_filename("2026-06-30-191055-Freiwasserschwimmen-HealthFit.FIT")
        self.assertIsNotNone(info)


class SafeIdTests(unittest.TestCase):
    def test_sanitizes_spaces_and_strips_extension(self):
        self.assertEqual(
            sd._safe_id_from_filename("2026-07-07-075900-Rad outdoor-WorkOutDoors.fit"),
            "2026-07-07-075900-Rad_outdoor-WorkOutDoors",
        )

    def test_never_produces_path_traversal_ids(self):
        activity_id = sd._safe_id_from_filename("../../etc/passwd.fit")
        self.assertNotIn("/", activity_id)
        self.assertNotIn("..", activity_id)


class FitSportMappingTests(unittest.TestCase):
    def test_known_combinations(self):
        self.assertEqual(sd._map_fit_sport("cycling", "road"), "Ride")
        self.assertEqual(sd._map_fit_sport("cycling", "mountain_biking"), "MountainBikeRide")
        self.assertEqual(sd._map_fit_sport("cycling", "indoor_cycling"), "VirtualRide")
        self.assertEqual(sd._map_fit_sport("swimming", "open_water"), "Swim")
        self.assertEqual(sd._map_fit_sport("swimming", "lap_swimming"), "Swim")
        self.assertEqual(sd._map_fit_sport("running", "trail"), "TrailRun")
        self.assertEqual(sd._map_fit_sport("training", "strength_training"), "WeightTraining")

    def test_falls_back_to_sport_only_when_subsport_unknown(self):
        self.assertEqual(sd._map_fit_sport("cycling", "some_future_subsport"), "Ride")

    def test_unknown_sport_does_not_crash(self):
        result = sd._map_fit_sport("some_brand_new_sport", "")
        self.assertTrue(result)  # produces *something* rather than raising

    def test_handles_missing_values(self):
        self.assertEqual(sd._map_fit_sport(None, None), "Workout")


class BuildActivityTests(unittest.TestCase):
    def test_uses_fit_session_when_available(self):
        fake_session = {
            "start_dt_utc": datetime(2026, 7, 7, 5, 59, 0, tzinfo=timezone.utc),
            "sport": "cycling",
            "sub_sport": "road",
            "total_distance": 42195.5,
            "total_timer_time": 5400.0,
            "total_elapsed_time": 5600.0,
            "total_ascent": 312.0,
        }
        entry = {"name": "2026-07-07-075900-Rad outdoor-WorkOutDoors.fit", "content_hash": "abc123"}
        with mock.patch.object(sd, "_parse_fit_session", return_value=fake_session):
            activity = sd._build_activity(entry, b"dummy")

        self.assertEqual(activity["id"], "2026-07-07-075900-Rad_outdoor-WorkOutDoors")
        self.assertEqual(activity["type"], "Ride")
        self.assertEqual(activity["distance"], 42195.5)
        self.assertEqual(activity["moving_time"], 5400.0)
        self.assertEqual(activity["total_elevation_gain"], 312.0)
        self.assertEqual(activity["name"], "Rad outdoor")
        self.assertEqual(activity["source_app"], "WorkOutDoors")
        # DST-aware conversion: 05:59 UTC -> 07:59 Europe/Berlin in July
        self.assertEqual(activity["start_date_local"], "2026-07-07T07:59:00")

    def test_falls_back_to_filename_when_fit_parsing_fails(self):
        entry = {"name": "2026-07-04-074153-Freiwasserschwimmen-WorkOutDoors.fit"}
        with mock.patch.object(sd, "_parse_fit_session", side_effect=RuntimeError("corrupt file")):
            activity = sd._build_activity(entry, b"broken")

        self.assertIsNotNone(activity)
        self.assertEqual(activity["start_date_local"], "2026-07-04T07:41:53")
        # No FIT session data available -> zeroed-out metrics rather than a crash
        self.assertEqual(activity["distance"], 0.0)
        self.assertEqual(activity["name"], "Freiwasserschwimmen")

    def test_returns_none_when_no_timestamp_available_at_all(self):
        entry = {"name": "totally_unparseable_name.fit"}
        with mock.patch.object(sd, "_parse_fit_session", return_value=None):
            activity = sd._build_activity(entry, b"dummy")
        self.assertIsNone(activity)


if __name__ == "__main__":
    unittest.main()
