## Summary

`climate_tookit.calculate_hazards.ensemble_hazards` currently violates expected ensemble order in two ways:

1. It pools different SSP scenarios together before the final aggregation step.
2. It computes hazard status from ensemble-mean climate statistics instead of preserving per-projection hazard results and only aggregating at the end.

This means output can silently blend `ssp245`, `ssp370`, and `ssp585` into one "ensemble" hazard assessment, and can also produce hazard labels that do not reflect the distribution of underlying model/scenario hazards.

## Why this matters

For this toolkit, ensembling should happen last.

Expected order:

1. fetch one projection
2. detect season / apply fixed window
3. compute season statistics for that projection
4. evaluate hazards for that projection
5. only then aggregate across projections, with scenario boundaries preserved unless explicitly requested otherwise

Current order is effectively:

1. fetch projection
2. compute season statistics
3. pool all projections into `(year, season_number)` buckets, regardless of scenario
4. average climate stats across pooled projections
5. evaluate hazards on those ensemble means

That can hide scenario divergence and produces hazard labels for a synthetic average projection that no model/scenario actually produced.

## Evidence from current code

### Scenario mixing before final ensemble

Results are appended for every `(model, scenario, window)` combination:

- `climate_tookit/calculate_hazards/ensemble_hazards.py`
  - `_evaluate(...)` returns `projection: {'model': model, 'scenario': scenario}`
  - `calculate_ensemble(...)` loops over `for sc in scenarios` and `for m in models`

But after that, projections are bucketed only by `(year, season_number)`:

```python
buckets[(si['year'], si['season_number'])].append(r)
```

No scenario key is retained in the aggregation bucket.

### Hazard evaluation happens after climate averaging

Per-window aggregation does:

```python
agg = _avg_stats(bucket)
...
'hazard_evaluation': _avg_hazards(crop, agg)
```

`_avg_hazards(...)` re-evaluates thresholds from the averaged climate stats, rather than aggregating already-evaluated projection-level hazard outcomes.

## Minimal repro from code path

Run `ensemble_hazards` with more than one scenario, e.g. `ssp245,ssp585`.

Even though the printed per-projection breakdown includes `scenario`, the aggregated `assessments` bucket is still one combined result per `(year, season_number)` because the grouping key drops scenario.

## Expected behavior

At minimum:

1. Scenario should remain part of the aggregation key, e.g. `(scenario, year, season_number)`.
2. Per-projection hazard evaluations should be preserved.
3. Final output should aggregate only at the last step, ideally reporting:
   - ensemble mean climate statistics
   - counts/shares of hazard statuses across projections
   - optionally per-scenario summaries before any cross-scenario rollup

## Existing issue search summary

Checked existing issues before posting:

- `#79` is broad `Calculate_hazards` feedback, but does not describe this specific aggregation-order bug.
- `#86` is about unsupported default `ssp370` in `ensemble_hazards`.
- `#87` is about `ensemble_hazards` importability.

This issue is distinct: incorrect ensemble construction / scenario mixing.

## Determination method

Determined by local source inspection and execution-path tracing in Codex / GPT-5 during package review of `ensemble_hazards.py`.
