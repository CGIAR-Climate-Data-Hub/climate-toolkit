# Issue Draft: Expand weather-station validation workflow and align standard metrics with xclim where applicable

## Summary

Current `weather_station.compare` proves basic station-vs-grid comparison works, but still uses all-vars single-station logic, limited daily metrics, and no `xclim` alignment for standard climate indices.

This issue tracks `weather_station.compare` v2.

## Why this matters

- nearby stations often have uneven variable coverage
- best precipitation station may differ from best temperature station
- daily precipitation correlation alone can be misleading
- product ranking should depend on use case
- standard indices should be benchmarked against `xclim` where clean analogues exist

## Checklist

### Phase 1. Variable-wise station selection
- [ ] Add `selection_strategy` to `weather_station.compare`
- [ ] Support `all_vars_single_station`
- [ ] Support `best_per_variable`
- [ ] Allow partial compare when some variables have no viable station
- [ ] Return selected station map by variable
- [ ] Report why each station was selected

### Phase 2. Confidence and overlap warnings
- [ ] Add overlap-day confidence classes
- [ ] Warn for low-confidence results
- [ ] Surface missing-variable and sparse-overlap warnings in text and JSON outputs

### Phase 3. Better precipitation occurrence metrics
- [ ] Add false alarm ratio
- [ ] Add critical success index
- [ ] Add precision / frequency-bias style occurrence metrics
- [ ] Keep wet-day hit/miss reporting

### Phase 4. Multi-timescale comparison
- [ ] Add monthly aggregated comparison
- [ ] Add seasonal aggregated comparison
- [ ] Add annual aggregated comparison
- [ ] Keep daily comparison block

### Phase 5. Precipitation intensity and extremes
- [ ] Add wet-day intensity bias
- [ ] Add quantile bias (`P50`, `P75`, `P90`, `P95`, `P99`)
- [ ] Add `Rx1day`
- [ ] Add `Rx5day`
- [ ] Add threshold exceedance counts (`R10mm`, `R20mm`, later others)

### Phase 6. Use-case ranking
- [ ] Add source ranking for `daily_monitoring`
- [ ] Add source ranking for `seasonal_totals`
- [ ] Add source ranking for `drought_screening`
- [ ] Add source ranking for `heavy_rain_screening`
- [ ] Add source ranking for `temperature_climatology`

### Phase 7. `xclim` alignment
- [ ] Identify current compare metrics with direct `xclim` analogues
- [ ] Add `xclim` crosswalk note for station-validation metrics
- [ ] Use `xclim` where practical for standard precipitation / temperature extremes
- [ ] Add regression tests comparing toolkit results to `xclim` reference outputs
- [ ] Document intentional deviations from `xclim`

Priority `xclim` candidates:
- [ ] `Rx1day`
- [ ] `Rx5day`
- [ ] `CDD`
- [ ] `CWD`
- [ ] `R10mm`
- [ ] `R20mm`
- [ ] warm / cold threshold counts where added

### Phase 8. Product metadata and caveats
- [ ] Add source metadata for likely station-informed products
- [ ] Warn when validation may be non-independent
- [ ] Distinguish gauge-informed vs reanalysis vs API products in output

### Phase 9. UX and logging
- [ ] Reduce backend log noise in normal runs
- [ ] Keep concise progress updates
- [ ] Improve failure summaries for GEE auth / coverage / station availability
- [ ] Add cleaner candidate-selection explanation

### Phase 10. Tests
- [ ] Add unit tests for variable-wise station selection
- [ ] Add unit tests for confidence classification
- [ ] Add unit tests for occurrence metrics
- [ ] Add unit tests for aggregated metrics
- [ ] Add unit tests for partial compare behavior
- [ ] Add unit tests for `xclim`-validated metrics

## Suggested implementation order

1. variable-wise station selection
2. confidence warnings
3. precipitation occurrence metrics
4. monthly / seasonal / annual aggregation
5. use-case ranking
6. `xclim` alignment for standard indices
7. logging cleanup
