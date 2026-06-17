## Title

Profile `ensemble_periods` runtime and optimize real bottlenecks

## Summary

Recent work made `compare_periods.ensemble_periods` somewhat faster by:

- applying requested GGCMI calendars directly
- skipping inner ETO sub-season detection in direct fixed-calendar mode
- suppressing noisy inner logs in compact mode

However, live rerun still showed only marginal speed improvement. This means skipped ETO work was only part of total cost. We need stage-level timing before making more changes.

## Problem

Current runtime is still slow enough to be a practical problem for NEX-GDDP ensemble analysis.

Observed symptom:

- explicit GGCMI fixed-calendar runs still take tens of seconds per model in some cases

Without profiling, we are guessing about cause. Remaining cost may be in one or more of:

- baseline historical fetch/cache read
- future fetch/cache read
- repeated dataframe assembly / JSON read path
- repeated ET0 / water-balance derivation
- repeated seasonal reduction logic
- final aggregation / rendering

## Why this matters

This workflow is central to future-climate comparison work. If one ensemble run remains slow for one site and one scenario, multi-site and multi-scenario use will become hard to scale.

We need evidence before attempting:

- parallel model execution
- cache layout changes
- batched fetch refactors
- reduction-path simplification

## Proposed work

Add explicit per-stage timers inside `climate_tookit.compare_periods.ensemble_periods` for each model:

- baseline fetch + stats
- future fetch + stats
- comparison assembly
- aggregate / print

Also expose run-level totals:

- total wall-clock
- mean per-model time
- slowest models
- cache-hit vs cache-miss context where possible

## Suggested output shape

Compact per-model timing:

```text
[01/17] ACCESS-CM2 | baseline=11.2s | future=9.8s | compare=0.4s | total=21.4s
```

End summary:

```text
Runtime summary:
- models_ok=17
- mean_model_time=...
- median_model_time=...
- slowest_models=...
- total_elapsed=...
```

## Acceptance criteria

- runtime breakdown visible for each model
- summary identifies dominant stage(s)
- one live benchmark captured after instrumentation
- next optimization step chosen from measured bottleneck, not guesswork

## Likely follow-on actions

- if fetch dominates: improve cache path or batch I/O, consider controlled parallelism
- if stats reduction dominates: simplify repeated transforms and season-stat passes
- if output/rendering dominates: trim report work from compute path
