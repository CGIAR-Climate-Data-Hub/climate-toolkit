# Example End-to-End Workflow

A simple "story" a new user can follow to understand the toolkit's
capabilities, from fetching raw climate data to projecting crop hazards.

> [!IMPORTANT]
> **The example commands below are prefixed with `uv run` so they work
> copy-paste.** Run them from the repo root after `uv sync`.
>
> - The `climate-toolkit-*` console scripts only exist once the package is
>   installed (`uv sync` or `pip install -e .`). Running the bare
>   `climate-toolkit-fetch ...` (without `uv run`, or from a non-installed
>   checkout) will fail with "command not recognized".
> - From a bare source checkout you can instead use the module form: every
>   `climate-toolkit-<name>` maps to `python -m climate_tookit.<module>`
>   (e.g. `python -m climate_tookit.season_analysis.seasons ...`).
> - Replace coordinates, dates, and any `<PLACEHOLDER>` with your own values.

## Prerequisites

1. **Google Earth Engine** (required for the GEE-backed sources):
   - Create an account at [earthengine.google.com](https://earthengine.google.com)
   - Authenticate once: `earthengine authenticate`
   - Set your Cloud project so Earth Engine can initialise. The toolkit reads
     it from the environment, **not** from a `.env` file automatically:
     ```bash
     # macOS / Linux
     export GCP_PROJECT_ID=your-ee-project-id
     ```
     ```powershell
     # Windows PowerShell
     $env:GCP_PROJECT_ID = "your-ee-project-id"
     ```
     (Or pass `uv run --env-file .env ...` if you keep it in a `.env`.)
2. **Install**: `uv sync` (preferred) or `pip install -e .`
3. **Inputs**: a latitude/longitude. Crop name and date ranges come later.

---

## Step 1 — Fetch raw climate data

`climate-toolkit-fetch` uses `--lat`/`--lon` (single site) and `--start`/`--end`.

```bash
uv run climate-toolkit-fetch \
  --source agera_5 \
  --lat -1.286 --lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/climate_data.csv
```

- Downloads source → transforms variable names → preprocesses (units, QC).
- **Source coverage:** AgERA5 (1979–present, incl. humidity), ERA5
  (1979–present), CHIRPS v3 `chirps_v3_daily_rnl` (1981–present, precip),
  NASA POWER (1984–present), NEX-GDDP (projections; needs `--scenario` and
  `--model`/`--models`).
- **Multiple NEX-GDDP models in one run** — use `--models` (comma list or
  `all`); one file is written per model:
  ```bash
  uv run climate-toolkit-fetch --source nex_gddp --lat -1.286 --lon 36.817 \
    --start 2050-01-01 --end 2050-12-31 \
    --variables precipitation,max_temperature,min_temperature \
    --models ACCESS-CM2,EC-Earth3,MRI-ESM2-0 --scenario ssp245 \
    --format csv -o outputs/nex_2050.csv
  ```

---

## Step 2 — Validate against weather stations (optional)

Discover nearby stations:

```bash
uv run climate-toolkit-weather-station-download \
  --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nearby_candidates \
  --open-report
```

Compare gridded vs. station data:

```bash
uv run climate-toolkit-weather-station-compare \
  --grid-source agera_5 \
  --station-source gsod \
  --station-id <STATION_ID> \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --format json
```

---

## Step 3 — Climatology (the local "normal")

```bash
uv run climate-toolkit-climatology \
  --location "-1.286,36.817" \
  --source agera_5 \
  --start-year 1991 --end-year 2020
```

For NEX-GDDP, `--source nex_gddp` runs the CMIP6 ensemble (averaged across
models); add `--model-workers` to parallelise.

---

## Step 4 — Detect rainy seasons

```bash
uv run climate-toolkit-seasons \
  --location "-1.286,36.817" \
  --source agera_5 \
  --start-year 2015 --end-year 2020
```

- Water-balance (Hargreaves ET0) detection of onset/cessation per year.
- Save plots/artifacts with `--output-dir outputs/seasons`.
- **If auto-detection is unreliable** (very wet or erratic climates), use a
  fixed calendar window instead (see Step 5's `--fixed-season`).

---

## Step 5 — Climate statistics by season

Auto-detected seasons:

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/climate_stats_2015_2020.json
```

Fixed seasons (e.g. MAM and OND):

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --fixed-season "03-01:05-31,10-01:12-31" \
  --output outputs/climate_stats_fixed.json
```

Outputs include seasonal rainfall, temperature extremes, water-balance
indicators (NDWS, NDWL0), heat-stress indices, and SPEI when requested.

---

## Step 6 — Compare periods

`climate-toolkit-periods` uses `--baseline-start` / `--baseline-end` /
`--focal-year` (note: not `*-year` suffixes).

```bash
uv run climate-toolkit-periods \
  --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/2020_vs_2001_2015.json
```

---

## Step 7 — Crop hazards

`climate-toolkit-hazards` takes the **crop as a positional argument** and uses
`--date-from` / `--date-to` (not `--start-date`/`--end-date`).

```bash
uv run climate-toolkit-hazards Maize \
  --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/maize_hazards_2020.json
```

Supported crops: Beans, Cassava, Groundnuts, Maize, Millet, Rice, Sorghum.
Indicators include NDWS, NDWL0, NTx35/NTx40, NDD, and crop-specific
precipitation/temperature thresholds.

---

## Step 8 — Project hazards (NEX-GDDP ensemble)

`climate-toolkit-hazards-ensemble` takes the crop positionally and uses
`--start-year`/`--end-year`, `--models` (comma list or `all`), `--scenarios`
(comma list), and `--model-workers` for parallelism.

```bash
uv run climate-toolkit-hazards-ensemble Maize \
  --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 \
  --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245,ssp585 \
  --model-workers 8 \
  --output outputs/maize_hazards_2050_2060.json
```

---

## Complete walkthrough: Maize suitability near Nairobi

```bash
# 1. Fetch climate data
uv run climate-toolkit-fetch --source agera_5 --lat -1.286 --lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/nairobi_climate.csv

# 2. (optional) discover nearby stations
uv run climate-toolkit-weather-station-download --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --report-prefix outputs/nairobi_stations --open-report

# 3. Climatology baseline
uv run climate-toolkit-climatology --location "-1.286,36.817" --source agera_5 \
  --start-year 1991 --end-year 2020

# 4. Detect rainy seasons
uv run climate-toolkit-seasons --location "-1.286,36.817" --source agera_5 \
  --start-year 2015 --end-year 2020

# 5. Climate statistics
uv run climate-toolkit-stats --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/nairobi_stats.json

# 6. Compare 2020 to a baseline
uv run climate-toolkit-periods --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/nairobi_2020_vs_baseline.json

# 7. Maize hazards in 2020
uv run climate-toolkit-hazards Maize --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source agera_5 \
  --output outputs/nairobi_maize_2020.json

# 8. Project maize hazards to 2050-2060
uv run climate-toolkit-hazards-ensemble Maize --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245 --model-workers 8 \
  --output outputs/nairobi_maize_2050_2060.json
```

---

## Notes & gotchas

- **Console scripts require installation** (`uv sync` / `pip install -e .`). A
  raw `requirements.txt` install does not expose them — use the
  `python -m climate_tookit.<module>` form instead.
- **Earth Engine project ID** must be in the environment (`GCP_PROJECT_ID`),
  or pass `uv run --env-file .env`. It is not auto-loaded from `.env`.
- **"auto"/"paired" source** resolves to `chirps_v3_daily_rnl` (precip) +
  `agera_5` (temperature) for the historical daily path.
- **CHIRPS naming**: v3 is `chirps_v3_daily_rnl` (recommended); the older
  `chirps_v2` ended in 2016. Prefer v3 or AgERA5 for reliability.
- **First GEE call** in a session is slow (auth handshake); repeat runs reuse
  the cache.
- **Flag conventions differ per tool** — run any command with `--help` to
  confirm (e.g. `fetch` uses `--lat/--lon`; `stats`/`seasons`/`hazards` use
  `--location`; `hazards` takes the crop positionally with `--date-from`/
  `--date-to`; `periods` uses `--baseline-start`/`--baseline-end`).
