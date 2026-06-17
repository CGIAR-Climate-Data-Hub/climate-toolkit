# NEX-GDDP Many-Points Benchmark Note

Audit date: 2026-06-10

## Question

Can real NEX-GDDP daily extraction be made fast enough for many site/model/
scenario permutations, and if so, should we use Xee or direct Earth Engine for
sparse point workloads?

## Test Setup

Project:

- `your-ee-project-id`

Dataset path:

- `NASA/GDDP-CMIP6`

Model:

- `MRI-ESM2-0`

Sites:

- 10 benchmark sites across East Africa, Sahel, and Andes
- file: `analysis/sites_benchmark.csv`

Extractor paths tested:

1. single-site Xee PoC
2. direct Earth Engine many-point extractor

## Official Guidance Reviewed

### Earth Engine

Official best-practices guidance says:

- when `reduceRegions()` struggles on large inputs, consider mapping
  `reduceRegion()` over a `FeatureCollection`, or use a controlled loop
- Earth Engine also documents the `"Collection query aborted after accumulating
  over 5000 elements"` failure mode

Source:

- <https://developers.google.com/earth-engine/guides/best_practices>

Official usage/quota guidance says:

- interactive quotas are per project
- defaults include `40` concurrent requests and `100 requests/s` per project
- fixed limits also include memory, aggregation, payload, and computed result
  size constraints
- `429 Too Many Requests` can occur when concurrency is exceeded

Source:

- <https://developers.google.com/earth-engine/guides/usage>

### Xee

Official Xee performance guidance says:

- high-volume endpoint is appropriate for reading stored collections
- consolidate operations server-side before opening in Xee
- avoid re-opening repeatedly; cache intermediate results
- start with modest parallelism

Source:

- <https://github.com/google/Xee/blob/main/docs/performance.md>

## Key Live Results

### Single-site Xee smoke tests

7-day real fetches succeeded for:

- Nairobi
- Lodwar
- Cusco

Observed runtime:

- about `8s` per 7-day site pull

Observed realism improvement over synthetic backend:

- Lodwar came back much hotter and drier than Nairobi
- Cusco came back much cooler than both
- this fixes core location-invariance problem seen in synthetic placeholder

### Direct Earth Engine many-point extractor

3 sites × 7 days × 1 model × 1 scenario:

- runtime: `1.03s`
- much faster than three separate Xee pulls (`~24s` total)

10 sites × 30 days × 1 model × `historical`:

- runtime: `1.35s`

10 sites × 30 days × 1 model × `ssp245`:

- runtime: `1.29s`

10 sites × 365 days × 1 model × `historical`:

- `chunk_days=30` -> `22.07s`
- `chunk_days=90` -> `6.12s`
- `chunk_days=365` -> `2.71s`

This shows:

- larger chunks substantially reduce overhead at this scale
- annual chunking outperformed monthly and quarterly chunking for 10 sites

### Cached ensemble wrapper

Small live proof run:

- 3 sites
- 7 days
- 2 models: `MRI-ESM2-0`, `ACCESS-CM2`
- 2 scenarios: `ssp245`, `ssp585`

First run:

- all four model/scenario combinations fetched from Earth Engine
- per-batch runtimes ranged about `1.08s` to `1.82s`
- outputs written to:
  - `analysis/nex_ensemble_poc_summary.csv`
  - `analysis/nex_ensemble_poc_manifest.csv`

Second identical run:

- same requests were served from local parquet cache
- manifest recorded `cache_hit=True` for all four batches
- cache files were created under:
  - `analysis/cache/nex_gddp_many_points/v1/<scenario>/<model>/...parquet`

What the cache key currently includes:

- cache schema version
- scenario
- model
- date start
- date end
- site-batch size and site-batch digest

This is enough to safely reuse results across repeated:

- site batches
- time windows
- model sweeps
- SSP sweeps

Current limitation:

- the cache is chunk-local, not query-global
- that is correct for reuse, but higher-level orchestration still needs to
  manage many chunks for large ensemble runs

### Decade-scale failure

10 sites × 1991-2000 × 1 model × `historical` with `chunk_days=3650` failed:

- error: `"Collection query aborted after accumulating over 5000 elements."`

This matches official Earth Engine guidance and gives practical sizing rule.

## Practical Rule Derived From Live Runs

For this direct EE design, output size grows roughly with:

- `site_count x day_count`

Safe operating rule:

- keep `site_count x chunk_days` below about `4500`

Reason:

- official Earth Engine guidance references failures once collections exceed
  about `5000` elements
- our 10-year one-chunk run failed far above that size
- our 10-site, 365-day one-chunk run (`3650` elements) succeeded

Example safe chunk sizes:

- 10 sites -> about 450 days
- 25 sites -> about 180 days
- 50 sites -> about 90 days
- 100 sites -> about 45 days

## Current Conclusion

### Use Xee when

- testing one site or a few sites
- you want xarray workflow
- you want grid/raster style access

### Use direct Earth Engine many-point extraction when

- extracting daily series for many sparse sites
- running many site/model/scenario permutations
- optimizing throughput matters more than xarray ergonomics
- reusing cached chunk outputs across repeated operator workflows

## Recommended Defaults

1. Keep Xee PoC for spot validation and raster-style analysis.
2. Use direct EE many-point extractor for sparse point batches.
3. Auto-size `chunk_days` from number of sites.
4. Use conservative target like `site_count x chunk_days <= 4500`.
5. Cache detailed outputs locally once fetched.
6. For ensemble sweeps, cache at chunk level and write manifest metadata for
   auditability.

## Relevant Files

- `analysis/run_nex_gddp_xee_smoke.py`
- `analysis/run_nex_gddp_many_points_ee.py`
- `analysis/run_nex_gddp_ensemble_cache.py`
- `analysis/sites_benchmark.csv`
- `analysis/nex_ensemble_poc_summary.csv`
- `analysis/nex_ensemble_poc_manifest.csv`
- `analysis/nex_many_points_historical_1991_full_chunk30_summary.csv`
- `analysis/nex_many_points_historical_1991_full_chunk90_summary.csv`
- `analysis/nex_many_points_historical_1991_full_chunk365_summary.csv`
