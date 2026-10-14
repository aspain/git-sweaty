import os
import sys
import types
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import generate_heatmaps  # noqa: E402
import setup_auth  # noqa: E402
import source_links  # noqa: E402
import utils  # noqa: E402

CASES = [
    ("strava", "strava.com/athletes/123/", "https://strava.com/athletes/123"),
    ("strava", "https://www.strava.com/", None),
    ("strava", "https://connect.garmin.com/modern/profile/abc", None),
    ("garmin", "https://connect.garmin.com/profile/abc/activities", "https://connect.garmin.com/modern/profile/abc"),
    ("garmin", "https://connect.garmin.com/modern/", None),
    ("intervals", "intervals.icu/", "https://intervals.icu"),
    ("intervals", "https://intervals.icu/athlete/i1/", "https://intervals.icu/athlete/i1"),
    ("intervals", "https://www.strava.com/athletes/1", None),
]


class SourceLinksTests(unittest.TestCase):
    def test_registry_covers_every_supported_source(self) -> None:
        self.assertEqual(set(source_links.SOURCE_LINK_SPECS), set(utils.SUPPORTED_SOURCES))

    def test_normalize_profile_url(self) -> None:
        for source, raw, expected in CASES:
            with self.subTest(source=source, raw=raw):
                if expected is None:
                    with self.assertRaises(ValueError):
                        source_links.normalize_profile_url(raw, source)
                else:
                    self.assertEqual(source_links.normalize_profile_url(raw, source), expected)

    def test_empty_value_normalizes_to_empty(self) -> None:
        self.assertEqual(source_links.normalize_profile_url("  ", "strava"), "")

    def test_setup_and_dashboard_generation_agree(self) -> None:
        for source, raw, expected in CASES:
            with self.subTest(source=source, raw=raw):
                rendered = generate_heatmaps._profile_url_from_config({source: {"profile_url": raw}}, source)
                self.assertEqual(rendered, expected)
                if expected is None:
                    with self.assertRaises(ValueError):
                        setup_auth._normalize_provider_profile_url(raw, source)
                else:
                    self.assertEqual(setup_auth._normalize_provider_profile_url(raw, source), expected)


if __name__ == "__main__":
    unittest.main()
