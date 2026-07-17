<p align="center">
  <img src="./site/git-sweaty-logo.svg" alt="git-sweaty-logo" /><br>
  <sub>
    (create your own README banner like this
    <a href="https://github.com/aspain/heatmap-logo">here</a>)
  </sub>
</p>

****Note:** As of July 1, 2026, Strava [no longer allows](https://communityhub.strava.com/insider-journal-9/an-update-to-our-developer-program-13428) API access with free-tier accounts. Strava subscribers can continue using git-sweaty; free users can optionally re-run setup and switch to Garmin as a data source.**

# Workout --> Interactive Dashboard

Turn your Strava and Garmin activities into GitHub-style contribution graphs. Automatically generate a free, interactive dashboard updated daily on GitHub Pages.  

**No coding required.**  

View the Interactive [Activity Dashboard](https://espindl.github.io/git-sweaty/).  
Once setup is complete, this dashboard link will automatically update to your own GitHub Pages URL.


![Dashboard Preview](site/readme-preview-20260222a.png)

## Quick Start

### macOS / Linux

Run this in Terminal.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)
```

### Windows (requires WSL)

Run this in PowerShell.

```powershell
wsl bash -lc "bash <(curl -fsSL https://raw.githubusercontent.com/aspain/git-sweaty/main/scripts/bootstrap.sh)"
```

This path is less polished, but it maps directly to the same `bootstrap.sh` flow used on macOS/Linux, which has been more reliable.

If you would rather avoid WSL troubleshooting on Windows, use [Manual Setup (No Scripts)](#manual-setup-no-scripts).

---

#### Once Setup Starts

You will need a GitHub account. If GitHub CLI (`gh`) is not installed yet, the bootstrap script will detect a supported package manager, offer to install it, and then walk you through GitHub sign-in. On Windows, this happens inside WSL.

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

---

## Updating Your Repository

- To pull in new updates and features from the original repo, use GitHub's **Sync fork** button on your fork's `main` branch.
- Activity data is stored on a dedicated `dashboard-data` branch and deployed from there
- `main` is intentionally kept free of generated `data/` and `site/data.json` artifacts so fork sync process stays cleaner.
- After syncing, manually run [Sync Heatmaps](../../actions/workflows/sync.yml) if you want your dashboard refreshed immediately. Otherwise updates will deploy at the next scheduled run.

---

## Switching Sources Later

You can switch between `strava` and `garmin` at any time.

- Re-run `./scripts/bootstrap.sh` (or the quickstart curl command) and choose a different source.
- If you re-run setup and choose the same source, setup asks whether to force a one-time full backfill. You can also update your response for unit preference, day of week start, placing strava/garmin profle link on your dashboard, and whether you'd like activity links in the tooltips.

---

## Other Features

- The GitHub Pages site is optimized for responsive desktop/mobile viewing.
- To click activity urls while viewing on desktop, click the graph dot to freeze the tooltip in place.
- If a day contains multiple activity types, that day’s colored square is split into equal segments — one per unique activity type on that day.
- Raw activities are stored locally for processing but are not committed (`activities/raw/` is ignored). This prevents publishing detailed per-activity payloads and GPS location traces.
- If neither `sync.start_date` nor `sync.lookback_years` is set, the sync workflow backfills all available history from the selected source (i.e. Strava/Garmin).
- Strava backfill state is stored in `data/backfill_state_strava.json`; Garmin backfill state is stored in `data/backfill_state_garmin.json`. If a backfill hits API limits (unlikely), this state allows the daily refresh automation to pick back up where it left off.
- The Sync action workflow includes a toggle labeled `Reset backfill cursor and re-fetch full history for the selected source` which forces a one-time full backfill. This is useful if you add/delete/modify activities which have already been loaded.

---

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

`GARMIN_TOKENS_B64` is optional unless you explicitly run token-only config, but it is recommended for reliable scheduled syncs. Garmin's current auth flow is much more reliable when the workflow can reuse saved tokens instead of doing a fresh password login every day.

Optional but recommended for automatic Garmin token rotation:

- Add `GARMIN_SECRET_UPDATE_TOKEN` (a GitHub token with repo write access to this fork). Setup attempts to configure this automatically from your current `gh` auth session.

### 3) Run the first sync and deploy

1. Go to `Actions` -> `Sync Heatmaps`.
2. Click `Run workflow` on the `main` branch.
3. Optional: set `source` explicitly (`strava` or `garmin`) when running manually.
4. Wait for `Sync Heatmaps` to complete successfully.
5. Confirm `Deploy Pages` runs (automatically after a successful sync).
6. Open your dashboard at:
   - `https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPO_NAME/`
