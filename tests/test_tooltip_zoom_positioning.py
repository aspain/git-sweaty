import json
import os
import re
import shutil
import subprocess
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class TooltipZoomPositioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            app_js = handle.read()

        function_patterns = {
            "clamp": r"function clamp\(value, min, max\)\s*{[\s\S]*?\n}\n",
            "get_viewport_metrics": r"function getViewportMetrics\(\)\s*{[\s\S]*?\n}\n",
            "tooltip_viewport_anchor_offset": r"function tooltipViewportAnchorOffset\(viewport\)\s*{[\s\S]*?\n}\n",
            "pick_tooltip_coordinate": r"function pickTooltipCoordinate\(preferred, alternate, min, max\)\s*{[\s\S]*?\n}\n",
            "get_touch_tooltip_scale": r"function getTouchTooltipScale\(\)\s*{[\s\S]*?\n}\n",
            "position_tooltip": r"function positionTooltip\(x, y\)\s*{[\s\S]*?\n}\n",
            "update_touch_tooltip_wrap_mode": r"function updateTouchTooltipWrapMode\(\)\s*{[\s\S]*?\n}\n",
        }
        extracted: dict[str, str] = {}
        for key, pattern in function_patterns.items():
            match = re.search(pattern, app_js)
            if not match:
                raise AssertionError(f"Could not find helper for {key} in site/app.js")
            extracted[key] = match.group(0)
        cls.sources = extracted
        cls.app_js = app_js

    def _run_position_script(self, payload: dict) -> object:
        script = (
            "const payload = JSON.parse(process.argv[1]);\n"
            "const window = {\n"
            "  innerWidth: payload.inner_width,\n"
            "  innerHeight: payload.inner_height,\n"
            "  visualViewport: payload.visual_viewport,\n"
            "};\n"
            "const useTouchInteractions = Boolean(payload.use_touch_interactions);\n"
            "const tooltip = {\n"
            "  style: {},\n"
            "  getBoundingClientRect: () => ({ width: payload.tooltip_rect.width, height: payload.tooltip_rect.height }),\n"
            "};\n"
            f"{self.sources['clamp']}\n"
            f"{self.sources['get_viewport_metrics']}\n"
            f"{self.sources['tooltip_viewport_anchor_offset']}\n"
            f"{self.sources['pick_tooltip_coordinate']}\n"
            f"{self.sources['position_tooltip']}\n"
            "positionTooltip(payload.point.x, payload.point.y);\n"
            "process.stdout.write(JSON.stringify(tooltip.style));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _run_touch_scale_script(self, payload: dict) -> object:
        script = (
            "const payload = JSON.parse(process.argv[1]);\n"
            "const TOUCH_TOOLTIP_MAX_EFFECTIVE_ZOOM = 1.2;\n"
            "const TOUCH_TOOLTIP_MIN_SCALE = 0.5;\n"
            "const window = {\n"
            "  visualViewport: payload.visual_viewport,\n"
            "};\n"
            "const useTouchInteractions = Boolean(payload.use_touch_interactions);\n"
            f"{self.sources['clamp']}\n"
            f"{self.sources['get_touch_tooltip_scale']}\n"
            "process.stdout.write(JSON.stringify({ scale: getTouchTooltipScale() }));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _run_wrap_mode_script(self, payload: dict) -> object:
        script = (
            "const payload = JSON.parse(process.argv[1]);\n"
            "const TOUCH_TOOLTIP_MAX_EFFECTIVE_ZOOM = 1.2;\n"
            "const TOUCH_TOOLTIP_MIN_SCALE = 0.5;\n"
            "const window = {\n"
            "  innerWidth: payload.inner_width,\n"
            "  innerHeight: payload.inner_height,\n"
            "  visualViewport: payload.visual_viewport,\n"
            "};\n"
            "const useTouchInteractions = true;\n"
            "const tooltip = {\n"
            "  scrollWidth: payload.tooltip_scroll_width,\n"
            "  style: {\n"
            "    removeProperty(name) { delete this[name]; },\n"
            "  },\n"
            "  classList: {\n"
            "    classes: new Set(),\n"
            "    add(name) { this.classes.add(name); },\n"
            "    remove(name) { this.classes.delete(name); },\n"
            "    contains(name) { return this.classes.has(name); },\n"
            "  },\n"
            "};\n"
            f"{self.sources['clamp']}\n"
            f"{self.sources['get_viewport_metrics']}\n"
            f"{self.sources['tooltip_viewport_anchor_offset']}\n"
            f"{self.sources['get_touch_tooltip_scale']}\n"
            f"{self.sources['update_touch_tooltip_wrap_mode']}\n"
            "updateTouchTooltipWrapMode();\n"
            "process.stdout.write(JSON.stringify({\n"
            "  style: tooltip.style,\n"
            "  nowrap: tooltip.classList.contains('nowrap'),\n"
            "}));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_desktop_positioning_ignores_visual_viewport_offsets(self) -> None:
        style = self._run_position_script(
            {
                "use_touch_interactions": False,
                "inner_width": 1200,
                "inner_height": 800,
                "visual_viewport": {
                    "offsetLeft": 240,
                    "offsetTop": 180,
                    "width": 700,
                    "height": 500,
                },
                "tooltip_rect": {"width": 200, "height": 80},
                "point": {"x": 100, "y": 90},
            }
        )
        self.assertEqual(style["left"], "112px")
        self.assertEqual(style["top"], "102px")
        self.assertEqual(style["bottom"], "auto")

    def test_desktop_positioning_flips_above_when_near_bottom_edge(self) -> None:
        style = self._run_position_script(
            {
                "use_touch_interactions": False,
                "inner_width": 1200,
                "inner_height": 180,
                "visual_viewport": {
                    "offsetLeft": 0,
                    "offsetTop": 0,
                    "width": 1200,
                    "height": 180,
                },
                "tooltip_rect": {"width": 200, "height": 80},
                "point": {"x": 300, "y": 150},
            }
        )
        self.assertEqual(style["left"], "312px")
        self.assertEqual(style["top"], "58px")

    def test_desktop_positioning_flips_left_when_near_right_edge(self) -> None:
        style = self._run_position_script(
            {
                "use_touch_interactions": False,
                "inner_width": 200,
                "inner_height": 300,
                "visual_viewport": {
                    "offsetLeft": 0,
                    "offsetTop": 0,
                    "width": 200,
                    "height": 300,
                },
                "tooltip_rect": {"width": 90, "height": 60},
                "point": {"x": 170, "y": 100},
            }
        )
        self.assertEqual(style["left"], "68px")

    def test_desktop_positioning_ignores_visual_viewport_dimensions(self) -> None:
        style = self._run_position_script(
            {
                "use_touch_interactions": False,
                "inner_width": 1200,
                "inner_height": 800,
                "visual_viewport": {
                    "offsetLeft": 0,
                    "offsetTop": 0,
                    "width": 700,
                    "height": 500,
                },
                "tooltip_rect": {"width": 200, "height": 80},
                "point": {"x": 900, "y": 100},
            }
        )
        self.assertEqual(style["left"], "912px")
        self.assertEqual(style["top"], "112px")

    def test_touch_positioning_uses_visual_viewport_offsets(self) -> None:
        style = self._run_position_script(
            {
                "use_touch_interactions": True,
                "inner_width": 1200,
                "inner_height": 800,
                "visual_viewport": {
                    "offsetLeft": 240,
                    "offsetTop": 180,
                    "width": 700,
                    "height": 500,
                },
                "tooltip_rect": {"width": 200, "height": 80},
                "point": {"x": 100, "y": 220},
            }
        )
        self.assertEqual(style["left"], "352px")
        self.assertEqual(style["top"], "308px")
        self.assertEqual(style["bottom"], "auto")

    def test_touch_wrap_mode_caps_tooltip_size_to_visual_viewport(self) -> None:
        result = self._run_wrap_mode_script(
            {
                "inner_width": 1200,
                "inner_height": 800,
                "visual_viewport": {
                    "offsetLeft": 20,
                    "offsetTop": 10,
                    "width": 200,
                    "height": 260,
                },
                "tooltip_scroll_width": 250,
            }
        )
        style = result["style"]
        self.assertEqual(style["maxWidth"], "176px")
        self.assertEqual(style["maxHeight"], "182px")
        self.assertEqual(style["overflowY"], "auto")
        self.assertEqual(style["overflowX"], "hidden")
        self.assertEqual(style["left"], "32px")
        self.assertEqual(style["top"], "22px")
        self.assertFalse(result["nowrap"])

    def test_touch_wrap_mode_uses_scaled_width_budget_when_zoomed(self) -> None:
        result = self._run_wrap_mode_script(
            {
                "inner_width": 1200,
                "inner_height": 800,
                "visual_viewport": {
                    "offsetLeft": 20,
                    "offsetTop": 10,
                    "width": 200,
                    "height": 260,
                    "scale": 2,
                },
                "tooltip_scroll_width": 250,
            }
        )
        style = result["style"]
        self.assertEqual(style["maxWidth"], "293px")
        self.assertTrue(result["nowrap"])

    def test_touch_tooltip_scale_caps_zoom_growth(self) -> None:
        result = self._run_touch_scale_script(
            {
                "use_touch_interactions": True,
                "visual_viewport": {"scale": 3},
            }
        )
        self.assertEqual(result["scale"], 0.5)

    def test_touch_tooltip_scale_is_neutral_without_zoom(self) -> None:
        result = self._run_touch_scale_script(
            {
                "use_touch_interactions": True,
                "visual_viewport": {"scale": 1},
            }
        )
        self.assertEqual(result["scale"], 1)

    def test_show_tooltip_no_longer_scales_by_visual_viewport(self) -> None:
        self.assertNotIn("scale(${tooltipScale})", self.app_js)
        self.assertNotIn("function getTooltipScale()", self.app_js)


if __name__ == "__main__":
    unittest.main()
