# Title

Precompute NOAA station coverage fractions and expose them in station selection

## Summary

Current weather-station workflow proves nearby-station discovery works, but candidate quality is still discovered too late:

- `ghcnd-stations.txt` and `ghcnd-inventory.txt` tell us where stations are and which elements exist
- they do **not** tell us how complete daily observations actually are for user target windows
- real site tests show huge precipitation gaps, especially in East Africa

This issue proposes a batch coverage-index build step for NOAA station backends, starting with `ghcn_daily`.

## Problem

Current selection flow often looks promising at metadata level, then disappoints when actual daily coverage is checked:

- Nairobi GHCN decade precip coverage examples:
  - Jomo Kenyatta: `1043 / 3653` days (`29%`) for `2011-2020`
  - Dagoretti: `252 / 3653` days (`7%`) for `2011-2020`
- Addis GHCN decade precip coverage example:
  - Addis Ababa-Bole: `1161 / 3653` days (`32%`) for `2011-2020`

This makes station ranking reactive and expensive. Toolkit should know much more up front.

## Why this matters

- users need to see candidate quality before running long compare jobs
- precipitation validation can be nearly useless if coverage is sparse
- current inventory-based ranking overstates viability
- repeated per-request station parsing wastes time
- same problem will recur for `gsod` and `global_hourly` if we do not define index pattern now

## Proposed approach

Build cached station-coverage index from NOAA station list + actual observation files.

Start with `ghcn_daily`.

For each station and variable, compute:

- archive start / end
- total observed days
- total expected days across archive span
- archive completeness fraction
- decade-window completeness fractions, at minimum:
  - `1991-2000`
  - `2001-2010`
  - `2011-2020`
  - `2021-present` if relevant
- variable-specific counts for:
  - `precipitation`
  - `max_temperature`
  - `min_temperature`
  - `mean_temperature` where present
  - optional later: `wind_speed`, `humidity`

## Expected artifacts

Suggested outputs:

- `outputs/cache/weather_stations/ghcn_daily/coverage/ghcn_daily_station_coverage.parquet`
- `outputs/cache/weather_stations/ghcn_daily/coverage/ghcn_daily_station_coverage.csv`
- optional summary QA report:
  - `outputs/cache/weather_stations/ghcn_daily/coverage/coverage_build_report.json`

Suggested schema:

- `station_id`
- `station_name`
- `lat`
- `lon`
- `elevation_m`
- `archive_start`
- `archive_end`
- `precip_days`
- `precip_expected_days`
- `precip_frac_archive`
- `precip_frac_1991_2000`
- `precip_frac_2001_2010`
- `precip_frac_2011_2020`
- `tmax_frac_archive`
- `tmax_frac_2011_2020`
- `tmin_frac_archive`
- `tmin_frac_2011_2020`
- `tavg_frac_archive`
- `last_obs_date_precip`
- `last_obs_date_tmax`
- `last_obs_date_tmin`

## How toolkit should use it

Station selection should prefer cached coverage-index values before downloading/parsing station file again.

Selection/report UX should show:

- distance
- elevation difference
- per-variable coverage fraction in requested window
- archive completeness
- last-observed date

This should appear in:

- `weather_station.download --selection-mode list`
- `weather_station.compare`
- any future map/report candidate view

## Separate-session / batch-job note

This scan is good fit for separate Codex instance or background batch task because:

- global station list is large
- many station `.dly` files must be inspected
- build may take significant wall time and network I/O on first run
- artifact can then be reused cheaply across many user requests

Recommended pattern:

1. fetch/cache station index files
2. iterate station `.dly` files
3. compute per-variable coverage fractions
4. save parquet/csv
5. later selection uses this artifact first

## Extension path

After `ghcn_daily`, extend same pattern to:

- `gsod`
- `global_hourly`
- optional crosswalk layer to `meteostat`

## Acceptance criteria

- one reusable `ghcn_daily` coverage artifact built and cached
- station selection can read coverage fractions without reparsing every station on every request
- candidate reports show per-variable coverage fractions clearly
- decade-window coverage fractions available for at least `2001-2010` and `2011-2020`
- documentation explains that inventory support != usable completeness

## Suggested implementation notes

- first implementation can be CLI script under `analysis/`
- later promote into package utility if stable
- use cache-aware incremental build:
  - skip stations already indexed unless `--refresh`
  - keep build manifest / timestamp
- consider parallel station-file parsing if safe

## Follow-on

If `ghcn_daily` coverage remains too weak for rainfall in focal regions, next step is not to force bad validation:

- add `gsod` backend
- add `global_hourly` backend
- possibly allow multi-station rainfall composite reference
