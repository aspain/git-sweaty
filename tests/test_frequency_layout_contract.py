import json
import os
import re
import shutil
import subprocess
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class FrequencyLayoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            cls.app_js = handle.read()

        match = re.search(
            r"function getDominantYearRailWidth\(widths\)\s*{[\s\S]*?\n}\n",
            cls.app_js,
        )
        if not match:
            raise AssertionError("Could not find getDominantYearRailWidth in site/app.js")
        cls.get_dominant_width_source = match.group(0)

    def _run_get_dominant_width(self, widths: list[float]) -> float:
        script = (
            "const payload = JSON.parse(process.argv[1]);\n"
            f"{self.get_dominant_width_source}\n"
            "const result = getDominantYearRailWidth(payload.widths);\n"
            "process.stdout.write(JSON.stringify({ result }));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps({"widths": widths})],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(json.loads(completed.stdout)["result"])

    def test_tie_between_two_year_width_buckets_prefers_smaller_bucket(self) -> None:
        result = self._run_get_dominant_width([212.2, 224.2])
        self.assertAlmostEqual(result, 212.2)

    def test_dominant_width_prefers_most_common_bucket_when_not_tied(self) -> None:
        result = self._run_get_dominant_width([212.1, 212.3, 224.1])
        self.assertAlmostEqual(result, 212.1)

    def test_frequency_rail_width_condition_is_not_viewport_gated(self) -> None:
        self.assertRegex(
            self.app_js,
            r"const frequencyRailWidth = \(\s*dominantYearRailWidth > 0\s*&& dominantYearRailWidth < graphRailWidth\s*\)\s*\?\s*dominantYearRailWidth\s*:\s*graphRailWidth;",
        )
        self.assertNotRegex(
            self.app_js,
            r"const frequencyRailWidth = \(\s*desktopLike\s*&&",
        )

    def test_frequency_trailing_pad_does_not_switch_off_for_narrow_layout(self) -> None:
        self.assertIn(
            'const desiredTrailingPad = readCssVar("--year-grid-pad-right", 0, frequencyCard);',
            self.app_js,
        )
        self.assertNotIn(
            "const desiredTrailingPad = isNarrowLayoutViewport()",
            self.app_js,
        )

    def test_days_off_hourly_unavailable_copy_is_current(self) -> None:
        self.assertIn("Hourly frequency unavailable for Days Off", self.app_js)
        self.assertNotIn("Hourly frequency view unavailable for Days Off", self.app_js)


if __name__ == "__main__":
    unittest.main()
