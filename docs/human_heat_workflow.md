# Human Heat Workflow

Current first-pass human heat support uses `Humidex` through `xclim`.

This is intentionally narrower than full occupational or outdoor-thermal
assessment workflows.

## Phase 1 choice

Selected metric:
- `humidex`

Deferred:
- `WBGT`
- `UTCI`
- higher-fidelity occupational heat workflows

## Why `humidex` first

- needs only temperature plus humidity or dewpoint
- available in current toolkit `xclim` stack
- matches current source coverage better than `WBGT` or `UTCI`
- can work on some future `nex_gddp` runs when `hurs` is available

## Why not `WBGT` first

`WBGT` is important, but current toolkit does not yet have coherent operational
support for broader wind / radiation treatment across intended historical and
future workflows.

## Why not `UTCI` first

`UTCI` is more physically rich, but first-pass package support is constrained by
input requirements:
- temperature
- humidity
- wind
- mean radiant temperature or radiation terms

Current package can support those inputs for some historical sources, but not
coherently across intended future workflows.

## Source support

Strong first-pass support:
- `agera_5`
- `nasa_power`
- `ghcn_daily` when humidity exists
- `gsod` when humidity exists
- `custom_station` when humidity or dewpoint exists
- `paired`
  - when temperature-side partner carries humidity or dewpoint
- `auto`
  - when chosen companion-temperature path carries humidity or dewpoint

Conditional support:
- `nex_gddp`
  - only when Earth Engine `hurs` exists for selected model / scenario / period

Not currently suitable:
- `era_5`
  - current runtime path does not expose operational humidity support clearly
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts`

## Current helper surface

Python helpers:
- `climate_tookit.climatology.build_human_heat_source_bundle`
- `climate_tookit.climatology.compute_daily_humidex`
- `climate_tookit.climatology.summarize_humidex_period`
- `climate_tookit.climatology.describe_human_heat_method`
- `climate_tookit.climatology.describe_human_heat_source_support`

Package propagation:
- `climate_statistics`
  - adds optional `human_heat_stress` block when humidity or dewpoint-backed
    inputs exist
- `compare_periods`
  - diffs `human_heat_stress` metrics when both baseline and focal windows
    support humidex
- `calculate_hazards`
  - adds generic humidex screening output and day-count summaries when
    humidity-backed inputs exist

## Current limits

- hazard classes are generic humidex screening classes, not full occupational
  or medical heat guidance
- no claim that `humidex` is globally best human heat metric

## Likely next steps

1. decide whether phase 2 uses:
   - `WBGT`
   - `UTCI`
   - some combination by source capability
2. add explicit method notes and source guardrails so users do not confuse
   generic humidex screening with full WBGT-style exposure assessment
