import os
import sys
import types
import unittest
from datetime import datetime


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import utils  # noqa: E402


class UtilsTests(unittest.TestCase):
    def test_deep_merge_recursively_merges_nested_dicts(self) -> None:
        base = {"a": 1, "b": {"c": 2, "d": 3}, "e": {"f": 4}}
        override = {"b": {"d": 30, "x": 99}, "e": 5}

        merged = utils._deep_merge(base, override)

        self.assertEqual(merged, {"a": 1, "b": {"c": 2, "d": 30, "x": 99}, "e": 5})
        self.assertEqual(base, {"a": 1, "b": {"c": 2, "d": 3}, "e": {"f": 4}})

    def test_normalize_source_accepts_supported_values_and_defaults(self) -> None:
        self.assertEqual(utils.normalize_source("Strava"), "strava")
        self.assertEqual(utils.normalize_source("  garmin "), "garmin")
        self.assertEqual(utils.normalize_source(None), "strava")

    def test_normalize_source_rejects_unknown_value(self) -> None:
        with self.assertRaises(ValueError) as exc_ctx:
            utils.normalize_source("fitbit")
        self.assertIn("Unsupported source", str(exc_ctx.exception))
        self.assertIn("garmin, strava", str(exc_ctx.exception))

    def test_parse_iso_datetime_handles_z_suffix(self) -> None:
        dt = utils.parse_iso_datetime("2026-02-13T08:15:30Z")
        self.assertEqual(dt, datetime.fromisoformat("2026-02-13T08:15:30+00:00"))

    def test_parse_iso_datetime_handles_fractional_seconds_with_long_precision(self) -> None:
        dt = utils.parse_iso_datetime("2026-02-13T08:15:30.123456789+00:00")
        self.assertEqual(dt, datetime.fromisoformat("2026-02-13T08:15:30.123456+00:00"))

    def test_format_helpers_cover_us_and_metric_units(self) -> None:
        self.assertEqual(utils.format_duration(3599.7), "1h 0m")
        self.assertEqual(utils.format_duration(90), "1m")
        self.assertEqual(utils.format_distance(1609.344, "mi"), "1.00 mi")
        self.assertEqual(utils.format_distance(1609.344, "km"), "1.61 km")
        self.assertEqual(utils.format_elevation(100, "ft"), "328 ft")
        self.assertEqual(utils.format_elevation(100, "m"), "100 m")

    def test_format_heart_rate_rounds_to_whole_bpm(self) -> None:
        self.assertEqual(utils.format_heart_rate(0.0), "0 bpm")
        self.assertEqual(utils.format_heart_rate(148.6), "149 bpm")
        self.assertEqual(utils.format_heart_rate(162.0), "162 bpm")


if __name__ == "__main__":
    unittest.main()
