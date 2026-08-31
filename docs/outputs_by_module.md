# Outputs by module

A reference of the **tables and figures each module produces** — what you get
back from every part of the toolkit, in what format. Use it to know which
columns and files to expect before you run a workflow. For call signatures and
parameters, see the [Python API](api/index.md) reference.

---

## 🌾 fetch_data — climate data ingestion

**Output format:** CSV, JSON

**Tables:**

- Daily time-series with columns: `date`, `precipitation`, `max_temperature`,
  `min_temperature`, `humidity`, `solar_radiation`, `wind_speed` (varies by source).

**Figures:** none (raw data only).

---

## 📅 season_analysis — rainy-season detection

**Output format:** CSV, JSON

**Tables:**

- **Season summary (CSV):** `year`, `season_number`, `onset`, `cessation`,
  `regime`, `length_days`, `total_rainfall_mm`, `rainy_days`, `dry_days`,
  `dry_spells`, `annual_rain_mm`, `humid_result`.
    - Livestock metrics (when livestock mode is enabled): `mean_thi`, `max_thi`,
      `thi_stress_days`.
- **Long-term means (JSON):** per-season aggregates — mean onset date, mean
  length, mean rainfall, etc.

**Figures:** none.

---

## 📊 climate_statistics — climate metrics & aggregation

**Output format:** JSON (primary) + CSV exports

**Tables:**

- **`raw_climate_summary`:** mean, min, max, std per variable per season.
- **`overall_statistics`** (per season): precipitation totals & stats;
  temperature stats (avg, max, min); ET0 (evapotranspiration); water balance
  (NDWS, NDWL0, WRSI); VPD (vapor-pressure deficit); heat stress (Humidex, THI).
- **`season_statistics`:** per-season headline metrics.
- **`monthly_series` (CSV):** aggregated daily → monthly data.
- **`spei` / `spi` (CSV):** drought indices with date, value, classification.
- **`annual_summary`:** year-by-year humidity test results.

**Figures:** none.

---

## 📈 compare_periods — historical period comparison

**Output format:** JSON, text console

**Tables:**

- **Comparison structure** (per variable per season): `focal` (focal-year value),
  `baseline_avg` (average across the baseline period), `diff` (focal − baseline),
  `pct_change` (`diff / baseline × 100`).
- Includes precipitation, temperature, water-stress, and heat-stress comparisons.

**Figures:** none.

---

## ⚠️ calculate_hazards — crop hazard assessment

**Output format:** JSON, text console, optional CSV

**Tables:**

- **`hazard_indicators`** — for each hazard type: `focal_value`, `baseline_avg`,
  `diff`, `stress_category` (no / moderate / severe / extreme stress), `reasoning`.

| Hazard | Meaning |
|--------|---------|
| Precipitation | Seasonal rainfall |
| TAVG | Average temperature |
| NDD | Normalized degree days |
| NTx35 | Days above 35 °C |
| NTx40 | Days above 40 °C |
| NDWS | Water-stress days |
| NDWL0 | Waterlogging days |
| WRSI | Water-requirement satisfaction (%) |
| THI | Livestock heat index |
| HUMIDEX | Human heat index |

**Figures:** none.

---

## 🌦️ weather_station (download) — station discovery

**Output format:** CSV, JSON, HTML (interactive)

**Tables:**

- **Candidate stations (CSV):** `station_id`, `station_name`, `distance_km`,
  `elevation_diff_m`; data completeness per variable (`precip_complete_%`,
  `temp_complete_%`); `data_years`, `selection_status`, `selection_rank`,
  `selection_reason`.

**Figures:** none (the HTML has an interactive table with filtering/sorting).

---

## 🔄 weather_station (compare) — station vs. grid validation

**Output format:** JSON, optional CSV, optional HTML + PNG

**Tables:**

- **Validation metrics (JSON)** — per (grid_source, variable) pair: `n_overlap_days`,
  `correlation`, `rmse`, `bias`, `mae`, `annual_total_grid`, `annual_total_station`,
  `pct_diff`, `wet_day_agreement_%`.
- **Daily comparison (optional CSV):** `date`, `grid_source`, `variable`,
  `station_value`, `grid_value`, `diff`, `pct_diff`, `quality_flag`.

**Figures (optional PNG):**

- Time-series comparison (grid vs. station over time).
- Scatter plot (grid vs. station values).
- Box plot (distribution by variable / source).

---

## 🌍 climatology — climatic normals & indices

**Output format:** JSON, CSV (per index), optional PNG

**Tables:**

- **WMO monthly normals (`ltm_monthly`):** `month`, `precip_mm`, `tmax_c`,
  `tmin_c`, `humidity_%`, `solar_rad`, `et0_mm`.
- **Drought indices (`spei` / `spi`, CSV):** `date`, `spei_value` / `spi_value`,
  `classification` (wet / normal / moderate / severe / extreme drought).
- **VPD statistics (`vpd`):** monthly vapor-pressure-deficit values.
- **Livestock heat stress (THI, CSV):** `date`, `daily_thi`, `thi_classification`
  (cool / thermal_comfort / heat_stress / severe_heat_stress).
- **Human heat stress (Humidex, CSV):** `date`, `daily_humidex`,
  `humidex_classification` (comfortable / warm / very_warm / hot / very_hot /
  dangerous / extreme_caution).

**Figures (optional PNG):**

- Monthly climatology line plots.
- Drought-index time-series.
- Heat-stress categories over time.

---

## 🔗 compare_datasets — multi-source comparison

**Output format:** per-source CSV, per-source PNG, multi-source PNG

**Tables:**

- **`{source}_annual_timeseries.csv`:** `year`, per-variable annual totals / means.
- **`{source}_monthly_climatology.csv`:** `month`, per-variable monthly means.
- **Console summary table:** mean, min, max, std, coefficient of variation per source.

**Figures (PNG at 150 DPI):**

- Per-source: `{source}_annual_timeseries.png` (annual trends);
  `{source}_monthly_climatology.png` (seasonal pattern).
- Multi-source: `multisource_annual_{variable}.png` and
  `multisource_monthly_climatology_{variable}.png` (overlay of all sources).

---

## Quick summary

| Module | Primary output | Tables | Figures | Report |
|--------|----------------|--------|---------|--------|
| **fetch_data** | CSV / JSON | Daily time-series | ❌ | ❌ |
| **season_analysis** | CSV + JSON | Season summary + LTM stats | ❌ | Console text |
| **climate_statistics** | JSON + CSV | Raw summary, overall, seasonal, monthly, SPEI/SPI | ❌ | JSON + console |
| **compare_periods** | JSON | Baseline vs. focal (with diffs & %) | ❌ | JSON + console |
| **calculate_hazards** | JSON | Hazard indicators with stress bands | ❌ | JSON + console |
| **weather_station (download)** | CSV + JSON + HTML | Station candidates with QA metrics | ❌ | Interactive HTML |
| **weather_station (compare)** | JSON + CSV (opt.) | Validation metrics (correlation, RMSE, bias, …) | ⚠️ optional | JSON + optional HTML |
| **climatology** | JSON + CSV | LTM monthly norms, drought / heat indices | ⚠️ optional | JSON + console |
| **compare_datasets** | CSV per source + PNG | Annual & monthly per-source tables | ✅ PNG plots | Console statistics |

**Legend:** ❌ no figures · ⚠️ optional figures · ✅ figures included.
