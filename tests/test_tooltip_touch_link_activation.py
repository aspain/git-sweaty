import json
import os
import re
import shutil
import subprocess
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class TooltipTouchLinkActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            app_js = handle.read()

        function_patterns = {
            "parse_strava_activity_url": r"function parseStravaActivityUrl\(value\)\s*{[\s\S]*?\n}\n",
            "normalize_tooltip_href": r"function normalizeTooltipHref\(value\)\s*{[\s\S]*?\n}\n",
            "resolve_tooltip_target_element": r"function resolveTooltipTargetElement\(target\)\s*{[\s\S]*?\n}\n",
            "tooltip_link_from_event_target": r"function tooltipLinkElementFromEventTarget\(target\)\s*{[\s\S]*?\n}\n",
            "remember_tooltip_pointer_type": r"function rememberTooltipPointerType\(event\)\s*{[\s\S]*?\n}\n",
            "is_touch_tooltip_activation_event": r"function isTouchTooltipActivationEvent\(event\)\s*{[\s\S]*?\n}\n",
            "now_ms": r"function nowMs\(\)\s*{[\s\S]*?\n}\n",
            "mark_touch_tooltip_link_click_suppress": r"function markTouchTooltipLinkClickSuppress\(durationMs = 1200\)\s*{[\s\S]*?\n}\n",
            "should_suppress_touch_tooltip_link_click": r"function shouldSuppressTouchTooltipLinkClick\(\)\s*{[\s\S]*?\n}\n",
            "open_tooltip_link_in_new_tab": r"function openTooltipLinkInNewTab\(linkElement\)\s*{[\s\S]*?\n}\n",
            "open_tooltip_link_in_current_tab": r"function openTooltipLinkInCurrentTab\(linkElement\)\s*{[\s\S]*?\n}\n",
            "handle_tooltip_link_activation": r"function handleTooltipLinkActivation\(event\)\s*{[\s\S]*?\n}\n",
        }
        extracted: dict[str, str] = {}
        for key, pattern in function_patterns.items():
            match = re.search(pattern, app_js)
            if not match:
                raise AssertionError(f"Could not find helper for {key} in site/app.js")
            extracted[key] = match.group(0)
        cls.sources = extracted

    def _run_js(self, payload: dict) -> object:
        script = (
            "const payload = JSON.parse(process.argv[1]);\n"
            "const Node = { TEXT_NODE: 3 };\n"
            "const markCalls = [];\n"
            "const openCalls = [];\n"
            "let assignedHref = null;\n"
            "let dismissCalls = 0;\n"
            "let lastTooltipPointerType = '';\n"
            "let touchTooltipLinkClickSuppressUntil = 0;\n"
            "const window = {\n"
            "  open: (href, target, features) => {\n"
            "    openCalls.push({ href, target, features });\n"
            "    return payload.window_open_returns_window ? { opener: {} } : null;\n"
            "  },\n"
            "  location: {\n"
            "    assign: (href) => { assignedHref = href; },\n"
            "    href: '',\n"
            "  },\n"
            "  setTimeout: (fn) => { fn(); return 1; },\n"
            "};\n"
            "const isTouch = Boolean(payload.is_touch);\n"
            "const hasTouchInput = payload.has_touch_input == null\n"
            "  ? Boolean(payload.is_touch)\n"
            "  : Boolean(payload.has_touch_input);\n"
            "const useTouchInteractions = isTouch || hasTouchInput;\n"
            "function markTouchTooltipInteractionBlock(durationMs) { markCalls.push(durationMs); }\n"
            "function dismissTooltipState() { dismissCalls += 1; }\n"
            f"{self.sources['parse_strava_activity_url']}\n"
            f"{self.sources['normalize_tooltip_href']}\n"
            f"{self.sources['resolve_tooltip_target_element']}\n"
            f"{self.sources['tooltip_link_from_event_target']}\n"
            f"{self.sources['remember_tooltip_pointer_type']}\n"
            f"{self.sources['is_touch_tooltip_activation_event']}\n"
            f"{self.sources['now_ms']}\n"
            f"{self.sources['mark_touch_tooltip_link_click_suppress']}\n"
            f"{self.sources['should_suppress_touch_tooltip_link_click']}\n"
            f"{self.sources['open_tooltip_link_in_new_tab']}\n"
            f"{self.sources['open_tooltip_link_in_current_tab']}\n"
            f"{self.sources['handle_tooltip_link_activation']}\n"
            "const linkElement = {\n"
            "  href: payload.href,\n"
            "  getAttribute: (name) => (name === 'href' ? payload.href : ''),\n"
            "  closest: (selector) => (selector === '.tooltip-link' ? linkElement : null),\n"
            "};\n"
            "const nonLinkTarget = { closest: () => null };\n"
            "const target = payload.use_link_target ? linkElement : nonLinkTarget;\n"
            "const event = {\n"
            "  target,\n"
            "  defaultPrevented: false,\n"
            "  propagationStopped: false,\n"
            "  preventDefault() { this.defaultPrevented = true; },\n"
            "  stopPropagation() { this.propagationStopped = true; },\n"
            "};\n"
            "const activated = handleTooltipLinkActivation(event);\n"
            "process.stdout.write(JSON.stringify({\n"
            "  activated,\n"
            "  defaultPrevented: event.defaultPrevented,\n"
            "  propagationStopped: event.propagationStopped,\n"
            "  markCalls,\n"
            "  openCalls,\n"
            "  assignedHref,\n"
            "  dismissCalls,\n"
            "}));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_touch_link_activation_prevents_default_without_same_tab_fallback(self) -> None:
        href = "https://www.strava.com/activities/12345"
        result = self._run_js(
            {
                "is_touch": True,
                "use_link_target": True,
                "window_open_returns_window": False,
                "href": href,
            }
        )
        self.assertTrue(result["activated"])
        self.assertTrue(result["defaultPrevented"])
        self.assertTrue(result["propagationStopped"])
        self.assertEqual(result["markCalls"], [1600])
        self.assertEqual(result["assignedHref"], href)
        self.assertEqual(result["dismissCalls"], 0)
        self.assertEqual(result["openCalls"], [])

    def test_touch_link_activation_uses_window_open_when_available(self) -> None:
        href = "https://www.strava.com/activities/67890"
        result = self._run_js(
            {
                "is_touch": True,
                "use_link_target": True,
                "window_open_returns_window": True,
                "href": href,
            }
        )
        self.assertTrue(result["activated"])
        self.assertTrue(result["defaultPrevented"])
        self.assertTrue(result["propagationStopped"])
        self.assertEqual(result["markCalls"], [1600])
        self.assertEqual(result["assignedHref"], href)
        self.assertEqual(result["dismissCalls"], 0)
        self.assertEqual(result["openCalls"], [])

    def test_desktop_link_activation_opens_new_tab_only(self) -> None:
        href = "https://www.strava.com/activities/24680"
        result = self._run_js(
            {
                "is_touch": False,
                "use_link_target": True,
                "window_open_returns_window": True,
                "href": href,
            }
        )
        self.assertTrue(result["activated"])
        self.assertTrue(result["defaultPrevented"])
        self.assertTrue(result["propagationStopped"])
        self.assertEqual(result["markCalls"], [])
        self.assertEqual(result["dismissCalls"], 1)
        self.assertEqual(result["assignedHref"], None)
        self.assertEqual(result["openCalls"], [
            {
                "href": href,
                "target": "_blank",
                "features": "noopener,noreferrer",
            }
        ])

    def test_returns_false_when_event_target_is_not_tooltip_link(self) -> None:
        result = self._run_js(
            {
                "is_touch": True,
                "use_link_target": False,
                "window_open_returns_window": False,
                "href": "https://www.strava.com/activities/12345",
            }
        )
        self.assertFalse(result["activated"])
        self.assertFalse(result["defaultPrevented"])
        self.assertFalse(result["propagationStopped"])
        self.assertEqual(result["markCalls"], [])
        self.assertEqual(result["openCalls"], [])
        self.assertIsNone(result["assignedHref"])
        self.assertEqual(result["dismissCalls"], 0)

    def test_touch_garmin_link_activation_navigates_same_tab(self) -> None:
        href = "https://connect.garmin.com/modern/activity/12345"
        result = self._run_js(
            {
                "is_touch": True,
                "use_link_target": True,
                "window_open_returns_window": False,
                "href": href,
            }
        )
        self.assertTrue(result["activated"])
        self.assertTrue(result["defaultPrevented"])
        self.assertTrue(result["propagationStopped"])
        self.assertEqual(result["assignedHref"], href)
        self.assertEqual(result["openCalls"], [])


    def test_touch_intervals_link_activation_navigates_same_tab(self) -> None:
        href = "https://intervals.icu/activities/i12345"
        result = self._run_js(
            {
                "is_touch": True,
                "use_link_target": True,
                "window_open_returns_window": False,
                "href": href,
            }
        )
        self.assertTrue(result["activated"])
        self.assertTrue(result["defaultPrevented"])
        self.assertTrue(result["propagationStopped"])
        self.assertEqual(result["assignedHref"], href)
        self.assertEqual(result["openCalls"], [])


if __name__ == "__main__":
    unittest.main()
