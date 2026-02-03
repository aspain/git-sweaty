import argparse
import os
import subprocess
from typing import Optional

from aggregate import aggregate as aggregate_func
from normalize import normalize as normalize_func
from sync_strava import sync_strava
from utils import ensure_dir, write_json
from generate_heatmaps import generate as generate_heatmaps

SUMMARY_TXT = os.path.join("data", "last_sync_summary.txt")


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


def run_pipeline(skip_sync: bool, dry_run: bool, prune_deleted: bool, commit: bool) -> None:
    if not skip_sync:
        summary = sync_strava(dry_run=dry_run, prune_deleted=prune_deleted)
        print(f"Synced: {summary}")

    items = normalize_func()
    _write_normalized(items)

    aggregates = aggregate_func()
    _write_aggregates(aggregates)

    generate_heatmaps()

    if commit and not dry_run:
        message = _summary_message("Sync Strava: update heatmaps")
        _commit_changes(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Strava sync pipeline")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune-deleted", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    run_pipeline(
        skip_sync=args.skip_sync,
        dry_run=args.dry_run,
        prune_deleted=args.prune_deleted,
        commit=args.commit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
