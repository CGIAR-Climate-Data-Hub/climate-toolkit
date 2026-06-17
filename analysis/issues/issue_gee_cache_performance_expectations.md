## Title

Clarify cold-cache vs warm-cache runtime expectations for GEE/Xee-backed historical workflows

## Issue body

### Summary

Historical workflows now work through the package-native GEE/Xee path, but current user-facing docs and runtime messaging still understate how different cold-cache and warm-cache behavior can be.

For end users this matters a lot:

- first run can take tens of seconds to minutes depending on source, site count, date span, and variable set
- repeat runs against same cache can be near-instant
- without clear messaging, users can mistake normal cold-cache behavior for a hang or failure

### Existing issue check

Checked open and closed issues before drafting.

No obvious existing issue covers:

- cold-cache vs warm-cache runtime expectations
- measured GEE/Xee fetch timings
- user guidance on stable project-local cache reuse

Related but distinct:

- `#74` usability issue outside VCS
- `#88` ERA5 runtime path uses GEE while repo still exposes CDS-based setup
- `#90` AgERA5 runtime uses generic GEE backend while source-specific stub remains

### What was measured

All timings below were observed on June 13, 2026 during live package testing with Earth Engine auth working and `GCP_PROJECT_ID` set.

#### Multisite fetch benchmark

Three sites, one full year (`2020-01-01` to `2020-12-31`):

- `chirps_v3_daily_rnl`, 3 sites, transformed stage, cold cache: about `22s`
- `agera_5` with `precipitation,max_temperature,min_temperature,humidity,wind_speed,solar_radiation`, 3 sites, transformed stage, cold cache: about `78s`
- warm-cache rerun for either source: about `0.75s`

#### Downstream module benchmark

Nairobi (`-1.286, 36.817`), fixed-season auto path (`03-01:05-31`):

- `climate_statistics --source auto`, cold cache: about `33.6s`
- same command, warm cache: about `0.06s`
- `season_analysis --source auto`, warm cache: immediate cache hits for both `chirps_v3_daily_rnl` and `agera_5`
- `calculate_hazards --source auto`, warm cache: immediate cache hits for both `chirps_v3_daily_rnl` and `agera_5`

### Why this matters

Package now encourages historical default path:

- precipitation from `chirps_v3_daily_rnl`
- temperature + companion variables from `agera_5`

That is sensible, but it means first-use experience can be noticeably slower than legacy single-source expectations. Users need better framing around:

- why first run is slower
- why second run is much faster
- where cache lives
- how to keep cache stable across sessions

### Suggested changes

1. Document cold-cache vs warm-cache expectations in README and module help.
2. Tell users to use stable project-local cache roots under `outputs/cache/...` for reuse across sessions.
3. Keep progress logging on by default for long GEE/Xee fetches.
4. Consider a short final line such as:
   - `Cold cache likely: first run may take longer; repeat runs should be much faster if cache is reused.`
5. Consider lightweight timing summaries in more module outputs, not only low-level fetch logs.

### Repro examples

Cold-cache multisite fetch:

```bash
env GCP_PROJECT_ID=YOUR_PROJECT_ID .venv/bin/python -m climate_tookit.fetch_data.fetch_data \
  --source chirps_v3_daily_rnl \
  --site "Nairobi,-1.286,36.817" \
  --site "Lodwar,3.119,35.5973" \
  --site "Cusco,-13.5319,-71.9675" \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --stage transformed \
  --cache-dir outputs/cache/multisite_default_pair_benchmark/chirps_v3 \
  --refresh-cache
```

Cold-cache AgERA5 companion fetch:

```bash
env GCP_PROJECT_ID=YOUR_PROJECT_ID .venv/bin/python -m climate_tookit.fetch_data.fetch_data \
  --source agera_5 \
  --site "Nairobi,-1.286,36.817" \
  --site "Lodwar,3.119,35.5973" \
  --site "Cusco,-13.5319,-71.9675" \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature,humidity,wind_speed,solar_radiation \
  --stage transformed \
  --cache-dir outputs/cache/multisite_default_pair_benchmark/agera5 \
  --refresh-cache
```

Warm-cache module rerun:

```bash
env GCP_PROJECT_ID=YOUR_PROJECT_ID .venv/bin/python -m climate_tookit.climate_statistics.statistics \
  --location=-1.286,36.817 \
  --start-year=2020 \
  --end-year=2020 \
  --source=auto \
  --fixed-season=03-01:05-31 \
  --format=json \
  --no-save
```
