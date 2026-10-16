import io
import os
import sys
import tempfile
import types
import unittest
from typing import Optional
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

requests_stub = types.ModuleType("requests")


class _RequestException(Exception):
    pass


class _HTTPError(_RequestException):
    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.response = response


def _default_request(*_args, **_kwargs):
    raise NotImplementedError("requests.request stub was not patched")


requests_stub.RequestException = _RequestException
requests_stub.HTTPError = _HTTPError
requests_stub.request = _default_request
sys.modules.setdefault("requests", requests_stub)

import run_pipeline  # noqa: E402


class RunPipelineSourceSwitchTests(unittest.TestCase):
    def _run_pipeline_with_mocks(self, source: str, previous_source: Optional[str]) -> mock.Mock:
        with (
            mock.patch("run_pipeline.load_config", return_value={"source": source}),
            mock.patch("run_pipeline._load_last_source", return_value=previous_source),
            mock.patch("run_pipeline._reset_for_source_switch") as reset_mock,
            mock.patch("run_pipeline._sync_for_source", return_value={"ok": True}),
            mock.patch("run_pipeline.normalize_func", return_value=[]),
            mock.patch("run_pipeline._write_normalized"),
            mock.patch("run_pipeline.aggregate_func", return_value={}),
            mock.patch("run_pipeline._write_aggregates"),
            mock.patch("run_pipeline.generate_heatmaps"),
            mock.patch("run_pipeline._persist_source"),
            mock.patch("run_pipeline._update_readme_live_site_link"),
        ):
            run_pipeline.run_pipeline(
                skip_sync=False,
                dry_run=False,
                prune_deleted=False,
                update_readme_link=False,
            )
            return reset_mock

    def test_run_pipeline_resets_when_source_changes(self) -> None:
        reset_mock = self._run_pipeline_with_mocks(source="garmin", previous_source="strava")
        reset_mock.assert_called_once()

    def test_run_pipeline_does_not_reset_when_source_is_unchanged(self) -> None:
        reset_mock = self._run_pipeline_with_mocks(source="strava", previous_source="strava")
        reset_mock.assert_not_called()

    def test_run_pipeline_resets_when_missing_source_marker_conflicts_with_persisted_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir, exist_ok=True)
            with open(os.path.join(data_dir, "activities_normalized.json"), "w", encoding="utf-8") as f:
                f.write("[]\n")
            with open(os.path.join(data_dir, "backfill_state_garmin.json"), "w", encoding="utf-8") as f:
                f.write("{}\n")

            previous_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                reset_mock = self._run_pipeline_with_mocks(source="strava", previous_source=None)
            finally:
                os.chdir(previous_cwd)

        reset_mock.assert_called_once()

    def test_run_pipeline_resets_when_switching_to_intervals(self) -> None:
        reset_mock = self._run_pipeline_with_mocks(source="intervals", previous_source="garmin")
        reset_mock.assert_called_once()

    def _detect_hint_with(self, *, state_sources=(), raw_sources=()) -> Optional[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "data"), exist_ok=True)
            for source in state_sources:
                with open(os.path.join(tmpdir, "data", f"backfill_state_{source}.json"), "w", encoding="utf-8") as f:
                    f.write("{}\n")
            for source in raw_sources:
                os.makedirs(os.path.join(tmpdir, "activities", "raw", source), exist_ok=True)
            previous_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                return run_pipeline._detect_persisted_source_hint()
            finally:
                os.chdir(previous_cwd)

    def test_detect_persisted_source_hint_handles_all_sources(self) -> None:
        self.assertIsNone(self._detect_hint_with())
        self.assertEqual(self._detect_hint_with(state_sources=["strava"]), "strava")
        self.assertEqual(self._detect_hint_with(raw_sources=["garmin"]), "garmin")
        self.assertEqual(self._detect_hint_with(state_sources=["intervals"]), "intervals")
        self.assertEqual(self._detect_hint_with(raw_sources=["intervals"]), "intervals")
        self.assertEqual(
            self._detect_hint_with(state_sources=["intervals"], raw_sources=["intervals"]),
            "intervals",
        )
        self.assertEqual(
            self._detect_hint_with(state_sources=["garmin"], raw_sources=["intervals"]),
            run_pipeline.SOURCE_HINT_MIXED_INTERVALS,
        )
        self.assertEqual(
            self._detect_hint_with(state_sources=["strava", "intervals"]),
            run_pipeline.SOURCE_HINT_MIXED_INTERVALS,
        )

    def test_run_pipeline_reports_intervals_mixed_state_without_blaming_garmin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir, exist_ok=True)
            for name in ("activities_normalized.json", "backfill_state_strava.json", "backfill_state_intervals.json"):
                with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
                    f.write("{}\n")

            previous_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    reset_mock = self._run_pipeline_with_mocks(source="intervals", previous_source=None)
            finally:
                os.chdir(previous_cwd)

        reset_mock.assert_called_once()
        self.assertIn("intervals.icu persisted state was detected", stdout.getvalue())
        self.assertNotIn("both Strava and Garmin", stdout.getvalue())

    def test_sync_for_source_dispatches_intervals(self) -> None:
        with mock.patch("run_pipeline.sync_intervals", return_value={"source": "intervals"}) as sync_mock:
            result = run_pipeline._sync_for_source("intervals", dry_run=True, prune_deleted=False)
        sync_mock.assert_called_once_with(dry_run=True, prune_deleted=False)
        self.assertEqual(result, {"source": "intervals"})

    def test_resettable_lists_include_intervals_paths(self) -> None:
        self.assertIn(os.path.join("data", "backfill_state_intervals.json"), run_pipeline.RESETTABLE_STATE_FILES)
        self.assertIn(os.path.join("data", "athletes_intervals.json"), run_pipeline.RESETTABLE_STATE_FILES)
        self.assertIn(os.path.join("activities", "raw", "intervals"), run_pipeline.RESETTABLE_RAW_DIRS)

    def test_run_pipeline_does_not_reset_for_missing_marker_with_no_hint_and_default_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir, exist_ok=True)
            with open(os.path.join(data_dir, "activities_normalized.json"), "w", encoding="utf-8") as f:
                f.write("[]\n")

            previous_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                reset_mock = self._run_pipeline_with_mocks(source="strava", previous_source=None)
            finally:
                os.chdir(previous_cwd)

        reset_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
