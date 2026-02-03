# Workout -> GitHub Heatmap

Sync Strava activities, normalize and aggregate them, and generate GitHub-style calendar heatmaps (SVG) per workout type/year. The heatmaps are embedded in this README and optionally rendered on a GitHub Pages site.

Live site: [Interactive Heatmaps](https://aspain.github.io/git-sweaty/)

## Quick start

1. Install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Add your Strava credentials to `config.local.yaml` (this file is ignored by git):

```yaml
strava:
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  refresh_token: "YOUR_REFRESH_TOKEN"
```

3. Run the pipeline:

```bash
python scripts/run_pipeline.py --commit
```

This will:
- sync raw activities into `activities/raw/`
- normalize into `data/activities_normalized.json`
- aggregate into `data/daily_aggregates.json`
- generate SVGs in `heatmaps/`
- update the README heatmap section
- build `site/data.json`
- commit the changes (one commit per run)

## Configuration

Base settings live in `config.yaml`. Put secrets in `config.local.yaml`.

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

## GitHub Actions (optional)

Add secrets to your repo:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`

Then enable the scheduled workflow in `.github/workflows/sync.yml`.

## Notes

- `activities/raw/` contains raw Strava payloads. Keep or prune based on your privacy needs.
- SVGs are deterministic and contain `<title>` tooltips for hover details.
- README updates automatically between the `HEATMAPS:START` and `HEATMAPS:END` markers.
- The sync script rate-limits to free Strava API caps (200 overall / 15 min, 2,000 overall daily; 100 read / 15 min, 1,000 read daily). Initial backfill may take multiple days; the cursor is stored in `data/backfill_state.json` and resumes automatically. Once backfill is complete, only the recent sync runs.

<!-- HEATMAPS:START -->
## Heatmaps

### Run

![Run 2026](heatmaps/Run/2026.svg)
![Run 2025](heatmaps/Run/2025.svg)
![Run 2024](heatmaps/Run/2024.svg)
![Run 2023](heatmaps/Run/2023.svg)
![Run 2022](heatmaps/Run/2022.svg)
![Run 2021](heatmaps/Run/2021.svg)
![Run 2020](heatmaps/Run/2020.svg)
![Run 2019](heatmaps/Run/2019.svg)

### Ride

![Ride 2026](heatmaps/Ride/2026.svg)
![Ride 2025](heatmaps/Ride/2025.svg)
![Ride 2024](heatmaps/Ride/2024.svg)
![Ride 2023](heatmaps/Ride/2023.svg)
![Ride 2022](heatmaps/Ride/2022.svg)
![Ride 2021](heatmaps/Ride/2021.svg)
![Ride 2020](heatmaps/Ride/2020.svg)
![Ride 2019](heatmaps/Ride/2019.svg)

### WeightTraining

![WeightTraining 2026](heatmaps/WeightTraining/2026.svg)
![WeightTraining 2025](heatmaps/WeightTraining/2025.svg)
![WeightTraining 2024](heatmaps/WeightTraining/2024.svg)
![WeightTraining 2023](heatmaps/WeightTraining/2023.svg)
![WeightTraining 2022](heatmaps/WeightTraining/2022.svg)
![WeightTraining 2021](heatmaps/WeightTraining/2021.svg)
![WeightTraining 2020](heatmaps/WeightTraining/2020.svg)
![WeightTraining 2019](heatmaps/WeightTraining/2019.svg)
<!-- HEATMAPS:END -->
