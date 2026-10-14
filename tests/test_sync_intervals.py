import base64
import contextlib
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import tempfile
import types
import unittest
from datetime import date, timedelta
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import intervals_api  # noqa: E402
import normalize  # noqa: E402
import sync_intervals  # noqa: E402
from utils import read_json, write_json  # noqa: E402


PROFILE = {"id": "i123", "name": "Pat Rider"}


class _MockResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.headers = headers or {}

    def json(self):
        return self._payload


class _UrlopenResponse(io.BytesIO):
    def __init__(self, status: int, body: bytes, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def getcode(self):
        return self.status


@contextlib.contextmanager
def _patch_http(side_effect=None, return_value=None):
    """Patch urllib for intervals_api; yields a mock called as (method, url, params=, auth=)."""
    request_mock = mock.Mock(side_effect=side_effect, return_value=return_value)

    def fake_urlopen(request, timeout=None):
        parsed = urllib.parse.urlsplit(request.full_url)
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = dict(urllib.parse.parse_qsl(parsed.query)) or None
        token = request.get_header("Authorization").split(" ", 1)[1]
        auth = tuple(base64.b64decode(token).decode("utf-8").split(":", 1))
        resp = request_mock(request.get_method(), url, params=params, auth=auth)
        body = json.dumps(resp._payload).encode("utf-8")
        if resp.status_code >= 400:
            raise urllib.error.HTTPError(request.full_url, resp.status_code, "error", resp.headers, io.BytesIO(body))
        return _UrlopenResponse(resp.status_code, body, resp.headers)

    with mock.patch.object(intervals_api.urllib.request, "urlopen", side_effect=fake_urlopen), mock.patch.object(
        intervals_api.time, "sleep"
    ), mock.patch.object(intervals_api, "print", create=True):
        yield request_mock


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

        with mock.patch.object(sync_intervals, "load_config", return_value=config), _patch_http(
            side_effect=route
        ) as request_mock:
            summary = sync_intervals.sync_intervals(dry_run, prune_deleted)
        self.activity_calls = activity_calls
        return summary, request_mock

    def test_fetch_window_uses_basic_auth_and_date_params(self) -> None:
        with _patch_http(return_value=_MockResponse(200, [])) as request_mock:
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
        with mock.patch.object(sync_intervals, "load_config", return_value=config), _patch_http(
            return_value=_MockResponse(401, {})
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
        self.assertEqual(summary["skipped_strava_stubs"], 1)
        # The backfill walk starts at the recent window's oldest day (one day of overlap).
        self.assertEqual(self.activity_calls[1]["newest"], self.activity_calls[0]["oldest"])
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

    def test_earlier_boundary_restarts_backfill(self) -> None:
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, []))
        new_start = (date.today() - timedelta(days=800)).isoformat()
        with mock.patch("builtins.print") as print_mock:
            self._run(_config(start_date=new_start), lambda *_a, **_k: _MockResponse(200, []))
        self.assertIn("Backfill boundary changed", str(print_mock.call_args_list))
        self.assertGreater(len(self.activity_calls), 1)

    def test_later_boundary_keeps_completed_backfill(self) -> None:
        # sync.lookback_years recomputes the bound from now(), so it moves later every run.
        config = {"intervals": {"api_key": "k", "athlete_id": "i123"}, "sync": {"lookback_years": 1}}
        after = int(sync_intervals.utc_now().timestamp()) - 365 * 86400
        with mock.patch.object(sync_intervals, "start_after_ts", return_value=after):
            self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        with mock.patch.object(sync_intervals, "start_after_ts", return_value=after + 86400), mock.patch(
            "builtins.print"
        ) as print_mock:
            summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        self.assertNotIn("Backfill boundary changed", str(print_mock.call_args_list))
        self.assertEqual(len(self.activity_calls), 1)
        self.assertTrue(summary["backfill_completed"])

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

    def test_prune_deleted_rescans_after_backfill_completed(self) -> None:
        today = date.today()
        old_day = today - timedelta(days=200)
        self._run(
            _config(),
            lambda *_a, **_k: _MockResponse(200, [_ride("i1", today), _ride("i2", old_day)]),
        )
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])

        def handler(_method, _url, **kwargs):
            params = kwargs["params"]
            return _MockResponse(200, [_ride("i1", today)] if params["oldest"] <= today.isoformat() <= params["newest"] else [])

        summary, _ = self._run(_config(), handler, prune_deleted=True)
        self.assertGreater(len(self.activity_calls), 1)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(os.listdir(sync_intervals.RAW_DIR), ["i1.json"])
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])

    def test_rate_limited_prune_scan_keeps_completed_state(self) -> None:
        today = date.today()
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        calls = []

        def limited(_method, _url, **kwargs):
            calls.append(kwargs["params"])
            return _MockResponse(200, []) if len(calls) == 1 else _MockResponse(429, {})

        with mock.patch("builtins.print"):
            summary, _ = self._run(_config(), limited, prune_deleted=True)
        self.assertTrue(summary["rate_limited"])
        self.assertEqual(summary["deleted"], 0)
        self.assertTrue(summary["backfill_completed"])
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])
        self.assertEqual(os.listdir(sync_intervals.RAW_DIR), ["i1.json"])

    def test_profile_rate_limit_stops_before_writing(self) -> None:
        today = date.today()
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        os.remove(sync_intervals.ATHLETE_PATH)
        state_before = read_json(sync_intervals.STATE_PATH)

        with mock.patch.object(sync_intervals, "load_config", return_value=_config()), _patch_http(
            return_value=_MockResponse(429, {})
        ) as request_mock, mock.patch("builtins.print"):
            summary = sync_intervals.sync_intervals(False, False)

        self.assertTrue(summary["rate_limited"])
        self.assertIn("rate limit", summary["rate_limit_message"])
        self.assertTrue(summary["backfill_completed"])
        self.assertEqual(summary["fetched"], 0)
        # Only the profile request was attempted; no activities fetched or files touched.
        self.assertTrue(all(c.args[1].endswith("/athlete/i123") for c in request_mock.call_args_list))
        self.assertFalse(os.path.exists(sync_intervals.ATHLETE_PATH))
        self.assertEqual(read_json(sync_intervals.STATE_PATH), state_before)
        self.assertTrue(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "i1.json")))

    def test_overlapping_windows_count_each_activity_once(self) -> None:
        today = date.today()
        # Every window (recent and backfill) returns the same activities; each counts once.
        with mock.patch("builtins.print"):
            summary, _ = self._run(
                _config(),
                lambda *_a, **_k: _MockResponse(200, [_ride("i1", today), _strava_stub("i2", today)]),
            )
        self.assertGreater(len(self.activity_calls), 2)
        self.assertEqual(summary["fetched"], 1)
        self.assertEqual(summary["skipped_strava_stubs"], 1)

    def test_strava_stub_detected_even_with_type(self) -> None:
        stub = dict(_strava_stub("i2", date.today()), type="Ride")
        self.assertTrue(sync_intervals._is_strava_stub(stub))
        self.assertTrue(sync_intervals._is_strava_stub({"id": "i3", "type": "Run", "_note": "x"}))
        self.assertFalse(sync_intervals._is_strava_stub(_ride("i1", date.today())))

    def test_rate_limited_first_run_then_success_keeps_derived_outputs(self) -> None:
        # First-ever run: the profile lookup is rate limited, but main()/run_pipeline still
        # write the summary and derived outputs without any fingerprint.
        with mock.patch.object(sys, "argv", ["sync_intervals.py"]), mock.patch.object(
            sync_intervals, "load_config", return_value=_config()
        ), _patch_http(return_value=_MockResponse(429, {})), mock.patch("builtins.print"):
            self.assertEqual(sync_intervals.main(), 0)
        self.assertTrue(read_json(sync_intervals.SUMMARY_JSON)["rate_limited"])
        self.assertFalse(os.path.exists(sync_intervals.ATHLETE_PATH))
        os.makedirs("site", exist_ok=True)
        write_json(os.path.join("data", "activities_normalized.json"), [])
        write_json(os.path.join("site", "data.json"), {})

        today = date.today()
        with mock.patch("builtins.print") as print_mock:
            summary, _ = self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        self.assertNotIn("resetting persisted data", str(print_mock.call_args_list))
        self.assertFalse(summary["rate_limited"])
        self.assertTrue(os.path.exists(sync_intervals.SUMMARY_JSON))
        self.assertTrue(os.path.exists(os.path.join("data", "activities_normalized.json")))
        self.assertTrue(os.path.exists(os.path.join("site", "data.json")))
        self.assertTrue(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "i1.json")))
        self.assertEqual(read_json(sync_intervals.ATHLETE_PATH)["athlete_id"], "i123")

    def test_missing_fingerprint_with_intervals_raw_data_still_resets(self) -> None:
        today = date.today()
        self._run(_config(), lambda *_a, **_k: _MockResponse(200, [_ride("i1", today)]))
        os.remove(sync_intervals.ATHLETE_PATH)
        with mock.patch("builtins.print") as print_mock:
            self._run(_config(), lambda *_a, **_k: _MockResponse(200, []))
        self.assertIn("No intervals.icu account fingerprint", str(print_mock.call_args_list))
        self.assertFalse(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "i1.json")))
        self.assertTrue(os.path.exists(sync_intervals.ATHLETE_PATH))

    def test_unbounded_backfill_stops_after_consecutive_empty_windows(self) -> None:
        today = date.today()
        config = _config(start_date=None)
        summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        # Recent window, MAX_EMPTY_WINDOWS backfill windows and one empty probe, not a walk to 1990.
        self.assertEqual(len(self.activity_calls), 1 + sync_intervals.MAX_EMPTY_WINDOWS + 1)
        probe = self.activity_calls[-1]
        self.assertEqual(probe["limit"], "1")
        self.assertEqual(probe["oldest"], sync_intervals.FLOOR_DATE.isoformat())
        self.assertEqual(probe["newest"], self.activity_calls[-2]["oldest"])
        self.assertTrue(summary["backfill_completed"])
        self.assertIsNone(summary["backfill_next_newest"])
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])

        # An activity resets the empty streak, so older history keeps being walked.
        old_day = today - timedelta(days=500)
        os.remove(sync_intervals.STATE_PATH)

        def handler(_method, _url, **kwargs):
            params = kwargs["params"]
            hit = params["oldest"] <= old_day.isoformat() <= params["newest"]
            return _MockResponse(200, [_ride("old", old_day)] if hit else [])

        summary, _ = self._run(config, handler)
        self.assertTrue(os.path.exists(os.path.join(sync_intervals.RAW_DIR, "old.json")))
        oldest_requested = date.fromisoformat(min(p["oldest"] for p in self.activity_calls))
        self.assertLess(oldest_requested, old_day - timedelta(days=sync_intervals.WINDOW_DAYS * 3))
        self.assertTrue(summary["backfill_completed"])

    @staticmethod
    def _history_handler(activities):
        """Serve `activities` like intervals.icu: by date range, newest-first, honoring limit."""

        def handler(_method, _url, **kwargs):
            params = kwargs["params"]
            hits = [a for a in activities if params["oldest"] <= a["start_date_local"][:10] <= params["newest"]]
            hits.sort(key=lambda a: a["start_date_local"], reverse=True)
            if "limit" in params:
                hits = hits[: int(params["limit"])]
            return _MockResponse(200, hits)

        return handler

    _GAP_HISTORY = (
        [_ride(f"y{year}", date(year, 6, 1)) for year in range(2015, 2019)]
        + [_strava_stub("s2018", date(2018, 9, 1))]
        + [_ride("y2022", date(2022, 3, 1)), _ride("now", date.today())]
    )

    def test_unbounded_backfill_probes_past_multi_year_gap(self) -> None:
        with mock.patch("builtins.print"):
            summary, _ = self._run(_config(start_date=None), self._history_handler(self._GAP_HISTORY))
        written = sorted(name[:-5] for name in os.listdir(sync_intervals.RAW_DIR))
        self.assertEqual(written, ["now", "y2015", "y2016", "y2017", "y2018", "y2022"])
        self.assertTrue(summary["backfill_completed"])
        self.assertTrue(read_json(sync_intervals.STATE_PATH)["completed"])
        probes = [p for p in self.activity_calls if "limit" in p]
        # Gap before 2022, gap 2019-2021 (jumps to the 2018 Strava stub), then an empty final probe.
        self.assertEqual(len(probes), 3)
        self.assertEqual(self.activity_calls[-1], probes[-1])
        # The walk does not crawl window by window down to FLOOR_DATE.
        oldest_window = min(p["oldest"] for p in self.activity_calls if "limit" not in p)
        self.assertGreater(oldest_window, "2012-01-01")

    def test_unbounded_prune_scan_probes_past_gap(self) -> None:
        os.makedirs(sync_intervals.RAW_DIR, exist_ok=True)
        sync_intervals._write_athlete_cache(PROFILE)
        write_json(os.path.join(sync_intervals.RAW_DIR, "gone.json"), sync_intervals._normalize_activity(_ride("gone", date.today())))
        with mock.patch("builtins.print"):
            summary, _ = self._run(
                _config(start_date=None), self._history_handler(self._GAP_HISTORY), prune_deleted=True
            )
        self.assertEqual(summary["deleted"], 1)
        written = sorted(name[:-5] for name in os.listdir(sync_intervals.RAW_DIR))
        self.assertEqual(written, ["now", "y2015", "y2016", "y2017", "y2018", "y2022"])

    def test_api_error_persists_cursor_then_raises(self) -> None:
        calls = []

        def failing(_method, _url, **kwargs):
            calls.append(kwargs["params"])
            # Recent window plus first backfill window succeed, then persistent 502s.
            if len(calls) <= 2:
                return _MockResponse(200, [])
            return _MockResponse(502, {})

        config = _config(recent_days=7, start_date=(date.today() - timedelta(days=1500)).isoformat())
        with mock.patch("builtins.print"), self.assertRaises(intervals_api.IntervalsApiError) as ctx:
            self._run(config, failing, dry_run=True)
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(os.listdir("."), [])

        calls.clear()
        with mock.patch("builtins.print"), self.assertRaises(intervals_api.IntervalsApiError):
            self._run(config, failing)
        self.assertEqual(len(calls), 2 + sync_intervals.MAX_REQUEST_ATTEMPTS)
        state = read_json(sync_intervals.STATE_PATH)
        self.assertEqual(state["next_newest"], calls[2]["newest"])
        self.assertFalse(state["completed"])
        self.assertEqual(state["last_success_date"], sync_intervals.utc_now().date().isoformat())

        summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        self.assertTrue(summary["backfill_completed"])
        # The resumed backfill starts at the window that failed.
        self.assertEqual(self.activity_calls[1]["newest"], calls[2]["newest"])

    def test_activity_on_window_boundary_fetched_and_counted_once(self) -> None:
        recent_oldest = sync_intervals.utc_now().date() - timedelta(days=7)
        window_oldest = recent_oldest - timedelta(days=sync_intervals.WINDOW_DAYS - 1)
        # Days on (and just below) the recent/backfill and backfill/backfill boundaries.
        days = {
            "a": recent_oldest,
            "b": recent_oldest - timedelta(days=1),
            "c": window_oldest,
            "d": window_oldest - timedelta(days=2),
        }
        activities = [_ride(activity_id, day) for activity_id, day in days.items()]
        inclusive = self._history_handler(activities)

        def start_of_day_newest(method, url, **kwargs):
            # The API treats a date-only `newest` as the start of that day.
            params = dict(kwargs["params"])
            params["newest"] = (date.fromisoformat(params["newest"]) - timedelta(days=1)).isoformat()
            return inclusive(method, url, params=params)

        for name, handler in (("inclusive", inclusive), ("start_of_day", start_of_day_newest)):
            with self.subTest(name), mock.patch.object(sync_intervals, "RAW_DIR", os.path.join(name, "raw")):
                summary, _ = self._run(_config(resume_backfill=False), handler)
                self.assertEqual(summary["fetched"], 4)
                self.assertEqual(summary["new_or_updated"], 4)
                self.assertEqual(sorted(os.listdir(sync_intervals.RAW_DIR)), ["a.json", "b.json", "c.json", "d.json"])

    def test_strava_stubs_counted_only_within_scope(self) -> None:
        start = date.today() - timedelta(days=400)
        stubs = [_strava_stub("in_scope", date.today()), _strava_stub("too_old", start - timedelta(days=10))]
        with mock.patch("builtins.print") as print_mock:
            summary, _ = self._run(_config(start_date=start.isoformat()), lambda *_a, **_k: _MockResponse(200, stubs))
        self.assertEqual(summary["skipped_strava_stubs"], 1)
        self.assertIn("Note: 1 intervals.icu activities", str(print_mock.call_args_list))

    def test_fetch_athlete_uses_shared_client_with_error_mapping(self) -> None:
        with mock.patch.object(intervals_api, "fetch_athlete", return_value=PROFILE) as fetch:
            self.assertEqual(sync_intervals._fetch_athlete("k", "i123"), PROFILE)
        fetch.assert_called_once_with(
            "k",
            "i123",
            max_attempts=sync_intervals.MAX_REQUEST_ATTEMPTS,
            max_retry_wait=sync_intervals.MAX_RETRY_WAIT_SECONDS,
        )
        with mock.patch.object(intervals_api, "fetch_athlete", side_effect=intervals_api.IntervalsRateLimitError("slow")):
            with self.assertRaises(sync_intervals.RateLimitExceeded):
                sync_intervals._fetch_athlete("k", "i123")
        with mock.patch.object(intervals_api, "fetch_athlete", side_effect=intervals_api.IntervalsAuthError("no", 403)):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403.*intervals.api_key"):
                sync_intervals._fetch_athlete("k", "i123")

    def test_activities_path_quotes_athlete_id(self) -> None:
        with _patch_http(return_value=_MockResponse(200, [])) as request_mock:
            sync_intervals._fetch_window("k", "i1/../x", date(2024, 1, 1), date(2024, 6, 1))
        self.assertEqual(request_mock.call_args.args[1], "https://intervals.icu/api/v1/athlete/i1%2F..%2Fx/activities")

    def test_bounded_backfill_walks_to_configured_start(self) -> None:
        start = date.today() - timedelta(days=1500)
        self._run(_config(start_date=start.isoformat()), lambda *_a, **_k: _MockResponse(200, []))
        oldest_requested = min(p["oldest"] for p in self.activity_calls)
        self.assertEqual(oldest_requested, (start - timedelta(days=1)).isoformat())

    def test_unbounded_prune_scan_reaches_oldest_local_activity(self) -> None:
        today = date.today()
        old_day = today - timedelta(days=1800)
        os.makedirs(sync_intervals.RAW_DIR, exist_ok=True)
        sync_intervals._write_athlete_cache(PROFILE)
        write_json(os.path.join(sync_intervals.RAW_DIR, "old.json"), sync_intervals._normalize_activity(_ride("old", old_day)))
        write_json(os.path.join(sync_intervals.RAW_DIR, "gone.json"), sync_intervals._normalize_activity(_ride("gone", today)))

        def handler(_method, _url, **kwargs):
            params = kwargs["params"]
            hit = params["oldest"] <= old_day.isoformat() <= params["newest"]
            return _MockResponse(200, [_ride("old", old_day)] if hit else [])

        with mock.patch("builtins.print"):
            summary, _ = self._run(_config(start_date=None), handler, prune_deleted=True)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(os.listdir(sync_intervals.RAW_DIR), ["old.json"])

    def test_recent_window_catches_up_after_missed_runs(self) -> None:
        today = date.today()
        config = _config(recent_days=3)
        self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        state = read_json(sync_intervals.STATE_PATH)
        self.assertEqual(state["last_success_date"], sync_intervals.utc_now().date().isoformat())

        # The workflow was broken for 20 days: the recent window reaches back to the last success.
        last_success = sync_intervals.utc_now().date() - timedelta(days=20)
        state["last_success_date"] = last_success.isoformat()
        write_json(sync_intervals.STATE_PATH, state)
        summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        self.assertEqual(len(self.activity_calls), 1)
        self.assertEqual(self.activity_calls[0]["oldest"], (last_success - timedelta(days=1)).isoformat())
        self.assertTrue(summary["backfill_completed"])
        self.assertEqual(
            read_json(sync_intervals.STATE_PATH)["last_success_date"], sync_intervals.utc_now().date().isoformat()
        )

        # Bounded by the configured start date.
        state = read_json(sync_intervals.STATE_PATH)
        state["last_success_date"] = (today - timedelta(days=1000)).isoformat()
        write_json(sync_intervals.STATE_PATH, state)
        start = today - timedelta(days=400)
        self._run(_config(recent_days=3, start_date=start.isoformat()), lambda *_a, **_k: _MockResponse(200, []))
        self.assertEqual(min(p["oldest"] for p in self.activity_calls), (start - timedelta(days=1)).isoformat())

    def test_rate_limited_recent_window_keeps_last_success_date(self) -> None:
        config = _config(recent_days=3)
        self._run(config, lambda *_a, **_k: _MockResponse(200, []))
        state = read_json(sync_intervals.STATE_PATH)
        state["last_success_date"] = "2020-01-01"
        write_json(sync_intervals.STATE_PATH, state)
        with mock.patch("builtins.print"):
            summary, _ = self._run(config, lambda *_a, **_k: _MockResponse(429, {}))
        self.assertTrue(summary["rate_limited"])
        self.assertEqual(read_json(sync_intervals.STATE_PATH)["last_success_date"], "2020-01-01")

    def test_summary_shape_identical_for_normal_and_rate_limited_paths(self) -> None:
        normal, _ = self._run(_config(), lambda *_a, **_k: _MockResponse(200, []))
        with mock.patch.object(sync_intervals, "load_config", return_value=_config()), _patch_http(
            return_value=_MockResponse(429, {})
        ), mock.patch("builtins.print"):
            limited = sync_intervals.sync_intervals(False, False)
        self.assertTrue(limited["rate_limited"])
        self.assertEqual(set(normal), set(limited))
        self.assertEqual(set(normal["recent_sync"]), set(limited["recent_sync"]))
        self.assertEqual(normal["rate_limit_message"], "")

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
