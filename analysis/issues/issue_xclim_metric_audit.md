## Title

Audit climate metrics against xclim definitions and reference outputs

## Summary

Several package metrics now exist across `climate_statistics`, `compare_periods`, `season_analysis`, and `calculate_hazards`, but we have not yet done a systematic validation pass against a widely used climate-indicator reference implementation.

[`xclim`](https://xclim.readthedocs.io/en/stable/) is a strong benchmark for this because it provides a large library of standard climate indicators and indices, with documented definitions, units, resampling logic, and established methodological conventions.

This issue is to audit overlapping package metrics against `xclim`, align definitions where appropriate, and explicitly document any intentional deviations.

## Why this matters

At the moment there is a real risk that:

- some metrics are named in a way that implies standard definitions, but are implemented differently
- seasonal and annual aggregations may not match standard resampling conventions
- percentage-change and anomaly summaries may be mathematically correct but still methodologically inconsistent with common climate-indicator practice
- variability and extremes are under-specified relative to what users will expect
- custom metrics may be mixed together with standard metrics without clear provenance

If we are asking users to compare sites, seasons, historical products, and NEX-GDDP futures, we need stronger confidence that the underlying metrics mean what we say they mean.

## Scope

This audit should focus first on metrics where a direct or near-direct `xclim` analogue exists.

Priority groups:

1. Core precipitation metrics
- annual / seasonal precipitation total
- wet-day frequency / rainy days
- simple daily intensity style metrics
- maximum 1-day precipitation
- maximum 5-day precipitation
- consecutive dry days
- consecutive wet days
- heavy / very heavy precipitation day counts
- percentile-based precipitation totals where relevant

2. Core temperature metrics
- mean temperature
- mean maximum temperature
- mean minimum temperature
- hottest / coldest day style summaries
- warm / cold day threshold counts where relevant

3. Drought / water-balance metrics
- SPEI implementation and summary logic
- dry-spell style metrics
- spell duration conventions

4. Ensemble summary statistics
- whether spread/uncertainty summaries are being calculated and reported in a defensible way
- whether inter-model spread is kept separate from temporal variability

## Out of scope for strict xclim matching

Some package metrics are custom and may not map cleanly to `xclim`. These should still be reviewed, but against their own methodological references, not forced into an `xclim` frame.

Examples:

- NDWS
- WRSI
- crop-calendar-aware season windows
- custom hazard thresholds

For these, the audit should instead answer:

- is the metric definition clearly documented?
- is the implementation internally consistent?
- what reference method or publication is it based on?

## Proposed approach

1. Build a crosswalk table:
- package metric name
- package module / function
- current formula or aggregation rule
- expected units
- nearest `xclim` indicator / index
- status: match / approximate / no analogue / needs redesign

2. Create reproducible reference tests using the same input daily series:
- run package metric
- run corresponding `xclim` metric
- compare values
- define tolerance where exact equality is not expected

3. Resolve discrepancies explicitly:
- fix implementation
- rename metric if it is not the standard metric users would assume
- document intentional deviation if we keep a non-standard formulation

4. Surface methodological provenance in docs:
- standard metric sourced from `xclim` / ETCCDI-style logic
- custom metric sourced from hazard- or crop-specific literature

## Deliverables

- crosswalk table for overlapping metrics
- unit tests comparing package outputs to `xclim` reference outputs
- documentation note listing:
  - metrics validated against `xclim`
  - metrics intentionally different from `xclim`
  - custom metrics requiring separate references

## Acceptance criteria

- overlapping standard metrics have an explicit `xclim` comparison result
- any metric that differs from `xclim` is either fixed, renamed, or documented
- at least one regression test exists for each validated metric family
- users can tell which outputs are standard indicators versus package-specific constructs

## Useful references

- `xclim` docs: [https://xclim.readthedocs.io/en/stable/](https://xclim.readthedocs.io/en/stable/)
- climate indices: [https://xclim.readthedocs.io/en/stable/indices.html](https://xclim.readthedocs.io/en/stable/indices.html)
- climate indicators API: [https://xclim.readthedocs.io/en/stable/api_indicators.html](https://xclim.readthedocs.io/en/stable/api_indicators.html)

## Suggested follow-on tasks

- start with precipitation metrics because they are most exposed in current outputs
- use `xclim` to benchmark variability and extremes before expanding hazard reporting
- keep NDWS / WRSI in a separate methodological review track rather than treating them as standard climate indices
