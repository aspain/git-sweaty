import os
import subprocess
import sys
import unittest
from argparse import Namespace
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import setup_auth  # noqa: E402


def _completed_process(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class SetupAuthPreflightTests(unittest.TestCase):
    def test_extract_gh_token_scopes_parses_status_output(self) -> None:
        output = """
        Logged in to github.com account user
          - Token scopes: 'repo', 'workflow', 'read:org'
        """

        scopes = setup_auth._extract_gh_token_scopes(output)

        self.assertEqual(scopes, {"repo", "workflow", "read:org"})

    def test_build_actions_secret_access_error_mentions_missing_scopes(self) -> None:
        message = setup_auth._build_actions_secret_access_error(
            repo="owner/repo",
            detail="HTTP 403: Resource not accessible by integration",
            status_output="  - Token scopes: 'repo'",
        )

        self.assertIn("Missing token scopes: workflow.", message)
        self.assertIn("gh auth refresh -s workflow,repo", message)
        self.assertIn("correct repository", message)

    def test_assert_actions_secret_access_succeeds_when_public_key_is_readable(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=0, stdout='{"key":"abc"}'),
        ) as run_mock:
            setup_auth._assert_actions_secret_access("owner/repo")

        run_mock.assert_called_once_with(
            ["gh", "api", "repos/owner/repo/actions/secrets/public-key"],
            check=False,
        )

    def test_assert_actions_secret_access_raises_targeted_fix_for_integration_403(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="gh: Resource not accessible by integration (HTTP 403)\n",
            ),
            _completed_process(
                returncode=0,
                stderr="  - Token scopes: 'repo'\n",
            ),
        ]

        with mock.patch("setup_auth._run", side_effect=responses):
            with self.assertRaises(RuntimeError) as exc_ctx:
                setup_auth._assert_actions_secret_access("owner/repo")

        message = str(exc_ctx.exception)
        self.assertIn("gh auth refresh -s workflow,repo", message)
        self.assertIn("Missing token scopes: workflow.", message)
        self.assertIn("organization fork", message)

    def test_assert_actions_secret_access_raises_generic_error_for_non_403_failures(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=1, stderr="gh: Not Found (HTTP 404)\n"),
        ):
            with self.assertRaises(RuntimeError) as exc_ctx:
                setup_auth._assert_actions_secret_access("owner/repo")

        self.assertIn("Unable to access Actions secrets API", str(exc_ctx.exception))

    def test_assert_actions_secret_access_raises_guidance_for_generic_403(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=1, stderr="gh: Forbidden (HTTP 403)\n"),
        ):
            with self.assertRaises(RuntimeError) as exc_ctx:
                setup_auth._assert_actions_secret_access("owner/repo")

        message = str(exc_ctx.exception)
        self.assertIn("gh auth refresh -s workflow,repo", message)
        self.assertIn("authorize SSO", message)


class SetupAuthBootstrapEnvTests(unittest.TestCase):
    def test_ensure_venv_pip_bootstraps_with_ensurepip_when_missing(self) -> None:
        venv_python = "/tmp/project/.venv/bin/python"
        responses = [
            _completed_process(returncode=1, stderr="No module named pip\n"),
            _completed_process(returncode=0, stdout="installed pip\n"),
            _completed_process(returncode=0, stdout="pip 24.0\n"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses) as run_mock:
            setup_auth._ensure_venv_pip(venv_python)

        self.assertEqual(
            run_mock.mock_calls,
            [
                mock.call([venv_python, "-m", "pip", "--version"], check=False),
                mock.call([venv_python, "-m", "ensurepip", "--upgrade"], check=False),
                mock.call([venv_python, "-m", "pip", "--version"], check=False),
            ],
        )

    def test_ensure_venv_pip_raises_with_actionable_error_when_ensurepip_fails(self) -> None:
        venv_python = "/tmp/project/.venv/bin/python"
        responses = [
            _completed_process(returncode=1, stderr="No module named pip\n"),
            _completed_process(returncode=1, stderr="No module named ensurepip\n"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            with self.assertRaises(RuntimeError) as exc_ctx:
                setup_auth._ensure_venv_pip(venv_python)

        message = str(exc_ctx.exception)
        self.assertIn("without pip", message)
        self.assertIn("--no-bootstrap-env", message)

    def test_bootstrap_env_calls_ensure_venv_pip_before_pip_installs(self) -> None:
        args = Namespace(no_bootstrap_env=False, env_bootstrapped=False)
        venv_python = "/repo/.venv/bin/python"
        requirements = "/repo/requirements.txt"
        script_path = "/repo/scripts/setup_auth.py"

        def fake_exists(path: str) -> bool:
            return path in {requirements, venv_python}

        with (
            mock.patch("setup_auth._in_virtualenv", return_value=False),
            mock.patch("setup_auth._project_root", return_value="/repo"),
            mock.patch("setup_auth._venv_python_path", return_value=venv_python),
            mock.patch("setup_auth.os.path.exists", side_effect=fake_exists),
            mock.patch("setup_auth._ensure_venv_pip") as ensure_pip_mock,
            mock.patch("setup_auth._run_stream") as run_stream_mock,
            mock.patch("setup_auth.subprocess.call", return_value=0),
            mock.patch("setup_auth.__file__", script_path),
            mock.patch("setup_auth.sys.argv", ["setup_auth.py"]),
        ):
            with self.assertRaises(SystemExit) as exc_ctx:
                setup_auth._bootstrap_env_and_reexec(args)

        self.assertEqual(exc_ctx.exception.code, 0)
        ensure_pip_mock.assert_called_once_with(venv_python)
        self.assertEqual(
            run_stream_mock.mock_calls,
            [
                mock.call([venv_python, "-m", "pip", "install", "--upgrade", "pip"], cwd="/repo"),
                mock.call([venv_python, "-m", "pip", "install", "-r", requirements], cwd="/repo"),
            ],
        )


class SetupAuthDispatchTests(unittest.TestCase):
    def test_existing_dashboard_source_normalizes_supported_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value=" Strava ",
        ):
            value = setup_auth._existing_dashboard_source("owner/repo")
        self.assertEqual(value, "strava")

    def test_existing_dashboard_source_ignores_unknown_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value="something-else",
        ):
            value = setup_auth._existing_dashboard_source("owner/repo")
        self.assertIsNone(value)

    def test_resolve_source_non_interactive_prefers_existing_source(self) -> None:
        args = Namespace(source=None)
        self.assertEqual(setup_auth._resolve_source(args, interactive=False, previous_source="garmin"), "garmin")

    def test_resolve_source_non_interactive_uses_default_without_existing_source(self) -> None:
        args = Namespace(source=None)
        self.assertEqual(setup_auth._resolve_source(args, interactive=False, previous_source=None), "strava")

    def test_existing_dashboard_week_start_normalizes_supported_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value=" Monday ",
        ):
            value = setup_auth._existing_dashboard_week_start("owner/repo")
        self.assertEqual(value, "monday")

    def test_existing_dashboard_week_start_ignores_unknown_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value="something-else",
        ):
            value = setup_auth._existing_dashboard_week_start("owner/repo")
        self.assertIsNone(value)

    def test_existing_dashboard_units_returns_valid_pair(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            side_effect=["mi", "ft"],
        ):
            value = setup_auth._existing_dashboard_units("owner/repo")
        self.assertEqual(value, ("mi", "ft"))

    def test_existing_dashboard_units_rejects_invalid_pair(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            side_effect=["mi", "m"],
        ):
            value = setup_auth._existing_dashboard_units("owner/repo")
        self.assertIsNone(value)

    def test_load_existing_dashboard_settings_requires_all_core_fields(self) -> None:
        with (
            mock.patch("setup_auth._existing_dashboard_source", return_value="strava"),
            mock.patch("setup_auth._existing_dashboard_units", return_value=("mi", "ft")),
            mock.patch("setup_auth._existing_dashboard_week_start", return_value="monday"),
        ):
            value = setup_auth._load_existing_dashboard_settings("owner/repo")
        self.assertEqual(
            value,
            setup_auth.ExistingDashboardSettings(
                source="strava",
                distance_unit="mi",
                elevation_unit="ft",
                week_start="monday",
            ),
        )

    def test_has_required_source_secrets_for_supported_sources(self) -> None:
        self.assertTrue(
            setup_auth._has_required_source_secrets(
                "strava",
                {"STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"},
            )
        )
        self.assertTrue(
            setup_auth._has_required_source_secrets(
                "garmin",
                {"GARMIN_TOKENS_B64"},
            )
        )
        self.assertTrue(
            setup_auth._has_required_source_secrets(
                "garmin",
                {"GARMIN_EMAIL", "GARMIN_PASSWORD"},
            )
        )
        self.assertFalse(
            setup_auth._has_required_source_secrets(
                "garmin",
                {"GARMIN_EMAIL"},
            )
        )

    def test_resolve_week_start_non_interactive_prefers_existing_value(self) -> None:
        args = Namespace(week_start=None)
        with mock.patch("setup_auth._existing_dashboard_week_start", return_value="monday"):
            value = setup_auth._resolve_week_start(args, interactive=False, repo="owner/repo")
        self.assertEqual(value, "monday")

    def test_resolve_week_start_non_interactive_defaults_to_sunday(self) -> None:
        args = Namespace(week_start=None)
        with mock.patch("setup_auth._existing_dashboard_week_start", return_value=None):
            value = setup_auth._resolve_week_start(args, interactive=False, repo="owner/repo")
        self.assertEqual(value, "sunday")

    def test_resolve_week_start_uses_explicit_argument(self) -> None:
        args = Namespace(week_start="monday")
        with mock.patch("setup_auth._existing_dashboard_week_start", return_value="sunday"):
            value = setup_auth._resolve_week_start(args, interactive=False, repo="owner/repo")
        self.assertEqual(value, "monday")

    def test_resolve_week_start_interactive_defaults_to_sunday_option(self) -> None:
        args = Namespace(week_start=None)
        with (
            mock.patch("setup_auth._existing_dashboard_week_start", return_value="monday"),
            mock.patch("setup_auth._prompt_week_start", return_value="sunday") as prompt_mock,
        ):
            value = setup_auth._resolve_week_start(args, interactive=True, repo="owner/repo")
        self.assertEqual(value, "sunday")
        prompt_mock.assert_called_once_with("sunday")

    def test_existing_dashboard_strava_activity_links_parses_truthy_value(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value=" YES ",
        ):
            value = setup_auth._existing_dashboard_strava_activity_links("owner/repo")
        self.assertTrue(value)

    def test_existing_dashboard_strava_activity_links_ignores_unknown_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value="sometimes",
        ):
            value = setup_auth._existing_dashboard_strava_activity_links("owner/repo")
        self.assertIsNone(value)

    def test_existing_dashboard_garmin_activity_links_parses_truthy_value(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value=" YES ",
        ):
            value = setup_auth._existing_dashboard_garmin_activity_links("owner/repo")
        self.assertTrue(value)

    def test_existing_dashboard_garmin_activity_links_ignores_unknown_values(self) -> None:
        with mock.patch(
            "setup_auth._get_variable",
            return_value="sometimes",
        ):
            value = setup_auth._existing_dashboard_garmin_activity_links("owner/repo")
        self.assertIsNone(value)

    def test_resolve_strava_activity_links_non_interactive_prefers_existing_value(self) -> None:
        args = Namespace(strava_activity_links=None)
        with mock.patch("setup_auth._existing_dashboard_strava_activity_links", return_value=True):
            value = setup_auth._resolve_strava_activity_links(args, interactive=False, repo="owner/repo")
        self.assertTrue(value)

    def test_resolve_strava_activity_links_non_interactive_defaults_to_disabled(self) -> None:
        args = Namespace(strava_activity_links=None)
        with mock.patch("setup_auth._existing_dashboard_strava_activity_links", return_value=None):
            value = setup_auth._resolve_strava_activity_links(args, interactive=False, repo="owner/repo")
        self.assertFalse(value)

    def test_resolve_strava_activity_links_uses_explicit_argument(self) -> None:
        args = Namespace(strava_activity_links="yes")
        with mock.patch("setup_auth._existing_dashboard_strava_activity_links", return_value=False):
            value = setup_auth._resolve_strava_activity_links(args, interactive=False, repo="owner/repo")
        self.assertTrue(value)

    def test_resolve_strava_activity_links_interactive_prompts_with_existing_default(self) -> None:
        args = Namespace(strava_activity_links=None)
        with (
            mock.patch("setup_auth._existing_dashboard_strava_activity_links", return_value=True),
            mock.patch("setup_auth._prompt_use_strava_activity_links", return_value=False) as prompt_mock,
        ):
            value = setup_auth._resolve_strava_activity_links(args, interactive=True, repo="owner/repo")
        self.assertFalse(value)
        prompt_mock.assert_called_once_with(default_enabled=True)

    def test_resolve_garmin_activity_links_non_interactive_prefers_existing_value(self) -> None:
        args = Namespace(garmin_activity_links=None)
        with mock.patch("setup_auth._existing_dashboard_garmin_activity_links", return_value=True):
            value = setup_auth._resolve_garmin_activity_links(args, interactive=False, repo="owner/repo")
        self.assertTrue(value)

    def test_resolve_garmin_activity_links_non_interactive_defaults_to_disabled(self) -> None:
        args = Namespace(garmin_activity_links=None)
        with mock.patch("setup_auth._existing_dashboard_garmin_activity_links", return_value=None):
            value = setup_auth._resolve_garmin_activity_links(args, interactive=False, repo="owner/repo")
        self.assertFalse(value)

    def test_resolve_garmin_activity_links_uses_explicit_argument(self) -> None:
        args = Namespace(garmin_activity_links="yes")
        with mock.patch("setup_auth._existing_dashboard_garmin_activity_links", return_value=False):
            value = setup_auth._resolve_garmin_activity_links(args, interactive=False, repo="owner/repo")
        self.assertTrue(value)

    def test_resolve_garmin_activity_links_interactive_prompts_with_existing_default(self) -> None:
        args = Namespace(garmin_activity_links=None)
        with (
            mock.patch("setup_auth._existing_dashboard_garmin_activity_links", return_value=True),
            mock.patch("setup_auth._prompt_use_garmin_activity_links", return_value=False) as prompt_mock,
        ):
            value = setup_auth._resolve_garmin_activity_links(args, interactive=True, repo="owner/repo")
        self.assertFalse(value)
        prompt_mock.assert_called_once_with(default_enabled=True)

    def test_normalize_strava_profile_url_accepts_strava_host(self) -> None:
        value = setup_auth._normalize_strava_profile_url("www.strava.com/athletes/123")
        self.assertEqual(value, "https://www.strava.com/athletes/123")

    def test_normalize_strava_profile_url_rejects_non_strava_host(self) -> None:
        with self.assertRaises(ValueError):
            setup_auth._normalize_strava_profile_url("https://example.com/athletes/123")

    def test_normalize_garmin_profile_url_accepts_connect_host(self) -> None:
        value = setup_auth._normalize_garmin_profile_url("connect.garmin.com/modern/profile/123")
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/123")

    def test_normalize_garmin_profile_url_canonicalizes_extra_path_segments(self) -> None:
        value = setup_auth._normalize_garmin_profile_url(
            "https://connect.garmin.com/modern/profile/123/activities"
        )
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/123")

    def test_normalize_garmin_profile_url_rejects_non_profile_path(self) -> None:
        with self.assertRaises(ValueError):
            setup_auth._normalize_garmin_profile_url("https://connect.garmin.com/modern/activity/123")

    def test_detect_strava_profile_url_from_token_payload(self) -> None:
        value = setup_auth._detect_strava_profile_url({"athlete": {"id": 42}})
        self.assertEqual(value, "https://www.strava.com/athletes/42")

    def test_garmin_profile_url_from_profile_uses_display_name(self) -> None:
        value = setup_auth._garmin_profile_url_from_profile({"displayName": "abc-123"})
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/abc-123")

    def test_garmin_profile_url_from_profile_uses_nested_user_data_alias(self) -> None:
        value = setup_auth._garmin_profile_url_from_profile({"userData": {"display_name": "abc-456"}})
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/abc-456")

    def test_coerce_garmin_profile_payload_reads_object_aliases(self) -> None:
        profile_obj = SimpleNamespace(display_name="abc-789", user_id=42)

        value = setup_auth._coerce_garmin_profile_payload(profile_obj)

        self.assertEqual(value["displayName"], "abc-789")
        self.assertEqual(value["userId"], 42)

    def test_fetch_garmin_profile_reads_garth_client_profile_object(self) -> None:
        fake_garth = SimpleNamespace(
            login=mock.Mock(),
            client=SimpleNamespace(profile=SimpleNamespace(display_name="abc-999")),
            UserProfile=None,
            connectapi=mock.Mock(),
        )

        with mock.patch.dict(sys.modules, {"garth": fake_garth}):
            value = setup_auth._fetch_garmin_profile(
                token_store_b64="",
                email="runner@example.com",
                password="secret",
            )

        self.assertEqual(value["displayName"], "abc-999")
        fake_garth.login.assert_called_once_with("runner@example.com", "secret")

    def test_dashboard_url_from_pages_api_prefers_cname(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(
                returncode=0,
                stdout='{"cname":"strava.nedevski.com","html_url":"https://nedevski.github.io/strava/"}',
            ),
        ):
            value = setup_auth._dashboard_url_from_pages_api("nedevski/strava")
        self.assertEqual(value, "https://strava.nedevski.com/")

    def test_dashboard_url_from_pages_api_falls_back_to_html_url(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(
                returncode=0,
                stdout='{"cname":"","html_url":"https://nedevski.github.io/strava/"}',
            ),
        ):
            value = setup_auth._dashboard_url_from_pages_api("nedevski/strava")
        self.assertEqual(value, "https://nedevski.github.io/strava/")

    def test_dashboard_url_from_pages_api_returns_none_on_error(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=1, stderr="gh: Not Found"),
        ):
            value = setup_auth._dashboard_url_from_pages_api("nedevski/strava")
        self.assertIsNone(value)

    def test_normalize_pages_custom_domain_accepts_host_and_url(self) -> None:
        self.assertEqual(
            setup_auth._normalize_pages_custom_domain("strava.nedevski.com"),
            "strava.nedevski.com",
        )
        self.assertEqual(
            setup_auth._normalize_pages_custom_domain("https://strava.nedevski.com/"),
            "strava.nedevski.com",
        )

    def test_normalize_pages_custom_domain_rejects_paths_and_ports(self) -> None:
        with self.assertRaises(ValueError):
            setup_auth._normalize_pages_custom_domain("https://strava.nedevski.com/path")
        with self.assertRaises(ValueError):
            setup_auth._normalize_pages_custom_domain("strava.nedevski.com:8443")

    def test_try_set_pages_custom_domain_sets_and_verifies(self) -> None:
        responses = [
            _completed_process(returncode=0, stdout="null\n"),
            _completed_process(returncode=0),
            _completed_process(returncode=0, stdout="strava.nedevski.com\n"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            ok, detail = setup_auth._try_set_pages_custom_domain("owner/repo", "strava.nedevski.com")

        self.assertTrue(ok)
        self.assertIn("custom domain set to strava.nedevski.com", detail)

    def test_try_clear_pages_custom_domain_clears_and_verifies(self) -> None:
        responses = [
            _completed_process(returncode=0, stdout="strava.nedevski.com\n"),
            _completed_process(returncode=0),
            _completed_process(returncode=0, stdout="null\n"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            ok, detail = setup_auth._try_clear_pages_custom_domain("owner/repo")

        self.assertTrue(ok)
        self.assertIn("custom domain cleared", detail.lower())

    def test_try_enable_repo_issues_noop_when_already_enabled(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=0, stdout="true\n"),
        ) as run_mock:
            ok, detail = setup_auth._try_enable_repo_issues("owner/repo")

        self.assertTrue(ok)
        self.assertIn("already enabled", detail.lower())
        run_mock.assert_called_once_with(
            ["gh", "api", "repos/owner/repo", "--jq", ".has_issues"],
            check=False,
        )

    def test_try_enable_repo_issues_sets_and_verifies(self) -> None:
        responses = [
            _completed_process(returncode=0, stdout="false\n"),
            _completed_process(returncode=0),
            _completed_process(returncode=0, stdout="true\n"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            ok, detail = setup_auth._try_enable_repo_issues("owner/repo")

        self.assertTrue(ok)
        self.assertIn("issues are enabled", detail.lower())

    def test_prompt_custom_pages_domain_can_request_clear_existing_domain(self) -> None:
        with (
            mock.patch("setup_auth._get_pages_custom_domain", return_value="strava.example.com"),
            mock.patch("setup_auth._prompt_choice", side_effect=["no", "yes"]),
        ):
            requested, domain = setup_auth._prompt_custom_pages_domain("owner/repo")
        self.assertTrue(requested)
        self.assertIsNone(domain)

    def test_prompt_custom_pages_domain_defaults_to_no(self) -> None:
        with (
            mock.patch("setup_auth._get_pages_custom_domain", return_value="strava.example.com"),
            mock.patch("setup_auth._prompt_choice", side_effect=["no", "no"]) as prompt_mock,
        ):
            setup_auth._prompt_custom_pages_domain("owner/repo")

        self.assertGreaterEqual(len(prompt_mock.call_args_list), 1)
        first_call = prompt_mock.call_args_list[0]
        self.assertEqual(first_call.args[0], "Use a custom dashboard domain? [y/n] (default: n): ")
        self.assertEqual(first_call.kwargs["default"], "n")

    def test_resolve_strava_profile_url_non_interactive_uses_existing_variable(self) -> None:
        args = Namespace(strava_profile_url=None)
        with (
            mock.patch("setup_auth._detect_strava_profile_url", return_value=""),
            mock.patch("setup_auth._get_variable", return_value="https://www.strava.com/athletes/456"),
        ):
            value = setup_auth._resolve_strava_profile_url(args, interactive=False, repo="owner/repo")
        self.assertEqual(value, "https://www.strava.com/athletes/456")

    def test_resolve_strava_profile_url_interactive_uses_detected_when_enabled(self) -> None:
        args = Namespace(strava_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch("setup_auth._detect_strava_profile_url", return_value="https://www.strava.com/athletes/789"),
            mock.patch("setup_auth._prompt_use_strava_profile_link", return_value=True) as prompt_mock,
        ):
            value = setup_auth._resolve_strava_profile_url(
                args,
                interactive=True,
                repo="owner/repo",
                tokens={"athlete": {"id": 789}},
            )
        self.assertEqual(value, "https://www.strava.com/athletes/789")
        prompt_mock.assert_called_once_with(default_enabled=True)

    def test_resolve_strava_profile_url_interactive_returns_empty_when_detection_missing(self) -> None:
        args = Namespace(strava_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch("setup_auth._detect_strava_profile_url", return_value=""),
            mock.patch("setup_auth._prompt_use_strava_profile_link", return_value=True) as opt_in_mock,
        ):
            value = setup_auth._resolve_strava_profile_url(
                args,
                interactive=True,
                repo="owner/repo",
                tokens={},
            )
        self.assertEqual(value, "")
        opt_in_mock.assert_called_once_with(default_enabled=False)

    def test_resolve_garmin_profile_url_non_interactive_uses_existing_variable(self) -> None:
        args = Namespace(garmin_profile_url=None)
        with (
            mock.patch("setup_auth._detect_garmin_profile_url", return_value=""),
            mock.patch("setup_auth._get_variable", return_value="https://connect.garmin.com/modern/profile/456"),
        ):
            value = setup_auth._resolve_garmin_profile_url(
                args,
                interactive=False,
                repo="owner/repo",
                token_store_b64="",
                email="",
                password="",
            )
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/456")

    def test_resolve_garmin_profile_url_interactive_uses_detected_when_enabled(self) -> None:
        args = Namespace(garmin_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch(
                "setup_auth._detect_garmin_profile_url",
                return_value="https://connect.garmin.com/modern/profile/789",
            ),
            mock.patch("setup_auth._prompt_use_garmin_profile_link", return_value=True) as prompt_mock,
        ):
            value = setup_auth._resolve_garmin_profile_url(
                args,
                interactive=True,
                repo="owner/repo",
                token_store_b64="token",
                email="user@example.com",
                password="secret",
            )
        self.assertEqual(value, "https://connect.garmin.com/modern/profile/789")
        prompt_mock.assert_called_once_with(default_enabled=True)

    def test_resolve_garmin_profile_url_interactive_returns_empty_when_detection_missing(self) -> None:
        args = Namespace(garmin_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch("setup_auth._detect_garmin_profile_url", return_value=""),
            mock.patch("setup_auth._prompt_use_garmin_profile_link", return_value=True) as opt_in_mock,
        ):
            value = setup_auth._resolve_garmin_profile_url(
                args,
                interactive=True,
                repo="owner/repo",
                token_store_b64="token",
                email="user@example.com",
                password="secret",
            )
        self.assertEqual(value, "")
        opt_in_mock.assert_called_once_with(default_enabled=False)

    def test_resolve_strava_profile_link_preference_interactive_can_disable(self) -> None:
        args = Namespace(strava_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value="https://www.strava.com/athletes/321"),
            mock.patch("setup_auth._prompt_use_strava_profile_link", return_value=False) as prompt_mock,
        ):
            enabled, prefilled = setup_auth._resolve_strava_profile_link_preference(
                args,
                interactive=True,
                repo="owner/repo",
            )
        self.assertFalse(enabled)
        self.assertEqual(prefilled, "")
        prompt_mock.assert_called_once_with(default_enabled=True)

    def test_resolve_strava_profile_link_preference_interactive_enables_without_manual_url(self) -> None:
        args = Namespace(strava_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch("setup_auth._prompt_use_strava_profile_link", return_value=True) as opt_in_mock,
        ):
            enabled, prefilled = setup_auth._resolve_strava_profile_link_preference(
                args,
                interactive=True,
                repo="owner/repo",
            )
        self.assertTrue(enabled)
        self.assertEqual(prefilled, "")
        opt_in_mock.assert_called_once_with(default_enabled=False)

    def test_resolve_garmin_profile_link_preference_interactive_enables_without_manual_url(self) -> None:
        args = Namespace(garmin_profile_url=None)
        with (
            mock.patch("setup_auth._get_variable", return_value=""),
            mock.patch("setup_auth._prompt_use_garmin_profile_link", return_value=True) as opt_in_mock,
        ):
            enabled, prefilled = setup_auth._resolve_garmin_profile_link_preference(
                args,
                interactive=True,
                repo="owner/repo",
            )
        self.assertTrue(enabled)
        self.assertEqual(prefilled, "")
        opt_in_mock.assert_called_once_with(default_enabled=False)

    def test_clear_variable_ignores_not_found(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=1, stderr="HTTP 404: Not Found"),
        ):
            setup_auth._clear_variable("DASHBOARD_STRAVA_PROFILE_URL", "owner/repo")

    def test_clear_variable_raises_on_other_errors(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=1, stderr="HTTP 403: Forbidden"),
        ):
            with self.assertRaises(RuntimeError):
                setup_auth._clear_variable("DASHBOARD_STRAVA_PROFILE_URL", "owner/repo")

    def test_try_enable_workflows_seeds_empty_repo_when_workflows_missing(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow sync.yml not found on the default branch",
            ),
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow pages.yml not found on the default branch",
            ),
            _completed_process(returncode=0, stdout="main\n"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=1, stderr="HTTP 409: Git Repository is empty."),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
        ]
        with mock.patch("setup_auth._run", side_effect=responses) as run_mock:
            ok, detail = setup_auth._try_enable_workflows(
                "owner/repo",
                ["sync.yml", "pages.yml"],
                source_repo="aspain/git-sweaty",
            )

        self.assertTrue(ok)
        self.assertIn("Seeded empty repository from aspain/git-sweaty", detail)
        self.assertIn(
            mock.call(
                ["gh", "repo", "sync", "owner/repo", "--source", "aspain/git-sweaty", "--branch", "main", "--force"],
                check=False,
            ),
            run_mock.mock_calls,
        )

    def test_try_enable_workflows_skips_seed_when_repo_not_empty(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow sync.yml not found on the default branch",
            ),
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow pages.yml not found on the default branch",
            ),
            _completed_process(returncode=0, stdout="main\n"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=0, stdout="[]"),
        ]
        with mock.patch("setup_auth._run", side_effect=responses) as run_mock:
            ok, detail = setup_auth._try_enable_workflows(
                "owner/repo",
                ["sync.yml", "pages.yml"],
                source_repo="aspain/git-sweaty",
            )

        self.assertFalse(ok)
        self.assertIn("repository is not empty", detail)
        self.assertFalse(
            any(
                call.args
                and isinstance(call.args[0], list)
                and call.args[0][:3] == ["gh", "repo", "sync"]
                for call in run_mock.mock_calls
            )
        )

    def test_try_enable_workflows_falls_back_to_git_seed_when_repo_sync_fails(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow sync.yml not found on the default branch",
            ),
            _completed_process(
                returncode=1,
                stderr="HTTP 404: workflow pages.yml not found on the default branch",
            ),
            _completed_process(returncode=0, stdout="main\n"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=1, stderr="HTTP 404: Not Found"),
            _completed_process(returncode=1, stderr="HTTP 409: Git Repository is empty."),
            _completed_process(returncode=0, stdout="main\n"),
            _completed_process(returncode=1, stderr="HTTP 404: Branch not found"),
            _completed_process(returncode=1, stderr="HTTP 404: Branch not found"),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
            _completed_process(returncode=0),
        ]
        with (
            mock.patch("setup_auth._run", side_effect=responses),
            mock.patch(
                "setup_auth._try_seed_empty_repo_via_git_push",
                return_value=(True, "Seeded empty repository via git push."),
            ) as git_seed_mock,
        ):
            ok, detail = setup_auth._try_enable_workflows(
                "owner/repo",
                ["sync.yml", "pages.yml"],
                source_repo="aspain/git-sweaty",
            )

        self.assertTrue(ok)
        self.assertIn("authenticated git push", detail)
        git_seed_mock.assert_called_once_with(
            repo="owner/repo",
            source_repo="aspain/git-sweaty",
            source_branch="main",
            destination_branch="main",
        )

    def test_try_dispatch_sync_uses_full_backfill_when_supported(self) -> None:
        with mock.patch(
            "setup_auth._run",
            return_value=_completed_process(returncode=0),
        ) as run_mock:
            ok, detail = setup_auth._try_dispatch_sync(
                "owner/repo",
                "strava",
                full_backfill=True,
            )

        self.assertTrue(ok)
        self.assertIn("full_backfill=true", detail)
        run_mock.assert_called_once_with(
            [
                "gh",
                "workflow",
                "run",
                "sync.yml",
                "--repo",
                "owner/repo",
                "-f",
                "source=strava",
                "-f",
                "full_backfill=true",
            ],
            check=False,
        )

    def test_try_dispatch_sync_falls_back_when_full_backfill_input_missing(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="could not create workflow dispatch event: HTTP 422: Unexpected inputs provided: [full_backfill]\n",
            ),
            _completed_process(returncode=0),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            ok, detail = setup_auth._try_dispatch_sync(
                "owner/repo",
                "garmin",
                full_backfill=True,
            )

        self.assertTrue(ok)
        self.assertIn("full_backfill input is not declared", detail)

    def test_try_dispatch_sync_falls_back_when_source_input_missing(self) -> None:
        responses = [
            _completed_process(
                returncode=1,
                stderr="could not create workflow dispatch event: HTTP 422: Unexpected inputs provided: [source]\n",
            ),
            _completed_process(returncode=0),
        ]
        with mock.patch("setup_auth._run", side_effect=responses):
            ok, detail = setup_auth._try_dispatch_sync(
                "owner/repo",
                "strava",
                full_backfill=False,
            )

        self.assertTrue(ok)
        self.assertIn("workflow does not declare 'source' input", detail)


class SetupAuthMainFlowTests(unittest.TestCase):
    @staticmethod
    def _default_args() -> Namespace:
        return Namespace(
            source=None,
            no_bootstrap_env=False,
            env_bootstrapped=False,
            client_id=None,
            client_secret=None,
            garmin_token_store_b64=None,
            garmin_email=None,
            garmin_password=None,
            store_garmin_password_secrets=False,
            repo=None,
            template_repo=None,
            unit_system=None,
            week_start=None,
            port=setup_auth.DEFAULT_PORT,
            timeout=setup_auth.DEFAULT_TIMEOUT,
            scope="read,activity:read_all",
            strava_profile_url=None,
            strava_activity_links=None,
            garmin_profile_url=None,
            garmin_activity_links=None,
            custom_domain=None,
            clear_custom_domain=False,
            no_browser=True,
            no_auto_github=False,
            no_watch=True,
        )

    def _run_main_for_source(self, previous_source: str, source: str, full_backfill_prompt_result: bool) -> tuple[
        int,
        mock.MagicMock,
        mock.MagicMock,
        mock.MagicMock,
    ]:
        args = self._default_args()
        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            resolve_domain_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None))
            )
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value=previous_source))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value=source))
            prompt_mock = stack.enter_context(
                mock.patch("setup_auth._prompt_full_backfill_choice", return_value=full_backfill_prompt_result)
            )
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            week_start_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_week_start", return_value="sunday")
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_auth_values",
                    return_value=("garmin-token-b64", "user@example.com", "password"),
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_profile_link_preference",
                    return_value=(True, ""),
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_profile_url",
                    return_value="https://connect.garmin.com/modern/profile/abc",
                )
            )
            stack.enter_context(mock.patch("setup_auth._resolve_garmin_activity_links", return_value=True))
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            dispatch_mock = stack.enter_context(
                mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok"))
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            return setup_auth.main(), prompt_mock, dispatch_mock, week_start_mock

    def test_main_prompts_full_backfill_on_same_source_rerun(self) -> None:
        result, prompt_mock, dispatch_mock, week_start_mock = self._run_main_for_source(
            previous_source="garmin",
            source="garmin",
            full_backfill_prompt_result=True,
        )
        self.assertEqual(result, 0)
        prompt_mock.assert_called_once_with("garmin")
        dispatch_mock.assert_called_once_with("owner/repo", "garmin", full_backfill=True)
        week_start_mock.assert_called_once_with(mock.ANY, True, "owner/repo")

    def test_main_skips_full_backfill_prompt_when_switching_source(self) -> None:
        result, prompt_mock, dispatch_mock, week_start_mock = self._run_main_for_source(
            previous_source="strava",
            source="garmin",
            full_backfill_prompt_result=True,
        )
        self.assertEqual(result, 0)
        prompt_mock.assert_not_called()
        dispatch_mock.assert_called_once_with("owner/repo", "garmin", full_backfill=False)
        week_start_mock.assert_called_once_with(mock.ANY, True, "owner/repo")

    def test_main_skips_reuse_prompt_when_core_settings_missing(self) -> None:
        with (
            mock.patch("setup_auth._load_existing_dashboard_settings", return_value=None),
            mock.patch("setup_auth._prompt_reuse_existing_settings") as reuse_mock,
        ):
            result, _, _, _ = self._run_main_for_source(
                previous_source="garmin",
                source="garmin",
                full_backfill_prompt_result=False,
            )
        self.assertEqual(result, 0)
        reuse_mock.assert_not_called()

    def test_main_reuse_settings_path_can_skip_credential_overwrite(self) -> None:
        args = self._default_args()
        existing_settings = setup_auth.ExistingDashboardSettings(
            source="strava",
            distance_unit="mi",
            elevation_unit="ft",
            week_start="monday",
        )

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            resolve_domain_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None))
            )
            stack.enter_context(mock.patch("setup_auth._load_existing_dashboard_settings", return_value=existing_settings))
            stack.enter_context(mock.patch("setup_auth._prompt_reuse_existing_settings", return_value=True))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(
                mock.patch(
                    "setup_auth._list_secret_names",
                    return_value={
                        "STRAVA_CLIENT_ID",
                        "STRAVA_CLIENT_SECRET",
                        "STRAVA_REFRESH_TOKEN",
                    },
                )
            )
            prompt_update_mock = stack.enter_context(
                mock.patch("setup_auth._prompt_update_credentials", return_value=False)
            )
            resolve_source_mock = stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="garmin"))
            resolve_units_mock = stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("km", "m")))
            resolve_week_start_mock = stack.enter_context(mock.patch("setup_auth._resolve_week_start", return_value="sunday"))
            resolve_activity_links_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_strava_activity_links", return_value=False)
            )
            resolve_profile_pref_mock = stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_link_preference",
                    return_value=(False, ""),
                )
            )
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_strava_activity_links", return_value=True))
            stack.enter_context(
                mock.patch(
                    "setup_auth._existing_dashboard_strava_profile_url",
                    return_value="https://www.strava.com/athletes/123",
                )
            )
            resolve_profile_mock = stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_url",
                    return_value="https://www.strava.com/athletes/123",
                )
            )
            set_secret_mock = stack.enter_context(mock.patch("setup_auth._set_secret"))
            set_rotation_mock = stack.enter_context(
                mock.patch("setup_auth._try_set_strava_secret_update_token", return_value=(True, "ok"))
            )
            set_variable_mock = stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._clear_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._dashboard_url_from_pages_api",
                    return_value="https://owner.github.io/repo/",
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        resolve_domain_mock.assert_not_called()
        prompt_update_mock.assert_called_once_with()
        resolve_source_mock.assert_not_called()
        resolve_units_mock.assert_not_called()
        resolve_week_start_mock.assert_not_called()
        resolve_activity_links_mock.assert_not_called()
        resolve_profile_pref_mock.assert_not_called()
        set_secret_mock.assert_not_called()
        set_rotation_mock.assert_not_called()
        resolve_profile_mock.assert_called_once_with(
            args,
            False,
            "owner/repo",
            tokens={},
            enabled_override=True,
            prefilled_url="https://www.strava.com/athletes/123",
            prompt_if_missing=False,
        )
        self.assertIn(
            mock.call("DASHBOARD_SOURCE", "strava", "owner/repo"),
            set_variable_mock.mock_calls,
        )
        self.assertIn(
            mock.call("DASHBOARD_WEEK_START", "monday", "owner/repo"),
            set_variable_mock.mock_calls,
        )

    def test_main_sets_optional_strava_profile_variable(self) -> None:
        args = self._default_args()
        args.client_id = "client-id"
        args.client_secret = "client-secret"

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None)))
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            resolve_week_start_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_week_start", return_value="sunday")
            )
            stack.enter_context(mock.patch("setup_auth._authorize_and_get_code", return_value="auth-code"))
            stack.enter_context(
                mock.patch(
                    "setup_auth._exchange_code_for_tokens",
                    return_value={"refresh_token": "refresh-token", "athlete": {}},
                )
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._try_set_strava_secret_update_token", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_link_preference",
                    return_value=(True, ""),
                )
            )
            resolve_profile_mock = stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_url",
                    return_value="https://www.strava.com/athletes/123",
                )
            )
            resolve_activity_links_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_strava_activity_links", return_value=True)
            )
            set_variable_mock = stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        resolve_week_start_mock.assert_called_once_with(args, True, "owner/repo")
        resolve_profile_mock.assert_called_once_with(
            args,
            True,
            "owner/repo",
            tokens={"refresh_token": "refresh-token", "athlete": {}},
            enabled_override=True,
            prefilled_url="",
            prompt_if_missing=False,
        )
        resolve_activity_links_mock.assert_called_once_with(
            args,
            True,
            "owner/repo",
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_STRAVA_PROFILE_URL",
                "https://www.strava.com/athletes/123",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_REPO",
                "owner/repo",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_WEEK_START",
                "sunday",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_STRAVA_ACTIVITY_LINKS",
                "true",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )

    def test_main_sets_optional_garmin_profile_variable(self) -> None:
        args = self._default_args()

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None)))
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="garmin"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="garmin"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            resolve_week_start_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_week_start", return_value="sunday")
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_auth_values",
                    return_value=("garmin-token-b64", "user@example.com", "password"),
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_profile_link_preference",
                    return_value=(True, ""),
                )
            )
            resolve_profile_mock = stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_profile_url",
                    return_value="https://connect.garmin.com/modern/profile/123",
                )
            )
            resolve_activity_links_mock = stack.enter_context(
                mock.patch("setup_auth._resolve_garmin_activity_links", return_value=True)
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            set_variable_mock = stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        resolve_week_start_mock.assert_called_once_with(args, True, "owner/repo")
        resolve_profile_mock.assert_called_once_with(
            args,
            True,
            "owner/repo",
            token_store_b64="garmin-token-b64",
            email="user@example.com",
            password="password",
            enabled_override=True,
            prefilled_url="",
            prompt_if_missing=False,
        )
        resolve_activity_links_mock.assert_called_once_with(
            args,
            True,
            "owner/repo",
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_GARMIN_PROFILE_URL",
                "https://connect.garmin.com/modern/profile/123",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )
        self.assertIn(
            mock.call(
                "DASHBOARD_GARMIN_ACTIVITY_LINKS",
                "true",
                "owner/repo",
            ),
            set_variable_mock.mock_calls,
        )

    def test_main_strava_resolves_link_preferences_before_oauth_authorize(self) -> None:
        args = self._default_args()
        args.client_id = "client-id"
        args.client_secret = "client-secret"
        events: list[str] = []

        def _record_strava_activity_links(*_args, **_kwargs) -> bool:
            events.append("strava_activity_links")
            return False

        def _record_strava_profile_pref(*_args, **_kwargs) -> tuple[bool, str]:
            events.append("strava_profile_preference")
            return False, ""

        def _record_authorize(*_args, **_kwargs) -> str:
            events.append("strava_authorize")
            return "auth-code"

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None)))
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            stack.enter_context(mock.patch("setup_auth._resolve_week_start", return_value="sunday"))
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_activity_links",
                    side_effect=_record_strava_activity_links,
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_link_preference",
                    side_effect=_record_strava_profile_pref,
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._authorize_and_get_code",
                    side_effect=_record_authorize,
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._exchange_code_for_tokens",
                    return_value={"refresh_token": "refresh-token", "athlete": {}},
                )
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._try_set_strava_secret_update_token", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._resolve_strava_profile_url", return_value=""))
            stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._clear_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        self.assertLess(events.index("strava_activity_links"), events.index("strava_authorize"))
        self.assertLess(events.index("strava_profile_preference"), events.index("strava_authorize"))

    def test_main_garmin_resolves_link_preferences_before_auth_values(self) -> None:
        args = self._default_args()
        events: list[str] = []

        def _record_garmin_activity_links(*_args, **_kwargs) -> bool:
            events.append("garmin_activity_links")
            return True

        def _record_garmin_profile_pref(*_args, **_kwargs) -> tuple[bool, str]:
            events.append("garmin_profile_preference")
            return True, ""

        def _record_garmin_auth(*_args, **_kwargs) -> tuple[str, str, str]:
            events.append("garmin_auth_values")
            return "garmin-token-b64", "user@example.com", "password"

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(False, None)))
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="garmin"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="garmin"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            stack.enter_context(mock.patch("setup_auth._resolve_week_start", return_value="sunday"))
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_activity_links",
                    side_effect=_record_garmin_activity_links,
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_profile_link_preference",
                    side_effect=_record_garmin_profile_pref,
                )
            )
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_garmin_auth_values",
                    side_effect=_record_garmin_auth,
                )
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._resolve_garmin_profile_url", return_value=""))
            stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._clear_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        self.assertLess(events.index("garmin_activity_links"), events.index("garmin_auth_values"))
        self.assertLess(events.index("garmin_profile_preference"), events.index("garmin_auth_values"))

    def test_main_applies_custom_pages_domain_when_requested(self) -> None:
        args = self._default_args()
        args.client_id = "client-id"
        args.client_secret = "client-secret"

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(
                mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(True, "strava.nedevski.com"))
            )
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            stack.enter_context(mock.patch("setup_auth._resolve_week_start", return_value="sunday"))
            stack.enter_context(mock.patch("setup_auth._authorize_and_get_code", return_value="auth-code"))
            stack.enter_context(
                mock.patch(
                    "setup_auth._exchange_code_for_tokens",
                    return_value={"refresh_token": "refresh-token", "athlete": {}},
                )
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._try_set_strava_secret_update_token", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_link_preference",
                    return_value=(False, ""),
                )
            )
            stack.enter_context(mock.patch("setup_auth._resolve_strava_profile_url", return_value=""))
            stack.enter_context(mock.patch("setup_auth._resolve_strava_activity_links", return_value=False))
            stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._clear_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            set_domain_mock = stack.enter_context(
                mock.patch("setup_auth._try_set_pages_custom_domain", return_value=(True, "ok"))
            )
            stack.enter_context(mock.patch("setup_auth._try_clear_pages_custom_domain", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        set_domain_mock.assert_called_once_with("owner/repo", "strava.nedevski.com")

    def test_main_clears_custom_pages_domain_when_requested(self) -> None:
        args = self._default_args()
        args.client_id = "client-id"
        args.client_secret = "client-secret"

        with ExitStack() as stack:
            stack.enter_context(mock.patch("setup_auth.parse_args", return_value=args))
            stack.enter_context(mock.patch("setup_auth._bootstrap_env_and_reexec"))
            stack.enter_context(mock.patch("setup_auth._isatty", return_value=True))
            stack.enter_context(mock.patch("setup_auth._assert_gh_ready"))
            stack.enter_context(mock.patch("setup_auth._resolve_repo_slug", return_value="owner/repo"))
            stack.enter_context(mock.patch("setup_auth._assert_repo_access"))
            stack.enter_context(mock.patch("setup_auth._assert_actions_secret_access"))
            stack.enter_context(
                mock.patch("setup_auth._resolve_custom_pages_domain", return_value=(True, None))
            )
            stack.enter_context(mock.patch("setup_auth._existing_dashboard_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._resolve_source", return_value="strava"))
            stack.enter_context(mock.patch("setup_auth._prompt_full_backfill_choice", return_value=False))
            stack.enter_context(mock.patch("setup_auth._resolve_units", return_value=("mi", "ft")))
            stack.enter_context(mock.patch("setup_auth._resolve_week_start", return_value="sunday"))
            stack.enter_context(mock.patch("setup_auth._authorize_and_get_code", return_value="auth-code"))
            stack.enter_context(
                mock.patch(
                    "setup_auth._exchange_code_for_tokens",
                    return_value={"refresh_token": "refresh-token", "athlete": {}},
                )
            )
            stack.enter_context(mock.patch("setup_auth._set_secret"))
            stack.enter_context(mock.patch("setup_auth._try_set_strava_secret_update_token", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._resolve_strava_profile_link_preference",
                    return_value=(False, ""),
                )
            )
            stack.enter_context(mock.patch("setup_auth._resolve_strava_profile_url", return_value=""))
            stack.enter_context(mock.patch("setup_auth._resolve_strava_activity_links", return_value=False))
            stack.enter_context(mock.patch("setup_auth._set_variable"))
            stack.enter_context(mock.patch("setup_auth._clear_variable"))
            stack.enter_context(mock.patch("setup_auth._try_enable_actions_permissions", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_repo_issues", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_enable_workflows", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_configure_pages", return_value=(True, "ok")))
            stack.enter_context(mock.patch("setup_auth._try_set_pages_custom_domain", return_value=(True, "ok")))
            clear_domain_mock = stack.enter_context(
                mock.patch("setup_auth._try_clear_pages_custom_domain", return_value=(True, "ok"))
            )
            stack.enter_context(mock.patch("setup_auth._try_dispatch_sync", return_value=(True, "ok")))
            stack.enter_context(
                mock.patch(
                    "setup_auth._find_latest_workflow_run",
                    return_value=(123, "https://example.test/run/123"),
                )
            )
            result = setup_auth.main()

        self.assertEqual(result, 0)
        clear_domain_mock.assert_called_once_with("owner/repo")


if __name__ == "__main__":
    unittest.main()
