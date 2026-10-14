import base64
import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import intervals_api  # noqa: E402


class _Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status
        self.headers = {}

    def getcode(self):
        return self.status


def _ok(payload) -> _Response:
    return _Response(json.dumps(payload).encode("utf-8"))


def _http_error(code: int, headers=None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://intervals.icu/x", code, "err", headers or {}, io.BytesIO(b"{}"))


class IntervalsApiTests(unittest.TestCase):
    def _get(self, responses, path="/athlete/0/activities", params=None, **kw):
        sleep = mock.Mock()
        with mock.patch.object(intervals_api.urllib.request, "urlopen", side_effect=responses) as urlopen, mock.patch.object(
            intervals_api, "print", create=True
        ):
            result = intervals_api.get_json("secret", path, params, sleep=sleep, **kw)
        return result, urlopen, sleep

    def test_basic_auth_url_and_params(self) -> None:
        payload, urlopen, sleep = self._get([_ok([{"id": "i1"}])], params={"oldest": "2024-01-01", "newest": "2024-06-01"})
        self.assertEqual(payload, [{"id": "i1"}])
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://intervals.icu/api/v1/athlete/0/activities?oldest=2024-01-01&newest=2024-06-01",
        )
        self.assertEqual(request.get_method(), "GET")
        token = request.get_header("Authorization").split(" ", 1)[1]
        self.assertEqual(base64.b64decode(token).decode("utf-8"), "API_KEY:secret")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)
        sleep.assert_not_called()

    def test_retry_after_honored_and_capped(self) -> None:
        responses = [
            _http_error(429, {"Retry-After": "7"}),
            _http_error(503, {"Retry-After": "9999"}),
            _ok({"id": "i1"}),
        ]
        payload, urlopen, sleep = self._get(responses, max_retry_wait=60)
        self.assertEqual(payload, {"id": "i1"})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [7, 60])
        self.assertEqual(urlopen.call_count, 3)

    def test_exponential_backoff_without_retry_after(self) -> None:
        _, _, sleep = self._get([_http_error(500), _http_error(502), _ok([])])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])

    def test_rate_limit_after_retries_exhausted(self) -> None:
        with self.assertRaises(intervals_api.IntervalsRateLimitError) as ctx:
            self._get([_http_error(429, {"Retry-After": "30"})] * 3, max_attempts=3)
        self.assertEqual(ctx.exception.retry_after, 30)
        self.assertEqual(ctx.exception.status, 429)
        self.assertIsInstance(ctx.exception, intervals_api.IntervalsApiError)

    def test_auth_and_not_found_fail_fast(self) -> None:
        for code, exc_type in ((401, intervals_api.IntervalsAuthError), (403, intervals_api.IntervalsAuthError), (404, intervals_api.IntervalsNotFoundError)):
            with self.subTest(code=code):
                with self.assertRaises(exc_type) as ctx:
                    self._get([_http_error(code), _ok({})])
                self.assertEqual(ctx.exception.status, code)

    def test_other_client_error_is_api_error(self) -> None:
        with self.assertRaises(intervals_api.IntervalsApiError) as ctx:
            self._get([_http_error(400)])
        self.assertNotIsInstance(ctx.exception, (intervals_api.IntervalsAuthError, intervals_api.IntervalsNotFoundError))

    def test_network_error_retried_then_raised(self) -> None:
        payload, _, sleep = self._get([urllib.error.URLError("boom"), ConnectionResetError("reset"), _ok([1])])
        self.assertEqual(payload, [1])
        self.assertEqual(sleep.call_count, 2)
        with self.assertRaisesRegex(intervals_api.IntervalsApiError, "boom"):
            self._get([urllib.error.URLError("boom")] * 2, max_attempts=2)

    def test_non_json_body_retried_then_clear_error(self) -> None:
        html = _Response(b"<html>Down for maintenance</html>")
        payload, _, sleep = self._get([html, _ok({"id": "i1"})])
        self.assertEqual(payload, {"id": "i1"})
        self.assertEqual(sleep.call_count, 1)
        pages = [_Response(b"<html>maintenance</html>") for _ in range(2)]
        with self.assertRaisesRegex(intervals_api.IntervalsApiError, "non-JSON response"):
            self._get(pages, max_attempts=2)

    def test_fetch_athlete_quotes_id_and_validates(self) -> None:
        with mock.patch.object(intervals_api.urllib.request, "urlopen", return_value=_ok({"id": "i1", "name": "Pat"})) as urlopen:
            athlete = intervals_api.fetch_athlete("secret", "i1/../x")
        self.assertEqual(athlete["name"], "Pat")
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://intervals.icu/api/v1/athlete/i1%2F..%2Fx")

        with mock.patch.object(intervals_api.urllib.request, "urlopen", return_value=_ok({"id": "i1"})) as urlopen:
            intervals_api.fetch_athlete("secret")
        self.assertTrue(urlopen.call_args.args[0].full_url.endswith("/athlete/0"))

        with mock.patch.object(intervals_api.urllib.request, "urlopen", return_value=_ok({"name": "x"})):
            with self.assertRaisesRegex(intervals_api.IntervalsApiError, "missing an athlete id"):
                intervals_api.fetch_athlete("secret")


if __name__ == "__main__":
    unittest.main()
