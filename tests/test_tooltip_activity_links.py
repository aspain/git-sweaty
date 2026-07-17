import json
import os
import re
import shutil
import subprocess
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class TooltipActivityLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            app_js = handle.read()

        function_patterns = {
            "parse_strava_activity_url": r"function parseStravaActivityUrl\(value\)\s*{[\s\S]*?\n}\n",
            "capitalize_label_start": r"function capitalizeLabelStart\(label\)\s*{[\s\S]*?\n}\n",
            "prettify_type": r"function prettifyType\(type\)\s*{[\s\S]*?\n}\n",
            "display_type": r"function displayType\(type\)\s*{[\s\S]*?\n}\n",
            "normalize_tooltip_href": r"function normalizeTooltipHref\(value\)\s*{[\s\S]*?\n}\n",
            "create_text_line": r"function createTooltipTextLine\(text\)\s*{[\s\S]*?\n}\n",
            "create_linked_line": r"function createTooltipLinkedTypeLine\(prefix, label, suffix, href\)\s*{[\s\S]*?\n}\n",
            "create_activity_line": r"function createTooltipActivityLine\(prefix, typeLabel, activityName, href\)\s*{[\s\S]*?\n}\n",
            "format_tooltip_duration": r"function formatTooltipDuration\(seconds\)\s*{[\s\S]*?\n}\n",
            "format_tooltip_metric_lines": r"function formatTooltipMetricLines\(entry, units, prefix = \"\"\)\s*{[\s\S]*?\n}\n",
            "activity_order": r"function activityTypeOrderForTooltip\(typeBreakdown, types\)\s*{[\s\S]*?\n}\n",
            "format_lines_with_links": r"function formatTypeBreakdownLinesWithLinks\(\s*typeBreakdown,\s*types,\s*activityLinksByType,\s*typeMetricsByType = null,\s*units = \{ distance: \"mi\", elevation: \"ft\" \},\s*\)\s*{[\s\S]*?\n}\n",
            "flatten_links": r"function flattenTooltipActivityLinks\(activityLinksByType\)\s*{[\s\S]*?\n}\n",
            "single_activity_line": r"function createSingleTooltipActivityLine\(typeLabel, activityLinksByType\)\s*{[\s\S]*?\n}\n",
            "first_link": r"function firstTooltipActivityLink\(activityLinksByType, preferredType\)\s*{[\s\S]*?\n}\n",
        }
        extracted: dict[str, str] = {}
        for key, pattern in function_patterns.items():
            match = re.search(pattern, app_js)
            if not match:
                raise AssertionError(f"Could not find helper for {key} in site/app.js")
            extracted[key] = match.group(0)
        cls.sources = extracted

    def _run_js(self, expression: str, payload: dict) -> object:
        script = (
            "const TYPE_LABEL_OVERRIDES = { HighIntensityIntervalTraining: \"HITT\", Workout: \"Other Workout\" };\n"
            "let TYPE_META = {};\n"
            f"{self.sources['parse_strava_activity_url']}\n"
            f"{self.sources['capitalize_label_start']}\n"
            f"{self.sources['prettify_type']}\n"
            f"{self.sources['display_type']}\n"
            f"{self.sources['normalize_tooltip_href']}\n"
            f"{self.sources['create_text_line']}\n"
            f"{self.sources['create_linked_line']}\n"
            f"{self.sources['create_activity_line']}\n"
            f"{self.sources['format_tooltip_duration']}\n"
            f"{self.sources['format_tooltip_metric_lines']}\n"
            f"{self.sources['activity_order']}\n"
            f"{self.sources['format_lines_with_links']}\n"
            f"{self.sources['flatten_links']}\n"
            f"{self.sources['single_activity_line']}\n"
            f"{self.sources['first_link']}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            f"const result = {expression};\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_format_type_breakdown_links_single_activity_type_label(self) -> None:
        result = self._run_js(
            "formatTypeBreakdownLinesWithLinks(payload.breakdown, payload.types, payload.links)",
            {
                "breakdown": {"typeCounts": {"WeightTraining": 1}},
                "types": ["WeightTraining"],
                "links": {
                    "WeightTraining": [
                        {"href": "https://www.strava.com/activities/101", "name": "Session"},
                    ]
                },
            },
        )
        self.assertEqual(
            result,
            [[{"text": "Weight Training: "}, {"text": "Session", "href": "https://www.strava.com/activities/101"}]],
        )

    def test_format_type_breakdown_links_lists_activity_rows_for_multiple_same_type(self) -> None:
        result = self._run_js(
            "formatTypeBreakdownLinesWithLinks(payload.breakdown, payload.types, payload.links)",
            {
                "breakdown": {"typeCounts": {"TrailRun": 2}},
                "types": ["TrailRun"],
                "links": {
                    "TrailRun": [
                        {"href": "https://www.strava.com/activities/202", "name": "Trail Run 1"},
                        {"href": "https://www.strava.com/activities/203", "name": "Trail Run 2"},
                    ]
                },
            },
        )
        self.assertEqual(
            result[0],
            [{"text": "Trail Run: "}, {"text": "Trail Run 1", "href": "https://www.strava.com/activities/202"}],
        )
        self.assertEqual(
            result[1],
            [{"text": "Trail Run: "}, {"text": "Trail Run 2", "href": "https://www.strava.com/activities/203"}],
        )

    def test_format_type_breakdown_lines_include_per_type_metrics(self) -> None:
        result = self._run_js(
            "formatTypeBreakdownLinesWithLinks(payload.breakdown, payload.types, payload.links, payload.typeMetrics, payload.units)",
            {
                "breakdown": {"typeCounts": {"TrailRun": 1, "Workout": 1}},
                "types": ["TrailRun", "Workout"],
                "links": {},
                "typeMetrics": {
                    "TrailRun": {"distance": 5230.368, "elevation_gain": 145.084, "moving_time": 2280},
                    "Workout": {"distance": 0, "elevation_gain": 0, "moving_time": 4320},
                },
                "units": {"distance": "mi", "elevation": "ft"},
            },
        )
        self.assertEqual(
            result,
            [
                [{"text": "Trail Run: 1"}],
                [{"text": "- Distance: 3.25 mi"}],
                [{"text": "- Elevation: 476 ft"}],
                [{"text": "- Duration: 38m"}],
                [{"text": "Other Workout: 1"}],
                [{"text": "- Duration: 1h 12m"}],
            ],
        )

    def test_single_activity_metric_lines_use_hyphen_prefix(self) -> None:
        result = self._run_js(
            "formatTooltipMetricLines(payload.entry, payload.units, '- ')",
            {
                "entry": {"distance": 1609.344, "elevation_gain": 30.48, "moving_time": 3600},
                "units": {"distance": "mi", "elevation": "ft"},
            },
        )
        self.assertEqual(
            result,
            [
                [{"text": "- Distance: 1.00 mi"}],
                [{"text": "- Elevation: 100 ft"}],
                [{"text": "- Duration: 1h 0m"}],
            ],
        )

    def test_format_type_breakdown_preserves_count_when_only_some_links_are_available(self) -> None:
        result = self._run_js(
            "formatTypeBreakdownLinesWithLinks(payload.breakdown, payload.types, payload.links)",
            {
                "breakdown": {"typeCounts": {"TrailRun": 3}},
                "types": ["TrailRun"],
                "links": {
                    "TrailRun": [
                        {"href": "https://www.strava.com/activities/202", "name": "Trail Run 1"},
                        {"href": "https://www.strava.com/activities/203", "name": "Trail Run 2"},
                    ]
                },
            },
        )
        self.assertEqual(
            result,
            [
                [{"text": "Trail Run: 3"}],
                [{"text": "Trail Run: "}, {"text": "Trail Run 1", "href": "https://www.strava.com/activities/202"}],
                [{"text": "Trail Run: "}, {"text": "Trail Run 2", "href": "https://www.strava.com/activities/203"}],
            ],
        )

    def test_single_activity_line_uses_activity_name_when_unique_link_exists(self) -> None:
        result = self._run_js(
            "createSingleTooltipActivityLine(payload.typeLabel, payload.links)",
            {
                "typeLabel": "Ride",
                "links": {
                    "Ride": [
                        {"href": "https://www.strava.com/activities/303", "name": "Outdoor Ride"},
                    ]
                },
            },
        )
        self.assertEqual(
            result,
            [{"text": "Ride: "}, {"text": "Outdoor Ride", "href": "https://www.strava.com/activities/303"}],
        )

    def test_first_tooltip_activity_link_prefers_type_and_requires_unique_link(self) -> None:
        result = self._run_js(
            "({ preferred: firstTooltipActivityLink(payload.links, payload.preferred), all: firstTooltipActivityLink(payload.links, 'all') })",
            {
                "preferred": "Run",
                "links": {
                    "Run": [{"href": "https://www.strava.com/activities/1"}],
                    "Ride": [{"href": "https://www.strava.com/activities/2"}],
                },
            },
        )
        self.assertEqual(result["preferred"], "https://www.strava.com/activities/1")
        self.assertEqual(result["all"], "")

    def test_parse_strava_activity_url_rejects_non_strava_hosts(self) -> None:
        result = self._run_js(
            "parseStravaActivityUrl(payload.value)",
            {"value": "https://example.com/activities/123"},
        )
        self.assertIsNone(result)

    def test_parse_strava_activity_url_accepts_garmin_activity_links(self) -> None:
        result = self._run_js(
            "parseStravaActivityUrl(payload.value)",
            {"value": "https://connect.garmin.com/modern/activity/123"},
        )
        self.assertEqual(result, {"href": "https://connect.garmin.com/modern/activity/123"})


if __name__ == "__main__":
    unittest.main()
