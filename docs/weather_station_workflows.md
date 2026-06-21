# Weather Station Workflows

Status: current user-facing workflow guide  
Updated: 2026-06-21

This guide covers observed-station support in `climate_tookit`.

## What weather-station support is for

Toolkit weather-station layer serves two main jobs:

1. use observed daily station data directly
2. compare observed station data against historical gridded products

Current package does **not** use this module for direct future `nex_gddp`
validation. Future GCM evaluation remains separate methodological work.

## Main entry points

CLI:

- `climate-toolkit-weather-station-download`
- `climate-toolkit-weather-station-compare`
- `climate-toolkit-stats`
- `climate-toolkit-seasons`

Python API:

- `climate_tookit.download_station_data`
- `climate_tookit.compare_station_to_grids`

## Station backends

`--station-source` controls where observed data comes from.

### `ghcn_daily`

Use NOAA GHCN-Daily only.

Best for:

- daily precipitation
- daily Tmin / Tmax where available

### `gsod`

Use NOAA GSOD only.

Best for:

- broader daily temperature coverage in some places
- longer multi-year overlap in some airport-based stations

### `auto`

Rank across both NOAA backends and return best available candidates under
current guardrails.

Best for:

- first-pass exploration
- places where one NOAA backend is sparse

### `custom_csv`

Use user-supplied CSV or JSON.

Best for:

- local measured station data
- partner datasets not in NOAA backends
- historical override workflows

## Selection modes

`--selection-mode` controls how toolkit handles candidate stations.

### `list`

Inspect candidates only.

What it does:

- ranks stations
- computes variable-by-variable completeness
- writes candidate review artifacts if `--report-prefix` used
- does not proceed into normal auto station selection

Use when:

- you want to inspect nearby stations first
- you want map / CSV / JSON review bundle

### `specified`

Use exact station ID through `--station-id`.

Use when:

- you already know exact NOAA station to use

### `auto`

Toolkit selects best eligible station(s).

Use when:

- you want workflow to pick best station under current rules
- you want repeatable automated screening

## Auto selection scope

`--auto-select` controls how many stations toolkit may keep.

Accepted forms:

- `auto-1`
- `auto-2`
- `auto-3`
- `auto-<n>`
- `auto-all`

Important behavior:

- `auto-all` still respects `--max-auto-stations`
- default `--max-auto-stations` is `10`
- `auto-1` means one best eligible station
- `auto-2` and above useful when you want multi-station compare outputs

## Compare selection strategy

`climate-toolkit-weather-station-compare` also has
`--selection-strategy`.

### `all_vars_single_station`

One station must support all requested variables.

Best for:

- simpler interpretation
- one station vs one grid-cell style comparison

Tradeoff:

- may reject useful precipitation station if same station lacks temperature

### `best_per_variable`

Toolkit may use different stations for different variables.

Example:

- one station for precipitation
- another station for Tmin / Tmax

Best for:

- sparse coverage locations
- cases where no single station has all fields

Tradeoff:

- interpretation becomes less clean because metrics are no longer from one
  physical station only

## Default guardrails

Default selection rules:

- search radius: `50 km`
- max elevation difference: `500 m`
- min completeness ratio: `0.70`
- max auto-selected stations: `10`
- candidate limit: `10`
- score limit: `25`

Completeness is evaluated **per variable**, not only one overall station score.

So if you request:

- `precipitation,max_temperature,min_temperature`

Toolkit checks whether each requested field clears completeness threshold.

## Guard relaxation behavior

Default strict completeness threshold:

- `0.70`

If no station passes, toolkit relaxes completeness through:

- `0.50`
- `0.30`
- `0.10`

If still no station satisfies all requested variables, selection layer may fall
back to partial-field candidates when partial fallback is allowed.

Implications:

- `auto` can still return useful precipitation-only or temperature-only station
  depending on workflow and variable request
- `list` mode is often best way to understand what passed and what failed

## Anchor elevation

Toolkit can estimate focal-location elevation through DEM lookup.

Purpose:

- compare candidate station elevation against focal location
- enforce `--max-elevation-diff-m`

Controls:

- `--target-elevation-m`: user supplies known elevation directly
- `--no-auto-anchor-elevation`: skip automatic DEM lookup

If automatic DEM lookup unavailable:

- toolkit continues without elevation-derived guard
- terminal output states that fallback

## Candidate review workflow

Recommended first step:

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nairobi_auto_candidates \
  --open-report
```

Artifacts:

- CSV
- JSON
- HTML map

Candidate review map shows:

- focal coordinates
- nearby candidate stations
- distance lines
- rank
- completeness-scaled station markers
- source counts and scope summary

Map caveat:

- basemap uses live web tiles, so internet needed for background layer

## Download workflow

Example:

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --stage preprocessed
```

Useful switches:

- `--stage raw`
- `--stage transformed`
- `--stage preprocessed`
- `--station-id ...` with `--selection-mode specified`
- `--disable-completeness-guard`
- `--refresh-cache`

Stage meaning:

- `raw`: closest to source values and source naming
- `transformed`: units / naming harmonized
- `preprocessed`: toolkit cleaning + QC checks applied

## Custom station files

Example:

```bash
climate-toolkit-weather-station-download \
  --station-source custom_csv \
  --custom-station-file path/to/station.csv \
  --custom-station-name "My station" \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Accepted file types:

- `.csv`
- `.json`

Minimum requirements:

- `date`
- at least one requested climate variable

Accepted variable aliases include:

- precipitation:
  - `precipitation`
  - `precip`
  - `rain`
  - `rainfall`
  - `prcp`
- max temperature:
  - `max_temperature`
  - `tmax`
  - `max`
- min temperature:
  - `min_temperature`
  - `tmin`
  - `min`
- mean temperature:
  - `mean_temperature`
  - `tmean`
  - `tavg`
  - `temp`
- humidity:
  - `humidity`
  - `relative_humidity`
  - `rh`
- wind:
  - `wind_speed`
  - `wind`
  - `wdsp`
- solar:
  - `solar_radiation`
  - `solar`
  - `radiation`

Optional metadata columns:

- `station_id`
- `station_name`
- `station_lat`
- `station_lon`
- `station_elevation_m`

If metadata missing:

- toolkit fills best-effort values from CLI inputs and file name

Units:

- `--custom-temp-unit c|f|k`
- `--custom-precip-unit mm|inch|tenth_mm`

Behavior:

- columns normalized
- dates parsed and clipped to requested window
- units converted
- mean temperature derived if missing but Tmin/Tmax present
- normalized result cached for later reuse

## Station vs grid comparison

Example:

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --selection-mode auto \
  --auto-select auto-1 \
  --selection-strategy all_vars_single_station \
  --grid-source paired \
  --grid-source nasa_power \
  --precip-source chirps_v3_daily_rnl \
  --temp-source agera_5 \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid_2011_2020.json
```

Current comparison purpose:

- compare observed station data against historical gridded climate products
- identify which grid source looks most representative locally

Not current purpose:

- direct future GCM validation
- direct `nex_gddp` station benchmarking inside this CLI

### Supported grid-source family

Historical comparison path supports historical grid/reanalysis products such as:

- `agera_5`
- `era_5`
- `nasa_power`
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `paired`
- `auto`
- `terraclimate`

Not current compare targets:

- `nex_gddp`
- station backends themselves
- `tamsat`

### Independence caveat

Some gridded products are partly station-informed.

Examples:

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `chirts`
- `paired` when partner source is station-informed
- `terraclimate`

So good agreement does **not** always mean independent validation.

More independent options for historical compare often include:

- `agera_5`
- `era_5`
- `nasa_power`
- `imerg`

Toolkit already surfaces warning when comparison source is not fully independent.

## Comparison outputs

Text / JSON output can include:

- station summary
- grid fetch failures
- daily station-level metrics
- monthly aggregated metrics
- seasonal aggregated metrics
- annual overlap summary
- pooled overall metrics when multiple stations contribute
- xclim annual precipitation reference indices when overlap dense enough
- use-case ranking heuristics for practical screening

### How to read them

Daily metrics:

- useful for event timing and wet-day occurrence
- daily precipitation correlation often weak even when product is still useful

Monthly / seasonal metrics:

- often more informative for climate suitability and planning
- better for judging systematic wet/dry bias

Annual summary:

- useful only when overlap coverage is dense enough
- sparse overlap should be treated as descriptive, not strong validation

xclim annual precipitation reference indices:

- computed only when overlap is dense enough for defensible annual reference use
- skipped when station overlap too gappy

## Historical override workflow

Custom station data can override selected historical variables in:

- `climate-toolkit-stats`
- `climate-toolkit-seasons`

Example:

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=agera_5 \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation,max_temperature,min_temperature \
  --custom-station-name "My station" \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Current behavior:

- station values replace chosen historical variables by date
- gridded values remain for variables not supplied by station file
- if uploaded station file has no rows in requested window, toolkit falls back to gridded values and prints warning

## Cache layout

Project-local cache roots:

- `outputs/cache/weather_stations/ghcn_daily`
- `outputs/cache/weather_stations/gsod`
- `outputs/cache/weather_stations/custom`
- `outputs/cache/weather_stations/dem_anchor`

Typical contents:

- station metadata / inventories
- downloaded NOAA station files
- custom normalized CSV files
- custom manifest JSON files
- DEM-derived focal-elevation lookups

Custom cache behavior:

- toolkit hashes source file path + size + modification time
- cached custom outputs sit under per-file cache folder
- stage and date-window specific CSV / JSON outputs reused unless `--refresh-cache`

## Practical workflow order

Recommended sequence:

1. run `selection-mode list`
2. inspect map / CSV / completeness by variable
3. decide whether one station or multiple stations make sense
4. run `weather-station-download` or `weather-station-compare`
5. only then feed custom observed data into historical override workflows if needed

## Current limitations

- sparse station coverage in some regions
- no single backend has perfect global daily coverage
- some places have enough precipitation records but poor temperature coverage, or vice versa
- compare workflow currently targets historical products, not future NEX-GDDP
- auto mode only uses current NOAA backends plus custom files
- HTML map is review artifact, not full GIS workflow
- best-per-variable comparison improves coverage but complicates interpretation

## Related files

- `README.md`
- `analysis/weather_station_module_design_2026-06-15.md`
- `analysis/weather_station_data_access_research_2026-06-15.md`
- `analysis/issues/weather_station_compare_window_guidance.md`
