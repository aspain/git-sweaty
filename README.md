# Workout --> Interactive Dashboard

Turn your Strava and Garmin activities into GitHub-style contribution graphs. Automatically generate a free, interactive dashboard updated daily on GitHub Pages.  

**No coding required.**  

View the Interactive [Activity Dashboard](https://iaewing.github.io/git-sweaty/).  
Once setup is complete, this dashboard link will automatically update to your own GitHub Pages URL.


![Dashboard Preview](site/readme-preview-20260222a.png)

## Quick Start

### macOS / Linux

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)
```

### Windows (requires WSL)

Run this in PowerShell.

```powershell
wsl bash -lc "bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)"
```

You will be prompted for:
- Setup mode:
  - Recommended (Online-only, no local clone): setup script will either:
    - use an existing fork
    - create a new fork
    - configure an existing writable repo
  - Advanced (Local clone + git remotes): setup script will prefer an existing compatible local clone when available, or guide fork-and-clone setup, then complete the rest of the setup.
  - Manual (No setup scripts): follow [Manual Setup (No Scripts)](#manual-setup-no-scripts)
- GitHub Pages custom domain (if you have one, for example `yoursite.example.com`)
- Source (`strava` or `garmin`)
- Unit preference (`US` or `Metric`)
- Heatmap week start (`Sunday` or `Monday`)
- Optional profile link in the dashboard header for the selected source (`Yes` or `No`)
- Optional tooltip links to individual activities for the selected source (`Yes` or `No`)
- Source auth credentials:
  - Strava: prompt will provide a link to create a [Strava API application](https://www.strava.com/settings/api) first, set Authorization Callback Domain to `localhost`.
    - Then paste the `client_id` + `client_secret` values in the prompt, then a browser tab will open for OAuth approval
  - Garmin: account email + password

The setup may take several minutes to complete when run for the first time. If any automation step fails, the script prints steps to remedy the failed step.  
Once the script succeeds, it will provide the URL for your dashboard.

### Updating Your Repository

- To pull in new updates and features from the original repo, use GitHub's **Sync fork** button on your fork's `main` branch.
- Activity data is stored on a dedicated `dashboard-data` branch and deployed from there
- `main` is intentionally kept free of generated `data/` and `site/data.json` artifacts so fork sync process stays cleaner.
- After syncing, manually run [Sync Heatmaps](../../actions/workflows/sync.yml) if you want your dashboard refreshed immediately. Otherwise updates will deploy at the next scheduled run.

### Switching Sources Later

You can switch between `strava` and `garmin` at any time.

- Re-run `./scripts/bootstrap.sh` (or the quickstart curl command) and choose a different source.
- If you re-run setup and choose the same source, setup asks whether to force a one-time full backfill. You can also update your response for unit preference, day of week start, placing strava/garmin profle link on your dashboard, and whether you'd like activity links in the tooltips.

## Other Features

- The GitHub Pages site is optimized for responsive desktop/mobile viewing.
- To click activity urls while viewing on desktop, click the graph dot to freeze the tooltip in place.
- If a day contains multiple activity types, that day’s colored square is split into equal segments — one per unique activity type on that day.
- Raw activities are stored locally for processing but are not committed (`activities/raw/` is ignored). This prevents publishing detailed per-activity payloads and GPS location traces.
- If neither `sync.start_date` nor `sync.lookback_years` is set, the sync workflow backfills all available history from the selected source (i.e. Strava/Garmin).
- Strava backfill state is stored in `data/backfill_state_strava.json`; Garmin backfill state is stored in `data/backfill_state_garmin.json`. If a backfill hits API limits (unlikely), this state allows the daily refresh automation to pick back up where it left off.
- The Sync action workflow includes a toggle labeled `Reset backfill cursor and re-fetch full history for the selected source` which forces a one-time full backfill. This is useful if you add/delete/modify activities which have already been loaded.

## Configuration (Optional)

Everything in this section is optional. Defaults work without changes.
Base settings live in `config.yaml`, and `config.local.yaml` overrides them when present.

Auth + source settings:
- `source` (`strava` or `garmin`)
- `strava.client_id`, `strava.client_secret`, `strava.refresh_token`, `strava.profile_url`
- `strava.include_activity_urls` (when `true`, yearly tooltip details include links to individual Strava activities)
- `garmin.token_store_b64`, `garmin.email`, `garmin.password`, `garmin.profile_url`
- `garmin.include_activity_urls` (when `true`, yearly tooltip details include links to individual Garmin activities)
- `garmin.strict_token_only` (when `true`, Garmin sync requires `garmin.token_store_b64` and does not fall back to email/password auth)

Sync scope + backfill behavior:
- `sync.start_date` (optional `YYYY-MM-DD` lower bound for history)
- `sync.lookback_years` (optional rolling lower bound; used only when `sync.start_date` is unset)
- `sync.recent_days` (sync recent activities even while backfilling)
- `sync.resume_backfill` (persist cursor so backfills continue across scheduled runs)
- `sync.per_page` (page size used when fetching provider activities; default `200`)
- `sync.prune_deleted` (remove local activities no longer returned by the provider; pruning only happens on runs that perform a full backfill scan)

Activity type behavior:
- `activities.types` (featured order in UI, and acts as allowlist when `activities.include_all_types` is `false`)
- `activities.include_all_types` (when `true`, include all seen sport types; when `false`, include only `activities.types`)
- `activities.exclude_types` (explicit type exclusions, even when `include_all_types` is `true`)
- `activities.type_aliases` (map raw provider type names to canonical type names before grouping/filtering)
- `activities.group_aliases` (map canonical type names to explicit grouped labels)
- `activities.group_other_types` (when `true`, non-featured types are grouped into broader buckets; repo default is `false`)
- `activities.other_bucket` (fallback group name when grouped type matching has no hit)

Display + rate-limit settings:
- `units.distance` (`mi` or `km`)
- `units.elevation` (`ft` or `m`)
- `heatmaps.week_start` (`sunday` or `monday`)
- `rate_limits.*` (Strava API pacing caps used by sync; ignored for Garmin)

## Manual Setup (No Scripts)

Use this if you do not want to run `bootstrap.sh` or `setup_auth.py`.

### 1) Shared steps (Strava + Garmin)

1. Fork this repository on GitHub.
2. In your fork, keep `main` current with upstream using **Sync fork**.
3. In your fork, enable GitHub Actions workflows:
   - `Settings` -> `Actions` -> `General`
4. In your fork, set GitHub Pages to deploy from Actions:
   - `Settings` -> `Pages` -> `Source` -> `GitHub Actions`
5. In your fork, add these repository variables:
   - `Settings` -> `Secrets and variables` -> `Actions` -> `Variables`
   - `DASHBOARD_SOURCE`: `strava` or `garmin`
   - `DASHBOARD_REPO`: your fork slug (example: `yourname/git-sweaty`)
   - `DASHBOARD_DISTANCE_UNIT`: `mi` or `km`
   - `DASHBOARD_ELEVATION_UNIT`: `ft` or `m`
   - `DASHBOARD_WEEK_START`: `sunday` or `monday`
6. Optional variables for dashboard links:
   - Strava: `DASHBOARD_STRAVA_PROFILE_URL`, `DASHBOARD_STRAVA_ACTIVITY_LINKS` (`true`/`false`)
   - Garmin: `DASHBOARD_GARMIN_PROFILE_URL`, `DASHBOARD_GARMIN_ACTIVITY_LINKS` (`true`/`false`)

### 2) Provider auth secrets

Set repository secrets here:
- `Settings` -> `Secrets and variables` -> `Actions` -> `Secrets`

#### Strava secrets

1. Create a Strava API app at [strava.com/settings/api](https://www.strava.com/settings/api).
2. Set `Authorization Callback Domain` to `localhost`.
3. Save your Strava `Client ID` and `Client Secret`.
4. Open this URL in a browser (replace `YOUR_CLIENT_ID`):

```text
https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%2Fexchange_token&approval_prompt=force&scope=read%2Cactivity%3Aread_all
```

5. Approve access. You will be redirected to a localhost URL. Copy the `code` value from that URL.
6. Exchange the code for tokens:

```bash
curl -sS -X POST https://www.strava.com/oauth/token \
  -d client_id=YOUR_CLIENT_ID \
  -d client_secret=YOUR_CLIENT_SECRET \
  -d code=YOUR_CODE \
  -d grant_type=authorization_code
```

7. From the response JSON, copy `refresh_token`.
8. Add these secrets to your fork:
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `STRAVA_REFRESH_TOKEN`
9. Optional but recommended for automatic token rotation:
   - Add `STRAVA_SECRET_UPDATE_TOKEN` (a GitHub token with repo write access to this fork).

#### Garmin secrets

Choose one auth path:

1. Easiest: add both
   - `GARMIN_EMAIL`
   - `GARMIN_PASSWORD`
2. Token-only path: add
   - `GARMIN_TOKENS_B64`

`GARMIN_TOKENS_B64` is optional unless you explicitly run token-only config.

### 3) Run the first sync and deploy

1. Go to `Actions` -> `Sync Heatmaps`.
2. Click `Run workflow` on the `main` branch.
3. Optional: set `source` explicitly (`strava` or `garmin`) when running manually.
4. Wait for `Sync Heatmaps` to complete successfully.
5. Confirm `Deploy Pages` runs (automatically after a successful sync).
6. Open your dashboard at:
   - `https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/`
