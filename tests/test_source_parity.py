import json
import os
import re
import shutil
import subprocess
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

import utils  # noqa: E402

APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")
INDEX_HTML_PATH = os.path.join(ROOT_DIR, "site", "index.html")
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
DEV_DASHBOARD_PATH = os.path.join(ROOT_DIR, "scripts", "dev_dashboard.sh")
SYNC_WORKFLOW_PATH = os.path.join(ROOT_DIR, ".github", "workflows", "sync.yml")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class SourceParityStaticTests(unittest.TestCase):
    """Every supported source must be wired into each enumerated surface."""

    def test_supported_sources(self) -> None:
        self.assertEqual(utils.SUPPORTED_SOURCES, {"strava", "garmin", "intervals"})

    def test_index_html_has_icon_and_css_for_every_source(self) -> None:
        html = _read(INDEX_HTML_PATH)
        for source in utils.SUPPORTED_SOURCES:
            self.assertIn(f'class="{source}-logo"', html)
            self.assertIn(f".strava-profile-link.profile-provider-{source} .{source}-logo", html)

    def test_config_has_section_for_every_source(self) -> None:
        config = _read(CONFIG_PATH)
        for source in utils.SUPPORTED_SOURCES:
            self.assertRegex(config, rf"(?m)^{source}:\s*$")
        self.assertIn('"strava", "garmin", or "intervals"', config)
        self.assertIn("api_key:", config)
        self.assertIn('athlete_id: "0"', config)

    def test_dev_dashboard_preflight_checks_every_source(self) -> None:
        script = _read(DEV_DASHBOARD_PATH)
        for source in utils.SUPPORTED_SOURCES:
            self.assertIn(f'source == "{source}"', script)
        self.assertIn('intervals.get("api_key")', script)

    def test_sync_workflow_handles_every_source_explicitly(self) -> None:
        workflow = _read(SYNC_WORKFLOW_PATH)
        for source in utils.SUPPORTED_SOURCES:
            self.assertIn(f"          - {source}\n", workflow)
            self.assertIn(f'"${{source}}" != "{source}"', workflow)
            self.assertIn(f'[[ "${{SYNC_SOURCE}}" == "{source}" ]]', workflow)
            self.assertIn(f"rm -f data/backfill_state_{source}.json", workflow)
        # Garmin config must not be written as a catch-all else-branch.
        self.assertNotRegex(workflow, r"(?m)^\s*else\n\s*cat <<CONFIG >> config.local.yaml\n\s*garmin:")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class SourceParityAppJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app_js = _read(APP_JS_PATH)
        patterns = [
            r"const PROFILE_PROVIDER_STRAVA = [^\n]+\n",
            r"const PROFILE_PROVIDER_GARMIN = [^\n]+\n",
            r"const PROFILE_PROVIDER_INTERVALS = [^\n]+\n",
            r"const PROVIDER_DISPLAY_NAMES = \{[\s\S]*?\n\};\n",
            r"function providerDisplayName\(source\)\s*{[\s\S]*?\n}\n",
            r"function parseStravaProfileUrl\(value\)\s*{[\s\S]*?\n}\n",
            r"function parseStravaActivityUrl\(value\)\s*{[\s\S]*?\n}\n",
            r"function payloadProfileUrl\(payload\)\s*{[\s\S]*?\n}\n",
        ]
        chunks = []
        for pattern in patterns:
            match = re.search(pattern, app_js)
            if not match:
                raise AssertionError(f"Could not find {pattern!r} in site/app.js")
            chunks.append(match.group(0))
        cls.source = "\n".join(chunks)

    def _run(self, expression: str, payload=None):
        script = (
            f"{self.source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            f"process.stdout.write(JSON.stringify({expression}));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps(payload)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_registry_covers_every_supported_source(self) -> None:
        names = self._run("PROVIDER_DISPLAY_NAMES")
        self.assertEqual(names, {"strava": "Strava", "garmin": "Garmin", "intervals": "intervals.icu"})

    def test_provider_display_names(self) -> None:
        result = self._run("payload.map((id) => providerDisplayName(id))", ["strava", "garmin", "intervals", " Intervals "])
        self.assertEqual(result, ["Strava", "Garmin", "intervals.icu", "intervals.icu"])
        self.assertEqual(self._run("providerDisplayName('fitbit')"), "")

    def test_profile_url_resolves_registered_provider(self) -> None:
        result = self._run(
            "payload.map((url) => parseStravaProfileUrl(url).provider)",
            [
                "https://www.strava.com/athletes/1",
                "https://connect.garmin.com/modern/profile/abc",
                "https://intervals.icu/athlete/i1",
            ],
        )
        self.assertEqual(result, ["strava", "garmin", "intervals"])
        self.assertTrue(all(self._run(f"Object.prototype.hasOwnProperty.call(PROVIDER_DISPLAY_NAMES, {json.dumps(p)})") for p in result))

    def test_activity_urls_accepted_for_every_source(self) -> None:
        urls = [
            "https://www.strava.com/activities/1",
            "https://connect.garmin.com/modern/activity/2",
            "https://intervals.icu/activities/i3",
        ]
        result = self._run("payload.map((url) => parseStravaActivityUrl(url)?.href || null)", urls)
        self.assertEqual(result, urls)

    def test_payload_profile_url_reads_intervals_specific_key(self) -> None:
        result = self._run(
            "payloadProfileUrl(payload)",
            {"intervals_profile_url": "https://intervals.icu/athlete/i1"},
        )
        self.assertEqual(result, "https://intervals.icu/athlete/i1")


if __name__ == "__main__":
    unittest.main()
