import os
import re
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INDEX_PATH = os.path.join(ROOT_DIR, "site", "index.html")


class SummaryResponsiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(INDEX_PATH, "r", encoding="utf-8") as handle:
            cls.html = handle.read()

    def _extract_media_block(self, start_marker: str, next_marker: str | None = None) -> str:
        start = self.html.find(start_marker)
        self.assertNotEqual(start, -1, f"Could not find media marker: {start_marker}")
        if next_marker is None:
            end = len(self.html)
        else:
            end = self.html.find(next_marker, start + len(start_marker))
            self.assertNotEqual(end, -1, f"Could not find end marker after {start_marker}: {next_marker}")
        return self.html[start:end]

    def _extract_selector_clamp(self, css_text: str, selector_regex: str) -> tuple[float, float, float]:
        match = re.search(
            rf"{selector_regex}\s*{{[\s\S]*?font-size:\s*clamp\((\d+(?:\.\d+)?)px,\s*(\d+(?:\.\d+)?)vw,\s*(\d+(?:\.\d+)?)px\);",
            css_text,
        )
        self.assertIsNotNone(match, f"Could not find clamp for selector pattern: {selector_regex}")
        assert match is not None
        return (float(match.group(1)), float(match.group(2)), float(match.group(3)))

    def _extract_summary_value_clamp(self, css_text: str) -> tuple[float, float, float]:
        combined_match = re.search(
            r"\.summary-value,\s*\.summary-type\s*{[\s\S]*?font-size:\s*clamp\((\d+(?:\.\d+)?)px,\s*(\d+(?:\.\d+)?)vw,\s*(\d+(?:\.\d+)?)px\);",
            css_text,
        )
        if combined_match:
            return (
                float(combined_match.group(1)),
                float(combined_match.group(2)),
                float(combined_match.group(3)),
            )
        return self._extract_selector_clamp(css_text, r"\.summary-value")

    @staticmethod
    def _clamp_size(clamp_tuple: tuple[float, float, float], width_px: int) -> float:
        min_px, vw, max_px = clamp_tuple
        preferred = vw * (width_px / 100.0)
        return max(min_px, min(max_px, preferred))

    def test_summary_titles_are_single_line_truncated(self) -> None:
        summary_title_block = re.search(r"\.summary-title\s*{[\s\S]*?}\n", self.html)
        self.assertIsNotNone(summary_title_block)
        assert summary_title_block is not None
        block = summary_title_block.group(0)
        self.assertIn("white-space: nowrap;", block)
        self.assertIn("overflow: hidden;", block)
        self.assertIn("text-overflow: ellipsis;", block)

    def test_summary_collapses_to_four_columns_at_narrow_layout(self) -> None:
        max_900 = self._extract_media_block("@media (max-width: 900px)", "@media (max-width: 720px)")
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", max_900)
        self.assertNotIn("grid-template-columns: repeat(3, minmax(0, 1fr));", max_900)

    def test_summary_font_sizes_shrink_monotonically_as_viewport_narrows(self) -> None:
        base_css = self.html[: self.html.find("@media (min-width: 721px)")]
        max_900 = self._extract_media_block("@media (max-width: 900px)", "@media (max-width: 720px)")
        max_720 = self._extract_media_block("@media (max-width: 720px)", "@media (max-width: 375px)")

        title_base = self._extract_selector_clamp(base_css, r"\.summary-title")
        title_900 = self._extract_selector_clamp(max_900, r"\.summary-title")
        title_720 = self._extract_selector_clamp(max_720, r"\.summary-title")

        value_base = self._extract_summary_value_clamp(base_css)
        value_900 = self._extract_summary_value_clamp(max_900)
        value_720 = self._extract_summary_value_clamp(max_720)

        def title_size_for_width(width: int) -> float:
            if width <= 720:
                return self._clamp_size(title_720, width)
            if width <= 900:
                return self._clamp_size(title_900, width)
            return self._clamp_size(title_base, width)

        def value_size_for_width(width: int) -> float:
            if width <= 720:
                return self._clamp_size(value_720, width)
            if width <= 900:
                return self._clamp_size(value_900, width)
            return self._clamp_size(value_base, width)

        widths_desc = [1300, 1000, 901, 900, 850, 721, 720, 680, 500, 376, 375, 320]

        for idx in range(1, len(widths_desc)):
            wider = widths_desc[idx - 1]
            narrower = widths_desc[idx]
            self.assertLessEqual(
                title_size_for_width(narrower),
                title_size_for_width(wider) + 1e-9,
                f"summary title size should not increase when narrowing ({wider}px -> {narrower}px)",
            )
            self.assertLessEqual(
                value_size_for_width(narrower),
                value_size_for_width(wider) + 1e-9,
                f"summary value size should not increase when narrowing ({wider}px -> {narrower}px)",
            )


if __name__ == "__main__":
    unittest.main()
