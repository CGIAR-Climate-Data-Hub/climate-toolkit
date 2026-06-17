# Weather Station Comparison Module Design

Date: 2026-06-15

## Purpose

Provide a separate module that uses observed weather station data as a real-world reference for comparing gridded climate products at or near a user-supplied location.

This module should:

1. Discover nearby candidate weather stations.
2. Rank stations by suitability, not just distance.
3. Download station observations for the overlap period.
4. Download matching gridded climate series for the same coordinates and dates.
5. Compare station vs gridded products.
6. Recommend which gridded products appear most reliable for the region and variable.

## Important Scope Constraint

Historical and future comparisons must stay separate.

- `station vs historical gridded` is a direct validation task.
- `station vs NEX-GDDP historical` is also a direct validation task.
- `station vs NEX-GDDP future` is not direct validation.

So the module should validate:

1. station vs observed/reanalysis historical products
2. station vs NEX-GDDP historical

Then future NEX-GDDP should be interpreted using the historical skill context, not compared directly to station observations.

## Additional Observational Caveat

Some gridded historical products are themselves influenced by station observations or interpolation between stations.

Implication:

- a strong match between grid and station does not always mean the grid product is independently skillful
- comparison results should be interpreted as `agreement with station-based reference`, not always as fully independent validation
- this matters especially for station-informed rainfall or temperature products

The module should expose this in product metadata and user-facing notes.

## Recommended Station Backends

Primary:

- `ghcn_daily`

Optional:

- `global_hourly`
- `gsod`
- `meteostat`

Recommended default:

- Use `ghcn_daily` for daily precipitation, Tmin, Tmax, and Tavg-style climate validation.
- Use `global_hourly` later where sub-daily validation is needed.
- Use `meteostat` mainly for convenience discovery or fallback, not as the only observational backend.

## Bundled Station Metadata

The package should ship station metadata, but not the observations.

### Recommended built-in files

```text
climate_tookit/data/stations/ghcn_daily_stations.parquet
climate_tookit/data/stations/global_hourly_stations.parquet
climate_tookit/data/stations/README.md
```

Optional later:

```text
climate_tookit/data/stations/gsod_stations.parquet
climate_tookit/data/stations/meteostat_station_crosswalk.parquet
```

### Why Parquet

- compact
- fast filtering
- preserves schema cleanly
- easier than fixed-width raw metadata at runtime

## Station Index Schema

### Core station table

One row per station per source.

Required columns:

| Column | Type | Notes |
|---|---|---|
| `source` | string | `ghcn_daily`, `global_hourly`, `gsod`, `meteostat` |
| `station_id` | string | source-native ID |
| `station_name` | string | normalized display name |
| `country_code` | string | ISO-ish code if available |
| `admin1` | string | region/state/province if available |
| `latitude` | float | decimal degrees |
| `longitude` | float | decimal degrees |
| `elevation_m` | float | meters above sea level |
| `start_date` | date | earliest known observation date |
| `end_date` | date | latest known observation date |
| `is_active` | bool | end date close to present |
| `has_prcp` | bool | daily precipitation available |
| `has_tmin` | bool | daily Tmin available |
| `has_tmax` | bool | daily Tmax available |
| `has_tavg` | bool | daily Tavg available |
| `has_wind` | bool | daily wind available |
| `has_rhum` | bool | daily humidity available |
| `has_pres` | bool | daily pressure available |
| `completeness_prcp` | float | 0-1 summary completeness if known |
| `completeness_temp` | float | 0-1 summary completeness if known |
| `network` | string | network/provider label if known |
| `wmo_id` | string | optional |
| `icao_id` | string | optional |
| `usaf_id` | string | optional |
| `ghcn_id` | string | optional crosswalk |
| `timezone` | string | optional |
| `metadata_version` | string | packaged metadata release stamp |

### Optional coverage-by-variable table

One row per station-variable.

| Column | Type | Notes |
|---|---|---|
| `source` | string | backend |
| `station_id` | string | source-native ID |
| `variable` | string | `precipitation`, `min_temperature`, etc. |
| `start_date` | date | variable-specific start |
| `end_date` | date | variable-specific end |
| `completeness` | float | 0-1 |
| `n_obs_days` | int | if known |

This second table is useful because `prcp` and `tmin/tmax` coverage often differ.

## Lat/Lon Handling

Coordinates used for caching and matching should be normalized.

Recommended convention:

- round lat/lon to `4` decimal places for cache keys and folder names
- preserve full precision internally in data frames

Reason:

- `4` decimal places is about `11 m` at the equator
- avoids fake uniqueness like `31.111111111111111` vs `31.11111`

Recommended cache token style:

```text
lat_m1p2860_lon_36p8170
```

## Station Discovery API

Recommended function:

```python
find_nearby_stations(
    lat: float,
    lon: float,
    variables: list[str],
    source: str = "ghcn_daily",
    radius_km: float = 150.0,
    max_results: int = 20,
    max_elev_diff_m: float | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame
```

Returned columns should include:

- station metadata
- `distance_km`
- `elevation_diff_m` if target elevation known
- variable overlap flags
- overlap days in requested window
- ranking score
- ranking components

## Target Elevation

If user does not supply elevation, estimate it from a DEM or leave elevation penalty inactive.

Recommended behavior:

- `target_elevation_m` optional input
- if absent, try a DEM lookup
- if still absent, do not penalize elevation difference

## Ranking Logic

Nearest station is not enough.

The station ranking should combine:

1. distance
2. elevation difference
3. overlap with requested dates
4. variable availability
5. completeness
6. recency

### Recommended score

Use a weighted score on `0-100`.

```text
station_score =
  30 * distance_score
  + 20 * elevation_score
  + 20 * overlap_score
  + 15 * completeness_score
  + 10 * variable_score
  +  5 * recency_score
```

### Component definitions

#### 1. Distance score

```text
distance_score = max(0, 1 - distance_km / radius_km)
```

This is simple and transparent. Later we can replace it with an exponential decay.

#### 2. Elevation score

If target elevation available:

```text
elevation_score = max(0, 1 - abs(elevation_diff_m) / 1000)
```

If target elevation unavailable:

- set `elevation_score = 0.5`
- label as `elevation_unknown = True`

#### 3. Overlap score

For requested window:

```text
overlap_score = overlap_days / requested_days
```

If requested dates absent, compute based on station archive span.

#### 4. Completeness score

Use variable-specific completeness if available. If several variables requested, take the mean of required variables.

```text
completeness_score = mean(variable completeness over requested variables)
```

#### 5. Variable score

Binary suitability for required variables:

```text
variable_score = n_required_variables_present / n_required_variables
```

#### 6. Recency score

Prefer recently active stations:

```text
recency_score =
  1.0 if end_date within 2 years of today
  0.7 if within 5 years
  0.4 if within 10 years
  0.1 otherwise
```

## Hard Filters Before Ranking

Apply these before computing the final ranked list:

1. Must have all required variables unless `allow_partial=True`
2. Must overlap requested period by at least `min_overlap_days`
3. Must be within `radius_km`
4. If `max_elev_diff_m` supplied, must satisfy it

Recommended defaults:

- `radius_km=150`
- `min_overlap_days=365` for annual comparison
- `min_overlap_days=90` for seasonal comparison

## Observation Download API

Recommended function:

```python
fetch_station_data(
    station_id: str,
    source: str,
    start: str,
    end: str,
    variables: list[str],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame
```

Return harmonized daily columns:

| Output column | Meaning |
|---|---|
| `date` | daily timestamp |
| `station_id` | source-native station ID |
| `source` | station backend |
| `precipitation` | mm/day |
| `min_temperature` | degC |
| `max_temperature` | degC |
| `mean_temperature` | degC |
| `wind_speed` | m/s or package standard |
| `relative_humidity` | percent |
| `surface_pressure` | kPa or package standard |

Also include:

- provenance columns
- missing flags
- QC flags

## Comparison Product Inputs

This module should compare station observations against gridded products in two separate tracks.

### Track A: historical products

Examples:

- `chirps_v2`
- `imerg`
- `agera5`
- `era5`
- `power`

Important caveat for this track:

- some products may include station information directly or indirectly
- products should therefore carry a metadata flag such as:
  - `reference_independence = high | medium | low`
  - `station_informed = true | false | unknown`

### Track B: NEX-GDDP historical

Examples:

- `nex_gddp` historical baseline only

Future `ssp*` periods should not be included in station validation metrics.

## User-Supplied Station Data

User upload must be a first-class path, not an edge case.

Recommended input modes:

1. auto-discovered public station data
2. specified public station ID
3. uploaded user station file

Supported upload reality:

- incomplete records
- missing months or years
- only rainfall
- only Tmin/Tmax
- irregular headers
- inconsistent units

### Recommended upload API

```python
load_user_station_data(
    path: str | Path,
    variable_map: dict[str, str] | None = None,
    units_map: dict[str, str] | None = None,
    station_name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
) -> pd.DataFrame
```

Required normalized output columns:

- `date`
- one or more of:
  - `precipitation`
  - `min_temperature`
  - `max_temperature`
  - `mean_temperature`
  - `wind_speed`
  - `relative_humidity`

### Partial-variable behavior

The module must not fail just because a user file lacks some variables.

Recommended behavior:

- compare only variables present in the uploaded file
- emit a clear note listing skipped variables
- compute per-variable metrics independently

Example:

- if upload has only precipitation:
  - rainfall comparison runs
  - temperature comparison is skipped with explanation

### Missing-data behavior

Recommended rules:

- never silently infill user station observations by default
- preserve missing values
- score only overlapping valid dates
- report overlap counts clearly

Optional later:

- allow user-approved gap-filling methods, but never as default

### Upload metadata sidecar

If possible, support optional metadata sidecar fields:

- station name
- source institution
- gauge type
- elevation
- units
- QC status
- contact / provenance note

This can be a small JSON or YAML file paired with the uploaded CSV.

## Gridded Download API

Recommended wrapper:

```python
fetch_gridded_reference_data(
    lat: float,
    lon: float,
    start: str,
    end: str,
    variables: list[str],
    source: str,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame
```

This should call the existing package download/harmonization pipeline rather than bypassing it.

## Comparison Metrics

At minimum, calculate metrics separately for precipitation and temperature.

### Daily metrics

- bias
- mean absolute error
- RMSE
- Pearson correlation
- number of overlapping days
- missing-data fraction

### Rainfall-specific metrics

- annual total bias
- seasonal total bias
- wet-day frequency bias
- rainy-day detection skill
- intensity bias on wet days only
- 95th percentile wet-day bias

### Temperature-specific metrics

- mean bias
- Tmin bias
- Tmax bias
- annual cycle correlation
- hottest-month bias
- coldest-month bias

## Output Objects

### 1. Station candidates table

Rows are candidate stations, with ranking components and final score.

### 2. Daily joined table

Columns:

- `date`
- `station_id`
- `station_source`
- `grid_source`
- `observed_*`
- `grid_*`

### 3. Metrics summary table

One row per station-source-variable combination.

### 4. Recommendation table

One row per variable, optionally per season.

Example:

| variable | best_source | basis |
|---|---|---|
| precipitation | `chirps_v2` | lowest seasonal total bias and best wet-day skill |
| temperature | `agera5` | lowest mean Tmax/Tmin bias |

## Cache Layout

Recommended structure:

```text
outputs/cache/weather_stations/
  metadata/
    ghcn_daily_stations.parquet
    global_hourly_stations.parquet
  observations/
    ghcn_daily/
      KE000063612/
        1981_1990.json
        1991_2000.json
        2001_2010.json
    global_hourly/
      63742099999/
        2025.csv
  comparisons/
    lat_m1p2860_lon_36p8170/
      historical/
        station_rankings.json
        metrics_summary.csv
      nex_gddp_historical/
        metrics_summary.csv
```

## CLI Proposal

### Discover nearby stations

```bash
.venv/bin/python -m climate_tookit.weather_station.compare \
  --lat -1.286 \
  --lon 36.817 \
  --variables precipitation,min_temperature,max_temperature \
  --station-source ghcn_daily \
  --radius-km 150 \
  --discover-only
```

### Run historical validation

```bash
.venv/bin/python -m climate_tookit.weather_station.compare \
  --lat -1.286 \
  --lon 36.817 \
  --variables precipitation,min_temperature,max_temperature \
  --station-source ghcn_daily \
  --grid-source chirps_v2,agera5 \
  --start 1991-01-01 \
  --end 2010-12-31 \
  --output outputs/weather_station_nairobi_historical.json
```

### Run NEX-GDDP historical validation

```bash
.venv/bin/python -m climate_tookit.weather_station.compare \
  --lat -1.286 \
  --lon 36.817 \
  --variables precipitation,min_temperature,max_temperature \
  --station-source ghcn_daily \
  --grid-source nex_gddp \
  --model MRI-ESM2-0 \
  --scenario historical \
  --start 1991-01-01 \
  --end 2010-12-31
```

## Guardrails

### 1. Do not compare future NEX-GDDP to stations

If user passes `scenario=ssp245` or similar:

- stop with a clear error
- explain that only historical overlap can be validated against station observations

### 2. Do not ensemble before per-source evaluation

Each source should be compared to station observations separately first.

Only after per-source metrics are computed should any source ranking or ensemble recommendation be considered.

### 3. Preserve provenance

Every output row should make clear:

- station backend
- whether station data are `public_downloaded` or `user_uploaded`
- station ID
- grid source
- model if applicable
- scenario if applicable
- variable mapping used

## Phased Implementation

### Phase 1

- bundle `ghcn_daily` metadata
- implement station discovery
- implement station ranking
- implement daily station fetch for `ghcn_daily`
- compare against historical gridded products

### Phase 2

- add `global_hourly`
- add `nex_gddp historical` comparison
- add recommendation summaries

### Phase 3

- add station crosswalks
- add optional `meteostat` discovery fallback
- add multi-site batch mode

## Recommendation

Build this as a separate module:

```text
climate_tookit/weather_station/
  __init__.py
  station_index.py
  download_station_data.py
  compare.py
  metrics.py
  cli.py
```

This keeps:

- observational validation logic separate
- historical gridded workflows separate
- NEX-GDDP future workflows separate

That separation is methodologically cleaner and will be easier to maintain.
