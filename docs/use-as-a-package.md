# Using climate-toolkit as a Python package

A practical, end-to-end guide to installing and using `climate_toolkit` as a
library from your own Python code. Every credential-free example here was run
against the real package and API.

> **Status note.** The package is `climate_toolkit` (import name), distributed
> as `climate-toolkit`. Version `0.1.0a0` (alpha). It is **not on PyPI yet**, so
> you install from source.

---

## Table of contents

1. [What you get](#1-what-you-get)
2. [Requirements](#2-requirements)
3. [Installation](#3-installation)
4. [Verify the install](#4-verify-the-install)
5. [Credentials: NASA POWER vs Earth Engine](#5-credentials-nasa-power-vs-earth-engine)
6. [Quick start (no credentials)](#6-quick-start-no-credentials)
7. [Earth Engine setup (for gridded / projection sources)](#7-earth-engine-setup)
8. [The public API — all seven functions](#8-the-public-api-all-seven-functions)
9. [Data sources reference](#9-data-sources-reference)
10. [Variables reference](#10-variables-reference)
11. [Caching and outputs](#11-caching-and-outputs)
12. [Recipes](#12-recipes)
13. [Using it in Jupyter / your own project](#13-using-it-in-jupyter-your-own-project)
14. [Troubleshooting](#14-troubleshooting)
15. [Getting more help](#15-getting-more-help)

---

## 1. What you get

!!! tip "New here?"
    For a 5-minute install and first run, start with
    [Getting started](getting_started.md). This page is the fuller reference —
    every public function, the sources and variables, caching, recipes, and
    troubleshooting.

`climate_toolkit` is a location-based climate analysis library. From a single
`import climate_toolkit as ct` you get **seven public functions**:

| Function | What it does |
|----------|--------------|
| `fetch_climate_data` | Download daily climate data for a point as a pandas DataFrame |
| `analyze_climate_statistics` | Seasonal climatology, water balance, SPI/SPEI over a multi-year window |
| `evaluate_hazards` | Crop/livestock hazard assessment for a growing season |
| `compare_climate_periods` | Diff a focal year against a baseline climatology |
| `compare_climate_sources` | Side-by-side comparison of gridded datasets for one site |
| `download_station_data` | Fetch daily observations from nearby weather stations |
| `compare_station_to_grids` | Validate gridded datasets against station observations |

Data comes from CHIRPS, AgERA5, TerraClimate, IMERG, TAMSAT, CHIRTS, ERA5,
NEX-GDDP, NASA POWER, CMIP6, SoilGrids, plus GHCN-Daily / GSOD stations.

---

## 2. Requirements

- **Python ≥ 3.10.** A system Python 3.9 will not work — use a 3.10+ virtual
  environment. The easiest way to get one is [`uv`](https://docs.astral.sh/uv/),
  which can provision Python 3.11 for you automatically.
- OS packages: none beyond what the Python wheels provide (no compiler needed).
- For Earth Engine-backed sources: a Google Cloud project and a one-time Earth
  Engine authentication (see §7). **NASA POWER and weather stations need
  neither.**

---

## 3. Installation

The full steps — GitHub install, Jupyter `%pip`, and the `uv` development
setup — are in [Getting started → Install](getting_started.md#1-install). In
short:

```bash
# into your own project or notebook (not on PyPI yet, so install from Git):
pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

# ...or, for development from a clone:
cd climate-toolkit && uv sync
```

After either, `import climate_toolkit` works from any directory. Run scripts in
the repo's environment with `uv run python my_script.py`.

---

## 4. Verify the install

```bash
uv run python -c "import climate_toolkit as ct; print(ct.__version__)"
# -> 0.1.0a0
```

Confirm the public surface:

```python
import climate_toolkit as ct
print([n for n in ct.__all__ if not n.startswith("__")])
# ['analyze_climate_statistics', 'compare_climate_periods',
#  'compare_climate_sources', 'compare_station_to_grids',
#  'download_station_data', 'evaluate_hazards', 'fetch_climate_data']
```

---

## 5. Credentials: NASA POWER vs Earth Engine

This is the single most important thing to understand before your first call.

- **`nasa_power`** (and weather stations `ghcn_daily` / `gsod`) use plain HTTPS
  and need **no credentials**. Start here.
- **Most gridded / projection sources** — `agera_5`, `era_5`, `chirps_*`,
  `chirts`, `imerg`, `terraclimate`, `cmip_6`, `nex_gddp`, `soil_grid`, `hwsd`
  — route through **Google Earth Engine** and require a one-time auth plus a
  project ID (see §7).

---

## 6. Quick start (no credentials)

### Fetch daily data → DataFrame

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),      # (lat, lon), Nairobi
    variables=[ClimateVariable.precipitation,
               ClimateVariable.max_temperature,
               ClimateVariable.min_temperature],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print(df.head())
#         date  precipitation  max_temperature  min_temperature
# 0 2020-01-01           0.04            27.17            14.07
# ...
```

`fetch_climate_data` returns a **pandas DataFrame**.

### Seasonal statistics → dict

```python
stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2015, end_year=2020,
    source="nasa_power",
)
print(stats.keys())
# location, period, source, ..., season_statistics, ltm_season_summary, ...
```

`analyze_climate_statistics` returns a nested **dict** of results. (Use ≥ ~20
years for a real long-term climatology; short windows just print a warning.)

---

## 7. Earth Engine setup

The gridded and projection sources need a one-time Earth Engine setup. The full
walkthrough — including the **free** noncommercial registration path — is in
[Getting started → Google Earth Engine credentials](getting_started.md#2-google-earth-engine-credentials).
In brief: run `earthengine authenticate`, set `GCP_PROJECT_ID`, then verify with
`climate-toolkit gee-check` (exits 0 on success).

Once that's done, any function works with EE sources:

```python
# ClimateVariable was imported in the quick-start snippet above.
vars3 = [ClimateVariable.precipitation,
         ClimateVariable.max_temperature,
         ClimateVariable.min_temperature]

df = ct.fetch_climate_data(
    source="agera_5",                       # Earth Engine
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
)

# NEX-GDDP projections need a model + scenario:
proj = ct.fetch_climate_data(
    source="nex_gddp", model="GFDL-ESM4", scenario="ssp245",
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2050, 1, 1), date_to=date(2050, 12, 31),
)
```

---

## 8. The public API — all seven functions

Every function has a full NumPy-style docstring: `help(ct.<function>)`.

### `fetch_climate_data`

```python
ct.fetch_climate_data(
    source, location_coord=None, variables=None,
    date_from=None, date_to=None, model=None, scenario=None,
    stage="preprocessed", cache_dir=None, refresh_cache=False,
    sites=None, sites_csv=None, station_id=None, workers=1, verbose=True,
)
```
Returns a DataFrame. `stage` controls how far the pipeline runs: `"raw"` →
`"transformed"` → `"preprocessed"` (default). Pass `sites=`/`sites_csv=` for
multi-site batch fetches (GEE sources and NEX-GDDP).

### `analyze_climate_statistics`

```python
ct.analyze_climate_statistics(
    location_coord, start_year, end_year, source,
    fixed_season=None, crop_name=None,
    spei_scale_months=None, spi_scale_months=None,
    workers=1, verbose=False,
)
```
Returns a dict with per-season statistics, water balance (ET0, NDWS, WRSI),
optional SPI/SPEI blocks, and long-term-mean summaries.

### `evaluate_hazards`

```python
ct.evaluate_hazards(
    crop_name, location_coord, date_from, date_to,   # dates are ISO strings
    season_start=None, season_end=None, fixed_season=None,
    source="auto", custom_thresholds=None,
    soilcp=100.0, soilsat=100.0, workers=1,
)
```
Crop/livestock hazard assessment (heat, drought, waterlogging, ...) over a
growing season. `date_from`/`date_to` are ISO date strings (e.g. `"2020-03-01"`).

### `compare_climate_periods`

```python
ct.compare_climate_periods(
    location, baseline_start, baseline_end, focal_year, source,
    fixed_season=None, crop_name=None, workers=1,
)
```
Diffs a focal year against a baseline climatology; returns a dict.

### `compare_climate_sources`

```python
ct.compare_climate_sources(
    sources, lat=None, lon=None, start=None, end=None,
    output_dir="./outputs", nex_model=None, nex_scenario="ssp245",
    workers=1,
)
```
Side-by-side comparison of multiple gridded datasets for one site. `sources` is
a list, e.g. `["nasa_power", "agera_5"]`.

### `download_station_data` (keyword-only args)

```python
ct.download_station_data(
    station_source="ghcn_daily",            # or "gsod"
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    max_distance_km=50.0, auto_select="auto-1",
)
```
Finds and downloads nearby weather-station observations. No Earth Engine needed.

### `compare_station_to_grids` (keyword-only args)

```python
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power", "agera_5"],
)
```
Validates gridded datasets against station observations; returns a dict.

---

## 9. Data sources reference

| `source` key | Data | Earth Engine? |
|--------------|------|:---:|
| `nasa_power` | Daily point climate, 1984– | No |
| `tamsat` | African rainfall + soil moisture (fragile; optional) | No (direct download) |
| `ghcn_daily`, `gsod` | Weather-station observations | No |
| `agera_5` | ERA5-Land daily aggregates (broad variable set; recommended default) | Yes |
| `era_5` | ERA5 daily reanalysis | Yes |
| `chirps_v2` / `chirps_v3_daily_rnl` | CHIRPS precipitation | Yes |
| `chirts` | CHIRTS temperature | Yes |
| `imerg` | GPM IMERG precipitation | Yes |
| `terraclimate` | Monthly water balance | Yes |
| `cmip_6` | GDDP-CMIP6 projections | Yes |
| `nex_gddp` | NEX-GDDP-CMIP6 projections (needs `model` + `scenario`) | Yes |
| `soil_grid`, `hwsd` | Static soil properties | Yes |

Legacy aliases (`era5`, `agera5`, `nasapower`, `nexgddp`, `ghcn`, ...) are
normalized automatically.

---

## 10. Variables reference

`variables` accepts a **list of enum members** — the robust form that works on
every version:

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

variables=[ClimateVariable.precipitation,
           ClimateVariable.max_temperature,
           ClimateVariable.min_temperature]
```

Recent builds also accept plain strings (e.g. `["precipitation",
"max_temperature"]` or the comma string `"precipitation,max_temperature"`),
matching the CLI. If you hit `AttributeError: 'str' object has no attribute
'name'`, you are on an older build — use the enum form above.

`ClimateVariable` names: `rainfall`, `precipitation`, `max_temperature`,
`min_temperature`, `mean_temperature`, `wind_speed`, `solar_radiation`,
`humidity`, `soil_moisture`. Soil properties live in `SoilVariable`.

If you omit `variables`, each source uses a sensible default set (and drops
variables it doesn't carry — e.g. NASA POWER has no soil moisture).

---

## 11. Caching and outputs

- Fetches cache under **`outputs/cache/<source>/...`**, keyed by location, date
  range, and variables. Repeat runs reuse cached frames.
- Force a cold fetch: `refresh_cache=True`.
- Relocate the cache: `cache_dir="/some/stable/path"`.
- Report outputs (from the analysis/compare functions) default to `./outputs`.

Both `outputs/` and `.tmp/` are git-ignored.

---

## 12. Recipes

### Compare two sources at one site

```python
ct.compare_climate_sources(
    sources=["nasa_power", "agera_5"],       # agera_5 needs Earth Engine
    lat=-1.286, lon=36.817,
    start="2020-01-01", end="2020-12-31",
    output_dir="./outputs",
)
```

### Hazard screen for a maize season

```python
ct.evaluate_hazards(
    crop_name="Maize",
    location_coord=(-1.286, 36.817),
    date_from="2020-03-01", date_to="2020-08-31",
)
```

### Focal year vs baseline climatology

```python
ct.compare_climate_periods(
    location=(-1.286, 36.817),
    baseline_start=1991, baseline_end=2020,
    focal_year=2023,
    source="agera_5",
)
```

### Validate a grid product against a nearby station

```python
from datetime import date
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2019, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power"],
)
```

---

## 13. Using it in Jupyter / your own project

Once installed into your environment (Track B), it's a normal import:

```python
import climate_toolkit as ct
from datetime import date

from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power", location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation],
    date_from=date(2022, 1, 1), date_to=date(2022, 3, 31),
)
df.set_index("date")["precipitation"].plot()   # returns a normal DataFrame
```

The import is lightweight (heavy deps load lazily), so notebooks start fast.

---

## 14. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `SyntaxError` / package won't import on `python3` | You're on Python 3.9. Use a 3.10+ env (`uv sync`). |
| `Earth Engine project ID missing` | Set `GCP_PROJECT_ID` (see §7). |
| `Project 'projects/YOUR_PROJECT_ID' not found` | You left the placeholder in — use your real project id. |
| auth refresh / DNS errors on EE sources | Re-run `ee.Authenticate()`; check network. |
| `command not recognized: climate-toolkit-*` | Console scripts exist only after `uv sync` / `pip install`; or run `python -m climate_toolkit.<module>`. |
| `OSError: File name too long` on a NASA POWER fetch | Pass an explicit `variables=[...]` list instead of relying on the full default set. |
| `AttributeError: 'str' object has no attribute 'name'` on `variables=` | Pass enum members (`ClimateVariable.*`) rather than strings. |

Preflight your Earth Engine setup anytime with:

```bash
uv run climate-toolkit gee-check
```

---

## 15. Getting more help

- `help(ct.fetch_climate_data)` (or any of the seven functions) for full
  parameter docs.
- The generated API reference and dataset pages on the documentation site
  linked from the project's `pyproject.toml` / README.
- `uv run climate-toolkit --help` to see the equivalent CLI subcommands.
