## Issue #91 human heat-stress method note

## Decision

Phase 1 human heat metric should be `humidex`, implemented through `xclim`.

Phase 1 scope:
- continuous metric support only
- no hazard-band semantics yet
- no claim that `humidex` is globally best physiological metric

Reason:
- package can support `humidex` from daily mean temperature plus humidity or
  dewpoint
- this works across current historical source paths better than `WBGT` or
  `UTCI`
- future-path support is possible where `nex_gddp` has `hurs`

## Candidate review

### `humidex`

Selected first.

Pros:
- available in `xclim`
- accepts dewpoint or relative humidity path
- fits current package input coverage
- feasible for:
  - `agera_5`
  - `nasa_power`
  - humidity-enabled stations / custom uploads
  - conditional `nex_gddp` runs with `hurs`

### `heat_index`

Not selected as first default.

Reason:
- `xclim` supports it, but notes validity only for temperatures above `20C`
- equation assumes instantaneous temperature and humidity, while toolkit mostly
  works with daily summaries
- less attractive as first global default for mixed tropical / highland /
  Andean workflows

### `UTCI`

Deferred.

Reason:
- `xclim` supports it
- operational workflow needs temperature, humidity, wind, and mean radiant
  temperature or radiation terms
- current package does not have coherent future-path support for those broader
  inputs

### `WBGT`

Deferred.

Reason:
- broader radiation / wind treatment needed for operational use
- current package source coverage is not coherent enough for first-pass future
  workflow

## Source audit

### Strong first-pass support

- `agera_5`
  - humidity available through current dewpoint + air-temperature derivation
- `nasa_power`
  - humidity available in current fetch path
- `ghcn_daily`, `gsod`, `custom_station`
  - supported when humidity / dewpoint fields exist

### Conditional support

- `nex_gddp`
  - usable for `humidex` only when Earth Engine `hurs` exists for selected
    model / scenario / period

### Weak or unsupported

- `era_5`
  - current runtime path does not expose operational humidity support clearly
- `chirps_v2`, `chirps_v3_daily_rnl`, `imerg`, `tamsat`
  - no human heat metric support as standalone sources
- `chirts`
  - temperature-only path, insufficient for `humidex`

## Package direction

Immediate implementation slice:
1. add `climate_tookit.climatology.human_heat_stress`
2. expose `compute_daily_humidex()` helper
3. expose source-support + method-description helpers
4. add tests

Later propagation:
1. `climate_statistics`
2. `compare_periods`
3. `calculate_hazards`

## References used for decision

- local `xclim` runtime/docstrings:
  - `humidex(tas, tdps=None, hurs=None)`
  - `heat_index(tas, hurs)` with validity note above `20C`
  - `universal_thermal_climate_index(tas, hurs, sfcWind, mrt|radiation...)`
- toolkit source audit in current repo

## Closing logic

`#91` can close once:
- method choice accepted
- helper lands
- remaining propagation work split into implementation follow-up if needed
