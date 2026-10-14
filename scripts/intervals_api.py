"""Minimal intervals.icu API client (stdlib only, shared by sync and setup scripts)."""

import base64
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional

API_BASE = "https://intervals.icu/api/v1"
TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_MAX_RETRY_WAIT = 120.0
USER_AGENT = "git-sweaty-intervals-sync"


class IntervalsApiError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class IntervalsAuthError(IntervalsApiError):
    """HTTP 401/403: invalid API key or athlete id not accessible with that key."""


class IntervalsNotFoundError(IntervalsApiError):
    """HTTP 404."""


class IntervalsRateLimitError(IntervalsApiError):
    """HTTP 429 that persisted after all retries."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message, status=429)
        self.retry_after = retry_after


def _parse_retry_after(headers: Any) -> Optional[float]:
    if headers is None:
        return None
    try:
        value = str(headers.get("Retry-After") or "").strip()
    except Exception:
        return None
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _wait_seconds(retry_after: Optional[float], attempt: int, max_retry_wait: float) -> float:
    wait = retry_after if retry_after is not None else float(2 ** attempt)
    return max(1.0, min(float(max_retry_wait), wait))


def _build_request(api_key: str, path: str, params: Optional[Dict[str, str]]) -> urllib.request.Request:
    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    token = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    return urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )


def _error_for_status(status: int, path: str) -> IntervalsApiError:
    if status in (401, 403):
        return IntervalsAuthError(
            f"intervals.icu rejected the request (HTTP {status}) for {path}. Check that the API key "
            "is valid and that the athlete id belongs to that key (use \"0\" for the key's own athlete).",
            status=status,
        )
    if status == 404:
        return IntervalsNotFoundError(f"intervals.icu returned HTTP 404 for {path}.", status=status)
    return IntervalsApiError(f"intervals.icu API request failed (HTTP {status}) for {path}.", status=status)


def get_json(
    api_key: str,
    path: str,
    params: Optional[Dict[str, str]] = None,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_retry_wait: float = DEFAULT_MAX_RETRY_WAIT,
    timeout: float = 30,
    sleep: Optional[Callable[[float], Any]] = None,
) -> Any:
    """GET `API_BASE + path` with HTTP basic auth and return the decoded JSON body.

    Retries 408/425/429/5xx, network errors and non-JSON 2xx bodies (e.g. an HTML
    maintenance page) up to `max_attempts`, honoring Retry-After (capped at
    `max_retry_wait`) or falling back to exponential backoff.
    """
    sleep_fn = sleep if sleep is not None else time.sleep
    attempts = max(1, int(max_attempts))
    request = _build_request(api_key, path, params)
    url = request.full_url
    for attempt in range(1, attempts + 1):
        last_attempt = attempt >= attempts
        retry_after: Optional[float] = None
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                status = int(getattr(resp, "status", None) or resp.getcode() or 200)
                body = resp.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            retry_after = _parse_retry_after(exc.headers)
            try:
                exc.close()
            except Exception:
                pass
            if status not in TRANSIENT_HTTP_STATUS_CODES:
                raise _error_for_status(status, path) from None
            if last_attempt:
                if status == 429:
                    raise IntervalsRateLimitError(
                        f"intervals.icu API rate limit reached (HTTP 429) after {attempts} attempts.",
                        retry_after=retry_after,
                    ) from None
                raise _error_for_status(status, path) from None
            problem = f"returned HTTP {status}"
        except (OSError, http.client.HTTPException) as exc:
            # URLError, timeouts, connection resets and truncated reads.
            if last_attempt:
                raise IntervalsApiError(f"intervals.icu API request failed for {path}: {exc}") from exc
            problem = f"network error ({exc})"
        else:
            try:
                return json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                if last_attempt:
                    raise IntervalsApiError(
                        f"intervals.icu returned a non-JSON response for {path} (HTTP {status}); "
                        "the service may be under maintenance. Try again later.",
                        status=status,
                    ) from None
                problem = f"returned a non-JSON response (HTTP {status})"
        wait = _wait_seconds(retry_after, attempt, max_retry_wait)
        print(f"intervals.icu API {problem} on {url}; retrying in {wait:g}s (attempt {attempt}/{attempts}).")
        sleep_fn(wait)
    raise IntervalsApiError(f"intervals.icu API request failed for {path}.")  # pragma: no cover


def athlete_path(athlete_id: str = "0") -> str:
    """URL path of an athlete resource, with the id quoted as a single path segment."""
    return f"/athlete/{urllib.parse.quote(str(athlete_id or '0').strip() or '0', safe='')}"


def fetch_athlete(api_key: str, athlete_id: str = "0", **kw: Any) -> Dict[str, Any]:
    """Return the athlete profile; athlete id "0" resolves to the API key's own athlete."""
    payload = get_json(api_key, athlete_path(athlete_id), **kw)
    if not isinstance(payload, dict) or not payload.get("id"):
        raise IntervalsApiError("intervals.icu athlete profile response is missing an athlete id.")
    return payload
