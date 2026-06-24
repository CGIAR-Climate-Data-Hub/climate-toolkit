## Issue #30 THI method note

Current implementation choice for first livestock heat-stress step:

- metric: cattle `THI`
- formula: `THI = (1.8*T + 32) - ((0.55 - 0.0055*RH) * ((1.8*T) - 26))`
- temperature input: daily mean dry-bulb temperature
  - use explicit mean temperature if present
  - otherwise derive from `(tmax + tmin) / 2`
- humidity input: daily relative humidity in percent

Default operational thresholds in code:

- `<= 72`: `none`
- `> 72` and `<= 78`: `mild`
- `> 78` and `<= 89`: `moderate`
- `> 89`: `severe`

Important scope limits:

- cattle-focused default only
- not presented as universal across livestock species
- `nex_gddp` THI now depends on Earth Engine `hurs` availability
  - supported for toolkit-supported models where `hurs` is present
  - not universal across all Earth Engine NEX-GDDP models / scenario-year combinations

Current source-support position:

- supported:
  - `agera_5`
  - `nasa_power`
  - `nex_gddp` when `hurs` is available for the selected model / scenario / period
  - weather-station workflows where humidity is available
  - custom station uploads with humidity / RH
- not yet supported:
  - precip-only sources (`chirps_v2`, `chirps_v3_daily_rnl`, `imerg`, `tamsat`)
  - temp-only `chirts`

Current output semantics:

- daily THI series
- stress-band classification per day
- period summaries with:
  - mean THI
  - max THI
  - day counts by band
  - total stress days

Still open after this first cut:

1. species-specific threshold profiles
2. explicit hazard-module integration
3. user-facing CLI / report surface
4. fuller catalog-aware handling for projected-climate humidity edge cases beyond current documented `hurs` gaps
5. literature sweep to decide whether default should stay on mean-temperature THI or also expose max-temperature screening variant

Additional repo follow-up now completed:

- public metadata helper: `climate_tookit.climatology.describe_thi_method()`
- user-facing method guide: `docs/thi_workflow.md`
