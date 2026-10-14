import os
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


if __name__ == "__main__":
    unittest.main()
