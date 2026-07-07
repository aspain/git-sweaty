import argparse
import json
import os
import re
import subprocess
import urllib.request
from typing import Optional

from aggregate import aggregate as aggregate_func
from normalize import normalize as normalize_func
from repo_helpers import (
    choose_repo_slug_from_env,
    normalize_dashboard_url,
    normalize_repo_slug,
    pages_url_from_slug,
)
from sync_dropbox import sync_dropbox
from sync_garmin import sync_garmin
from sync_strava import sync_strava
from utils import ensure_dir, load_config, normalize_source, write_json
from generate_heatmaps import generate as generate_heatmaps

README_MD = "README.md"
SOURCE_STATE_PATH = os.path.join("data", "source_state.json")
RESETTABLE_OUTPUTS = [
    os.path.join("data", "activities_normalized.json"),
    os.path.join("data", "daily_aggregates.json"),
    os.path.join("data", "last_sync_summary.json"),
    os.path.join("data", "last_sync_summary.txt"),
    os.path.join("site", "data.json"),
]
RESETTABLE_STATE_FILES = [
    os.path.join("data", "source_state.json"),
    os.path.join("data", "backfill_state.json"),
    os.path.join("data", "backfill_state_strava.json"),
    os.path.join("data", "backfill_state_garmin.json"),
    os.path.join("data", "backfill_state_dropbox.json"),
    os.path.join("data", "athletes.json"),
    os.path.join("data", "athletes_strava.json"),
    os.path.join("data", "athletes_garmin.json"),
]
RESETTABLE_RAW_DIRS = [
    os.path.join("activities", "raw"),
    os.path.join("activities", "raw", "strava"),
    os.path.join("activities", "raw", "garmin"),
    os.path.join("activities", "raw", "dropbox"),
]
SOURCE_HINT_STRAVA = "strava"
SOURCE_HINT_GARMIN = "garmin"
SOURCE_HINT_DROPBOX = "dropbox"
SOURCE_HINT_MIXED = "mixed"
README_LIVE_SITE_RE = re.compile(
    r"(?im)^([ \t]*(?:-\s*)?(?:Live site:\s*\[Interactive Heatmaps\]|View the Interactive \[Activity Dashboard\])\()https?://[^)]+(\)[ \t]*\.?[ \t]*)$",
    re.IGNORECASE,
)


def _write_normalized(items):
    ensure_dir("data")
    write_json(os.path.join("data", "activities_normalized.json"), items)


def _write_aggregates(payload):
    ensure_dir("data")
    write_json(os.path.join("data", "daily_aggregates.json"), payload)


def _repo_slug_from_git() -> Optional[str]:
    env_slug = choose_repo_slug_from_env(
        dashboard_repo=os.environ.get("DASHBOARD_REPO", ""),
        github_repository=os.environ.get("GITHUB_REPOSITORY", ""),
        github_actions=os.environ.get("GITHUB_ACTIONS", ""),
    )
    if env_slug:
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

    return normalize_repo_slug(result.stdout.strip())


def _pages_url_from_slug(slug: str) -> str:
    return pages_url_from_slug(slug)


def _normalize_dashboard_url(value: str) -> str:
    return normalize_dashboard_url(value)


def _dashboard_url_from_pages_api(repo_slug: str) -> Optional[str]:
    slug = str(repo_slug or "").strip()
    if not slug or "/" not in slug:
        return None

    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        return None

    request = urllib.request.Request(
        f"https://api.github.com/repos/{slug}/pages",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "git-sweaty-run-pipeline",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
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


def _update_readme_live_site_link() -> None:
    if not os.path.exists(README_MD):
        return

    slug = _repo_slug_from_git()
    if not slug:
        return

    target_url = _dashboard_url_from_pages_api(slug) or _pages_url_from_slug(slug)
    with open(README_MD, "r", encoding="utf-8") as f:
        content = f.read()

    updated = README_LIVE_SITE_RE.sub(rf"\1{target_url}\2", content, count=1)
    if updated == content:
        return

    with open(README_MD, "w", encoding="utf-8") as f:
        f.write(updated)


def _load_last_source() -> Optional[str]:
    if not os.path.exists(SOURCE_STATE_PATH):
        return None
    try:
        import json

        with open(SOURCE_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("source")
    if not isinstance(value, str):
        return None
    return value


def _persist_source(source: str) -> None:
    ensure_dir("data")
    write_json(SOURCE_STATE_PATH, {"source": source})


def _clear_outputs_for_source_switch() -> None:
    for path in RESETTABLE_OUTPUTS:
        if os.path.exists(path):
            os.remove(path)


def _clear_state_for_source_switch() -> None:
    for path in RESETTABLE_STATE_FILES:
        if os.path.exists(path):
            os.remove(path)
    for path in RESETTABLE_RAW_DIRS:
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path)


def _reset_for_source_switch() -> None:
    _clear_outputs_for_source_switch()
    _clear_state_for_source_switch()


def _detect_persisted_source_hint() -> Optional[str]:
    has_strava_state = os.path.exists(os.path.join("data", "backfill_state_strava.json"))
    has_garmin_state = os.path.exists(os.path.join("data", "backfill_state_garmin.json"))
    has_dropbox_state = os.path.exists(os.path.join("data", "backfill_state_dropbox.json"))
    has_strava_raw = os.path.isdir(os.path.join("activities", "raw", "strava"))
    has_garmin_raw = os.path.isdir(os.path.join("activities", "raw", "garmin"))
    has_dropbox_raw = os.path.isdir(os.path.join("activities", "raw", "dropbox"))

    has_strava = has_strava_state or has_strava_raw
    has_garmin = has_garmin_state or has_garmin_raw
    has_dropbox = has_dropbox_state or has_dropbox_raw
    present = [
        hint
        for hint, flag in (
            (SOURCE_HINT_STRAVA, has_strava),
            (SOURCE_HINT_GARMIN, has_garmin),
            (SOURCE_HINT_DROPBOX, has_dropbox),
        )
        if flag
    ]
    if len(present) > 1:
        return SOURCE_HINT_MIXED
    if present:
        return present[0]
    return None


def _sync_for_source(source: str, dry_run: bool, prune_deleted: bool):
    if source == "strava":
        return sync_strava(dry_run=dry_run, prune_deleted=prune_deleted)
    if source == "garmin":
        return sync_garmin(dry_run=dry_run, prune_deleted=prune_deleted)
    if source == "dropbox":
        return sync_dropbox(dry_run=dry_run, prune_deleted=prune_deleted)
    raise ValueError(f"Unsupported source '{source}'")


def run_pipeline(
    skip_sync: bool,
    dry_run: bool,
    prune_deleted: bool,
    update_readme_link: bool,
) -> None:
    config = load_config()
    source = normalize_source(config.get("source", "strava"))
    previous_source = _load_last_source()
    if previous_source and previous_source != source:
        print(
            f"Source changed from {previous_source} to {source}; "
            "resetting persisted outputs, backfill state, and raw caches for a full fresh sync."
        )
        _reset_for_source_switch()
    elif (
        previous_source is None
        and os.path.exists(os.path.join("data", "activities_normalized.json"))
    ):
        source_hint = _detect_persisted_source_hint()
        should_reset = False
        if source_hint == SOURCE_HINT_MIXED:
            print(
                "No saved source marker found and both Strava and Garmin persisted state were detected; "
                "resetting persisted outputs, backfill state, and raw caches to avoid mixed-source history."
            )
            should_reset = True
        elif source_hint and source_hint != source:
            print(
                f"No saved source marker found and persisted state suggests '{source_hint}' history; "
                f"selected source is '{source}', so resetting persisted outputs, backfill state, and raw caches."
            )
            should_reset = True
        elif source != "strava":
            print(
                "No saved source marker found; resetting persisted outputs, backfill state, "
                "and raw caches to avoid mixed-source history."
            )
            should_reset = True

        if should_reset:
            _reset_for_source_switch()

    if not skip_sync:
        summary = _sync_for_source(source, dry_run=dry_run, prune_deleted=prune_deleted)
        print(f"Synced ({source}): {summary}")

    items = normalize_func()
    _write_normalized(items)

    aggregates = aggregate_func()
    _write_aggregates(aggregates)

    generate_heatmaps(write_svgs=False)
    if not dry_run:
        _persist_source(source)
    if update_readme_link:
        _update_readme_live_site_link()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run activity sync pipeline")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune-deleted", action="store_true")
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
        update_readme_link=args.update_readme_link,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
