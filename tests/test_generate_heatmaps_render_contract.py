import json
import os
import re
import sys
import tempfile
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

import generate_heatmaps  # noqa: E402


class GenerateHeatmapsRenderContractTests(unittest.TestCase):
    def test_year_range_uses_start_date_lookback_or_data(self) -> None:
        with mock.patch("generate_heatmaps.utc_now", return_value=datetime(2026, 2, 14, tzinfo=timezone.utc)):
            years_from_start = generate_heatmaps._year_range_from_config(
                {"sync": {"start_date": "2024-03-01"}},
                {"2025": {}},
            )
            years_from_lookback = generate_heatmaps._year_range_from_config(
                {"sync": {"lookback_years": 2}},
                {"2020": {}},
            )
            years_from_data = generate_heatmaps._year_range_from_config(
                {"sync": {}},
                {"2021": {}, "2023": {}},
            )

        self.assertEqual(years_from_start, [2024, 2025, 2026])
        self.assertEqual(years_from_lookback, [2025, 2026])
        self.assertEqual(years_from_data, [2021, 2022, 2023, 2024, 2025, 2026])

    def test_type_totals_sums_positive_counts_only(self) -> None:
        aggregates_years = {
            "2025": {
                "Run": {
                    "2025-01-01": {"count": 2},
                    "2025-01-02": {"count": 0},
                },
                "Ride": {
                    "2025-01-01": {"count": 3},
                },
            },
            "2026": {
                "Run": {
                    "2026-01-01": {"count": 1},
                }
            },
        }
        self.assertEqual(generate_heatmaps._type_totals(aggregates_years), {"Run": 3, "Ride": 3})

    def test_svg_for_year_contains_expected_labels_and_titles(self) -> None:
        entries = {
            "2025-01-01": {
                "count": 2,
                "distance": 1609.344,
                "moving_time": 3600,
                "elevation_gain": 100,
                "activity_ids": ["a", "b"],
            }
        }
        svg = generate_heatmaps._svg_for_year(
            2025,
            entries,
            {"distance": "mi", "elevation": "ft"},
            generate_heatmaps.DEFAULT_COLORS,
        )

        self.assertIn(">2025</text>", svg)
        self.assertIn(">Jan</text>", svg)
        self.assertIn(">Dec</text>", svg)
        self.assertIn(">Sun</text>", svg)
        self.assertIn(">Sat</text>", svg)
        self.assertIn('data-date="2025-01-01"', svg)
        self.assertIn("<title>2025-01-01\n2 workouts\nDistance: 1.00 mi\nDuration: 1h 0m\nElevation: 328 ft</title>", svg)

    def test_svg_for_year_supports_monday_week_start(self) -> None:
        entries = {
            "2025-01-05": {
                "count": 1,
                "distance": 0,
                "moving_time": 600,
                "elevation_gain": 0,
                "activity_ids": ["a"],
            }
        }
        svg = generate_heatmaps._svg_for_year(
            2025,
            entries,
            {"distance": "mi", "elevation": "ft"},
            generate_heatmaps.DEFAULT_COLORS,
            week_start="monday",
        )

        day_labels = re.findall(
            r'text-anchor="end" dominant-baseline="middle">([A-Za-z]{3})</text>',
            svg,
        )
        self.assertEqual(day_labels, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertRegex(
            svg,
            r'<rect x="0" y="84" width="12" height="12" rx="3" ry="3" fill="[^"]+" data-date="2025-01-05">',
        )

    def test_load_activities_filters_invalid_rows_and_parses_hour(self) -> None:
        rows = [
            {
                "id": "123",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Run",
                "raw_type": "Run",
                "start_date_local": "2026-02-01T09:15:00+00:00",
                "name": "Morning Run",
            },
            {
                "date": "2026-02-02",
                "year": 2026,
                "type": "Ride",
                "raw_type": "Ride",
                "start_date_local": "bad-date",
            },
            {"date": "2026-02-03", "year": 2026, "type": "Run"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            activities_path = os.path.join(tmpdir, "activities_normalized.json")
            with open(activities_path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle)

            with mock.patch("generate_heatmaps.ACTIVITIES_PATH", activities_path):
                activities = generate_heatmaps._load_activities()

        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[0]["hour"], 9)
        self.assertIsNone(activities[1]["hour"])
        self.assertNotIn("url", activities[0])

    def test_load_activities_includes_strava_urls_when_enabled(self) -> None:
        rows = [
            {
                "id": "123456789",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Run",
                "raw_type": "Run",
                "start_date_local": "2026-02-01T09:15:00+00:00",
                "name": "Morning Run",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            activities_path = os.path.join(tmpdir, "activities_normalized.json")
            with open(activities_path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle)

            with mock.patch("generate_heatmaps.ACTIVITIES_PATH", activities_path):
                activities = generate_heatmaps._load_activities(
                    source="strava",
                    include_strava_activity_urls=True,
                )

        self.assertEqual(activities[0]["url"], "https://www.strava.com/activities/123456789")
        self.assertEqual(activities[0]["name"], "Morning Run")

    def test_load_activities_includes_garmin_urls_when_enabled(self) -> None:
        rows = [
            {
                "id": "888999",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Run",
                "raw_type": "Run",
                "start_date_local": "2026-02-01T09:15:00+00:00",
                "name": "Garmin Run",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            activities_path = os.path.join(tmpdir, "activities_normalized.json")
            with open(activities_path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle)

            with mock.patch("generate_heatmaps.ACTIVITIES_PATH", activities_path):
                activities = generate_heatmaps._load_activities(
                    source="garmin",
                    include_activity_urls=True,
                )

        self.assertEqual(activities[0]["url"], "https://connect.garmin.com/modern/activity/888999")
        self.assertEqual(activities[0]["name"], "Garmin Run")

    def test_generate_includes_repo_slug_when_available(self) -> None:
        captured = {}

        with (
            mock.patch("generate_heatmaps.load_config", return_value={"sync": {}, "activities": {}, "source": "strava"}),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value="owner/repo"),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(captured["payload"].get("repo"), "owner/repo")

    def test_repo_slug_prefers_dashboard_repo_env(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"DASHBOARD_REPO": "owner/custom-fork", "GITHUB_REPOSITORY": "owner/git-sweaty"},
            clear=False,
        ):
            repo_slug = generate_heatmaps._repo_slug_from_git()

        self.assertEqual(repo_slug, "owner/custom-fork")

    def test_repo_slug_prefers_github_repository_on_actions_env_mismatch(self) -> None:
        renamed_repo = "owner/custom-renamed-repo"
        with mock.patch.dict(
            "os.environ",
            {
                "DASHBOARD_REPO": "owner/git-sweaty",
                "GITHUB_REPOSITORY": renamed_repo,
                "GITHUB_ACTIONS": "true",
            },
            clear=False,
        ):
            repo_slug = generate_heatmaps._repo_slug_from_git()

        self.assertEqual(repo_slug, renamed_repo)

    def test_repo_slug_uses_github_repository_when_dashboard_repo_invalid(self) -> None:
        renamed_repo = "owner/custom-renamed-repo"
        with mock.patch.dict(
            "os.environ",
            {
                "DASHBOARD_REPO": "not-a-slug",
                "GITHUB_REPOSITORY": renamed_repo,
                "GITHUB_ACTIONS": "true",
            },
            clear=False,
        ):
            repo_slug = generate_heatmaps._repo_slug_from_git()

        self.assertEqual(repo_slug, renamed_repo)

    def test_generate_includes_strava_profile_url_when_configured(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "strava",
                    "strava": {"profile_url": "https://www.strava.com/athletes/12345"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(
            captured["payload"].get("strava_profile_url"),
            "https://www.strava.com/athletes/12345",
        )

    def test_generate_includes_week_start_when_configured(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "strava",
                    "heatmaps": {"week_start": "monday"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(captured["payload"].get("week_start"), "monday")

    def test_generate_passes_strava_activity_link_opt_in_to_load_activities(self) -> None:
        captured = {}
        load_args = {}

        def _fake_load_activities(*, source: str, include_strava_activity_urls: bool = False, **kwargs):
            load_args["source"] = source
            load_args["include_strava_activity_urls"] = include_strava_activity_urls
            load_args["extra_kwargs"] = kwargs
            return []

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "strava",
                    "strava": {"include_activity_urls": True},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", side_effect=_fake_load_activities),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(
            load_args,
            {
                "source": "strava",
                "include_strava_activity_urls": True,
                "extra_kwargs": {},
            },
        )

    def test_generate_includes_garmin_profile_url_when_configured(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "garmin",
                    "garmin": {"profile_url": "https://connect.garmin.com/modern/profile/abc123"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(
            captured["payload"].get("garmin_profile_url"),
            "https://connect.garmin.com/modern/profile/abc123",
        )

    def test_generate_canonicalizes_garmin_profile_url_when_configured(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "garmin",
                    "garmin": {"profile_url": "https://connect.garmin.com/modern/profile/abc123/activities"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(
            captured["payload"].get("garmin_profile_url"),
            "https://connect.garmin.com/modern/profile/abc123",
        )

    def test_generate_passes_garmin_activity_link_opt_in_to_load_activities(self) -> None:
        load_args = {}

        def _fake_load_activities(*, source: str, include_garmin_activity_urls: bool = False, **kwargs):
            load_args["source"] = source
            load_args["include_garmin_activity_urls"] = include_garmin_activity_urls
            load_args["extra_kwargs"] = kwargs
            return []

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "garmin",
                    "garmin": {"include_activity_urls": True},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", side_effect=_fake_load_activities),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data"),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(
            load_args,
            {
                "source": "garmin",
                "include_garmin_activity_urls": True,
                "extra_kwargs": {},
            },
        )


    def test_load_activities_includes_intervals_urls_when_enabled(self) -> None:
        rows = [
            {
                "id": "i98765432",
                "date": "2026-02-01",
                "year": 2026,
                "type": "Ride",
                "raw_type": "VirtualRide",
                "start_date_local": "2026-02-01T09:15:00",
                "name": "Zwift Ride",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            activities_path = os.path.join(tmpdir, "activities_normalized.json")
            with open(activities_path, "w", encoding="utf-8") as handle:
                json.dump(rows, handle)

            with mock.patch("generate_heatmaps.ACTIVITIES_PATH", activities_path):
                activities = generate_heatmaps._load_activities(
                    source="intervals",
                    include_activity_urls=True,
                )
                activities_without_urls = generate_heatmaps._load_activities(source="intervals")

        self.assertEqual(activities[0]["url"], "https://intervals.icu/activities/i98765432")
        self.assertEqual(activities[0]["name"], "Zwift Ride")
        self.assertNotIn("url", activities_without_urls[0])

    def test_generate_includes_intervals_profile_url_when_configured(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "intervals",
                    "intervals": {"profile_url": "intervals.icu/athlete/i12345/"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(captured["payload"].get("source"), "intervals")
        self.assertEqual(captured["payload"].get("profile_url"), "https://intervals.icu/athlete/i12345")
        self.assertEqual(captured["payload"].get("intervals_profile_url"), "https://intervals.icu/athlete/i12345")

    def test_generate_accepts_setup_default_intervals_profile_url(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "intervals",
                    "intervals": {"profile_url": "https://intervals.icu"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(captured["payload"].get("intervals_profile_url"), "https://intervals.icu")

    def test_generate_rejects_non_intervals_profile_url_for_intervals_source(self) -> None:
        captured = {}

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "intervals",
                    "intervals": {"profile_url": "https://www.strava.com/athletes/123"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", return_value=[]),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data", side_effect=lambda payload: captured.setdefault("payload", payload)),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertNotIn("profile_url", captured["payload"])

    def test_generate_passes_intervals_activity_link_opt_in_to_load_activities(self) -> None:
        load_args = {}

        def _fake_load_activities(*, source: str, **kwargs):
            load_args["source"] = source
            load_args["kwargs"] = kwargs
            return []

        with (
            mock.patch(
                "generate_heatmaps.load_config",
                return_value={
                    "sync": {},
                    "activities": {},
                    "source": "intervals",
                    "intervals": {"include_activity_urls": "true"},
                },
            ),
            mock.patch("generate_heatmaps.os.path.exists", return_value=False),
            mock.patch("generate_heatmaps._load_activities", side_effect=_fake_load_activities),
            mock.patch("generate_heatmaps._repo_slug_from_git", return_value=None),
            mock.patch("generate_heatmaps._write_site_data"),
        ):
            generate_heatmaps.generate(write_svgs=False)

        self.assertEqual(load_args, {"source": "intervals", "kwargs": {"include_intervals_activity_urls": True}})

    def test_source_link_registry_covers_every_supported_source(self) -> None:
        import utils

        self.assertEqual(set(generate_heatmaps.SOURCE_LINK_SPECS), set(utils.SUPPORTED_SOURCES))
        expected_urls = {
            "strava": "https://www.strava.com/activities/42",
            "garmin": "https://connect.garmin.com/modern/activity/42",
            "intervals": "https://intervals.icu/activities/42",
        }
        for source, expected in expected_urls.items():
            self.assertEqual(generate_heatmaps._activity_url_from_id(source, "42"), expected)
            self.assertIsNotNone(generate_heatmaps._host_regex_for_source(source))
        self.assertEqual(generate_heatmaps.SOURCE_LINK_SPECS["intervals"]["display_name"], "intervals.icu")


if __name__ == "__main__":
    unittest.main()
