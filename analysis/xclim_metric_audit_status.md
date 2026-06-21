# xclim Metric Audit Status

Status: working note  
Updated: 2026-06-21

This note records the current outcome of the package-to-`xclim` audit work for
issue `#6`.

## Bottom line

There are now two distinct groups:

1. Direct standard-metric checks
- Core precipitation and temperature period metrics can now be checked against
  `xclim` indicators through
  `climate_tookit.climatology.compute_xclim_core_period_metrics()`.
- Focused regression tests now verify that the package’s core period reducers
  agree with those `xclim` reference values for the overlapping standard
  metrics.
- `climate_statistics.statistics` now also exposes these as a top-level
  `xclim_references` block so JSON/CLI consumers can see the standardized
  reference rows without relying on weather-station comparison helpers.
- `compare_periods.periods` and `compare_periods.ensemble_periods` now carry
  that block forward into baseline/focal/future comparison outputs, instead of
  leaving standard-extremes context behind at the single-period statistics
  layer.

2. Nearest-reference checks
- Toolkit `SPI` and `SPEI` do not use the exact same fitting machinery as
  `xclim`, but they now have explicit nearest-reference comparison helpers:
  - `compute_xclim_spi_reference()`
  - `compute_xclim_spei_reference()`
- Synthetic regression tests show the toolkit outputs track those references
  very closely, even though exact parity is not expected.

## Crosswalk

| Package metric family | Package path | `xclim` analogue | Current status | Notes |
| --- | --- | --- | --- | --- |
| Period precipitation total | `climate_statistics.overall_statistics` / `season_statistics` | `precip_accumulation` | direct check | Covered by focused regression tests. |
| Rainy days | same | `wetdays` | direct check | Uses `>= 1 mm/day` threshold convention. |
| Dry days | same | `dry_days` | direct check | Uses `< 1 mm/day` style threshold via xclim helper. |
| Max 1-day precipitation | same | `max_1day_precipitation_amount` | direct check | Covered in focused regression tests. |
| Max 5-day precipitation | `weather_station.compare` / `climatology.xclim_reference` | `max_n_day_precipitation_amount` | direct check | Annual precipitation-reference comparison now regression-tested through shared xclim helper. |
| Consecutive dry days | same compare helper | `maximum_consecutive_dry_days` | direct check | Weather-station comparison helper now regression-tested. |
| Consecutive wet days | same compare helper | `maximum_consecutive_wet_days` | direct check | Weather-station comparison helper now regression-tested. |
| Heavy precipitation day count | same compare helper | `wetdays` with `10 mm/day` threshold | direct check | Stored as `r10mm_days`. |
| Very heavy precipitation day count | same compare helper | `wetdays` with `20 mm/day` threshold | direct check | Stored as `r20mm_days`. |
| NDD dry-day count | `calculate_hazards.calculate_season_statistics` | `dry_days` with `< 1 mm/day` | direct check | Hazard count semantics match xclim-style dry-day counting. |
| NTx35 hot-day count | `calculate_hazards.calculate_season_statistics` | `tx_days_above` with `>= 35 degC` | direct check | Count definition audited separately from Atlas-style hazard bands. |
| NTx40 very-hot-day count | `calculate_hazards.calculate_season_statistics` | `tx_days_above` with `>= 40 degC` | direct check | Count definition audited separately from Atlas-style hazard bands. |
| Simple intensity | same | `daily_pr_intensity` | direct check | Compared on seasonal slice. |
| Mean Tmax | same | `tx_mean` | direct check | Celsius conversion handled in reference helper. |
| Mean Tmin | same | `tn_mean` | direct check | Celsius conversion handled in reference helper. |
| Mean Tavg | same | `tg_mean` surrogate from daily mean temperature | direct check | Built from `(tmax + tmin) / 2` before reference comparison. |
| Max Tmax | same | `tx_max` | direct check | Covered in focused regression tests. |
| Min Tmin | same | `tn_min` | direct check | Covered in focused regression tests. |
| SPI | `climatology.spei.compute_monthly_spi` | `standardized_index` nearest reference | near-match | High-correlation reference test; not exact parity by design. |
| SPEI | `climatology.spei.compute_monthly_spei` | `standardized_index` nearest reference | near-match | High-correlation reference test; not exact parity by design. |
| NDWS / NDWL0 / WRSI | hazards / statistics / periods | none | custom | Must stay outside strict `xclim` matching. |

## What was validated in tests

Focused tests now cover:

- direct `xclim` comparison for core period metrics
- direct `xclim` comparison for seasonal slice metrics
- direct `xclim` comparison for hazard threshold-count semantics:
  `NDD`, `NTx35`, `NTx40`
- direct `xclim` comparison for weather-station annual precipitation reference indices:
  `rx1day`, `rx5day`, `CDD`, `CWD`, `R10mm`, `R20mm`, `SDII`
- climate-statistics result payload / rendering for top-level
  `xclim_references` standard rows and skip reasons
- compare-periods / ensemble-periods propagation of xclim reference deltas
- SPI nearest-reference agreement
- SPEI nearest-reference agreement
- compact statistics rendering that keeps xclim/SPEI summaries visible without
  dumping long monthly tables

## Important caveats

### SPI / SPEI are not strict xclim clones

Toolkit `SPI` / `SPEI` currently use:

- month-wise generalized-logistic fitting
- unbiased PWM default

Nearest `xclim` reference currently uses:

- `xclim.indices.stats.standardized_index`
- `fisk` distribution
- xclim fitting workflow

That means:

- agreement should be assessed by tracking behavior and magnitude, not bitwise equality
- users should not be told they are getting literal xclim outputs

### NDWS / WRSI are custom crop-water-balance diagnostics

These should continue to be described as:

- crop-water-balance metrics
- model-assumption dependent
- not standard ETCCDI / xclim indicators

## Remaining gaps

- extend direct `xclim` crosswalk into any future user-facing percentile-based
  precipitation totals if we expose them beyond weather-station diagnostics
- decide whether any currently named metrics should be renamed if their
  semantics differ from what a standard climate-indicator user would assume
- decide whether additional user-facing extremes beyond the current annual
  xclim reference block should be elevated into core statistics outputs
- keep count-definition audit separate from hazard-band calibration:
  `NDD` / `NTx35` / `NTx40` day counts can align with xclim while crop stress
  threshold bands remain Atlas-inspired provisional interpretation
