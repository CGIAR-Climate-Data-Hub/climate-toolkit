## Summary

Propagate phase-1 human heat metric support through package workflows.

Current state:
- `climate_tookit.climatology.human_heat_stress` now provides xclim-backed
  `humidex` helpers
- method choice and source audit resolved in `#91`

Missing:
- `climate_statistics` summaries
- `compare_periods` outputs
- `calculate_hazards` decision on whether generic human heat classes belong in
  hazard workflow yet

## Scope

Use `humidex` as current human heat metric. Do not reopen `WBGT` / `UTCI`
selection here.

## Tasks

1. `climate_statistics`
- add optional human heat summary block when humidity or dewpoint-backed inputs
  exist
- keep output explicit that this is continuous metric support

2. `compare_periods`
- add human heat summary in baseline/focal/future comparisons where source
  support exists

3. `calculate_hazards`
- decide whether phase-1 stops at continuous metric
- if any bands are added, label them as generic screening, not definitive
  occupational-health thresholds

4. docs/tests
- update docs and CLI examples
- add regression tests across supported and unsupported source patterns

## Acceptance criteria

- human heat summary available in at least `climate_statistics`
- compare-period reporting path documented or implemented
- hazard-layer stance explicit
- no false claim that toolkit supports full `WBGT`/`UTCI` workflow
