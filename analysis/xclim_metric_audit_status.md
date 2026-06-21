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

- add direct `xclim` audit for additional precipitation extremes used in
  weather-station and hazard workflows
- extend comparison to `max_5day`, consecutive wet/dry days, and heavy-rain
  day counts where exposed to users
- decide whether any currently named metrics should be renamed if their
  semantics differ from what a standard climate-indicator user would assume

