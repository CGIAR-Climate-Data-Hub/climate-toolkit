# NEX-GDDP Access R&D Note

This branch tracks R&D work for landing real `nex_gddp` retrieval path in
package and measuring whether it is usable in practice.

## Problem

Original package state was synthetic placeholder data. Branch now replaces that
with real Earth Engine/Xee retrieval for `nex_gddp`.

## Access Constraint

Real NEX-GDDP retrieval through Google Earth Engine and Xee requires:

- Earth Engine authentication
- Google Cloud project registered for Earth Engine use
- server-side quota and credential management

That is acceptable for operators and developers, but too much setup for normal
end users running local CLI commands.

## R&D Direction

Treat Xee-backed NEX-GDDP as real package backend for now, while still planning
for operator-owned or hosted deployment model.

Current repo state on this branch:

- `nex_gddp` package path now routes to real Xee-backed Earth Engine adapter
- main package pipeline smoke succeeded through `fetch_data`
- Earth Engine auth and project setup are still required
- active runtime targets Earth Engine NEX-GDDP dataset version `1.1`
- version `1.2` should be tracked as future sourcing work, not emitted as
  runtime fallback noise

Current PoC file:

- `climate_tookit/fetch_data/source_data/sources/nex_gddp_xee.py`
- `analysis/run_nex_gddp_xee_smoke.py`
- `analysis/run_nex_gddp_many_points_ee.py`

Current PoC goals:

- prove real Earth Engine fetch path
- preserve toolkit dataframe contract: `date`, `pr`, `tasmax`, `tasmin`
- normalize units at source adapter boundary
- enforce `historical` vs SSP date rules early

## Arid-region rainbomb warning rationale

Current branch adds a targeted warning for suspicious NEX-GDDP daily rainfall
spikes in arid-like time series, not a generic global extreme-rainfall warning.

Reason:

- dryland rainfall is naturally more event-concentrated than humid climates
- very high event/annual or event/background ratios can appear in arid regimes
  even when mean rainfall stays low
- that makes ratio-driven downscaling or bias-correction artifacts especially
  important to inspect in deserts and semi-arid zones

Source basis:

- Zaerpour, Papalexiou, and Tang (2026), *Widespread shift toward extreme
  dominated precipitation with pronounced trends in arid and mediterranean
  regions*:
  [Nature PDF](https://www.nature.com/articles/s41598-026-47708-y_reference.pdf)
  This paper reports that extreme-precipitation dominance is highest in desert
  climates and that in arid regions the trend can be driven strongly by
  declining total rainfall, not only by stronger absolute extremes.
- Klutse et al. (2024), *Projected Changes in Rainfall Extremes over West
  African Cities Under Specific Global Warming Levels Using CORDEX and
  NEX-GDDP Datasets*:
  [ResearchGate page](https://www.researchgate.net/publication/383874166_Projected_Changes_in_Rainfall_Extremes_over_West_African_Cities_Under_Specific_Global_Warming_Levels_Using_CORDEX_and_NEX-GDDP_Datasets)
  This paper supports using NEX-GDDP for rainfall-extremes analysis, but also
  reinforces that extreme-rainfall behavior should be interpreted regionally
  and through ensemble comparison rather than by trusting isolated spikes.

## Recommended Product Shape

1. Hosted toolkit service owns Earth Engine auth and project configuration.
2. End users call toolkit API, not Earth Engine directly.
3. Service caches repeated site/model/scenario requests.
4. Local toolkit now returns real data, but still depends on operator Earth
   Engine credentials.

## Immediate R&D Tasks

1. Validate live Xee fetch with operator credentials.
2. Measure latency for single-site and many-site runs.
3. Decide batching and cache strategy for repeated site requests.
4. Replace synthetic `nex_gddp` adapter with real path in fetch/source/transform/preprocess entry points.
   Status: done.
