#!/usr/bin/env python3
"""
Bootstrap Strava OAuth and GitHub Actions secrets for this repository.

This script performs:
1) Browser-based Strava OAuth authorization with a localhost callback.
2) Authorization-code exchange for a refresh token.
3) GitHub secret updates via `gh secret set`.
"""

from __future__ import annotations

import argparse
import getpass
import html
import http.server
import secrets
import shutil
import socketserver
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import json
import webbrowser
from dataclasses import dataclass
from typing import Optional


TOKEN_ENDPOINT = "https://www.strava.com/oauth/token"
AUTHORIZE_ENDPOINT = "https://www.strava.com/oauth/authorize"
CALLBACK_PATH = "/exchange_token"


@dataclass
class CallbackResult:
    code: Optional[str] = None
    error: Optional[str] = None


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


def _prompt(value: Optional[str], label: str, secret: bool = False) -> str:
    if value:
        return value.strip()
    if secret:
        return getpass.getpass(f"{label}: ").strip()
    return input(f"{label}: ").strip()


def _assert_gh_ready(repo: Optional[str]) -> None:
    if shutil.which("gh") is None:
        raise RuntimeError(
            "GitHub CLI (`gh`) is required. Install it from https://cli.github.com/ and run `gh auth login`."
        )

    status = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if status.returncode != 0:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run `gh auth login` and re-run this script."
        )

    if repo:
        check = subprocess.run(
            ["gh", "repo", "view", repo, "--json", "name"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            raise RuntimeError(
                f"Unable to access repository '{repo}' with current gh auth context."
            )


def _set_secret(name: str, value: str, repo: Optional[str]) -> None:
    cmd = ["gh", "secret", "set", name]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        subprocess.run(
            cmd,
            input=value,
            text=True,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr.splitlines()[0]}" if stderr else ""
        raise RuntimeError(f"Failed to set GitHub secret {name}{detail}") from None


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap Strava OAuth and store required GitHub Actions secrets."
    )
    parser.add_argument("--client-id", default=None, help="Strava client ID.")
    parser.add_argument(
        "--client-secret",
        default=None,
        help=(
            "Strava client secret. Supported for convenience, but interactive prompt is safer "
            "because command-line arguments may be visible to local process inspection."
        ),
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional GitHub repo in OWNER/REPO form. If omitted, gh uses current repo context.",
    )
    parser.add_argument("--port", type=int, default=8765, help="Local callback port.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Seconds to wait for OAuth callback.",
    )
    parser.add_argument(
        "--scope",
        default="read,activity:read_all",
        help="Strava OAuth scopes.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser; print auth URL only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.port < 1 or args.port > 65535:
        raise ValueError("--port must be between 1 and 65535.")
    if args.timeout <= 0:
        raise ValueError("--timeout must be a positive number of seconds.")

    if args.client_secret:
        print(
            "Warning: passing --client-secret can expose the value via shell history/process inspection. "
            "Prompted input is safer.",
            file=sys.stderr,
        )

    client_id = _prompt(args.client_id, "STRAVA_CLIENT_ID")
    client_secret = _prompt(args.client_secret, "STRAVA_CLIENT_SECRET", secret=True)
    if not client_id or not client_secret:
        raise ValueError("Both STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET are required.")

    _assert_gh_ready(args.repo)

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

    print("\nUpdating repository secrets via gh...")
    _set_secret("STRAVA_CLIENT_ID", client_id, args.repo)
    _set_secret("STRAVA_CLIENT_SECRET", client_secret, args.repo)
    _set_secret("STRAVA_REFRESH_TOKEN", refresh_token, args.repo)

    athlete = tokens.get("athlete") or {}
    athlete_name = " ".join(
        [str(athlete.get("firstname", "")).strip(), str(athlete.get("lastname", "")).strip()]
    ).strip()
    print("\nSuccess.")
    if athlete_name:
        print(f"Authorized athlete: {athlete_name}")
    print("Secrets set: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN")
    print("Next: enable GitHub Pages (Source: GitHub Actions) and run the Sync workflow once.")
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
