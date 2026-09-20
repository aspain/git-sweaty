import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import sync_garmin  # noqa: E402


class SyncGarminPruningTests(unittest.TestCase):
    def setUp(self) -> None:
        tmpdir = self.enterContext(tempfile.TemporaryDirectory())
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(tmpdir)
        self.config = {"sync": {"per_page": 2, "recent_days": 0}}
        self.client = SimpleNamespace(get_activities=mock.Mock())
        self.enterContext(mock.patch("sync_garmin.load_config", return_value=self.config))
        self.enterContext(mock.patch("sync_garmin._load_garmin_client", return_value=self.client))
        os.makedirs(sync_garmin.RAW_DIR)

    @staticmethod
    def _activity(activity_id: int) -> dict:
        return {
            "activityId": activity_id,
            "startTimeGMT": f"2026-01-{activity_id:02d}T12:00:00Z",
            "activityType": {"typeKey": "running"},
            "duration": 600,
        }

    def _cached_ids(self) -> set:
        return {name[:-5] for name in os.listdir(sync_garmin.RAW_DIR) if name.endswith(".json")}

    def test_resumed_backfill_preserves_activities_from_previous_pages(self) -> None:
        self.client.get_activities.side_effect = [
            [self._activity(3), self._activity(2)],
            RuntimeError("429 Too Many Requests"),
        ]
        first = sync_garmin.sync_garmin(dry_run=False, prune_deleted=True)
        self.assertTrue(first["rate_limited"])
        self.assertEqual(first["backfill_next_offset"], 2)
        self.assertEqual(self._cached_ids(), {"2", "3"})

        self.client.get_activities.reset_mock()
        self.client.get_activities.side_effect = [[self._activity(1)]]
        resumed = sync_garmin.sync_garmin(dry_run=False, prune_deleted=True)

        self.client.get_activities.assert_called_once_with(2, 2)
        self.assertTrue(resumed["backfill_completed"])
        self.assertEqual(self._cached_ids(), {"1", "2", "3"})
        self.assertEqual(resumed["deleted"], 0)

    def test_empty_resumed_page_preserves_cached_activities(self) -> None:
        sync_garmin._write_activity(sync_garmin._normalize_activity(self._activity(2)))
        sync_garmin._save_state({
            "after": 0,
            "activity_scope": sync_garmin._activity_scope(self.config),
            "next_offset": 2,
            "completed": False,
        })
        self.client.get_activities.return_value = []

        summary = sync_garmin.sync_garmin(dry_run=False, prune_deleted=True)

        self.client.get_activities.assert_called_once_with(2, 2)
        self.assertTrue(summary["backfill_completed"])
        self.assertEqual(self._cached_ids(), {"2"})
        self.assertEqual(summary["deleted"], 0)

    def test_full_scan_still_prunes_when_starting_from_zero(self) -> None:
        for saved_offset in (None, 0):
            with self.subTest(saved_offset=saved_offset):
                sync_garmin._write_activity(sync_garmin._normalize_activity(self._activity(2)))
                sync_garmin._save_state({
                    "after": 0,
                    "activity_scope": sync_garmin._activity_scope(self.config),
                    "next_offset": saved_offset,
                    "completed": False,
                })
                self.client.get_activities.reset_mock()
                self.client.get_activities.side_effect = [[self._activity(1)]]

                summary = sync_garmin.sync_garmin(dry_run=False, prune_deleted=True)

                self.client.get_activities.assert_called_once_with(0, 2)
                self.assertTrue(summary["backfill_completed"])
                self.assertEqual(self._cached_ids(), {"1"})
                self.assertEqual(summary["deleted"], 1)

    def test_changed_boundary_restarts_full_scan_and_allows_pruning(self) -> None:
        sync_garmin._write_activity(sync_garmin._normalize_activity(self._activity(2)))
        sync_garmin._save_state({
            "after": 1,
            "activity_scope": sync_garmin._activity_scope(self.config),
            "next_offset": 2,
            "completed": False,
        })
        self.client.get_activities.side_effect = [[self._activity(1)]]

        summary = sync_garmin.sync_garmin(dry_run=False, prune_deleted=True)

        self.client.get_activities.assert_called_once_with(0, 2)
        self.assertEqual(self._cached_ids(), {"1"})
        self.assertEqual(summary["deleted"], 1)


if __name__ == "__main__":
    unittest.main()
