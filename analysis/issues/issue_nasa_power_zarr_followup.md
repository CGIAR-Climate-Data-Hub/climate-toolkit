# Follow up NASA POWER Zarr backend option for multi-site / long-timeseries workloads

## Summary

Current `nasa_power` backend uses direct NASA POWER point API requests. That is
simple and reliable for small jobs, but likely inefficient for:

- many points
- long daily time series
- repeated station-vs-grid and multi-site comparison runs

External suggestion worth testing:

- use NASA POWER public Zarr stores instead of hundreds of point API requests
- vectorize point extraction across many sites instead of looping point-by-point
- compare temporal-indexed vs spatial-indexed layouts

Candidate stores mentioned:

- temporal:
  `https://nasa-power.s3.amazonaws.com/merra2/temporal/power_merra2_daily_temporal_lst.zarr/`
- spatial:
  `https://nasa-power.s3.amazonaws.com/merra2/spatial/power_merra2_daily_spatial_lst.zarr/`

Claim from field use:

- temporal layout much faster for long time series across a few or many points
- spatial layout better for larger windows across fewer dates
- example script reportedly found spatial about 8x slower than temporal even for 5 points

## Why this matters

- `nasa_power` is key current local-open source in toolkit
- weather-station comparison and multi-site workflows will often request many
  long point series
- current API path may become bottleneck before compute/analysis stage

## Proposed work

1. Inspect NASA POWER Zarr schema and variable coverage against current API backend.
2. Benchmark:
   - current point API
   - temporal Zarr
   - spatial Zarr
3. Test vectorized extraction across many points, not serial point loop.
4. Check whether backend can preserve current toolkit contracts:
   - same variable names
   - same units / transformations
   - same cache structure expectations
5. Decide whether to:
   - keep API only
   - add optional Zarr backend for large jobs
   - switch default backend for some workload shapes

## Acceptance criteria

- benchmark note exists for API vs temporal Zarr vs spatial Zarr
- recommendation documented by workload type
- no backend change without evidence on correctness and real runtime gain

## Notes

- likely best fit: temporal Zarr for long time series across many sites
- spatial Zarr may still help for map/window style workflows later
- backend must remain vectorized; per-point loop would waste main benefit

---

## Benchmark update (2026-06-23)

### Tested harness

- script: `analysis/run_nasa_power_zarr_benchmark.py`
- sites: from `analysis/sites_benchmark.csv`
- compared:
  - current toolkit API backend (`api_point`)
  - temporal Zarr (`zarr_temporal`)
  - spatial Zarr (`zarr_spatial`)
- local rerun prerequisite for harness:
  - install `zarr` and `s3fs` in analysis environment first

### Important context

Current toolkit `nasa_power` backend already requests the **full date range per
site** from the NASA POWER point API. It is **not** making one HTTP request per
day. That means Zarr has to beat:

- one API request per site per period
- plus current toolkit normalization/caching path

This makes crossover less likely for modest site counts.

### Variable coverage findings

Shared Zarr coverage confirmed for:

- `precipitation` -> `PRECTOTCORR`
- `mean_temperature` -> `T2M`
- `max_temperature` -> `T2M_MAX`
- `min_temperature` -> `T2M_MIN`
- `humidity` -> `RH2M`
- `wind_speed` -> `WS2M`

Gap found:

- toolkit `solar_radiation` -> `ALLSKY_SFC_SW_DWN`
- not present in tested public temporal or spatial Zarr stores

That means public Zarr stores cannot currently do full drop-in replacement for
current toolkit NASA POWER variable contract.

### Correctness check on shared variables

One-site short-window comparison against current API path showed Zarr values
match API values to tiny float-rounding differences only:

- max absolute difference stayed on order of `~3e-05`
- nearest-grid resolution for Nairobi sample resolved to `lat=-1.5`, `lon=36.875`

Interpretation:

- shared-variable numerical content is effectively consistent
- main decision is runtime + coverage, not value mismatch

### Chunk geometry

Observed Zarr chunking:

- temporal store:
  - `[5844, 15, 15]` for `time, lat, lon`
- spatial store:
  - `[1, 361, 576]` for `time, lat, lon`

Interpretation:

- temporal store is chunked for long time series over local spatial tiles
- spatial store is chunked as one whole global grid per day
- spatial layout is structurally poor for point extraction over long periods

### Runtime summary

#### API vs temporal Zarr

| Sites | Period | API seconds | Temporal Zarr seconds | Temporal/API ratio |
| --- | --- | ---: | ---: | ---: |
| 1 | 10 days | 1.678 | 10.176 | 6.06x |
| 1 | 1 year | 1.574 | 9.289 | 5.90x |
| 1 | 10 years | 3.909 | 14.359 | 3.67x |
| 5 | 10 days | 7.038 | 15.176 | 2.16x |
| 5 | 1 year | 9.344 | 17.492 | 1.87x |
| 5 | 10 years | 18.246 | 27.351 | 1.50x |
| 10 | 1 year | 18.237 | 27.089 | 1.49x |
| 10 | 10 years | 33.742 | 50.495 | 1.50x |

Trend:

- temporal Zarr gets relatively closer as workload grows
- but in tested shapes it still stayed slower than current API backend
- temporal Zarr also still lacked `solar_radiation`

#### Spatial Zarr

Short-window point extraction only:

| Sites | Period | Spatial Zarr seconds |
| --- | --- | ---: |
| 1 | 10 days | 18.682 |
| 5 | 10 days | 16.788 |

Interpretation:

- even on tiny short-window runs, spatial Zarr stayed slower than API
- it was also slower than temporal Zarr for 1-site short-window test
- chunk geometry suggests it is wrong layout for toolkit point workflows

### Recommendation

Current recommendation:

- keep current NASA POWER point API backend as default
- do **not** switch toolkit backend to public Zarr stores now
- do **not** add public Zarr path as preferred multi-site default yet

Why:

1. API already performs well for tested toolkit-like workloads
2. temporal Zarr stayed slower up to 10 sites / 10 years
3. public Zarr stores currently miss toolkit `solar_radiation`
4. spatial store chunking is poor fit for point time-series extraction

### Nice-to-have follow-up

Public Zarr may still be worth revisiting if one of these changes:

- toolkit starts doing much larger batches (dozens to hundreds of sites per run)
- toolkit can tolerate hybrid backend behavior
  - e.g. Zarr for shared vars + API fallback for solar
- NASA publishes fuller or differently chunked public Zarr stores
- direct local chunk caching or multi-run reuse changes amortized cost

### Practical issue outcome

Issue `#54` should be treated as:

- benchmark/evaluation complete
- backend change **not** recommended now
- retain note so future larger-workload scaling work can revisit with evidence
