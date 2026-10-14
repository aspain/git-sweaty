import os
import sys
import types
import unittest
from contextlib import ExitStack
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import sync_garmin  # noqa: E402


SCOPE = {"include_all_types": True, "exclude_types": []}


class SyncGarminBackfillBoundaryTests(unittest.TestCase):
    def _run(self, state, after):
        saved = []
        fetch = mock.Mock(return_value=[])
        recent = {"fetched": 0, "new_or_updated": 0, "activity_ids": [], "rate_limited": False}
        with ExitStack() as stack:
            stack.enter_context(mock.patch("sync_garmin.load_config", return_value={}))
            stack.enter_context(mock.patch("sync_garmin._start_after_ts", return_value=after))
            stack.enter_context(mock.patch("sync_garmin._activity_scope", return_value=SCOPE))
            stack.enter_context(mock.patch("sync_garmin._maybe_reset_for_new_account"))
            stack.enter_context(mock.patch("sync_garmin._load_garmin_client", return_value=object()))
            stack.enter_context(mock.patch("sync_garmin.ensure_dir"))
            stack.enter_context(mock.patch("sync_garmin._sync_recent", return_value=recent))
            stack.enter_context(mock.patch("sync_garmin._load_state", return_value=dict(state)))
            stack.enter_context(mock.patch("sync_garmin._save_state", side_effect=saved.append))
            stack.enter_context(mock.patch("sync_garmin._fetch_page", fetch))
            stack.enter_context(mock.patch("builtins.print"))
            summary = sync_garmin.sync_garmin(dry_run=False, prune_deleted=False)
        return summary, saved, fetch

    def test_later_lookback_bound_keeps_completed_backfill(self) -> None:
        state = {"after": 1000, "completed": True, "next_offset": None, "activity_scope": SCOPE}
        summary, saved, fetch = self._run(state, after=2000)
        fetch.assert_not_called()
        self.assertTrue(summary["backfill_completed"])
        self.assertEqual(saved[-1]["after"], 1000)
        self.assertTrue(saved[-1]["completed"])

    def test_later_lookback_bound_resumes_in_progress_offset(self) -> None:
        state = {"after": 1000, "completed": False, "next_offset": 400, "activity_scope": SCOPE}
        _summary, _saved, fetch = self._run(state, after=2000)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1], 400)

    def test_earlier_bound_restarts_backfill(self) -> None:
        state = {"after": 1000, "completed": True, "next_offset": None, "activity_scope": SCOPE}
        summary, saved, fetch = self._run(state, after=500)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1], 0)
        self.assertEqual(saved[-1]["after"], 500)
        self.assertTrue(summary["backfill_completed"])

    def test_invalid_saved_bound_restarts_backfill(self) -> None:
        state = {"after": "bogus", "completed": True, "activity_scope": SCOPE}
        _summary, saved, fetch = self._run(state, after=2000)
        fetch.assert_called_once()
        self.assertEqual(saved[-1]["after"], 2000)


if __name__ == "__main__":
    unittest.main()
