import os
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
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

import normalize  # noqa: E402
import sync_intervals  # noqa: E402
from utils import read_json  # noqa: E402


PROFILE = {"id": "i123", "name": "Pat Rider"}


class _MockResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.headers = headers or {}

    def json(self):
        return self._payload


def _ride(activity_id: str, day: date) -> dict:
    return {
        "id": activity_id,
        "start_date_local": f"{day.isoformat()}T07:12:00",
        "start_date": f"{day.isoformat()}T05:12:00Z",
        "type": "Ride",
        "name": "Morning Ride",
        "distance": 42000.5,
        "moving_time": 5400,
        "elapsed_time": 6000,
        "total_elevation_gain": 350.0,
        "source": "GARMIN_CONNECT",
        "icu_training_load": 77,
        "average_heartrate": 141,
        "calories": 980,
        "icu_zone_times": [1, 2, 3],
    }


def _strava_stub(activity_id: str, day: date) -> dict:
    return {
        "id": activity_id,
        "start_date_local": f"{day.isoformat()}T09:00:00",
        "source": "STRAVA",
        "_note": "STRAVA activities are not available via the API",
    }


def _config(**sync_overrides) -> dict:
    start = (date.today() - timedelta(days=400)).isoformat()
    sync_cfg = {"start_date": start, "recent_days": 7}
    sync_cfg.update(sync_overrides)
    return {
        "source": "intervals",
        "intervals": {"api_key": "secret-key", "athlete_id": "i123"},
        "sync": sync_cfg,
    }


class SyncIntervalsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmpdir.name)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        self._tmpdir.cleanup()

    def _run(
        self,
        config: dict,
        handler,
        dry_run: bool = False,
        prune_deleted: bool = False,
        profile: dict = PROFILE,
    ):
        """Run a sync; `handler` serves activity-list requests, the profile is served here."""
        activity_calls = []

        def route(method, url, **kwargs):
            if url.endswith("/activities"):
                activity_calls.append(kwargs["params"])
                return handler(method, url, **kwargs)
            return _MockResponse(200, profile)

        with mock.patch.object(sync_intervals, "load_config", return_value=config), mock.patch.object(
            sync_intervals.requests, "request", side_effect=route, create=True
        ) as request_mock, mock.patch.object(sync_intervals.time, "sleep"):
            summary = sync_intervals.sync_intervals(dry_run, prune_deleted)
        self.activity_calls = activity_calls
        return summary, request_mock

    def test_fetch_window_uses_basic_auth_and_date_params(self) -> None:
        with mock.patch.object(
            sync_intervals.requests, "request", return_value=_MockResponse(200, []), create=True
        ) as request_mock:
            sync_intervals._fetch_window("secret-key", "i123", date(2024, 1, 1), date(2024, 6, 1))

        args, kwargs = request_mock.call_args
        self.assertEqual(args, ("GET", "https://intervals.icu/api/v1/athlete/i123/activities"))
        self.assertEqual(kwargs["auth"], ("API_KEY", "secret-key"))
        self.assertEqual(kwargs["params"], {"oldest": "2024-01-01", "newest": "2024-06-01"})

    def test_missing_api_key_raises_clear_error(self) -> None:
        config = _config()
        config["intervals"]["api_key"] = ""
        with self.assertRaisesRegex(ValueError, "intervals.api_key"):
            self._run(config, lambda *_a, **_k: _MockResponse(200, []))

    def test_default_athlete_id_is_zero(self) -> None:
        self.assertEqual(sync_intervals._credentials({"intervals": {"api_key": "k"}}), ("k", "0"))

    def test_unauthorized_raises_clear_error(self) -> None:
        config = _config()
        with mock.patch.object(sync_intervals, "load_config", return_value=config), mock.patch.object(
            sync_intervals.requests, "request", return_value=_MockResponse(401, {}), create=True
        ) as request_mock:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401.*api_key"):
                sync_intervals.sync_intervals(False, False)
        # Fails fast on the profile request, without retries.
        self.assertEqual(request_mock.call_count, 1)
        self.assertTrue(request_mock.call_args.args[1].endswith("/athlete/i123"))

    def test_normalize_activity_keeps_native_fields(self) -> None:
        raw = _ride("i98765", date(2024, 5, 1))
        activity = sync_intervals._normalize_activity(raw)
        self.assertEqual(
            activity,
            {
                "id": "i98765",
                "start_date_local": "2024-05-01T07:12:00",
                "start_date": "2024-05-01T05:12:00Z",
                "type": "Ride",
                "name": "Morning Ride",
                "distance": 42000.5,
                "moving_time": 5400,
                "elapsed_time": 6000,
                "total_elevation_gain": 350.0,
                "source": "GARMIN_CONNECT",
                "icu_training_load": 77,
                "average_heartrate": 141,
                "calories": 980,
                "provider": "intervals",
            },
        )
        normalized = normalize._normalize_activity(activity, {}, "intervals")
        self.assertEqual(normalized["type"], "Ride")
        self.assertEqual(normalized["date"], "2024-05-01")
        self.assertEqual(normalized["moving_time"], 5400.0)
        self.assertEqual(normalized["elevation_gain"], 350.0)

    def test_sync_writes_activities_and_skips_strava_stubs(self) -> None:
        today = date.today()

        def handler(_method, _url, **kwargs):
            params = kwargs["params"]
            if params["oldest"] <= today.isoformat() <= params["newest"]:
                return _MockResponse(200, [_ride("i1", today), _strava_stub("i2", today)])
            return _MockResponse(200, [])

        with mock.patch("builtins.print") as print_mock:
            summary, _ = self._run(_config(), handler)

        self.assertEqual(summary["source"], "intervals")
        self.assertEqual(summary["new_or_updated"], 1)
        self.assertTrue(summary["backfill_completed"])
        self.assertIsNone(summary["backfill_next_newest"])
        # Seen once by the recent window and once by the backfill walk.
        self.assertEqual(summary["skipped_strava_stubs"], 2)
        raw_dir = sync_intervals.RAW_DIR
        self.assertEqual(sorted(os.listdir(raw_dir)), ["i1.json"])
        self.assertEqual(read_json(os.path.join(raw_dir, "i1.json"))["provider"], "intervals")
        printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list if call.args)
        self.assertIn("imported from Strava", printed)

    def test_rate_limit_persists_backfill_cursor_and_resumes(self) -> None:
        calls = []

        def limited(_method, _url, **kwargs):
            calls.append(kwargs["params"])
            # Recent window plus first backfill window succeed, then persistent 429s.
            if len(calls) <= 2:
                return _MockResponse(200, [])
            return _MockResponse(429, {}, {"Retry-After": "5"})

        config = _config(recent_days=7)
        with mock.patch("builtins.print"):
            summary, _ = self._run(config, limited)
        self.assertTrue(summary["rate_limited"])
        self.assertFalse(summary["backfill_completed"])
        cursor = summary["backfill_next_newest"]
        self.assertEqual(cursor, calls[2]["newest"])
        state = read_json(sync_intervals.STATE_PATH)
        self.assertEqual(state["next_newest"], cursor)
        self.assertFalse(state["completed"])

        # Bounded retries on the failing window before giving up.
        self.assertEqual(len(calls), 2 + sync_intervals.MAX_REQUEST_ATTEMPTS)

        summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        self.assertTrue(summary["backfill_completed"])
        # Second call is the first backfill window: it must start at the saved cursor.
        self.assertEqual(self.activity_calls[1]["newest"], cursor)
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])

    def test_dry_run_writes_nothing(self) -> None:
        today = date.today()
        summary, _ = self._run(
            _config(),
            lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]),
            dry_run=True,
        )
        self.assertGreater(summary["fetched"], 0)
        self.assertEqual(summary["new_or_updated"], 0)
        self.assertEqual(os.listdir("."), [])

    def test_rate_limit_honors_retry_after_then_succeeds(self) -> None:
        responses = [
            _MockResponse(429, {}, {"Retry-After": "7"}),
            _MockResponse(429, {}, {"Retry-After": "9999"}),
            _MockResponse(200, [{"id": "i1"}]),
        ]
        with mock.patch.object(
            sync_intervals.requests, "request", side_effect=responses, create=True
        ), mock.patch.object(sync_intervals.time, "sleep") as sleep_mock, mock.patch("builtins.print"):
            payload = sync_intervals._request_json("k", "/athlete/0/activities")
        self.assertEqual(payload, [{"id": "i1"}])
        self.assertEqual(
            [call.args[0] for call in sleep_mock.call_args_list],
            [7, sync_intervals.MAX_RETRY_WAIT_SECONDS],
        )

    def test_athlete_profile_fetched_once_and_cached_without_api_key(self) -> None:
        config = _config()
        config["intervals"]["athlete_id"] = "0"
        _, request_mock = self._run(config, lambda *_a, **_k: _MockResponse(200, []))

        profile_urls = [c.args[1] for c in request_mock.call_args_list if not c.args[1].endswith("/activities")]
        self.assertEqual(profile_urls, ["https://intervals.icu/api/v1/athlete/0"])
        # Athlete "0" is resolved to the real id for the activity requests.
        activity_urls = {c.args[1] for c in request_mock.call_args_list if c.args[1].endswith("/activities")}
        self.assertEqual(activity_urls, {"https://intervals.icu/api/v1/athlete/i123/activities"})

        cache = read_json(sync_intervals.ATHLETE_PATH)
        self.assertEqual(cache["athlete_id"], "i123")
        self.assertEqual(cache["name"], "Pat Rider")
        with open(sync_intervals.ATHLETE_PATH, "r", encoding="utf-8") as f:
            self.assertNotIn("secret-key", f.read())

    def test_account_change_resets_persisted_data(self) -> None:
        today = date.today()
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "activities_normalized.json"), "w", encoding="utf-8") as f:
            f.write("[]")

        # Same account with a rotated key keeps data.
        config = _config()
        config["intervals"]["api_key"] = "rotated-key"
        self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        self.assertTrue(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "i1.json")))

        with mock.patch("builtins.print") as print_mock:
            self._run(
                _config(),
                lambda *_a, **_k: _MockResponse(200, []),
                profile={"id": "i999", "name": "Someone Else"},
            )
        self.assertIn("different intervals.icu account", str(print_mock.call_args_list))
        self.assertFalse(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "i1.json")))
        self.assertFalse(os.path.exists(os.path.join("data", "activities_normalized.json")))
        self.assertEqual(read_json(sync_intervals.ATHLETE_PATH)["athlete_id"], "i999")

    def test_scope_lower_bound_filters_and_limits_requests(self) -> None:
        start = date.today() - timedelta(days=400)
        old_day = start - timedelta(days=1)

        def handler(_method, _url, **kwargs):
            return _MockResponse(200, [_ride("old", old_day)] if kwargs["params"]["oldest"] <= old_day.isoformat() else [])

        summary, _ = self._run(_config(start_date=start.isoformat()), handler)
        self.assertEqual(summary["fetched"], 0)
        self.assertFalse(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "old.json")))
        oldest_requested = min(params["oldest"] for params in self.activity_calls)
        self.assertEqual(oldest_requested, (start - timedelta(days=1)).isoformat())
        for params in self.activity_calls:
            span = date.fromisoformat(params["newest"]) - date.fromisoformat(params["oldest"])
            self.assertLess(span.days, sync_intervals.WINDOW_DAYS)

    def test_recent_window_and_completed_backfill_skip(self) -> None:
        config = _config(recent_days=3)
        self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        # Backfill already completed: only the recent window is requested.
        self.assertEqual(len(self.activity_calls), 1)
        self.assertEqual(
            self.activity_calls[0]["oldest"], (date.today() - timedelta(days=3)).isoformat()
        )
        self.assertTrue(summary["backfill_completed"])

    def test_boundary_change_restarts_backfill(self) -> None:
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, []))
        new_start = (date.today() - timedelta(days=30)).isoformat()
        with mock.patch("builtins.print") as print_mock:
            self._run(_config(start_date=new_start), lambda *_a, **_k: _MockResponse(200, []))
        self.assertIn("Backfill boundary changed", str(print_mock.call_args_list))
        self.assertGreater(len(self.activity_calls), 1)

    def test_prune_deleted_removes_missing_activities_after_full_scan(self) -> None:
        today = date.today()
        self._run(
            _config(),
            lambda *_a, **_k: _MockResponse(200, [_ride("i1", today), _ride("i2", today)]),
        )
        # Next run restarts the full scan (resume_backfill off) and i2 is gone upstream.
        summary, _ = self._run(
            _config(resume_backfill=False),
            lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]),
            prune_deleted=True,
        )
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(os.listdir(sync_intervals.RAW_DIR), ["i1.json"])

    def test_prune_deleted_skipped_when_rate_limited(self) -> None:
        today = date.today()
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        with mock.patch("builtins.print") as print_mock:
            summary, _ = self._run(
                _config(resume_backfill=False),
                lambda *_a, **_k: _MockResponse(429, {}),
                prune_deleted=True,
            )
        self.assertIn("Skipping prune_deleted", str(print_mock.call_args_list))
        self.assertTrue(summary["rate_limited"])
        self.assertEqual(summary["deleted"], 0)
        self.assertEqual(os.listdir(sync_intervals.RAW_DIR), ["i1.json"])

    def test_main_writes_summary_files(self) -> None:
        summary = {
            "source": "intervals",
            "new_or_updated": 2,
            "deleted": 0,
            "lookback_start_ts": int(sync_intervals.utc_now().timestamp()),
            "skipped_strava_stubs": 3,
            "rate_limited": False,
        }
        with mock.patch.object(sys, "argv", ["sync_intervals.py"]), mock.patch(
            "builtins.print"
        ), mock.patch.object(sync_intervals, "sync_intervals", return_value=summary), mock.patch.object(
            sync_intervals, "load_config", return_value=_config()
        ):
            self.assertEqual(sync_intervals.main(), 0)
        self.assertEqual(read_json(sync_intervals.SUMMARY_JSON)["source"], "intervals")
        with open(sync_intervals.SUMMARY_TXT, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Sync intervals.icu: 2 new/updated, 0 deleted", text)
        self.assertIn("3 Strava imports skipped", text)


if __name__ == "__main__":
    unittest.main()
