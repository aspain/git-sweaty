# Workout -> GitHub Heatmap

Sync Strava activities, normalize and aggregate them, and generate GitHub-style calendar heatmaps (SVG) per workout type/year. The heatmaps are embedded in this README and optionally rendered on a GitHub Pages site.

- Live site: [Interactive Heatmaps](https://aspain.github.io/git-sweaty/)
- Last updated: <!-- UPDATED:START -->2026-02-03 18:08 UTC<!-- UPDATED:END -->
- Note: The GitHub Pages site is optimized for responsive desktop/mobile viewing.

## Strava App Setup

Create a Strava API application at [Strava API Settings](https://www.strava.com/settings/api). Use `localhost` for the **Authorization Callback Domain**.

## Quick start (GitHub Actions only)

1. Generate a **refresh token** via OAuth (the token shown on the Strava API page often does **not** work):

Open this URL in your browser (replace `CLIENT_ID`):

```
https://www.strava.com/oauth/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=read,activity:read_all
```

After approval you’ll be redirected to a `localhost` URL that won’t load. That’s expected. Copy the `code` from the URL and exchange it:

```bash
curl -X POST https://www.strava.com/oauth/token \
  -d client_id=CLIENT_ID \
  -d client_secret=CLIENT_SECRET \
  -d code=THE_CODE_FROM_THE_URL \
  -d grant_type=authorization_code
```

Copy the `refresh_token` from the response.

2. Add GitHub secrets (repo → Settings → Secrets and variables → Actions):
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN` (from the OAuth exchange above)

3. Run the workflow:
Go to **Actions → Sync Strava Heatmaps → Run workflow**.

This will:
- sync raw activities into `activities/raw/`
- normalize into `data/activities_normalized.json`
- aggregate into `data/daily_aggregates.json`
- generate SVGs in `heatmaps/`
- update the README heatmap section
- build `site/data.json`
- commit the changes (one commit per run)

## Configuration

Base settings live in `config.yaml`. Secrets are injected by GitHub Actions at runtime (no local `config.local.yaml` needed).

Key options:
- `sync.lookback_years` (default 5)
- `sync.start_date` (YYYY-MM-DD, overrides lookback_years)
- `sync.recent_days` (sync recent activities even while backfilling)
- `sync.resume_backfill` (persist cursor to continue older pages across days)
- `activities.types` (activity types to include)
- `activities.type_aliases` (map Strava types to your canonical types)
- `units.distance` (`mi` or `km`)
- `units.elevation` (`ft` or `m`)
- `rate_limits.*` (free Strava API throttling caps)

## GitHub Actions

Add secrets to your repo:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`

Then enable the scheduled workflow in `.github/workflows/sync.yml`.

## Notes

- Raw activities are stored locally for processing but are not committed (`activities/raw/` is ignored).
- Normalized data does not include Strava activity URLs.
- SVGs are deterministic and optimized for README rendering.
- README updates automatically between the `HEATMAPS:START` and `HEATMAPS:END` markers.
- The sync script rate-limits to free Strava API caps (200 overall / 15 min, 2,000 overall daily; 100 read / 15 min, 1,000 read daily). Initial backfill may take multiple days; the cursor is stored in `data/backfill_state.json` and resumes automatically. Once backfill is complete, only the recent sync runs.

<!-- HEATMAPS:START -->
## Heatmaps

Heatmaps are published on the GitHub Pages site linked above.

Preview:

![Run 2025](heatmaps/Run/2025.svg)
<!-- HEATMAPS:END -->
