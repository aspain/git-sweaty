import argparse
import os
import re
import subprocess
from typing import Optional

from aggregate import aggregate as aggregate_func
from normalize import normalize as normalize_func
from sync_strava import sync_strava
from utils import ensure_dir, write_json
from generate_heatmaps import generate as generate_heatmaps

SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")
README_MD = "README.md"
README_LIVE_SITE_RE = re.compile(
    r"(?im)^(-\s*(?:Live site:\s*\[Interactive Heatmaps\]|View the Interactive \[Activity Dashboard\])\()https?://[^)]+(\)\s*)$",
    re.IGNORECASE,
)


def _write_normalized(items):
    ensure_dir("data")
    write_json(os.path.join("data", "activities_normalized.json"), items)


def _write_aggregates(payload):
    ensure_dir("data")
    write_json(os.path.join("data", "daily_aggregates.json"), payload)


def _commit_changes(message: str) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        print("No changes to commit")
        return

    subprocess.run(
        [
            "git",
            "add",
            "data",
            "heatmaps",
            "site",
            "README.md",
        ],
        check=True,
    )
    subprocess.run(["git", "commit", "-m", message], check=True)


def _summary_message(default: str) -> str:
    if os.path.exists(SUMMARY_TXT):
        with open(SUMMARY_TXT, "r", encoding="utf-8") as f:
            line = f.readline().strip()
            if line:
                return line
    return default


def _repo_slug_from_git() -> Optional[str]:
    env_slug = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if env_slug and "/" in env_slug:
        return env_slug

    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    url = result.stdout.strip()
    # Handles:
    # - https://github.com/owner/repo.git
    # - git@github.com:owner/repo.git
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", url)
    if not m:
        return None
    return f"{m.group('owner')}/{m.group('repo')}"


def _pages_url_from_slug(slug: str) -> str:
    owner, repo = slug.split("/", 1)
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def _update_readme_live_site_link() -> None:
    if not os.path.exists(README_MD):
        return

    slug = _repo_slug_from_git()
    if not slug:
        return

    target_url = _pages_url_from_slug(slug)
    with open(README_MD, "r", encoding="utf-8") as f:
        content = f.read()

    updated = README_LIVE_SITE_RE.sub(rf"\1{target_url}\2", content, count=1)
    if updated == content:
        return

    with open(README_MD, "w", encoding="utf-8") as f:
        f.write(updated)


def run_pipeline(
    skip_sync: bool,
    dry_run: bool,
    prune_deleted: bool,
    commit: bool,
    update_readme_link: bool,
) -> None:
    if not skip_sync:
        summary = sync_strava(dry_run=dry_run, prune_deleted=prune_deleted)
        print(f"Synced: {summary}")

    items = normalize_func()
    _write_normalized(items)

    aggregates = aggregate_func()
    _write_aggregates(aggregates)

    generate_heatmaps()
    if update_readme_link:
        _update_readme_live_site_link()

    if commit and not dry_run:
        message = _summary_message("Sync Strava: update heatmaps")
        _commit_changes(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Strava sync pipeline")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune-deleted", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument(
        "--update-readme-link",
        action="store_true",
        help="Update README dashboard URL based on the current repository slug.",
    )
    args = parser.parse_args()

    run_pipeline(
        skip_sync=args.skip_sync,
        dry_run=args.dry_run,
        prune_deleted=args.prune_deleted,
        commit=args.commit,
        update_readme_link=args.update_readme_link,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
