# Add explicit paired-source support for precip-only and temp-only datasets

## Summary

Several analysis modules currently assume one source can supply enough daily variables to drive:
- ET0
- water balance
- precipitation-based season detection / fixed-window season stats

That assumption is too narrow for real use. Some scientifically valid workflows need:
- precipitation from one source
- temperature from another source

Examples:
- `chirps` + `era_5`
- `chirps` + `agera_5`
- `imerg` + `era_5`
- `imerg` + `agera_5`

`chirts` can also act as temperature partner, but daily coverage ends in 2016, so it should be treated as legacy/historical rather than preferred.

## Why this matters

Current behavior mixes three patterns:

1. true full-climate sources
   - `era_5`
   - `agera_5`
   - `nasa_power`
   - `nex_gddp`

2. special-case patched precip-only sources
   - `chirps` currently works in `climate_statistics.statistics` only because code injects fallback `tmax=25`, `tmin=15`

3. sources rejected because there is no explicit pairing interface
   - `imerg`
   - `chirts`
   - post-2016 `chirps+chirts`

This makes interface scientifically muddy:
- some precip-only runs are allowed via synthetic temperature
- other precip-only runs are rejected
- paired-source use, which is legitimate, is not first-class

## Current evidence

Live `climate_statistics.statistics` source-matrix pass:
- passes: `era_5`, `agera_5`, `auto`, `chirps`, `nasa_power`, `nex_gddp`
- clean reject: `terraclimate`, `imerg`, `chirps+chirts`

Key findings documented in:
- `analysis/climate_statistics_source_matrix.md`

Important nuance:
- `imerg` is not scientifically incompatible with module goals
- it is only unsupported in current single-source interface

## Proposed design

Add explicit paired-source support to analysis modules that depend on both precip and temperature:
- `climate_tookit/climate_statistics/statistics.py`
- `climate_tookit/season_analysis/seasons.py`
- `climate_tookit/compare_periods/periods.py`
- likely `climate_tookit/calculate_hazards/hazards.py` too

Possible CLI/API shape:

```text
--precip-source chirps|imerg|era_5|agera_5|...
--temp-source   era_5|agera_5|nasa_power|chirts|...
```

Then:
- single-source mode stays available for full-variable datasets
- paired-source mode becomes explicit and reproducible
- legacy preset `chirps+chirts` can remain as shorthand for historical windows

## Expected behavior

1. If single source provides precip + temp:
   - use it directly

2. If source is precip-only:
   - require explicit temp partner
   - do not fabricate default temperatures for scientific runs

3. If source is temp-only:
   - require explicit precip partner

4. If paired sources have incompatible temporal coverage:
   - fail with clean message describing exact coverage mismatch

## Open questions

1. Should `chirps` single-source fallback (`tmax=25`, `tmin=15`) be deprecated immediately, or kept behind explicit legacy flag?
2. Should `auto` remain single-source/fallback logic only, or should it eventually resolve paired combinations too?
3. Do we want one generic merge utility in fetch/preprocess layer, or module-local pairing first?

## Suggested first implementation step

Implement paired-source support first in `climate_statistics.statistics`, because:
- requirements are clearest there
- stress tests already expose source-policy inconsistencies
- downstream modules can then reuse same merge contract

