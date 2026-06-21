## Title

Improve terminal UX for long-running climate-toolkit workflows

## Summary

Current terminal output is too verbose, too dense, and poorly structured for interactive use. During long-running workflows, especially NEX-GDDP ensemble runs and season-detection-heavy analyses, users need to see:

- what stage is currently running
- whether data is downloading or coming from cache
- what decisions or fallbacks were applied
- whether run is making progress
- what warnings need attention

Instead, current output often floods terminal with per-year and per-season diagnostics, making it difficult to monitor run status or understand what matters.

## Problem

Observed UX problems:

- Per-year rainfall / humidity / adaptive-parameter diagnostics dominate terminal output.
- Important state changes such as cache hits, download starts, fallback to fixed seasons, or direct calendar application are buried.
- Model-by-model progress is visible, but stage-level progress inside each model is not consistently clear.
- User cannot easily distinguish:
  - downloading vs cached reuse
  - active processing vs stalled run
  - routine diagnostics vs warnings/errors
- Long ensemble runs produce too much scrolling output to be practically reviewable during execution.

This is especially problematic for:

- `compare_periods.ensemble_periods`
- `climate_statistics.statistics`
- `season_analysis.seasons`
- `calculate_hazards.hazards`
- future multi-site / multi-model batch workflows

## Why this matters

This is not only cosmetic. Poor terminal UX makes it harder to:

- monitor long downloads
- detect stuck or failing runs early
- understand whether cache is working
- interpret fallback decisions
- identify warnings that actually need review
- trust workflow behavior during alpha testing

## Desired behavior

Default terminal mode should be compact and operationally useful.

Users should see:

- current high-level stage
- progress through sites / models / chunks
- cache hit vs download
- key decisions
  - auto season detection used
  - GGCMI preset applied
  - direct fixed-season mode used
  - year-crossing restriction triggered
- warnings and errors
- elapsed time and rough ETA where possible

Detailed diagnostics should still be available, but not in default mode.

## Proposed direction

Introduce explicit output levels:

- `--quiet`
  - errors only
- default / normal
  - concise progress + key decisions + warnings + end summary
- `--verbose`
  - richer per-stage diagnostics
- `--debug-log <file>`
  - full detector internals and detailed year-by-year trace written to file

## Suggested default output shape

Examples of more useful compact messages:

```text
[01/17] ACCESS-CM2 | baseline fetch | cache miss
[01/17] ACCESS-CM2 | baseline fetch | complete | 2m14s
[01/17] ACCESS-CM2 | future fetch   | cache hit
[01/17] ACCESS-CM2 | season mode    | auto failed -> GGCMI preset 10-22:01-09
[01/17] ACCESS-CM2 | aggregate      | complete | total 2m21s | eta 34m45s
```

Detailed lines like these should move out of default output:

- annual rainfall by year
- humidity guard details by year
- adaptive detector parameters by year
- duplicate-drop notes
- per-year fixed-season internals
- ETO sub-season diagnostics unless explicitly requested

## Design questions

- Should all modules share one common progress/logging utility?
- Should verbose detector output go to stderr and summaries to stdout?
- Should there be separate machine-readable progress events for future UI integration?
- Should cache events be standardized across historical, paired, and NEX-GDDP workflows?
- Should per-year diagnostics be summarized at end rather than streamed live?

## Initial acceptance criteria

- Default output for long runs is substantially shorter and easier to follow.
- User can clearly tell whether workflow is downloading, using cache, detecting seasons, or aggregating.
- Fallback decisions are always visible in default mode.
- Per-year diagnostic spam is suppressed unless `--verbose` or `--debug-log` is used.
- End-of-run summary includes:
  - models/sites processed
  - success/failure counts
  - cache reuse summary
  - warnings summary
  - total elapsed time

## Related follow-up work

- harmonize progress reporting across all CLI modules
- standardize cache hit/miss messages
- standardize warning formatting
- consider progress bars for model/site/chunk loops
- consider log file output for reproducible run auditing

## Current progress

This issue is no longer untouched.

Implemented so far:

- `climate_statistics.statistics`
  - default pandas output is now compact
  - raw climate tables and monthly SPI/SPEI previews are hidden unless `--verbose`
  - important run metadata and warnings still remain visible
- `compare_periods.periods`
  - added `--verbose`
  - monthly SPI/SPEI tables are now hidden in compact mode
  - compact mode prints a short rerun hint instead of dumping long monthly tables
- both paths now surface a clearer note when outputs include custom
  crop-water-balance metrics (`NDWS`, `NDWL0`, `WRSI`)

Still outstanding:

- broader stage/progress harmonization across fetch, season, hazard, and
  ensemble workflows
- standardized progress formatting across GEE/Xee, NEX-GDDP, TAMSAT, and
  weather-station paths

## 2026-06-21 follow-up

Live smoke on `compare_periods.periods` and
`compare_periods.ensemble_periods` showed progress, but also confirmed
remaining UX debt outside raw verbosity:

- GEE/Xee chunk logging still prints two lines for same chunk lifecycle
  (`starting` then `cache hit` / `fetched`) when one terminal line would be
  easier to scan.
- Low-level prefixes like `INFO gee_xee_batch.py:81` are useful for debugging
  but not ideal as default human-facing progress language.
- Some tables are still too wide for normal terminal windows, especially
  ensemble and comparison outputs with many spread columns.
- Long explanatory text in columns such as ranking notes should wrap or move to
  a detail view instead of forcing horizontal overflow.
- Stage naming still mixes compute concepts and transport concepts:
  `site`, `batch`, `chunk`, `starting`, `cache hit`, `fetched`, `completed`.
  Default mode should normalize these into clearer lifecycle language.

Concrete next targets:

- collapse per-chunk `starting` + terminal outcome into one progress line in
  compact mode
- keep machine/debug detail available only in verbose / debug-log mode
- standardize human-facing labels for:
  - fetch start
  - cache reuse
  - live download
  - season detection
  - aggregation
  - completion / failure
- add width-aware table rendering or compact column selection for large compare
  / ensemble tables
- wrap or truncate low-priority note fields in terminal views while preserving
  full content in JSON
