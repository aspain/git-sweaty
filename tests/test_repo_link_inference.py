import json
import os
import re
import shutil
import subprocess
import unittest
from typing import Optional


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(ROOT_DIR, "site", "app.js")


@unittest.skipUnless(shutil.which("node"), "node is required for JS unit tests")
class RepoLinkInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(APP_JS_PATH, "r", encoding="utf-8") as handle:
            app_js = handle.read()
        infer_match = re.search(
            r"function inferGitHubRepoFromLocation\(loc\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        parse_match = re.search(
            r"function parseGitHubRepo\(value\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        resolve_match = re.search(
            r"function resolveGitHubRepo\(loc, fallbackRepo\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        normalize_slug_match = re.search(
            r"function normalizeRepoSlug\(value\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        should_hide_footer_match = re.search(
            r"function shouldHideHostedFooter\(repoCandidate\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        footer_powered_label_match = re.search(
            r"function footerPoweredLabelText\(repoCandidate\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        host_match = re.search(
            r"function isGitHubHostedLocation\(loc\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        custom_url_match = re.search(
            r"function customDashboardUrlFromLocation\(loc\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        custom_label_match = re.search(
            r"function customDashboardLabelFromUrl\(url\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        header_link_match = re.search(
            r"function resolveHeaderRepoLink\(loc, fallbackRepo\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        footer_link_match = re.search(
            r"function resolveFooterHostedLink\(loc, fallbackRepo\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        strava_match = re.search(
            r"function parseStravaProfileUrl\(value\)\s*{[\s\S]*?\n}\n",
            app_js,
        )
        if (
            not infer_match
            or not parse_match
            or not resolve_match
            or not normalize_slug_match
            or not should_hide_footer_match
            or not footer_powered_label_match
            or not host_match
            or not custom_url_match
            or not custom_label_match
            or not header_link_match
            or not footer_link_match
            or not strava_match
        ):
            raise AssertionError("Could not find repo inference helpers in site/app.js")
        cls.parse_source = parse_match.group(0)
        cls.infer_source = infer_match.group(0)
        cls.resolve_source = resolve_match.group(0)
        cls.normalize_slug_source = normalize_slug_match.group(0)
        cls.should_hide_footer_source = should_hide_footer_match.group(0)
        cls.footer_powered_label_source = footer_powered_label_match.group(0)
        cls.host_source = host_match.group(0)
        cls.custom_url_source = custom_url_match.group(0)
        cls.custom_label_source = custom_label_match.group(0)
        cls.header_link_source = header_link_match.group(0)
        cls.footer_link_source = footer_link_match.group(0)
        cls.strava_parse_source = strava_match.group(0)

    def _resolve_repo(self, hostname: str, pathname: str, fallback_repo=None):
        script = (
            f"{self.parse_source}\n"
            f"{self.infer_source}\n"
            f"{self.resolve_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = resolveGitHubRepo(payload.loc, payload.fallback);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            [
                "node",
                "-e",
                script,
                json.dumps({
                    "loc": {"hostname": hostname, "pathname": pathname},
                    "fallback": fallback_repo,
                }),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _resolve_header_link(
        self,
        hostname: str,
        pathname: str,
        protocol: str = "https:",
        fallback_repo=None,
        host: Optional[str] = None,
        search: str = "",
    ):
        script = (
            f"{self.parse_source}\n"
            f"{self.infer_source}\n"
            f"{self.resolve_source}\n"
            f"{self.host_source}\n"
            f"{self.custom_url_source}\n"
            f"{self.custom_label_source}\n"
            f"{self.header_link_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = resolveHeaderRepoLink(payload.loc, payload.fallback);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            [
                "node",
                "-e",
                script,
                json.dumps({
                    "loc": {
                        "hostname": hostname,
                        "host": host,
                        "pathname": pathname,
                        "protocol": protocol,
                        "search": search,
                    },
                    "fallback": fallback_repo,
                }),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _parse_strava_profile(self, value):
        script = (
            f"{self.strava_parse_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = parseStravaProfileUrl(payload.value);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps({"value": value})],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _resolve_footer_link(
        self,
        hostname: str,
        pathname: str,
        protocol: str = "https:",
        fallback_repo=None,
        host: Optional[str] = None,
        search: str = "",
    ):
        script = (
            f"{self.parse_source}\n"
            f"{self.infer_source}\n"
            f"{self.resolve_source}\n"
            f"{self.footer_link_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = resolveFooterHostedLink(payload.loc, payload.fallback);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            [
                "node",
                "-e",
                script,
                json.dumps({
                    "loc": {
                        "hostname": hostname,
                        "host": host,
                        "pathname": pathname,
                        "protocol": protocol,
                        "search": search,
                    },
                    "fallback": fallback_repo,
                }),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _should_hide_footer_hosted(self, repo_candidate):
        script = (
            "const CREATOR_REPO_SLUG = \"aspain/git-sweaty\";\n"
            f"{self.parse_source}\n"
            f"{self.normalize_slug_source}\n"
            f"{self.should_hide_footer_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = shouldHideHostedFooter(payload.value);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps({"value": repo_candidate})],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def _footer_powered_label_text(self, repo_candidate):
        script = (
            "const CREATOR_REPO_SLUG = \"aspain/git-sweaty\";\n"
            f"{self.parse_source}\n"
            f"{self.normalize_slug_source}\n"
            f"{self.should_hide_footer_source}\n"
            f"{self.footer_powered_label_source}\n"
            "const payload = JSON.parse(process.argv[1]);\n"
            "const result = footerPoweredLabelText(payload.value);\n"
            "process.stdout.write(JSON.stringify(result));\n"
        )
        completed = subprocess.run(
            ["node", "-e", script, json.dumps({"value": repo_candidate})],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_infers_project_pages_repo(self) -> None:
        result = self._resolve_repo("aspain.github.io", "/git-sweaty/")
        self.assertEqual(result, {"owner": "aspain", "repo": "git-sweaty"})

    def test_infers_user_pages_repo_at_root(self) -> None:
        result = self._resolve_repo("aspain.github.io", "/")
        self.assertEqual(result, {"owner": "aspain", "repo": "aspain.github.io"})

    def test_infers_github_com_repo(self) -> None:
        result = self._resolve_repo("github.com", "/aspain/git-sweaty/")
        self.assertEqual(result, {"owner": "aspain", "repo": "git-sweaty"})

    def test_custom_domain_uses_payload_repo_slug_fallback(self) -> None:
        result = self._resolve_repo("subdomain.example.com", "/", "owner/repo")
        self.assertEqual(result, {"owner": "owner", "repo": "repo"})

    def test_custom_domain_uses_payload_repo_url_fallback(self) -> None:
        result = self._resolve_repo("subdomain.example.com", "/", "https://github.com/owner/repo")
        self.assertEqual(result, {"owner": "owner", "repo": "repo"})

    def test_custom_domain_returns_null_without_fallback(self) -> None:
        result = self._resolve_repo("subdomain.example.com", "/")
        self.assertIsNone(result)

    def test_header_link_prefers_repo_when_fallback_available(self) -> None:
        result = self._resolve_header_link(
            "strava.nedevski.com",
            "/",
            protocol="https:",
            fallback_repo="owner/repo",
        )
        self.assertEqual(
            result,
            {
                "href": "https://github.com/owner/repo",
                "text": "owner/repo",
            },
        )

    def test_header_link_uses_custom_domain_url_without_repo_fallback(self) -> None:
        result = self._resolve_header_link(
            "strava.nedevski.com",
            "/",
            protocol="https:",
        )
        self.assertEqual(
            result,
            {
                "href": "https://strava.nedevski.com/",
                "text": "strava.nedevski.com",
            },
        )

    def test_header_link_keeps_custom_path_and_query_without_repo_fallback(self) -> None:
        result = self._resolve_header_link(
            "strava.nedevski.com",
            "/dashboard/",
            protocol="https:",
            search="?year=2026",
        )
        self.assertEqual(
            result,
            {
                "href": "https://strava.nedevski.com/dashboard/?year=2026",
                "text": "strava.nedevski.com/dashboard?year=2026",
            },
        )

    def test_header_link_keeps_custom_port_in_label_and_href_without_repo_fallback(self) -> None:
        result = self._resolve_header_link(
            "localhost",
            "/preview/",
            protocol="http:",
            host="localhost:4173",
        )
        self.assertEqual(
            result,
            {
                "href": "http://localhost:4173/preview/",
                "text": "localhost:4173/preview",
            },
        )

    def test_header_link_falls_back_to_repo_for_non_http_protocol(self) -> None:
        result = self._resolve_header_link(
            "strava.nedevski.com",
            "/",
            protocol="file:",
            fallback_repo="owner/repo",
        )
        self.assertEqual(
            result,
            {
                "href": "https://github.com/owner/repo",
                "text": "owner/repo",
            },
        )

    def test_footer_link_uses_repo_slug_when_available(self) -> None:
        result = self._resolve_footer_link(
            "strava.nedevski.com",
            "/",
            protocol="https:",
            fallback_repo="owner/repo",
        )
        self.assertEqual(
            result,
            {
                "href": "https://github.com/owner/repo",
                "text": "owner/repo",
            },
        )

    def test_footer_link_returns_null_without_repo_slug(self) -> None:
        result = self._resolve_footer_link(
            "strava.nedevski.com",
            "/",
            protocol="https:",
        )
        self.assertIsNone(result)

    def test_footer_hides_hosted_prefix_for_creator_repo_slug(self) -> None:
        result = self._should_hide_footer_hosted("aspain/git-sweaty")
        self.assertTrue(result)

    def test_footer_hides_hosted_prefix_for_creator_repo_url(self) -> None:
        result = self._should_hide_footer_hosted("https://github.com/aspain/git-sweaty")
        self.assertTrue(result)

    def test_footer_keeps_hosted_prefix_for_other_repos(self) -> None:
        result = self._should_hide_footer_hosted("owner/repo")
        self.assertFalse(result)

    def test_footer_powered_label_capitalized_for_creator_repo(self) -> None:
        result = self._footer_powered_label_text("aspain/git-sweaty")
        self.assertEqual(result, "Powered")

    def test_footer_powered_label_lowercase_for_other_repos(self) -> None:
        result = self._footer_powered_label_text("owner/repo")
        self.assertEqual(result, "powered")

    def test_parses_valid_strava_profile_url(self) -> None:
        result = self._parse_strava_profile("https://www.strava.com/athletes/12345")
        self.assertEqual(
            result,
            {
                "href": "https://www.strava.com/athletes/12345",
                "label": "Strava",
            },
        )

    def test_rejects_non_strava_profile_url(self) -> None:
        result = self._parse_strava_profile("https://example.com/athletes/12345")
        self.assertIsNone(result)

    def test_parses_valid_garmin_profile_url(self) -> None:
        result = self._parse_strava_profile("https://connect.garmin.com/modern/profile/abcd-1234")
        self.assertEqual(
            result,
            {
                "href": "https://connect.garmin.com/modern/profile/abcd-1234",
                "label": "Garmin",
            },
        )

    def test_rejects_non_profile_garmin_url(self) -> None:
        result = self._parse_strava_profile("https://connect.garmin.com/modern/activity/12345")
        self.assertIsNone(result)

    def test_parses_valid_garmin_profile_url_with_trailing_segments(self) -> None:
        result = self._parse_strava_profile("https://connect.garmin.com/modern/profile/abcd-1234/activities")
        self.assertEqual(
            result,
            {
                "href": "https://connect.garmin.com/modern/profile/abcd-1234",
                "label": "Garmin",
            },
        )


    def test_parses_valid_intervals_profile_url(self) -> None:
        result = self._parse_strava_profile("https://intervals.icu/athlete/i12345/")
        self.assertEqual(
            result,
            {
                "href": "https://intervals.icu/athlete/i12345",
                "label": "intervals.icu",
                "provider": "intervals",
            },
        )

    def test_accepts_bare_intervals_host_profile_url(self) -> None:
        result = self._parse_strava_profile("https://intervals.icu/")
        self.assertEqual(result, {"href": "https://intervals.icu", "label": "intervals.icu", "provider": "intervals"})

    def test_rejects_bare_strava_host_profile_url(self) -> None:
        result = self._parse_strava_profile("https://www.strava.com/")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
