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

Current PoC file:

- `climate_tookit/fetch_data/source_data/sources/nex_gddp_xee.py`
- `analysis/run_nex_gddp_xee_smoke.py`
- `analysis/run_nex_gddp_many_points_ee.py`

Current PoC goals:

- prove real Earth Engine fetch path
- preserve toolkit dataframe contract: `date`, `pr`, `tasmax`, `tasmin`
- normalize units at source adapter boundary
- enforce `historical` vs SSP date rules early

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
