import os
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

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

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import sync_strava  # noqa: E402


SCOPE = {"include_all_types": True, "exclude_types": []}


class SyncStravaBackfillBoundaryTests(unittest.TestCase):
    def _run(self, state, after):
        saved = []
        fetch = mock.Mock(return_value=[])
        recent = {"fetched": 0, "new_or_updated": 0, "activity_ids": [], "rate_limited": False}
        with ExitStack() as stack:
            stack.enter_context(mock.patch("sync_strava.load_config", return_value={}))
            stack.enter_context(mock.patch("sync_strava._start_after_ts", return_value=after))
            stack.enter_context(mock.patch("sync_strava._activity_scope", return_value=SCOPE))
            stack.enter_context(mock.patch("sync_strava._get_access_token", return_value="tok"))
            stack.enter_context(
                mock.patch("sync_strava._maybe_reset_for_new_athlete", return_value="tok")
            )
            stack.enter_context(mock.patch("sync_strava.ensure_dir"))
            stack.enter_context(
                mock.patch("sync_strava._sync_recent", return_value=(recent, "tok"))
            )
            stack.enter_context(mock.patch("sync_strava._load_state", return_value=dict(state)))
            stack.enter_context(mock.patch("sync_strava._save_state", side_effect=saved.append))
            stack.enter_context(mock.patch("sync_strava._fetch_page", fetch))
            stack.enter_context(mock.patch("builtins.print"))
            summary = sync_strava.sync_strava(dry_run=False, prune_deleted=False)
        return summary, saved, fetch

    def test_later_lookback_bound_keeps_completed_backfill(self) -> None:
        state = {"after": 1000, "completed": True, "next_before": None, "activity_scope": SCOPE}
        summary, saved, fetch = self._run(state, after=2000)
        fetch.assert_not_called()
        self.assertTrue(summary["backfill_completed"])
        self.assertEqual(saved[-1]["after"], 1000)
        self.assertTrue(saved[-1]["completed"])

    def test_later_lookback_bound_resumes_in_progress_cursor(self) -> None:
        state = {"after": 1000, "completed": False, "next_before": 5000, "activity_scope": SCOPE}
        _summary, _saved, fetch = self._run(state, after=2000)
        fetch.assert_called_once()
        args = fetch.call_args.args
        self.assertEqual(args[3], 2000)  # after
        self.assertEqual(args[4], 5000)  # before (resume cursor)

    def test_earlier_bound_restarts_backfill(self) -> None:
        state = {"after": 1000, "completed": True, "next_before": None, "activity_scope": SCOPE}
        summary, saved, fetch = self._run(state, after=500)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[3], 500)
        self.assertEqual(saved[-1]["after"], 500)
        self.assertTrue(summary["backfill_completed"])

    def test_missing_saved_bound_restarts_backfill(self) -> None:
        state = {"completed": True, "activity_scope": SCOPE}
        _summary, saved, fetch = self._run(state, after=2000)
        fetch.assert_called_once()
        self.assertEqual(saved[-1]["after"], 2000)


class SyncStravaResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    @staticmethod
    def _touch(path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}")

    def test_has_existing_data_counts_backfill_state_files(self) -> None:
        self.assertFalse(sync_strava._has_existing_data())
        self._touch(sync_strava.LEGACY_STATE_PATH)
        self.assertTrue(sync_strava._has_existing_data())

    def test_has_existing_data_ignores_athlete_files(self) -> None:
        self._touch(sync_strava.ATHLETE_PATH)
        self.assertFalse(sync_strava._has_existing_data())

    def test_reset_removes_outputs_state_athlete_and_legacy_raw_files(self) -> None:
        paths = [
            os.path.join("data", "activities_normalized.json"),
            os.path.join("site", "data.json"),
            sync_strava.STATE_PATH,
            sync_strava.LEGACY_STATE_PATH,
            sync_strava.ATHLETE_PATH,
            sync_strava.LEGACY_ATHLETE_PATH,
            os.path.join(sync_strava.RAW_DIR, "1.json"),
            os.path.join("activities", "raw", "legacy.json"),
        ]
        keep = [
            os.path.join("activities", "raw", "notes.txt"),
            os.path.join("activities", "raw", "garmin", "2.json"),
        ]
        for path in paths + keep:
            self._touch(path)

        sync_strava._reset_persisted_data()

        for path in paths:
            self.assertFalse(os.path.exists(path), path)
        self.assertFalse(os.path.exists(sync_strava.RAW_DIR))
        for path in keep:
            self.assertTrue(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
