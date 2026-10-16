import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNC_WORKFLOW_PATH = os.path.join(ROOT_DIR, ".github", "workflows", "sync.yml")


class WorkflowSecretRotationTests(unittest.TestCase):
    def test_piped_secret_values_are_read_from_stdin(self) -> None:
        with open(SYNC_WORKFLOW_PATH, "r", encoding="utf-8") as handle:
            workflow = handle.read()

        self.assertNotIn("--body -", workflow)
        self.assertIn("| GH_TOKEN=", workflow)
        self.assertIn("gh secret set STRAVA_REFRESH_TOKEN", workflow)
        self.assertIn("gh secret set GARMIN_TOKENS_B64", workflow)
        self.assertNotIn("gh secret set INTERVALS_API_KEY", workflow)

    def test_workflow_supports_intervals_source(self) -> None:
        with open(SYNC_WORKFLOW_PATH, "r", encoding="utf-8") as handle:
            workflow = handle.read()

        self.assertIn("          - intervals\n", workflow)
        self.assertIn('"${source}" != "intervals"', workflow)
        self.assertIn('missing+=("INTERVALS_API_KEY")', workflow)
        self.assertIn("INTERVALS_API_KEY: ${{ secrets.INTERVALS_API_KEY }}", workflow)
        self.assertIn(
            "INTERVALS_ATHLETE_ID: ${{ vars.INTERVALS_ATHLETE_ID || secrets.INTERVALS_ATHLETE_ID }}", workflow
        )
        self.assertIn("DASHBOARD_INTERVALS_PROFILE_URL: ${{ vars.DASHBOARD_INTERVALS_PROFILE_URL }}", workflow)
        self.assertIn("DASHBOARD_INTERVALS_ACTIVITY_LINKS: ${{ vars.DASHBOARD_INTERVALS_ACTIVITY_LINKS }}", workflow)
        self.assertIn("rm -f data/backfill_state_intervals.json", workflow)


    @unittest.skipUnless(shutil.which("bash"), "bash is required to run the workflow step")
    def test_intervals_config_step_escapes_secret_values(self) -> None:
        with open(SYNC_WORKFLOW_PATH, "r", encoding="utf-8") as handle:
            workflow = handle.read()
        start = workflow.index("      - name: Write config.local.yaml")
        run_start = workflow.index("        run: |\n", start) + len("        run: |\n")
        run_end = workflow.index("\n      - name:", run_start)
        script = textwrap.dedent(workflow[run_start:run_end])

        tricky_key = 'k"ey\\with: #yaml'
        env = dict(
            os.environ,
            SYNC_SOURCE="intervals",
            INTERVALS_API_KEY=tricky_key,
            INTERVALS_ATHLETE_ID=" i42 ",
            DASHBOARD_INTERVALS_PROFILE_URL='https://intervals.icu/"x"',
            DASHBOARD_INTERVALS_ACTIVITY_LINKS="Yes",
            DASHBOARD_DISTANCE_UNIT="km",
        )
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["bash", "-c", script], cwd=tmp, env=env, check=True, capture_output=True)
            loaded = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import json, yaml; print(json.dumps(yaml.safe_load(open('config.local.yaml'))))",
                ],
                cwd=tmp,
                check=True,
                capture_output=True,
                text=True,
            )
        config = json.loads(loaded.stdout)
        self.assertEqual(config["source"], "intervals")
        self.assertEqual(
            config["intervals"],
            {
                "api_key": tricky_key,
                "athlete_id": "i42",
                "profile_url": 'https://intervals.icu/"x"',
                "include_activity_urls": True,
            },
        )
        self.assertEqual(config["units"], {"distance": "km"})


if __name__ == "__main__":
    unittest.main()
