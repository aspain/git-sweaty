#!/usr/bin/env python3
"""
Bootstrap activity-provider auth and GitHub setup for this repository.

This script performs:
0) Optional local virtualenv bootstrap (.venv + requirements install).
1) Provider-specific auth/bootstrap (Strava OAuth or Garmin credentials).
2) GitHub secret + variable updates via gh CLI.
3) Best-effort GitHub setup automation (workflows, pages, first run).
"""

import argparse
import random
import getpass
import html
import http.server
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import json
import webbrowser
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional, Tuple

from garmin_token_store import (
    decode_token_store_b64,
    encode_token_store_dir_as_zip_b64,
    hydrate_token_store_from_legacy_file,
    token_store_ready,
    write_token_store_bytes,
)
from repo_helpers import (
    normalize_dashboard_url as _shared_normalize_dashboard_url,
    normalize_repo_slug as _shared_normalize_repo_slug,
    pages_url_from_slug as _shared_pages_url_from_slug,
)

if sys.version_info < (3, 9):
    raise SystemExit(
        "Python 3.9+ is required to run scripts/setup_auth.py. "
        f"Detected {sys.version.split()[0]}. "
        "Please run with Python 3.11 (recommended)."
    )


TOKEN_ENDPOINT = "https://www.strava.com/oauth/token"
AUTHORIZE_ENDPOINT = "https://www.strava.com/oauth/authorize"
STRAVA_ATHLETE_ENDPOINT = "https://www.strava.com/api/v3/athlete"
CALLBACK_PATH = "/exchange_token"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT = 180
DEFAULT_SOURCE = "strava"
DEFAULT_TEMPLATE_REPO = "aspain/git-sweaty"
VENV_DIRNAME = ".venv"
GARMIN_AUTH_MAX_ATTEMPTS = 3

STATUS_OK = "OK"
STATUS_SKIPPED = "SKIPPED"
STATUS_MANUAL_REQUIRED = "MANUAL_REQUIRED"

UNIT_PRESETS = {
    "us": ("mi", "ft"),
    "metric": ("km", "m"),
}
DEFAULT_WEEK_START = "sunday"
WEEK_START_CHOICES = {"sunday", "monday"}
STRAVA_HOST_RE = re.compile(r"(^|\.)strava\.com$", re.IGNORECASE)
GARMIN_CONNECT_HOST_RE = re.compile(r"(^|\.)connect\.garmin\.com$", re.IGNORECASE)
TRUTHY_BOOL_TEXT = {"1", "true", "yes", "y", "on"}
FALSEY_BOOL_TEXT = {"0", "false", "no", "n", "off", ""}
STRAVA_REQUIRED_SECRET_NAMES = {
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_REFRESH_TOKEN",
}
GARMIN_PRIMARY_SECRET_NAMES = {"GARMIN_TOKENS_B64"}
GARMIN_FALLBACK_SECRET_NAMES = {"GARMIN_EMAIL", "GARMIN_PASSWORD"}


@dataclass
class StepResult:
    name: str
    status: str
    detail: str
    manual_help: Optional[str] = None


@dataclass
class CallbackResult:
    code: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExistingDashboardSettings:
    source: str
    distance_unit: str
    elevation_unit: str
    week_start: str


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    result: CallbackResult = CallbackResult()
    expected_state: str = ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_error(404, "Not Found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        error = query.get("error", [""])[0]

        if error:
            self.__class__.result.error = f"Strava returned error: {error}"
        elif not code:
            self.__class__.result.error = "Missing code query parameter in callback URL."
        elif state != self.__class__.expected_state:
            self.__class__.result.error = "State mismatch in callback. Please retry."
        else:
            self.__class__.result.code = code

        message = "Authorization received. You can close this tab and return to the terminal."
        if self.__class__.result.error:
            message = f"Authorization failed: {self.__class__.result.error}"

        safe_message = html.escape(message, quote=True)
        body = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Strava Auth</title></head><body>"
            f"<p>{safe_message}</p></body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def _run_stream(cmd: list[str], *, cwd: Optional[str] = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd)


def _first_stderr_line(stderr: str) -> str:
    text = (stderr or "").strip()
    if not text:
        return "Unknown error."
    return text.splitlines()[0]


def _is_transient_gh_failure(stderr: str) -> bool:
    text = (stderr or "").lower()
    transient_tokens = [
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection refused",
    ]
    return any(token in text for token in transient_tokens)


def _isatty() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def _prompt(value: Optional[str], label: str, secret: bool = False) -> str:
    if value:
        return value.strip()
    if secret:
        return _prompt_secret_masked(f"{label}: ").strip()
    return input(f"{label}: ").strip()


def _prompt_secret_masked(prompt: str) -> str:
    if not _isatty():
        return getpass.getpass(prompt)

    try:
        import termios
        import tty
    except ImportError:
        return getpass.getpass(prompt)

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    chars: list[str] = []
    sys.stdout.write(prompt)
    sys.stdout.flush()

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in ("\x7f", "\x08"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch == "\x04":
                if not chars:
                    raise EOFError("Input closed.")
                continue
            if ord(ch) < 32:
                continue
            chars.append(ch)
            sys.stdout.write("*")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)

    return "".join(chars)


def _assert_gh_ready() -> None:
    if shutil.which("gh") is None:
        raise RuntimeError(
            "GitHub CLI (`gh`) is required. Install it from https://cli.github.com/ and run `gh auth login`."
        )

    status = _run(["gh", "auth", "status"], check=False)
    if status.returncode != 0:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run `gh auth login` and re-run this script."
        )


def _assert_repo_access(repo: str) -> None:
    check = _run(
        ["gh", "repo", "view", repo, "--json", "nameWithOwner"],
        check=False,
    )
    if check.returncode != 0:
        detail = _first_stderr_line(check.stderr)
        raise RuntimeError(f"Unable to access repository '{repo}' with current gh auth context: {detail}")


def _extract_gh_token_scopes(status_output: str) -> set[str]:
    scopes: set[str] = set()
    for line in (status_output or "").splitlines():
        if "Token scopes:" not in line:
            continue
        _, raw_scopes = line.split("Token scopes:", 1)
        for part in raw_scopes.split(","):
            scope = part.strip().strip("'\"`")
            if scope:
                scopes.add(scope)
    return scopes


def _build_actions_secret_access_error(repo: str, detail: str, status_output: str) -> str:
    required_scopes = {"repo", "workflow"}
    granted_scopes = _extract_gh_token_scopes(status_output)
    missing_scopes = sorted(scope for scope in required_scopes if scope not in granted_scopes)
    missing_scope_hint = (
        f"Missing token scopes: {', '.join(missing_scopes)}. "
        if missing_scopes
        else "Token scopes could not be verified from `gh auth status`; ensure `repo` and `workflow` are granted. "
    )
    return (
        f"GitHub auth can access '{repo}' but cannot read the Actions secrets public key ({detail}). "
        + missing_scope_hint
        + "Fix: run `gh auth refresh -s workflow,repo`, then retry. "
        + "If this is an organization fork, ensure SSO/OAuth access is authorized for the token. "
        + "Also confirm you are targeting the correct repository (usually your fork)."
    )


def _assert_actions_secret_access(repo: str) -> None:
    check = _run(
        ["gh", "api", f"repos/{repo}/actions/secrets/public-key"],
        check=False,
    )
    if check.returncode == 0:
        return

    detail = _first_stderr_line(check.stderr)
    error_text = f"{check.stderr or ''}\n{check.stdout or ''}".lower()
    if "resource not accessible by integration" in error_text:
        status = _run(["gh", "auth", "status"], check=False)
        status_text = f"{status.stdout or ''}\n{status.stderr or ''}"
        raise RuntimeError(_build_actions_secret_access_error(repo, detail, status_text))
    if "http 403" in error_text:
        raise RuntimeError(
            f"Access to Actions secrets API was forbidden for '{repo}' ({detail}). "
            "Ensure `gh` auth has `repo` and `workflow` scopes (`gh auth refresh -s workflow,repo`), "
            "authorize SSO if required, and confirm you are using the correct fork."
        )

    raise RuntimeError(
        f"Unable to access Actions secrets API for repository '{repo}' with current gh auth context: {detail}"
    )


def _normalize_repo_slug(value: Optional[str]) -> Optional[str]:
    return _shared_normalize_repo_slug(value)


def _repo_slug_from_git() -> Optional[str]:
    result = _run(["git", "config", "--get", "remote.origin.url"], check=False)
    if result.returncode != 0:
        return None
    return _normalize_repo_slug(result.stdout.strip())


def _repo_slug_from_gh_context() -> Optional[str]:
    result = _run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        check=False,
    )
    if result.returncode != 0:
        return None
    return _normalize_repo_slug(result.stdout.strip())


def _resolve_repo_slug(explicit_repo: Optional[str]) -> Optional[str]:
    candidates = [
        explicit_repo,
        _repo_slug_from_git(),
        os.environ.get("GH_REPO"),
        _repo_slug_from_gh_context(),
    ]
    for candidate in candidates:
        normalized = _normalize_repo_slug(candidate)
        if normalized:
            return normalized
    return None


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _in_virtualenv() -> bool:
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    real_prefix = getattr(sys, "real_prefix", None)
    return bool(real_prefix or (sys.prefix != base_prefix))


def _venv_python_path(venv_dir: str) -> str:
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _venv_has_pip(venv_python: str) -> bool:
    probe = _run([venv_python, "-m", "pip", "--version"], check=False)
    return probe.returncode == 0


def _ensure_venv_pip(venv_python: str) -> None:
    if _venv_has_pip(venv_python):
        return

    print("pip is missing in .venv; attempting bootstrap via ensurepip...")
    ensure = _run([venv_python, "-m", "ensurepip", "--upgrade"], check=False)
    if ensure.returncode != 0:
        detail = _first_stderr_line(ensure.stderr or ensure.stdout)
        raise RuntimeError(
            "The local virtual environment was created without pip and automatic pip bootstrap failed "
            f"({detail}). Install Python with ensurepip support (for example install the OS package that "
            "provides python3-venv), or run with --no-bootstrap-env and manage your environment manually."
        )
    if not _venv_has_pip(venv_python):
        raise RuntimeError(
            "The local virtual environment was created without pip and could not be repaired automatically."
        )


def _bootstrap_env_and_reexec(args: argparse.Namespace) -> None:
    if args.no_bootstrap_env or args.env_bootstrapped or _in_virtualenv():
        return

    root = _project_root()
    requirements = os.path.join(root, "requirements.txt")
    if not os.path.exists(requirements):
        return

    venv_dir = os.path.join(root, VENV_DIRNAME)
    venv_python = _venv_python_path(venv_dir)
    if not os.path.exists(venv_python):
        print("\nCreating local virtual environment (.venv)...")
        _run_stream([sys.executable, "-m", "venv", venv_dir], cwd=root)

    _ensure_venv_pip(venv_python)
    print("Installing Python dependencies into .venv...")
    _run_stream([venv_python, "-m", "pip", "install", "--upgrade", "pip"], cwd=root)
    _run_stream([venv_python, "-m", "pip", "install", "-r", requirements], cwd=root)

    script_path = os.path.abspath(__file__)
    child_args = [arg for arg in sys.argv[1:] if arg != "--env-bootstrapped"]
    child_args.append("--env-bootstrapped")
    print("Re-launching setup inside .venv...")
    raise SystemExit(subprocess.call([venv_python, script_path, *child_args], cwd=root))


def _set_secret(name: str, value: str, repo: str) -> None:
    cmd = ["gh", "secret", "set", name, "--repo", repo]
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        result = _run(cmd, input_text=value, check=False)
        if result.returncode == 0:
            return
        stderr = (result.stderr or "").strip()
        if attempt < max_attempts and _is_transient_gh_failure(stderr):
            sleep_seconds = min(8, 2 ** (attempt - 1))
            print(
                f"Transient error setting secret {name}; retrying in {sleep_seconds}s "
                f"(attempt {attempt}/{max_attempts})..."
            )
            time.sleep(sleep_seconds)
            continue
        detail = f": {stderr.splitlines()[0]}" if stderr else ""
        raise RuntimeError(f"Failed to set GitHub secret {name}{detail}")


def _gh_auth_token() -> Optional[str]:
    result = _run(["gh", "auth", "token"], check=False)
    if result.returncode != 0:
        return None
    token = (result.stdout or "").strip()
    return token or None


def _try_set_strava_secret_update_token(repo: str) -> Tuple[bool, str]:
    token = _gh_auth_token()
    if not token:
        return (
            False,
            "Could not read current gh auth token; STRAVA_SECRET_UPDATE_TOKEN was not configured.",
        )
    try:
        _set_secret("STRAVA_SECRET_UPDATE_TOKEN", token, repo)
    except RuntimeError as exc:
        return False, f"Unable to set STRAVA_SECRET_UPDATE_TOKEN automatically: {exc}"
    return (
        True,
        "Configured STRAVA_SECRET_UPDATE_TOKEN from current gh auth session.",
    )


def _set_variable(name: str, value: str, repo: str) -> None:
    cmd = ["gh", "variable", "set", name, "--repo", repo, "--body", value]
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        result = _run(cmd, check=False)
        if result.returncode == 0:
            return
        stderr = (result.stderr or "").strip()
        if attempt < max_attempts and _is_transient_gh_failure(stderr):
            sleep_seconds = min(8, 2 ** (attempt - 1))
            print(
                f"Transient error setting variable {name}; retrying in {sleep_seconds}s "
                f"(attempt {attempt}/{max_attempts})..."
            )
            time.sleep(sleep_seconds)
            continue
        detail = f": {stderr.splitlines()[0]}" if stderr else ""
        raise RuntimeError(f"Failed to set GitHub variable {name}{detail}")


def _clear_variable(name: str, repo: str) -> None:
    result = _run(["gh", "variable", "delete", name, "--repo", repo], check=False)
    if result.returncode == 0:
        return
    error_text = (result.stderr or "").lower()
    if "not found" in error_text or "http 404" in error_text:
        return
    detail = _first_stderr_line(result.stderr)
    raise RuntimeError(f"Failed to clear GitHub variable {name}: {detail}")


def _get_variable(name: str, repo: str) -> Optional[str]:
    try:
        result = _run(["gh", "variable", "get", name, "--repo", repo], check=False)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value if value else None


def _existing_dashboard_source(repo: str) -> Optional[str]:
    value = _get_variable("DASHBOARD_SOURCE", repo)
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"strava", "garmin"}:
        return normalized
    return None


def _normalize_distance_unit(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"mi", "km"}:
        return normalized
    raise ValueError(f"Unsupported distance unit '{value}'. Expected one of: km, mi.")


def _normalize_elevation_unit(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ft", "m"}:
        return normalized
    raise ValueError(f"Unsupported elevation unit '{value}'. Expected one of: ft, m.")


def _existing_dashboard_units(repo: str) -> Optional[Tuple[str, str]]:
    distance_raw = _get_variable("DASHBOARD_DISTANCE_UNIT", repo)
    elevation_raw = _get_variable("DASHBOARD_ELEVATION_UNIT", repo)
    if distance_raw is None or elevation_raw is None:
        return None
    try:
        distance = _normalize_distance_unit(distance_raw)
        elevation = _normalize_elevation_unit(elevation_raw)
    except ValueError:
        return None
    if (distance, elevation) not in set(UNIT_PRESETS.values()):
        return None
    return distance, elevation


def _existing_dashboard_profile_url(repo: str, source: str) -> str:
    source_name = str(source or "").strip().lower()
    if source_name == "strava":
        variable_name = "DASHBOARD_STRAVA_PROFILE_URL"
        normalizer = _normalize_strava_profile_url
    elif source_name == "garmin":
        variable_name = "DASHBOARD_GARMIN_PROFILE_URL"
        normalizer = _normalize_garmin_profile_url
    else:
        return ""
    raw = _get_variable(variable_name, repo)
    if not raw:
        return ""
    try:
        return normalizer(raw)
    except ValueError:
        return ""


def _existing_dashboard_strava_profile_url(repo: str) -> str:
    return _existing_dashboard_profile_url(repo, "strava")


def _existing_dashboard_garmin_profile_url(repo: str) -> str:
    return _existing_dashboard_profile_url(repo, "garmin")


def _load_existing_dashboard_settings(repo: str) -> Optional[ExistingDashboardSettings]:
    source = _existing_dashboard_source(repo)
    units = _existing_dashboard_units(repo)
    week_start = _existing_dashboard_week_start(repo)
    if not source or units is None or not week_start:
        return None
    distance_unit, elevation_unit = units
    return ExistingDashboardSettings(
        source=source,
        distance_unit=distance_unit,
        elevation_unit=elevation_unit,
        week_start=week_start,
    )


def _normalize_week_start(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "sun": "sunday",
        "sunday": "sunday",
        "mon": "monday",
        "monday": "monday",
    }
    resolved = aliases.get(normalized)
    if resolved:
        return resolved
    allowed = ", ".join(sorted(WEEK_START_CHOICES))
    raise ValueError(f"Unsupported week start '{value}'. Expected one of: {allowed}.")


def _existing_dashboard_week_start(repo: str) -> Optional[str]:
    value = _get_variable("DASHBOARD_WEEK_START", repo)
    if value is None:
        return None
    try:
        return _normalize_week_start(value)
    except ValueError:
        return None


def _parse_bool_text(value: Optional[str], *, field_name: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in TRUTHY_BOOL_TEXT:
        return True
    if normalized in FALSEY_BOOL_TEXT:
        return False
    allowed_values = ", ".join(sorted(TRUTHY_BOOL_TEXT | FALSEY_BOOL_TEXT))
    raise ValueError(f"Unsupported value for {field_name}: {value!r}. Expected one of: {allowed_values}.")


def _existing_dashboard_activity_links(repo: str, source: str) -> Optional[bool]:
    source_name = str(source or "").strip().upper()
    if source_name not in {"STRAVA", "GARMIN"}:
        return None
    variable_name = f"DASHBOARD_{source_name}_ACTIVITY_LINKS"
    value = _get_variable(variable_name, repo)
    if value is None:
        return None
    try:
        return _parse_bool_text(value, field_name=variable_name)
    except ValueError:
        return None


def _existing_dashboard_strava_activity_links(repo: str) -> Optional[bool]:
    return _existing_dashboard_activity_links(repo, "strava")


def _existing_dashboard_garmin_activity_links(repo: str) -> Optional[bool]:
    return _existing_dashboard_activity_links(repo, "garmin")


def _list_secret_names(repo: str) -> set[str]:
    try:
        result = _run(["gh", "secret", "list", "--repo", repo, "--json", "name"], check=False)
    except FileNotFoundError:
        return set()
    if result.returncode != 0:
        return set()
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return set()
    names: set[str] = set()
    if not isinstance(payload, list):
        return names
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _has_required_source_secrets(source: str, secret_names: set[str]) -> bool:
    normalized_source = str(source or "").strip().lower()
    if normalized_source == "strava":
        return STRAVA_REQUIRED_SECRET_NAMES.issubset(secret_names)
    if normalized_source == "garmin":
        has_primary = GARMIN_PRIMARY_SECRET_NAMES.issubset(secret_names)
        has_fallback = GARMIN_FALLBACK_SECRET_NAMES.issubset(secret_names)
        return has_primary or has_fallback
    return False


def _prompt_reuse_existing_settings() -> bool:
    choice = _prompt_choice(
        "\nReuse existing dashboard settings? [y/n] (default: y): ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default="y",
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _prompt_update_credentials() -> bool:
    choice = _prompt_choice(
        "Update credentials now? [y/n] (default: n): ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default="n",
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _has_explicit_setup_overrides(args: argparse.Namespace) -> bool:
    return any(
        getattr(args, key, None) is not None
        for key in (
            "source",
            "unit_system",
            "week_start",
            "strava_profile_url",
            "strava_activity_links",
            "garmin_profile_url",
            "garmin_activity_links",
        )
    )


def _has_explicit_credentials_for_source(args: argparse.Namespace, source: str) -> bool:
    normalized_source = str(source or "").strip().lower()
    if normalized_source == "strava":
        return bool(getattr(args, "client_id", None) or getattr(args, "client_secret", None))
    if normalized_source == "garmin":
        return bool(
            getattr(args, "garmin_token_store_b64", None)
            or getattr(args, "garmin_email", None)
            or getattr(args, "garmin_password", None)
        )
    return False


def _prompt_full_backfill_choice(source: str) -> bool:
    print(
        "\nThis repository is already configured for "
        f"{source}. You can keep incremental sync or force a full history re-fetch."
    )
    choice = _prompt_choice(
        "Run a full backfill this time? [y/n] (default: n): ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default="n",
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _authorize_and_get_code(
    client_id: str,
    redirect_uri: str,
    scope: str,
    port: int,
    timeout_seconds: int,
    open_browser: bool,
) -> str:
    state = secrets.token_urlsafe(20)
    OAuthCallbackHandler.result = CallbackResult()
    OAuthCallbackHandler.expected_state = state

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "approval_prompt": "force",
        "scope": scope,
        "state": state,
    }
    auth_url = f"{AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"

    print("\nOpen this URL to authorize Strava access:")
    print(auth_url)

    with ReusableTCPServer(("localhost", port), OAuthCallbackHandler) as server:
        server.timeout = 1
        if open_browser:
            webbrowser.open(auth_url, new=1, autoraise=True)

        print(f"\nWaiting for callback on {redirect_uri} (timeout: {timeout_seconds}s)...")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            server.handle_request()
            if OAuthCallbackHandler.result.code or OAuthCallbackHandler.result.error:
                break

    if OAuthCallbackHandler.result.error:
        raise RuntimeError(OAuthCallbackHandler.result.error)
    if not OAuthCallbackHandler.result.code:
        raise TimeoutError("Timed out waiting for Strava OAuth callback.")
    return OAuthCallbackHandler.result.code


def _exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict:
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Strava token exchange failed with HTTP status {exc.code}.") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", "unknown network error")
        raise RuntimeError(f"Strava token exchange request failed: {reason}.") from None

    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError("Unexpected token response format from Strava.") from None

    refresh_token = response_payload.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Strava response did not include refresh_token.")
    return response_payload


def _parse_iso8601_utc(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pages_url_from_slug(slug: str) -> str:
    return _shared_pages_url_from_slug(slug)


def _normalize_dashboard_url(value: str) -> str:
    return _shared_normalize_dashboard_url(value)


def _dashboard_url_from_pages_api(repo: str) -> Optional[str]:
    try:
        result = _run(["gh", "api", f"repos/{repo}/pages"], check=False)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    custom_url = _normalize_dashboard_url(payload.get("cname", ""))
    if custom_url:
        return custom_url

    html_url = _normalize_dashboard_url(payload.get("html_url", ""))
    if html_url:
        return html_url
    return None


def _normalize_pages_custom_domain(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Custom domain cannot be empty.")

    candidate = raw if "://" in raw else f"https://{raw.lstrip('/')}"
    parsed = urllib.parse.urlparse(candidate)
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Custom domain must use http(s) or be a plain host.")

    host = str(parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise ValueError("Custom domain must include a valid host.")
    if parsed.port is not None:
        raise ValueError("Custom domain must not include a port.")
    path = str(parsed.path or "").strip()
    if path and path not in {"/"}:
        raise ValueError("Custom domain must be host-only (no path).")
    if parsed.query or parsed.fragment:
        raise ValueError("Custom domain must not include query or fragment.")
    return host


def _get_pages_custom_domain(repo: str) -> Optional[str]:
    result = _run(
        ["gh", "api", f"repos/{repo}/pages", "--jq", ".cname"],
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = str(result.stdout or "").strip()
    if not raw or raw.lower() == "null":
        return None
    try:
        return _normalize_pages_custom_domain(raw)
    except ValueError:
        return None


def _prompt_custom_pages_domain(repo: str) -> Tuple[bool, Optional[str]]:
    existing = _get_pages_custom_domain(repo)

    print("\nOptional: set a custom dashboard domain (example: strava.example.com).")
    default_choice = "n"
    use_custom = _prompt_choice(
        "Use a custom dashboard domain? [y/n] (default: n): ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default=default_choice,
        invalid_message="Please enter 'y' or 'n'.",
    )
    if use_custom != "yes":
        if existing:
            clear_choice = _prompt_choice(
                f"Clear existing custom domain '{existing}'? [y/n]: ",
                {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
                default="y",
                invalid_message="Please enter 'y' or 'n'.",
            )
            if clear_choice == "yes":
                return True, None
        return False, None

    while True:
        if existing:
            response = input(
                f"Custom domain host (press Enter to keep '{existing}'): "
            ).strip()
            if not response:
                return True, existing
        else:
            response = input("Custom domain host (for example strava.example.com): ").strip()
            if not response:
                print("Please enter a domain host, or choose 'n' in the previous prompt.")
                continue

        try:
            return True, _normalize_pages_custom_domain(response)
        except ValueError as exc:
            print(f"Invalid custom domain: {exc}")


def _resolve_custom_pages_domain(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
) -> Tuple[bool, Optional[str]]:
    if bool(getattr(args, "clear_custom_domain", False)):
        return True, None

    explicit = getattr(args, "custom_domain", None)
    if explicit is not None:
        explicit_text = str(explicit).strip()
        if not explicit_text:
            return True, None
        return True, _normalize_pages_custom_domain(explicit_text)

    if not interactive:
        return False, None

    return _prompt_custom_pages_domain(repo)


def _prompt_choice(
    prompt: str,
    choices: dict[str, str],
    default: Optional[str] = None,
    invalid_message: Optional[str] = None,
) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            if default is not None:
                answer = default
            else:
                if invalid_message:
                    print(invalid_message)
                else:
                    allowed = ", ".join(sorted(choices.keys()))
                    print(f"Please enter one of: {allowed}")
                continue
        if answer in choices:
            return choices[answer]
        if invalid_message:
            print(invalid_message)
        else:
            allowed = ", ".join(sorted(choices.keys()))
            print(f"Please enter one of: {allowed}")


def _prompt_source() -> str:
    print("\nChoose activity source:")
    print("  1) Strava")
    print("  2) Garmin")
    selected = _prompt_choice(
        "Selection (enter 1 or 2): ",
        {"1": "strava", "2": "garmin"},
        default=None,
        invalid_message="Please enter '1' or '2'.",
    )
    return selected


def _resolve_source(
    args: argparse.Namespace,
    interactive: bool,
    previous_source: Optional[str] = None,
) -> str:
    if args.source:
        return args.source
    if interactive:
        return _prompt_source()
    if previous_source in {"strava", "garmin"}:
        return previous_source
    return DEFAULT_SOURCE


def _normalize_provider_profile_url(value: Optional[str], source: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = f"https://{raw.lstrip('/')}"
    parsed = urllib.parse.urlparse(raw)
    host = str(parsed.hostname or "").lower()
    normalized_source = str(source or "").strip().lower()

    if normalized_source == "strava":
        if not host or not STRAVA_HOST_RE.search(host):
            raise ValueError("Strava profile URL must use a strava.com hostname.")
        path_error = "Strava profile URL must include a profile path (for example /athletes/<id>)."
        normalized_path = str(parsed.path or "").strip().rstrip("/") or "/"
        if not normalized_path or normalized_path == "/":
            raise ValueError(path_error)
    elif normalized_source == "garmin":
        if not host or not GARMIN_CONNECT_HOST_RE.search(host):
            raise ValueError("Garmin profile URL must use a connect.garmin.com hostname.")
        path_error = "Garmin profile URL must include a profile path (for example /modern/profile/<id>)."
        path = str(parsed.path or "").strip()
        match = re.match(r"^/(?:modern/)?profile/([^/]+)(?:/.*)?$", path, flags=re.IGNORECASE)
        if not match:
            raise ValueError(path_error)
        normalized_path = f"/modern/profile/{match.group(1)}"
    else:
        raise ValueError(f"Unsupported source for profile URL normalization: {source!r}")

    normalized = urllib.parse.urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            normalized_path,
            "",
            parsed.query,
            "",
        )
    )
    return normalized


def _normalize_strava_profile_url(value: Optional[str]) -> str:
    return _normalize_provider_profile_url(value, "strava")


def _normalize_garmin_profile_url(value: Optional[str]) -> str:
    return _normalize_provider_profile_url(value, "garmin")


def _strava_profile_url_from_athlete(athlete: object) -> str:
    if not isinstance(athlete, dict):
        return ""
    athlete_id = athlete.get("id")
    if athlete_id is None:
        return ""
    athlete_id_text = str(athlete_id).strip()
    if not athlete_id_text:
        return ""
    return f"https://www.strava.com/athletes/{athlete_id_text}"


def _fetch_strava_athlete(access_token: str) -> dict:
    token = str(access_token or "").strip()
    if not token:
        return {}
    request = urllib.request.Request(
        STRAVA_ATHLETE_ENDPOINT,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except Exception:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _detect_strava_profile_url(tokens: dict) -> str:
    token_payload = tokens if isinstance(tokens, dict) else {}
    detected = _strava_profile_url_from_athlete(token_payload.get("athlete"))
    if detected:
        return detected

    access_token = str(token_payload.get("access_token") or "").strip()
    if not access_token:
        return ""
    athlete = _fetch_strava_athlete(access_token)
    return _strava_profile_url_from_athlete(athlete)


def _garmin_profile_url_from_profile(profile: object) -> str:
    if not isinstance(profile, dict):
        return ""

    direct_candidate_fields = (
        "displayName",
        "display_name",
        "profileId",
        "profile_id",
        "id",
        "userProfilePk",
        "userId",
        "user_id",
        "userName",
        "user_name",
    )
    nested_candidate_roots = (
        "profile",
        "userData",
    )

    candidate_values: list[object] = []
    for key in direct_candidate_fields:
        candidate_values.append(profile.get(key))
    for root in nested_candidate_roots:
        nested = profile.get(root)
        if isinstance(nested, dict):
            for key in direct_candidate_fields:
                candidate_values.append(nested.get(key))

    for value in candidate_values:
        if value in (None, ""):
            continue
        profile_id = str(value).strip()
        if not profile_id:
            continue
        encoded_id = urllib.parse.quote(profile_id, safe="")
        if encoded_id:
            return f"https://connect.garmin.com/modern/profile/{encoded_id}"
    return ""


def _coerce_garmin_profile_payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}

    payload: dict[str, object] = {}
    field_aliases = (
        ("displayName", "displayName"),
        ("display_name", "displayName"),
        ("profileId", "profileId"),
        ("profile_id", "profileId"),
        ("id", "id"),
        ("userProfilePk", "userProfilePk"),
        ("userId", "userId"),
        ("user_id", "userId"),
        ("userName", "userName"),
        ("user_name", "userName"),
        ("fullName", "fullName"),
        ("full_name", "fullName"),
    )
    for source_attr, target_key in field_aliases:
        attr_value = getattr(value, source_attr, None)
        if attr_value in (None, ""):
            continue
        payload[target_key] = attr_value
    return payload


def _fetch_garmin_profile(
    *,
    token_store_b64: str,
    email: str,
    password: str,
) -> dict:
    try:
        import garth
    except ImportError:
        return {}

    token_value = str(token_store_b64 or "").strip()
    email_value = str(email or "").strip()
    password_value = str(password or "").strip()

    with tempfile.TemporaryDirectory(prefix="garmin-profile-") as tmpdir:
        token_store_dir = os.path.join(tmpdir, "token_store")
        resumed = False
        if token_value:
            try:
                token_bytes = decode_token_store_b64(token_value)
                write_token_store_bytes(token_bytes, token_store_dir)
                if token_store_ready(token_store_dir):
                    garth.resume(token_store_dir)
                    resumed = True
            except Exception:
                resumed = False

        if not resumed:
            if not email_value or not password_value:
                return {}
            try:
                garth.login(email_value, password_value)
            except Exception:
                return {}

        profile_candidates: list[dict] = []

        def _add_profile_candidate(candidate: object) -> bool:
            payload = _coerce_garmin_profile_payload(candidate)
            if not payload:
                return False
            profile_candidates.append(payload)
            return bool(_garmin_profile_url_from_profile(payload))

        garth_client = getattr(garth, "client", None)
        if garth_client is not None:
            try:
                if _add_profile_candidate(getattr(garth_client, "profile", None)):
                    return profile_candidates[-1]
            except Exception:
                pass

        user_profile_cls = getattr(garth, "UserProfile", None)
        if user_profile_cls is not None and hasattr(user_profile_cls, "get"):
            try:
                if _add_profile_candidate(user_profile_cls.get()):
                    return profile_candidates[-1]
            except Exception:
                pass

        for path in (
            "/userprofile-service/socialProfile",
            "/userprofile-service/userprofile/profile",
        ):
            try:
                if _add_profile_candidate(garth.connectapi(path)):
                    return profile_candidates[-1]
            except Exception:
                continue

        # Fallback to Garmin wrapper session helpers used by sync path.
        try:
            from garminconnect import Garmin
        except Exception:
            Garmin = None  # type: ignore[assignment]

        if Garmin:
            clients = []
            for factory in (
                (lambda: Garmin(email=email_value, password=password_value)),
                (lambda: Garmin(email_value, password_value)),
                (lambda: Garmin()),
            ):
                try:
                    clients.append(factory())
                except Exception:
                    continue
            for client in clients:
                login_ok = False
                for login_attempt in (
                    (lambda: client.login(tokenstore=token_store_dir)),
                    (lambda: client.login(token_store=token_store_dir)),
                    (lambda: client.login(token_store_dir)),
                    (lambda: client.login(email_value, password_value)),
                    (lambda: client.login(email=email_value, password=password_value)),
                    (lambda: client.login()),
                ):
                    try:
                        login_attempt()
                        login_ok = True
                        break
                    except TypeError:
                        continue
                    except Exception:
                        continue
                if not login_ok:
                    continue

                display_name = getattr(client, "display_name", None)
                if _add_profile_candidate({"displayName": display_name}):
                    return profile_candidates[-1]
                garth_client_obj = getattr(client, "garth", None)
                if garth_client_obj is not None:
                    try:
                        if _add_profile_candidate(getattr(garth_client_obj, "profile", None)):
                            return profile_candidates[-1]
                    except Exception:
                        pass
                for path in (
                    "/userprofile-service/socialProfile",
                    "/userprofile-service/userprofile/profile",
                ):
                    connectapi = getattr(client, "connectapi", None)
                    if not callable(connectapi):
                        continue
                    try:
                        if _add_profile_candidate(connectapi(path)):
                            return profile_candidates[-1]
                    except Exception:
                        continue

    return {}


def _detect_garmin_profile_url(
    *,
    token_store_b64: str,
    email: str,
    password: str,
) -> str:
    profile = _fetch_garmin_profile(
        token_store_b64=token_store_b64,
        email=email,
        password=password,
    )
    return _garmin_profile_url_from_profile(profile)


def _prompt_use_strava_profile_link(default_enabled: bool) -> bool:
    print("\nOptional: show your Strava profile link in the dashboard header.")
    default_choice = "y" if default_enabled else "n"
    choice = _prompt_choice(
        "Show Strava profile link in dashboard? [y/n]: ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default=default_choice,
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _prompt_use_strava_activity_links(default_enabled: bool) -> bool:
    print("\nOptional: include links to Strava activities in yearly heatmap tooltips.")
    print("Desktop tip: click a heatmap dot to pin the tooltip so links are clickable.")
    default_choice = "y" if default_enabled else "n"
    choice = _prompt_choice(
        "Show Strava activity links in tooltip details? [y/n]: ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default=default_choice,
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _prompt_use_garmin_profile_link(default_enabled: bool) -> bool:
    print("\nOptional: show your Garmin profile link in the dashboard header.")
    default_choice = "y" if default_enabled else "n"
    choice = _prompt_choice(
        "Show Garmin profile link in dashboard? [y/n]: ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default=default_choice,
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _prompt_use_garmin_activity_links(default_enabled: bool) -> bool:
    print("\nOptional: include links to Garmin activities in yearly heatmap tooltips.")
    print("Desktop tip: click a heatmap dot to pin the tooltip so links are clickable.")
    default_choice = "y" if default_enabled else "n"
    choice = _prompt_choice(
        "Show Garmin activity links in tooltip details? [y/n]: ",
        {"y": "yes", "yes": "yes", "n": "no", "no": "no"},
        default=default_choice,
        invalid_message="Please enter 'y' or 'n'.",
    )
    return choice == "yes"


def _resolve_strava_profile_url(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
    tokens: Optional[dict] = None,
    *,
    enabled_override: Optional[bool] = None,
    prefilled_url: str = "",
    prompt_if_missing: bool = True,
) -> str:
    explicit = getattr(args, "strava_profile_url", None)
    if explicit is not None:
        explicit_text = str(explicit).strip()
        if not explicit_text:
            return ""
        return _normalize_strava_profile_url(explicit_text)

    detected = _normalize_strava_profile_url(_detect_strava_profile_url(tokens or {}))

    existing_raw = _get_variable("DASHBOARD_STRAVA_PROFILE_URL", repo)
    try:
        existing_value = _normalize_strava_profile_url(existing_raw)
    except ValueError:
        existing_value = ""

    try:
        prefilled_value = _normalize_strava_profile_url(prefilled_url)
    except ValueError:
        prefilled_value = ""

    candidate = detected or prefilled_value or existing_value
    if enabled_override is not None:
        if not enabled_override:
            return ""
        if candidate:
            return candidate
        return ""

    if interactive:
        enabled = _prompt_use_strava_profile_link(default_enabled=bool(candidate))
        if not enabled:
            return ""
        if candidate:
            return candidate
        return ""

    return candidate


def _resolve_garmin_profile_url(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
    *,
    token_store_b64: str,
    email: str,
    password: str,
    enabled_override: Optional[bool] = None,
    prefilled_url: str = "",
    prompt_if_missing: bool = True,
) -> str:
    explicit = getattr(args, "garmin_profile_url", None)
    if explicit is not None:
        explicit_text = str(explicit).strip()
        if not explicit_text:
            return ""
        return _normalize_garmin_profile_url(explicit_text)

    detected = ""
    if token_store_b64 or (email and password):
        detected = _normalize_garmin_profile_url(
            _detect_garmin_profile_url(
                token_store_b64=token_store_b64,
                email=email,
                password=password,
            )
        )

    existing_raw = _get_variable("DASHBOARD_GARMIN_PROFILE_URL", repo)
    try:
        existing_value = _normalize_garmin_profile_url(existing_raw)
    except ValueError:
        existing_value = ""

    try:
        prefilled_value = _normalize_garmin_profile_url(prefilled_url)
    except ValueError:
        prefilled_value = ""

    candidate = detected or prefilled_value or existing_value
    if enabled_override is not None:
        if not enabled_override:
            return ""
        if candidate:
            return candidate
        return ""

    if interactive:
        enabled = _prompt_use_garmin_profile_link(default_enabled=bool(candidate))
        if not enabled:
            return ""
        if candidate:
            return candidate
        return ""

    return candidate


def _resolve_strava_profile_link_preference(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
) -> Tuple[Optional[bool], str]:
    explicit = getattr(args, "strava_profile_url", None)
    if explicit is not None:
        explicit_text = str(explicit).strip()
        if not explicit_text:
            return False, ""
        return True, _normalize_strava_profile_url(explicit_text)

    existing_raw = _get_variable("DASHBOARD_STRAVA_PROFILE_URL", repo)
    try:
        existing_value = _normalize_strava_profile_url(existing_raw)
    except ValueError:
        existing_value = ""

    if not interactive:
        return None, existing_value

    enabled = _prompt_use_strava_profile_link(default_enabled=bool(existing_value))
    if not enabled:
        return False, ""
    if existing_value:
        return True, existing_value
    return True, ""


def _resolve_garmin_profile_link_preference(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
) -> Tuple[Optional[bool], str]:
    explicit = getattr(args, "garmin_profile_url", None)
    if explicit is not None:
        explicit_text = str(explicit).strip()
        if not explicit_text:
            return False, ""
        return True, _normalize_garmin_profile_url(explicit_text)

    existing_raw = _get_variable("DASHBOARD_GARMIN_PROFILE_URL", repo)
    try:
        existing_value = _normalize_garmin_profile_url(existing_raw)
    except ValueError:
        existing_value = ""

    if not interactive:
        return None, existing_value

    enabled = _prompt_use_garmin_profile_link(default_enabled=bool(existing_value))
    if not enabled:
        return False, ""
    if existing_value:
        return True, existing_value
    return True, ""


def _resolve_strava_activity_links(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
) -> bool:
    explicit = getattr(args, "strava_activity_links", None)
    if explicit is not None:
        return _parse_bool_text(explicit, field_name="--strava-activity-links")

    existing = _existing_dashboard_strava_activity_links(repo)
    if interactive:
        return _prompt_use_strava_activity_links(default_enabled=bool(existing))
    return bool(existing)


def _resolve_garmin_activity_links(
    args: argparse.Namespace,
    interactive: bool,
    repo: str,
) -> bool:
    explicit = getattr(args, "garmin_activity_links", None)
    if explicit is not None:
        return _parse_bool_text(explicit, field_name="--garmin-activity-links")

    existing = _existing_dashboard_garmin_activity_links(repo)
    if interactive:
        return _prompt_use_garmin_activity_links(default_enabled=bool(existing))
    return bool(existing)


def _iter_exception_chain(exc: Exception) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None:
        current_id = id(current)
        if current_id in seen:
            break
        seen.add(current_id)
        yield current
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None


def _extract_http_status_code(exc: Exception) -> Optional[int]:
    for item in _iter_exception_chain(exc):
        for attr in ("status_code", "status"):
            value = getattr(item, attr, None)
            if isinstance(value, int):
                return value
        response = getattr(item, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def _extract_http_url(exc: Exception) -> str:
    for item in _iter_exception_chain(exc):
        response = getattr(item, "response", None)
        url = getattr(response, "url", None)
        if isinstance(url, str) and url:
            return url
        request = getattr(item, "request", None)
        url = getattr(request, "url", None)
        if isinstance(url, str) and url:
            return url
    return ""


def _extract_retry_after_seconds(exc: Exception) -> Optional[int]:
    for item in _iter_exception_chain(exc):
        response = getattr(item, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            continue

        retry_after: Optional[str] = None
        if hasattr(headers, "get"):
            value = headers.get("Retry-After")
            retry_after = str(value) if value is not None else None
        elif isinstance(headers, dict):
            value = headers.get("Retry-After")
            retry_after = str(value) if value is not None else None

        if not retry_after:
            continue
        retry_after = retry_after.strip()
        if not retry_after:
            continue

        try:
            seconds = int(retry_after)
            return max(0, seconds)
        except ValueError:
            pass

        try:
            dt = parsedate_to_datetime(retry_after)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = int((dt - datetime.now(timezone.utc)).total_seconds())
            return max(0, delta)
        except Exception:
            continue

    return None


def _compute_retry_delay_seconds(exc: Exception, attempt: int) -> float:
    base_delay = min(20.0, float(2 * attempt))
    retry_after = _extract_retry_after_seconds(exc)
    if retry_after is not None:
        base_delay = max(base_delay, float(retry_after))
    jitter = random.uniform(0.0, 0.75)
    return min(60.0, base_delay + jitter)


def _is_retryable_garmin_auth_error(exc: Exception) -> bool:
    status = _extract_http_status_code(exc)
    url = _extract_http_url(exc).lower()
    text = str(exc).lower()

    if status == 429:
        return True
    if status in {500, 502, 503, 504}:
        return True
    if status == 401 and ("sso.garmin.com/sso/signin" in url or "sso.garmin.com/sso/signin" in text):
        return True

    transient_tokens = [
        "429 client error",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "timed out",
        "timeout",
    ]
    return any(token in text for token in transient_tokens)


def _generate_garmin_token_store_b64(email: str, password: str) -> str:
    try:
        import garth
    except ImportError:
        raise RuntimeError(
            "Missing Garmin auth dependency 'garth'. Re-run setup without --no-bootstrap-env."
        ) from None

    last_error: Optional[Exception] = None
    for attempt in range(1, GARMIN_AUTH_MAX_ATTEMPTS + 1):
        with tempfile.TemporaryDirectory(prefix="garmin-token-store-") as tmpdir:
            try:
                garth.login(email, password)
                save_errors: list[str] = []
                try:
                    garth.save(tmpdir)
                except Exception as exc:
                    save_errors.append(str(exc))

                if not token_store_ready(tmpdir):
                    legacy_path = os.path.join(tmpdir, "garth-session.json")
                    try:
                        garth.save(legacy_path)
                    except Exception as exc:
                        save_errors.append(str(exc))
                    hydrate_token_store_from_legacy_file(legacy_path, tmpdir)

                if not token_store_ready(tmpdir):
                    details = "; ".join(save_errors) if save_errors else "unknown save failure"
                    raise RuntimeError(
                        "garth token store is incomplete (expected oauth1_token.json and oauth2_token.json). "
                        f"Save details: {details}"
                    )

                if hasattr(garth, "resume"):
                    try:
                        garth.resume(tmpdir)
                    except Exception as exc:
                        raise RuntimeError(
                            f"garth token store failed resume validation: {exc}"
                        ) from exc

                return encode_token_store_dir_as_zip_b64(tmpdir)
            except Exception as exc:
                last_error = exc
                if attempt >= GARMIN_AUTH_MAX_ATTEMPTS or not _is_retryable_garmin_auth_error(exc):
                    break
                delay_seconds = _compute_retry_delay_seconds(exc, attempt)
                print(
                    "Garmin authentication failed with a transient error; "
                    f"retrying in {delay_seconds:.1f}s ({attempt}/{GARMIN_AUTH_MAX_ATTEMPTS})..."
                )
                time.sleep(delay_seconds)

    detail = str(last_error) if last_error else "unknown Garmin authentication failure"
    raise RuntimeError(
        f"Unable to generate GARMIN_TOKENS_B64 from provided Garmin credentials: {detail}"
    ) from None


def _prompt_units() -> Tuple[str, str]:
    print("\nChoose unit system:")
    print("  1) US (miles + feet)")
    print("  2) Metric (km + meters)")
    system = _prompt_choice(
        "Selection (enter 1 or 2): ",
        {"1": "us", "2": "metric"},
        default=None,
        invalid_message="Please enter '1' or '2'.",
    )
    return UNIT_PRESETS[system]


def _prompt_week_start(default_week_start: str) -> str:
    default_normalized = _normalize_week_start(default_week_start)
    default_choice = "1" if default_normalized == "sunday" else "2"
    print("\nChoose heatmap week start (top row in yearly cards):")
    print("  1) Sunday")
    print("  2) Monday")
    selected = _prompt_choice(
        f"Selection (enter 1 or 2) (default: {default_choice}): ",
        {"1": "sunday", "2": "monday"},
        default=default_choice,
        invalid_message="Please enter '1' or '2'.",
    )
    return selected


def _resolve_week_start(args: argparse.Namespace, interactive: bool, repo: str) -> str:
    explicit = getattr(args, "week_start", None)
    if explicit:
        return _normalize_week_start(explicit)

    existing = _existing_dashboard_week_start(repo)
    if interactive:
        return _prompt_week_start(DEFAULT_WEEK_START)

    return existing or DEFAULT_WEEK_START


def _resolve_garmin_auth_values(args: argparse.Namespace, interactive: bool) -> Tuple[str, str, str]:
    token_store_b64 = (args.garmin_token_store_b64 or "").strip()
    email = (args.garmin_email or "").strip()
    password = (args.garmin_password or "").strip()

    if not token_store_b64:
        if not email:
            if interactive:
                email = _prompt(None, "GARMIN_EMAIL")
            else:
                raise RuntimeError(
                    "Missing Garmin credentials in non-interactive mode. "
                    "Provide --garmin-token-store-b64 or --garmin-email/--garmin-password."
                )
        if not password:
            if interactive:
                password = _prompt(None, "GARMIN_PASSWORD", secret=True)
            else:
                raise RuntimeError(
                    "Missing Garmin credentials in non-interactive mode. "
                    "Provide --garmin-token-store-b64 or --garmin-email/--garmin-password."
                )
        print("Generating GARMIN_TOKENS_B64 from Garmin credentials...")
        token_store_b64 = _generate_garmin_token_store_b64(email, password)

    return token_store_b64, email, password


def _resolve_units(args: argparse.Namespace, interactive: bool) -> Tuple[str, str]:
    if args.unit_system:
        return UNIT_PRESETS[args.unit_system]

    if interactive:
        return _prompt_units()

    raise RuntimeError(
        "Missing unit selection in non-interactive mode. "
        "Provide --unit-system {us|metric}."
    )


def _add_step(
    steps: list[StepResult],
    name: str,
    status: str,
    detail: str,
    manual_help: Optional[str] = None,
) -> None:
    steps.append(StepResult(name=name, status=status, detail=detail, manual_help=manual_help))


def _try_enable_actions_permissions(repo: str) -> Tuple[bool, str]:
    def _current_permissions() -> Tuple[Optional[bool], Optional[str]]:
        result = _run(
            ["gh", "api", f"repos/{repo}/actions/permissions"],
            check=False,
        )
        if result.returncode != 0:
            return None, None
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return None, None
        enabled = payload.get("enabled")
        allowed_actions = payload.get("allowed_actions")
        return enabled if isinstance(enabled, bool) else None, (
            str(allowed_actions) if isinstance(allowed_actions, str) else None
        )

    errors: list[str] = []
    attempts = [
        [
            "gh",
            "api",
            "-X",
            "PUT",
            f"repos/{repo}/actions/permissions",
            "-F",
            "enabled=true",
            "-f",
            "allowed_actions=all",
        ],
        [
            "gh",
            "api",
            "-X",
            "PUT",
            f"repos/{repo}/actions/permissions",
            "-F",
            "enabled=true",
        ],
    ]
    for cmd in attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0:
            enabled, allowed_actions = _current_permissions()
            if enabled:
                if allowed_actions:
                    return (
                        True,
                        f"Repository Actions are enabled (allowed_actions={allowed_actions}).",
                    )
                return True, "Repository Actions permissions configured."
            return True, "Repository Actions permissions configured."
        errors.append(_first_stderr_line(result.stderr))

    enabled, allowed_actions = _current_permissions()
    if enabled:
        if allowed_actions:
            return (
                True,
                (
                    "Repository Actions are already enabled "
                    f"(allowed_actions={allowed_actions}); API update was not required."
                ),
            )
        return True, "Repository Actions are already enabled; API update was not required."

    if errors:
        # Deduplicate while preserving order for concise summaries.
        ordered_unique = list(dict.fromkeys(errors))
        return False, "; ".join(ordered_unique)
    return False, "Unable to configure repository Actions permissions automatically."


def _repo_has_issues_enabled(repo: str) -> Optional[bool]:
    result = _run(["gh", "api", f"repos/{repo}", "--jq", ".has_issues"], check=False)
    if result.returncode != 0:
        return None
    value = str(result.stdout or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _try_enable_repo_issues(repo: str) -> Tuple[bool, str]:
    current = _repo_has_issues_enabled(repo)
    if current is True:
        return True, "Repository Issues are already enabled."

    errors: list[str] = []
    attempts = [
        ["gh", "api", "-X", "PATCH", f"repos/{repo}", "-F", "has_issues=true"],
        ["gh", "api", "-X", "PATCH", f"repos/{repo}", "-f", "has_issues=true"],
    ]
    for cmd in attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0 and _repo_has_issues_enabled(repo) is True:
            return True, "Repository Issues are enabled."
        if result.returncode != 0:
            errors.append(_first_stderr_line(result.stderr))

    final_state = _repo_has_issues_enabled(repo)
    if final_state is True:
        return True, "Repository Issues are enabled."

    if errors:
        ordered_unique = list(dict.fromkeys(errors))
        return False, "; ".join(ordered_unique)
    return False, "Unable to enable repository Issues automatically."


def _repo_default_branch(repo: str) -> str:
    result = _run(["gh", "api", f"repos/{repo}", "--jq", ".default_branch"], check=False)
    if result.returncode != 0:
        return "main"
    value = str(result.stdout or "").strip()
    return value or "main"


def _workflow_file_exists(repo: str, workflow: str, branch: str) -> bool:
    endpoint = f"repos/{repo}/contents/.github/workflows/{workflow}"
    result = _run(["gh", "api", endpoint, "-f", f"ref={branch}"], check=False)
    return result.returncode == 0


def _repo_has_commits(repo: str) -> bool:
    result = _run(["gh", "api", f"repos/{repo}/commits?per_page=1"], check=False)
    if result.returncode == 0:
        return True
    error_text = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    if "git repository is empty" in error_text:
        return False
    if "http 409" in error_text and "empty" in error_text:
        return False
    return True


def _try_seed_missing_workflow_files(
    repo: str,
    workflows: list[str],
    source_repo: str,
) -> Tuple[bool, str]:
    source = _normalize_repo_slug(source_repo)
    if not source:
        return False, "Template source repository is invalid."
    if source == repo:
        return False, "Template source repository matches destination; cannot auto-seed workflows."

    default_branch = _repo_default_branch(repo)
    missing = [workflow for workflow in workflows if not _workflow_file_exists(repo, workflow, default_branch)]
    if not missing:
        return True, "Workflow files already exist on the default branch."

    if _repo_has_commits(repo):
        return (
            False,
            (
                "Workflow files are missing on the default branch and the repository is not empty. "
                "Automatic template sync was skipped to avoid overwriting existing content."
            ),
        )

    source_branch = _repo_default_branch(source)

    sync_attempts = [
        ["gh", "repo", "sync", repo, "--source", source, "--branch", default_branch, "--force"],
        ["gh", "repo", "sync", repo, "--source", source, "--force"],
    ]
    sync_error = "Unable to sync destination repository from template source."
    for cmd in sync_attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0:
            return (
                True,
                f"Seeded empty repository from {source} so workflows are available on {default_branch}.",
            )
        sync_error = _first_stderr_line(result.stderr)

    seeded_via_git, git_seed_detail = _try_seed_empty_repo_via_git_push(
        repo=repo,
        source_repo=source,
        source_branch=source_branch,
        destination_branch=default_branch,
    )
    if seeded_via_git:
        return (
            True,
            (
                f"Seeded empty repository from {source} via authenticated git push after sync fallback failed "
                f"({sync_error})."
            ),
        )

    return False, f"Could not sync empty repository from {source}: {sync_error}; {git_seed_detail}"


def _try_seed_empty_repo_via_git_push(
    *,
    repo: str,
    source_repo: str,
    source_branch: str,
    destination_branch: str,
) -> Tuple[bool, str]:
    if shutil.which("git") is None:
        return False, "git is required to seed empty repositories when workflow sync fallback is needed."

    token = _gh_auth_token()
    if not token:
        return False, "Unable to read gh auth token for authenticated git push fallback."
    encoded_token = urllib.parse.quote(token, safe="")

    def _redact_git_error(text: str) -> str:
        redacted = text or ""
        for secret in (token, encoded_token):
            if secret:
                redacted = redacted.replace(secret, "***")
        return redacted

    tmpdir = tempfile.mkdtemp(prefix="git-sweaty-seed-")
    clone_dir = os.path.join(tmpdir, "template")
    try:
        clone_result = _run(
            [
                "git",
                "clone",
                "--branch",
                source_branch,
                f"https://github.com/{source_repo}.git",
                clone_dir,
            ],
            check=False,
        )
        if clone_result.returncode != 0:
            return False, f"Could not clone template repository {source_repo}: {_first_stderr_line(clone_result.stderr)}"

        push_setup_error: Optional[str] = None
        setup_git_result = _run(["gh", "auth", "setup-git"], check=False)
        push_commands: list[list[str]] = []
        if setup_git_result.returncode == 0:
            push_commands.extend(
                [
                    [
                        "git",
                        "-C",
                        clone_dir,
                        "push",
                        f"https://github.com/{repo}.git",
                        f"HEAD:{destination_branch}",
                    ],
                    [
                        "git",
                        "-C",
                        clone_dir,
                        "push",
                        f"https://github.com/{repo}.git",
                        f"HEAD:{destination_branch}",
                        "--force",
                    ],
                ]
            )
        else:
            push_setup_error = _first_stderr_line(_redact_git_error(setup_git_result.stderr))

        push_commands.extend(
            [
            [
                "git",
                "-C",
                clone_dir,
                "push",
                f"https://x-access-token:{encoded_token}@github.com/{repo}.git",
                f"HEAD:{destination_branch}",
            ],
            [
                "git",
                "-C",
                clone_dir,
                "push",
                f"https://x-access-token:{encoded_token}@github.com/{repo}.git",
                f"HEAD:{destination_branch}",
                "--force",
            ],
            ]
        )

        push_errors: list[str] = []
        for push_cmd in push_commands:
            push_result = _run(push_cmd, check=False)
            if push_result.returncode == 0:
                return True, f"Seeded empty repository from {source_repo} via authenticated git push."
            push_errors.append(_first_stderr_line(_redact_git_error(push_result.stderr)))

        details = list(dict.fromkeys(error for error in push_errors if error))
        if push_setup_error:
            details.insert(0, f"gh auth setup-git failed: {push_setup_error}")
        detail_text = "; ".join(details) if details else "Unknown push failure."
        return (
            False,
            "Could not push template branch to destination repository via authenticated git fallback: "
            f"{detail_text}"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _try_enable_workflows(
    repo: str,
    workflows: list[str],
    *,
    source_repo: str = DEFAULT_TEMPLATE_REPO,
) -> Tuple[bool, str]:
    def _all_not_found(enable_failures: list[str]) -> bool:
        if not enable_failures:
            return False
        return all("workflow" in entry.lower() and "not found" in entry.lower() for entry in enable_failures)

    def _attempt_enable() -> list[str]:
        failures: list[str] = []
        for workflow in workflows:
            result = _run(
                ["gh", "workflow", "enable", workflow, "--repo", repo],
                check=False,
            )
            if result.returncode != 0:
                failures.append(f"{workflow}: {_first_stderr_line(result.stderr)}")
        return failures

    failures = _attempt_enable()
    if not failures:
        return True, "sync.yml and pages.yml are enabled."

    if _all_not_found(failures):
        seeded, seed_detail = _try_seed_missing_workflow_files(repo, workflows, source_repo)
        if seeded:
            retry_failures = _attempt_enable()
            retry_count = 0
            max_retries = 6
            while retry_failures and _all_not_found(retry_failures) and retry_count < max_retries:
                retry_count += 1
                time.sleep(2)
                retry_failures = _attempt_enable()
            if not retry_failures:
                return True, f"sync.yml and pages.yml are enabled. {seed_detail}"
            return False, f"{seed_detail}; {'; '.join(retry_failures)}"
        return False, f"{'; '.join(failures)}; {seed_detail}"

    return False, "; ".join(failures)


def _resolve_template_repo(value: Optional[str]) -> str:
    explicit = _normalize_repo_slug(value)
    if explicit:
        return explicit
    env_value = _normalize_repo_slug(os.environ.get("GIT_SWEATY_UPSTREAM_REPO"))
    if env_value:
        return env_value
    return DEFAULT_TEMPLATE_REPO


def _get_pages_build_type(repo: str) -> Optional[str]:
    result = _run(
        ["gh", "api", f"repos/{repo}/pages", "--jq", ".build_type"],
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    return value if value else None


def _try_configure_pages(repo: str) -> Tuple[bool, str]:
    current = _get_pages_build_type(repo)
    if current == "workflow":
        return True, "GitHub Pages already configured for GitHub Actions."

    attempts = [
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", "build_type=workflow"],
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "build_type=workflow"],
    ]
    errors = []
    for cmd in attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0 and _get_pages_build_type(repo) == "workflow":
            return True, "GitHub Pages configured to deploy from GitHub Actions."
        if result.returncode != 0:
            errors.append(_first_stderr_line(result.stderr))

    final_build_type = _get_pages_build_type(repo)
    if final_build_type == "workflow":
        return True, "GitHub Pages configured to deploy from GitHub Actions."

    if errors:
        return False, "; ".join(errors)
    return False, "Unable to configure GitHub Pages build type automatically."


def _try_set_pages_custom_domain(repo: str, domain: str) -> Tuple[bool, str]:
    normalized = _normalize_pages_custom_domain(domain)
    current = _get_pages_custom_domain(repo)
    if current == normalized:
        return True, f"GitHub Pages custom domain already set to {normalized}."

    attempts = [
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", f"cname={normalized}", "-f", "build_type=workflow"],
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", f"cname={normalized}"],
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", f"cname={normalized}", "-f", "build_type=workflow"],
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", f"cname={normalized}"],
    ]
    errors = []
    for cmd in attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0:
            verified = _get_pages_custom_domain(repo)
            if verified == normalized:
                return True, f"GitHub Pages custom domain set to {normalized}."
            return (
                True,
                f"Requested custom domain {normalized}; verify DNS and Pages settings if it does not appear yet.",
            )
        errors.append(_first_stderr_line(result.stderr))

    final_domain = _get_pages_custom_domain(repo)
    if final_domain == normalized:
        return True, f"GitHub Pages custom domain set to {normalized}."

    if errors:
        return False, "; ".join(list(dict.fromkeys(errors)))
    return False, f"Unable to set custom domain {normalized} automatically."


def _try_clear_pages_custom_domain(repo: str) -> Tuple[bool, str]:
    current = _get_pages_custom_domain(repo)
    if not current:
        return True, "GitHub Pages custom domain is already unset."

    attempts = [
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", "cname=", "-f", "build_type=workflow"],
        ["gh", "api", "-X", "PUT", f"repos/{repo}/pages", "-f", "cname="],
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "cname=", "-f", "build_type=workflow"],
        ["gh", "api", "-X", "POST", f"repos/{repo}/pages", "-f", "cname="],
    ]
    errors = []
    for cmd in attempts:
        result = _run(cmd, check=False)
        if result.returncode == 0:
            verified = _get_pages_custom_domain(repo)
            if not verified:
                return True, "GitHub Pages custom domain cleared."
            return (
                True,
                (
                    "Requested custom domain removal; verify Pages settings if the previous domain "
                    f"({verified}) still appears."
                ),
            )
        errors.append(_first_stderr_line(result.stderr))

    final_domain = _get_pages_custom_domain(repo)
    if not final_domain:
        return True, "GitHub Pages custom domain cleared."

    if errors:
        return False, "; ".join(list(dict.fromkeys(errors)))
    return False, f"Unable to clear custom domain {final_domain} automatically."


def _try_dispatch_sync(repo: str, source: str, full_backfill: bool = False) -> Tuple[bool, str]:
    attempts: list[tuple[bool, bool]] = []
    if full_backfill:
        attempts.extend(
            [
                (True, True),
                (True, False),
                (False, True),
                (False, False),
            ]
        )
    else:
        attempts.extend([(True, False), (False, False)])

    seen: set[tuple[bool, bool]] = set()
    ordered_attempts = []
    for attempt in attempts:
        if attempt in seen:
            continue
        seen.add(attempt)
        ordered_attempts.append(attempt)

    last_unexpected_input_error: Optional[str] = None
    for include_source, include_full_backfill in ordered_attempts:
        cmd = ["gh", "workflow", "run", "sync.yml", "--repo", repo]
        if include_source:
            cmd.extend(["-f", f"source={source}"])
        if include_full_backfill:
            cmd.extend(["-f", "full_backfill=true"])

        result = _run(cmd, check=False)
        if result.returncode == 0:
            if include_source and include_full_backfill:
                return (
                    True,
                    "Dispatched sync.yml via workflow_dispatch with source and full_backfill=true.",
                )
            if include_source and full_backfill:
                return (
                    True,
                    "Dispatched sync.yml via workflow_dispatch with source input; full_backfill input is not declared by this workflow.",
                )
            if include_full_backfill:
                return (
                    True,
                    "Dispatched sync.yml via workflow_dispatch with full_backfill=true; source input is not declared by this workflow.",
                )
            if include_source:
                return True, "Dispatched sync.yml via workflow_dispatch."
            return (
                True,
                "Dispatched sync.yml via workflow_dispatch (workflow does not declare 'source' input; using DASHBOARD_SOURCE variable/default).",
            )

        stderr_line = _first_stderr_line(result.stderr)
        if "Unexpected inputs provided" in stderr_line:
            last_unexpected_input_error = stderr_line
            continue
        return False, stderr_line

    if last_unexpected_input_error:
        return False, last_unexpected_input_error
    return False, "Unable to dispatch sync.yml via workflow_dispatch."


def _try_dispatch_pages(repo: str) -> Tuple[bool, str]:
    result = _run(["gh", "workflow", "run", "pages.yml", "--repo", repo], check=False)
    if result.returncode != 0:
        return False, _first_stderr_line(result.stderr)
    return True, "Dispatched pages.yml via workflow_dispatch."


def _watch_run(repo: str, run_id: int) -> Tuple[bool, str]:
    print(f"\nWatching workflow run {run_id}...")
    watch = subprocess.run(
        ["gh", "run", "watch", str(run_id), "--repo", repo, "--exit-status"],
        check=False,
    )
    if watch.returncode == 0:
        return True, "Workflow run completed (see output above)."
    return False, "Workflow run failed or could not be watched to completion."


def _find_latest_workflow_run(
    repo: str,
    workflow: str,
    event: str,
    not_before: datetime,
    poll_attempts: int = 45,
    sleep_seconds: int = 2,
    progress_label: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    time_skew_grace = timedelta(minutes=2)
    earliest_allowed = not_before - time_skew_grace

    def _pick_run(runs: object) -> Tuple[Optional[int], Optional[str]]:
        if not isinstance(runs, list):
            return None, None
        primary: list[tuple[datetime, int, Optional[str]]] = []
        fallback: list[tuple[datetime, int, Optional[str]]] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            created_at = _parse_iso8601_utc(str(run.get("createdAt", "")))
            run_id = run.get("databaseId")
            run_url = run.get("url")
            if created_at is None or not isinstance(run_id, int):
                continue
            if created_at >= not_before:
                primary.append((created_at, run_id, str(run_url) if run_url else None))
            elif created_at >= earliest_allowed:
                fallback.append((created_at, run_id, str(run_url) if run_url else None))
        if primary:
            primary.sort(key=lambda item: item[0], reverse=True)
            _, run_id, run_url = primary[0]
            return run_id, run_url
        if fallback:
            fallback.sort(key=lambda item: item[0], reverse=True)
            _, run_id, run_url = fallback[0]
            return run_id, run_url
        return None, None

    if progress_label:
        timeout_seconds = poll_attempts * sleep_seconds
        print(f"\nWaiting for {progress_label} (up to {timeout_seconds}s)...")
    for attempt in range(1, poll_attempts + 1):
        fields = "databaseId,url,createdAt"
        list_cmd = [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--limit",
            "30",
            "--json",
            fields,
        ]
        if event:
            list_cmd.extend(["--event", event])
        result = _run(list_cmd, check=False)
        if result.returncode == 0:
            try:
                runs = json.loads(result.stdout or "[]")
            except json.JSONDecodeError:
                runs = []
            run_id, run_url = _pick_run(runs)
            if run_id is not None:
                if progress_label:
                    print(f"Detected {progress_label}.")
                return run_id, run_url

        # Some environments report delayed/mismatched event classification for newly dispatched runs.
        # Fall back to scanning the same workflow without event filtering before giving up this poll.
        if event:
            fallback_result = _run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    repo,
                    "--workflow",
                    workflow,
                    "--limit",
                    "30",
                    "--json",
                    fields,
                ],
                check=False,
            )
            if fallback_result.returncode == 0:
                try:
                    fallback_runs = json.loads(fallback_result.stdout or "[]")
                except json.JSONDecodeError:
                    fallback_runs = []
                run_id, run_url = _pick_run(fallback_runs)
                if run_id is not None:
                    if progress_label:
                        print(f"Detected {progress_label}.")
                    return run_id, run_url
        if progress_label and (attempt == 1 or attempt % 5 == 0):
            print(f"Still waiting for {progress_label}... ({attempt}/{poll_attempts})")
        time.sleep(sleep_seconds)
    return None, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap provider auth and automate GitHub setup for this repository."
    )
    parser.add_argument(
        "--source",
        choices=["strava", "garmin"],
        default=None,
        help="Activity source to configure.",
    )
    parser.add_argument(
        "--no-bootstrap-env",
        action="store_true",
        help="Skip automatic local virtualenv bootstrap (.venv + requirements install).",
    )
    parser.add_argument(
        "--env-bootstrapped",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--client-id", default=None, help="Strava client ID.")
    parser.add_argument(
        "--client-secret",
        default=None,
        help="Strava client secret.",
    )
    parser.add_argument(
        "--garmin-token-store-b64",
        default=None,
        help="Garmin token store as base64 (optional; generated from email/password if omitted).",
    )
    parser.add_argument(
        "--garmin-email",
        default=None,
        help="Garmin account email (used to generate GARMIN_TOKENS_B64 when token is omitted).",
    )
    parser.add_argument(
        "--garmin-password",
        default=None,
        help="Garmin account password (used to generate GARMIN_TOKENS_B64 when token is omitted).",
    )
    parser.add_argument(
        "--store-garmin-password-secrets",
        action="store_true",
        help="Deprecated: GARMIN_EMAIL and GARMIN_PASSWORD are now stored automatically when provided.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional GitHub repo in OWNER/REPO form. If omitted, the script auto-detects it.",
    )
    parser.add_argument(
        "--template-repo",
        default=None,
        help=(
            "Template source repository used to seed empty targets when workflow files are missing "
            "(defaults to GIT_SWEATY_UPSTREAM_REPO or aspain/git-sweaty)."
        ),
    )
    parser.add_argument(
        "--unit-system",
        choices=["us", "metric"],
        default=None,
        help="Units preset for dashboard metrics.",
    )
    parser.add_argument(
        "--week-start",
        choices=["sunday", "monday"],
        default=None,
        help="Week start day for yearly heatmap y-axis labels.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local callback port.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for OAuth callback.",
    )
    parser.add_argument(
        "--scope",
        default="read,activity:read_all",
        help="Strava OAuth scopes.",
    )
    parser.add_argument(
        "--strava-profile-url",
        default=None,
        help="Optional Strava profile URL override shown in the dashboard header (auto-detected by default).",
    )
    parser.add_argument(
        "--strava-activity-links",
        choices=["yes", "no", "true", "false", "1", "0"],
        default=None,
        help="Whether to show Strava activity links in yearly heatmap tooltip details.",
    )
    parser.add_argument(
        "--garmin-profile-url",
        default=None,
        help="Optional Garmin profile URL override shown in the dashboard header (auto-detected by default).",
    )
    parser.add_argument(
        "--garmin-activity-links",
        choices=["yes", "no", "true", "false", "1", "0"],
        default=None,
        help="Whether to show Garmin activity links in yearly heatmap tooltip details.",
    )
    parser.add_argument(
        "--custom-domain",
        default=None,
        help="Optional custom GitHub Pages domain host (for example strava.example.com).",
    )
    parser.add_argument(
        "--clear-custom-domain",
        action="store_true",
        help="Clear existing GitHub Pages custom domain during setup.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser; print auth URL only.",
    )
    parser.add_argument(
        "--no-auto-github",
        action="store_true",
        help="Skip GitHub Pages/workflow automation after setting secrets and units.",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="Do not watch the first workflow run after dispatching it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _bootstrap_env_and_reexec(args)
    interactive = _isatty()

    if args.port < 1 or args.port > 65535:
        raise ValueError("--port must be between 1 and 65535.")
    if args.timeout <= 0:
        raise ValueError("--timeout must be a positive number of seconds.")

    _assert_gh_ready()

    repo = _resolve_repo_slug(args.repo)
    if not repo:
        if interactive:
            while True:
                response = input("GitHub repository (OWNER/REPO): ").strip()
                repo = _normalize_repo_slug(response)
                if repo:
                    break
                print("Please enter repository as OWNER/REPO.")
        else:
            raise RuntimeError(
                "Unable to determine repository in non-interactive mode. "
                "Re-run with --repo OWNER/REPO."
            )
    _assert_repo_access(repo)
    _assert_actions_secret_access(repo)
    print(f"Using repository: {repo}")
    template_repo = _resolve_template_repo(getattr(args, "template_repo", None))
    existing_settings = _load_existing_dashboard_settings(repo)
    previous_source = existing_settings.source if existing_settings else _existing_dashboard_source(repo)
    reuse_existing_settings = False
    explicit_setup_overrides = _has_explicit_setup_overrides(args)
    if interactive and not explicit_setup_overrides:
        if existing_settings is None:
            print("\nNo existing settings found; running full setup.")
        else:
            reuse_existing_settings = _prompt_reuse_existing_settings()

    custom_domain_requested = False
    custom_pages_domain: Optional[str] = None
    if not args.no_auto_github:
        explicit_domain_override = (
            bool(getattr(args, "clear_custom_domain", False))
            or getattr(args, "custom_domain", None) is not None
        )
        should_prompt_domain = not (interactive and reuse_existing_settings and not explicit_domain_override)
        if should_prompt_domain:
            custom_domain_requested, custom_pages_domain = _resolve_custom_pages_domain(args, interactive, repo)

    if reuse_existing_settings and existing_settings is not None:
        source = existing_settings.source
        distance_unit = existing_settings.distance_unit
        elevation_unit = existing_settings.elevation_unit
        week_start = existing_settings.week_start
    else:
        source = _resolve_source(args, interactive, previous_source)
        distance_unit, elevation_unit = _resolve_units(args, interactive)
        week_start = _resolve_week_start(args, interactive, repo)

    full_backfill = False
    if interactive and previous_source == source:
        full_backfill = _prompt_full_backfill_choice(source)

    strava_profile_url = ""
    strava_activity_links_enabled = False
    garmin_profile_url = ""
    garmin_activity_links_enabled = False
    strava_profile_link_enabled_override: Optional[bool] = None
    strava_profile_url_prefilled = ""
    garmin_profile_link_enabled_override: Optional[bool] = None
    garmin_profile_url_prefilled = ""
    if source == "strava":
        if reuse_existing_settings:
            strava_activity_links_enabled = bool(_existing_dashboard_strava_activity_links(repo))
            strava_profile_url_prefilled = _existing_dashboard_strava_profile_url(repo)
            strava_profile_link_enabled_override = bool(strava_profile_url_prefilled)
        else:
            strava_activity_links_enabled = _resolve_strava_activity_links(args, interactive, repo)
            (
                strava_profile_link_enabled_override,
                strava_profile_url_prefilled,
            ) = _resolve_strava_profile_link_preference(args, interactive, repo)
    elif source == "garmin":
        if reuse_existing_settings:
            garmin_activity_links_enabled = bool(_existing_dashboard_garmin_activity_links(repo))
            garmin_profile_url_prefilled = _existing_dashboard_garmin_profile_url(repo)
            garmin_profile_link_enabled_override = bool(garmin_profile_url_prefilled)
        else:
            garmin_activity_links_enabled = _resolve_garmin_activity_links(args, interactive, repo)
            (
                garmin_profile_link_enabled_override,
                garmin_profile_url_prefilled,
            ) = _resolve_garmin_profile_link_preference(args, interactive, repo)

    update_credentials = True
    if (
        interactive
        and reuse_existing_settings
        and not _has_explicit_credentials_for_source(args, source)
    ):
        secret_names = _list_secret_names(repo)
        if _has_required_source_secrets(source, secret_names):
            update_credentials = _prompt_update_credentials()
        else:
            print(f"\nMissing required {source.capitalize()} credential secrets; credential re-entry is required.")

    print("\nUpdating repository secrets via gh...")
    configured_secret_names: list[str] = []
    athlete_name = ""
    strava_rotation_secret_ok: Optional[bool] = None
    strava_rotation_secret_detail = ""
    if source == "strava":
        if update_credentials:
            if interactive and not args.client_id:
                print("\nEnter your Strava API credentials from https://www.strava.com/settings/api")
            if not interactive and not args.client_id:
                raise RuntimeError("Missing STRAVA_CLIENT_ID in non-interactive mode. Re-run with --client-id.")
            if not interactive and not args.client_secret:
                raise RuntimeError("Missing STRAVA_CLIENT_SECRET in non-interactive mode. Re-run with --client-secret.")

            client_id = _prompt(args.client_id, "STRAVA_CLIENT_ID")
            client_secret = _prompt(args.client_secret, "STRAVA_CLIENT_SECRET", secret=True)
            if not client_id or not client_secret:
                if interactive:
                    raise ValueError("Both STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET are required.")
                raise RuntimeError(
                    "Missing Strava credentials in non-interactive mode. "
                    "Provide both --client-id and --client-secret."
                )

            redirect_uri = f"http://localhost:{args.port}{CALLBACK_PATH}"
            code = _authorize_and_get_code(
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=args.scope,
                port=args.port,
                timeout_seconds=args.timeout,
                open_browser=not args.no_browser,
            )

            tokens = _exchange_code_for_tokens(client_id, client_secret, code)
            refresh_token = tokens["refresh_token"]

            _set_secret("STRAVA_CLIENT_ID", client_id, repo)
            _set_secret("STRAVA_CLIENT_SECRET", client_secret, repo)
            _set_secret("STRAVA_REFRESH_TOKEN", refresh_token, repo)
            configured_secret_names.extend(
                ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
            )
            strava_rotation_secret_ok, strava_rotation_secret_detail = _try_set_strava_secret_update_token(
                repo
            )
            if strava_rotation_secret_ok:
                configured_secret_names.append("STRAVA_SECRET_UPDATE_TOKEN")
            athlete = tokens.get("athlete") or {}
            athlete_name = " ".join(
                [str(athlete.get("firstname", "")).strip(), str(athlete.get("lastname", "")).strip()]
            ).strip()
        else:
            strava_rotation_secret_ok = False
            strava_rotation_secret_detail = "Reusing existing Strava credentials from GitHub secrets."
        strava_profile_url = _resolve_strava_profile_url(
            args,
            interactive and update_credentials,
            repo,
            tokens=tokens if update_credentials else {},
            enabled_override=strava_profile_link_enabled_override,
            prefilled_url=strava_profile_url_prefilled,
            prompt_if_missing=False if strava_profile_link_enabled_override is not None else True,
        )
    elif source == "garmin":
        token_store_b64 = ""
        garmin_email = ""
        garmin_password = ""
        if update_credentials:
            token_store_b64, garmin_email, garmin_password = _resolve_garmin_auth_values(args, interactive)
            if token_store_b64:
                _set_secret("GARMIN_TOKENS_B64", token_store_b64, repo)
                configured_secret_names.append("GARMIN_TOKENS_B64")
            if garmin_email and garmin_password:
                _set_secret("GARMIN_EMAIL", garmin_email, repo)
                _set_secret("GARMIN_PASSWORD", garmin_password, repo)
                configured_secret_names.extend(["GARMIN_EMAIL", "GARMIN_PASSWORD"])
        garmin_profile_url = _resolve_garmin_profile_url(
            args,
            interactive and update_credentials,
            repo,
            token_store_b64=token_store_b64,
            email=garmin_email,
            password=garmin_password,
            enabled_override=garmin_profile_link_enabled_override,
            prefilled_url=garmin_profile_url_prefilled,
            prompt_if_missing=False if garmin_profile_link_enabled_override is not None else True,
        )
    else:
        raise RuntimeError(f"Unsupported source: {source}")

    steps: list[StepResult] = []
    repo_url = f"https://github.com/{repo}"
    workflow_url = f"{repo_url}/actions/workflows/sync.yml"
    pages_url = f"{repo_url}/settings/pages"
    actions_url = f"{repo_url}/actions"
    actions_settings_url = f"{repo_url}/settings/actions"
    secrets_settings_url = f"{repo_url}/settings/secrets/actions"
    variables_settings_url = f"{repo_url}/settings/variables/actions"

    if source == "strava":
        _add_step(
            steps,
            name="Auto-rotate Strava refresh token",
            status=STATUS_OK if strava_rotation_secret_ok else STATUS_SKIPPED,
            detail=strava_rotation_secret_detail,
            manual_help=(
                None
                if strava_rotation_secret_ok
                else (
                    f"Optional: set STRAVA_SECRET_UPDATE_TOKEN in {secrets_settings_url} "
                    "to allow workflow auto-rotation of STRAVA_REFRESH_TOKEN."
                )
            ),
        )

    variable_errors = []
    print("Updating repository variables via gh...")
    variable_pairs = [
        ("DASHBOARD_SOURCE", source),
        ("DASHBOARD_REPO", repo),
        ("DASHBOARD_DISTANCE_UNIT", distance_unit),
        ("DASHBOARD_ELEVATION_UNIT", elevation_unit),
        ("DASHBOARD_WEEK_START", week_start),
    ]
    if source == "strava":
        variable_pairs.append(("DASHBOARD_STRAVA_PROFILE_URL", strava_profile_url))
        variable_pairs.append(
            ("DASHBOARD_STRAVA_ACTIVITY_LINKS", "true" if strava_activity_links_enabled else "")
        )
    elif source == "garmin":
        variable_pairs.append(("DASHBOARD_GARMIN_PROFILE_URL", garmin_profile_url))
        variable_pairs.append(
            ("DASHBOARD_GARMIN_ACTIVITY_LINKS", "true" if garmin_activity_links_enabled else "")
        )
    for name, value in variable_pairs:
        try:
            if name in {
                "DASHBOARD_STRAVA_PROFILE_URL",
                "DASHBOARD_STRAVA_ACTIVITY_LINKS",
                "DASHBOARD_GARMIN_PROFILE_URL",
                "DASHBOARD_GARMIN_ACTIVITY_LINKS",
            } and not value:
                _clear_variable(name, repo)
            else:
                _set_variable(name, value, repo)
        except RuntimeError as exc:
            variable_errors.append(str(exc))

    variable_summary = (
        f"DASHBOARD_SOURCE={source}, DASHBOARD_REPO={repo}, "
        f"DASHBOARD_DISTANCE_UNIT={distance_unit}, DASHBOARD_ELEVATION_UNIT={elevation_unit}, "
        f"DASHBOARD_WEEK_START={week_start}"
    )
    if source == "strava" and strava_profile_url:
        variable_summary = f"{variable_summary}, DASHBOARD_STRAVA_PROFILE_URL={strava_profile_url}"
    if source == "strava" and strava_activity_links_enabled:
        variable_summary = f"{variable_summary}, DASHBOARD_STRAVA_ACTIVITY_LINKS=true"
    if source == "garmin" and garmin_profile_url:
        variable_summary = f"{variable_summary}, DASHBOARD_GARMIN_PROFILE_URL={garmin_profile_url}"
    if source == "garmin" and garmin_activity_links_enabled:
        variable_summary = f"{variable_summary}, DASHBOARD_GARMIN_ACTIVITY_LINKS=true"

    if variable_errors:
        _add_step(
            steps,
            name="Store dashboard variables",
            status=STATUS_MANUAL_REQUIRED,
            detail=f"Could not store one or more dashboard variables automatically: {variable_errors[0]}",
            manual_help=(
                f"Open {variables_settings_url} and set {variable_summary}."
            ),
        )
    else:
        _add_step(
            steps,
            name="Store dashboard variables",
            status=STATUS_OK,
            detail=f"Saved {variable_summary}.",
        )
    print("\nCredentials configured.")
    if athlete_name:
        print(f"Authorized athlete: {athlete_name}")
    print(f"Source set: {source}")
    if configured_secret_names:
        print(f"Secrets set: {', '.join(configured_secret_names)}")
    if not variable_errors:
        print(f"Variables set: {variable_summary}")

    if args.no_auto_github:
        _add_step(
            steps,
            name="GitHub automation",
            status=STATUS_SKIPPED,
            detail="Skipped (--no-auto-github).",
            manual_help=f"Run the workflow manually: {workflow_url}",
        )
    else:
        enabled, detail = _try_enable_actions_permissions(repo)
        _add_step(
            steps,
            name="Actions permissions",
            status=STATUS_OK if enabled else STATUS_MANUAL_REQUIRED,
            detail=detail if enabled else f"Could not configure automatically: {detail}",
            manual_help=None if enabled else f"Open {actions_settings_url} and allow Actions/workflows.",
        )

        issues_enabled, issues_detail = _try_enable_repo_issues(repo)
        _add_step(
            steps,
            name="Issues tab",
            status=STATUS_OK if issues_enabled else STATUS_MANUAL_REQUIRED,
            detail=issues_detail if issues_enabled else f"Could not configure automatically: {issues_detail}",
            manual_help=(
                None
                if issues_enabled
                else f"Open {repo_url}/settings and enable Issues under Features."
            ),
        )

        workflows_enabled, workflow_detail = _try_enable_workflows(
            repo,
            ["sync.yml", "pages.yml"],
            source_repo=template_repo,
        )
        _add_step(
            steps,
            name="Enable workflows",
            status=STATUS_OK if workflows_enabled else STATUS_MANUAL_REQUIRED,
            detail=workflow_detail if workflows_enabled else f"Could not enable automatically: {workflow_detail}",
            manual_help=None if workflows_enabled else f"Open {actions_url} and click 'Enable workflows' if shown.",
        )

        pages_configured, pages_detail = _try_configure_pages(repo)
        _add_step(
            steps,
            name="GitHub Pages source",
            status=STATUS_OK if pages_configured else STATUS_MANUAL_REQUIRED,
            detail=pages_detail if pages_configured else f"Could not configure automatically: {pages_detail}",
            manual_help=None if pages_configured else f"Open {pages_url} and set Source to 'GitHub Actions'.",
        )

        if custom_domain_requested:
            if custom_pages_domain:
                domain_set, domain_detail = _try_set_pages_custom_domain(repo, custom_pages_domain)
                _add_step(
                    steps,
                    name="GitHub Pages custom domain",
                    status=STATUS_OK if domain_set else STATUS_MANUAL_REQUIRED,
                    detail=domain_detail if domain_set else f"Could not configure automatically: {domain_detail}",
                    manual_help=None if domain_set else f"Open {pages_url} and set Custom domain to {custom_pages_domain}.",
                )
            else:
                domain_cleared, domain_detail = _try_clear_pages_custom_domain(repo)
                _add_step(
                    steps,
                    name="GitHub Pages custom domain",
                    status=STATUS_OK if domain_cleared else STATUS_MANUAL_REQUIRED,
                    detail=domain_detail if domain_cleared else f"Could not configure automatically: {domain_detail}",
                    manual_help=None if domain_cleared else f"Open {pages_url} and clear the Custom domain field.",
                )

        dispatch_started_at = datetime.now(timezone.utc)
        dispatched, dispatch_detail = _try_dispatch_sync(
            repo,
            source,
            full_backfill=full_backfill,
        )
        _add_step(
            steps,
            name="Run first sync workflow",
            status=STATUS_OK if dispatched else STATUS_MANUAL_REQUIRED,
            detail=dispatch_detail if dispatched else f"Could not dispatch automatically: {dispatch_detail}",
            manual_help=None if dispatched else f"Open {workflow_url} and click 'Run workflow'.",
        )

        run_id: Optional[int] = None
        run_url: Optional[str] = None
        sync_watch_ok = False
        if dispatched:
            run_id, run_url = _find_latest_workflow_run(
                repo=repo,
                workflow="sync.yml",
                event="workflow_dispatch",
                not_before=dispatch_started_at,
                progress_label="Sync workflow run",
            )
            if run_url:
                _add_step(
                    steps,
                    name="Locate run URL",
                    status=STATUS_OK,
                    detail=f"Workflow run URL: {run_url}",
                )
            else:
                _add_step(
                    steps,
                    name="Locate run URL",
                    status=STATUS_MANUAL_REQUIRED,
                    detail="Dispatched workflow but could not resolve run URL automatically.",
                    manual_help=f"Open {workflow_url} to view the latest run.",
                )

            if args.no_watch:
                _add_step(
                    steps,
                    name="Watch workflow run",
                    status=STATUS_SKIPPED,
                    detail="Skipped (--no-watch).",
                    manual_help=run_url or workflow_url,
                )
            elif run_id is not None:
                watched, watch_detail = _watch_run(repo, run_id)
                sync_watch_ok = watched
                _add_step(
                    steps,
                    name="Watch workflow run",
                    status=STATUS_OK if watched else STATUS_MANUAL_REQUIRED,
                    detail=watch_detail,
                    manual_help=None if watched else (run_url or workflow_url),
                )
            else:
                _add_step(
                    steps,
                    name="Watch workflow run",
                    status=STATUS_SKIPPED,
                    detail="Skipped because run ID could not be determined.",
                    manual_help=workflow_url,
                )

            pages_run_id: Optional[int] = None
            pages_run_url: Optional[str] = None
            pages_workflow_url = f"{repo_url}/actions/workflows/pages.yml"
            pages_discovery_start = dispatch_started_at
            if args.no_watch:
                _add_step(
                    steps,
                    name="Watch Pages deploy",
                    status=STATUS_SKIPPED,
                    detail="Skipped (--no-watch).",
                    manual_help=pages_workflow_url,
                )
            elif run_id is None:
                _add_step(
                    steps,
                    name="Watch Pages deploy",
                    status=STATUS_SKIPPED,
                    detail="Skipped because sync run ID could not be determined.",
                    manual_help=pages_workflow_url,
                )
            elif not sync_watch_ok:
                _add_step(
                    steps,
                    name="Watch Pages deploy",
                    status=STATUS_SKIPPED,
                    detail="Skipped because sync run did not finish cleanly in CLI watch.",
                    manual_help=pages_workflow_url,
                )
            else:
                pages_run_id, pages_run_url = _find_latest_workflow_run(
                    repo=repo,
                    workflow="pages.yml",
                    event="workflow_run",
                    not_before=pages_discovery_start,
                    poll_attempts=75,
                    sleep_seconds=2,
                    progress_label="Pages deploy run",
                )
                if pages_run_url:
                    _add_step(
                        steps,
                        name="Locate Pages deploy run",
                        status=STATUS_OK,
                        detail=f"Deploy Pages run URL: {pages_run_url}",
                    )
                else:
                    manual_dispatched, manual_dispatch_detail = _try_dispatch_pages(repo)
                    if manual_dispatched:
                        pages_run_id, pages_run_url = _find_latest_workflow_run(
                            repo=repo,
                            workflow="pages.yml",
                            event="workflow_dispatch",
                            not_before=pages_discovery_start,
                            poll_attempts=30,
                            sleep_seconds=2,
                            progress_label="manual Pages deploy run",
                        )
                        if pages_run_url:
                            _add_step(
                                steps,
                                name="Locate Pages deploy run",
                                status=STATUS_OK,
                                detail=f"Deploy Pages run URL: {pages_run_url}",
                            )
                        else:
                            _add_step(
                                steps,
                                name="Locate Pages deploy run",
                                status=STATUS_MANUAL_REQUIRED,
                                detail=(
                                    "Could not find a Deploy Pages run after sync completed, and "
                                    "manual pages dispatch did not surface a run URL automatically."
                                ),
                                manual_help=pages_workflow_url,
                            )
                    else:
                        _add_step(
                            steps,
                            name="Locate Pages deploy run",
                            status=STATUS_MANUAL_REQUIRED,
                            detail=(
                                "Could not find a Deploy Pages run after sync completed, and "
                                f"automatic pages dispatch failed: {manual_dispatch_detail}"
                            ),
                            manual_help=pages_workflow_url,
                        )

                if pages_run_id is not None:
                    watched_pages, pages_watch_detail = _watch_run(repo, pages_run_id)
                    _add_step(
                        steps,
                        name="Watch Pages deploy",
                        status=STATUS_OK if watched_pages else STATUS_MANUAL_REQUIRED,
                        detail=pages_watch_detail if watched_pages else "Could not monitor Deploy Pages to completion.",
                        manual_help=None if watched_pages else (pages_run_url or pages_workflow_url),
                    )
                elif pages_run_url is not None:
                    _add_step(
                        steps,
                        name="Watch Pages deploy",
                        status=STATUS_MANUAL_REQUIRED,
                        detail="Found Deploy Pages run URL but could not resolve run ID for watch.",
                        manual_help=pages_run_url,
                    )

    print("\nSetup summary:")
    for step in steps:
        print(f"- [{step.status}] {step.name}: {step.detail}")
        if step.status == STATUS_MANUAL_REQUIRED and step.manual_help:
            print(f"  Manual: {step.manual_help}")

    dashboard_url = _dashboard_url_from_pages_api(repo) or _pages_url_from_slug(repo)
    has_manual_steps = any(step.status == STATUS_MANUAL_REQUIRED for step in steps)
    if has_manual_steps:
        print("\nSetup completed with manual steps remaining.")
        print(f"Dashboard URL: {dashboard_url}")
    elif args.no_auto_github:
        print("\nSetup completed. GitHub automation was skipped (--no-auto-github).")
        print(f"Run sync.yml to publish, then open: {dashboard_url}")
    elif args.no_watch:
        print("\nSetup completed. Workflows were started but not watched (--no-watch).")
        print(f"Check Actions for completion, then open: {dashboard_url}")
    else:
        print(f"\nYour dashboard is now live at {dashboard_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
