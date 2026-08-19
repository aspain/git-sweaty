import os
import re
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


def _extract_function_body(source: str, name: str) -> str:
    """Extract a top-level JS function body by tracking brace depth.

    Needed because several HR touchpoints live in functions with nested
    braces (forEach callbacks, if blocks); a non-greedy regex stops at the
    first inner closing brace and misses the HR code we want to assert on.
    """
    pattern = re.compile(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{")
    match = pattern.search(source)
    if not match:
        return ""
    depth = 1
    i = match.end()
    while i < len(source) and depth > 0:
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return source[match.end():i]


class HeartRateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            cls.app_js = handle.read()

    def test_format_tooltip_metric_lines_renders_heart_rate_line(self) -> None:
        body = _extract_function_body(self.app_js, "formatTooltipMetricLines")
        self.assertTrue(body)
        self.assertIn("Heart rate:", body)
        self.assertIn("Math.round(heartRate)", body)

    def test_build_summary_accumulates_time_weighted_heart_rate(self) -> None:
        body = _extract_function_body(self.app_js, "buildSummary")
        self.assertTrue(body)
        self.assertIn("totals.hr_weighted_sum += Number(", body)
        self.assertIn("totals.hr_time += Number(", body)
        self.assertIn("totals.heart_rate = totals.hr_time > 0", body)

    def test_combined_type_details_carries_heart_rate_per_type(self) -> None:
        body = _extract_function_body(self.app_js, "buildCombinedTypeDetailsByDate")
        self.assertTrue(body)
        self.assertIn("heart_rate: Number(dayEntry?.heart_rate || 0)", body)

    def test_combine_year_aggregates_rolls_up_heart_rate(self) -> None:
        body = _extract_function_body(self.app_js, "combineYearAggregates")
        self.assertTrue(body)
        self.assertIn("combined[dateStr].hr_weighted_sum += Number(", body)
        self.assertIn("combined[dateStr].hr_time += Number(", body)
        self.assertIn("heart_rate: entry.hr_time > 0 ? entry.hr_weighted_sum / entry.hr_time", body)


if __name__ == "__main__":
    unittest.main()
