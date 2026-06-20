# NEX-GDDP Parallel Optimization Findings

Date: 2026-06-20

## Purpose

Summarize live Earth Engine benchmark evidence for NEX-GDDP parallel worker
tuning and record practical default guidance for toolkit users and developers.

## Bottom line

For current toolkit workload shape, optimization order is:

1. keep annual chunking (`chunk_days=365`) for sparse daily point extraction
2. add bounded model/process parallelism
3. stop scaling workers once throughput flattens for workload size

No quota / `429` / retry signal was observed in tested matrices up to
`32` workers, but throughput still showed diminishing returns. This means
parallelism helps, but it is not free and it is not infinite.

## Evidence base

Benchmark harness:

- `analysis/run_nex_parallel_optimization_benchmark.py`

Primary benchmark artifacts:

- `analysis/nex_parallel_opt_historical_1991_3models_w1246.json`
- `analysis/nex_parallel_opt_historical_1991_3models_w810.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w468.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w101216.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w202432.json`
- `analysis/nex_parallel_opt_cusco_all18_1985_2014_w816.json`
- `analysis/nex_parallel_opt_nairobi_policy_1985_2014_w816.json`

## Key results

### A. Smaller three-model job

Historical, `1991` only, `3` models, `10` sites, `chunk_days=365`,
`point_batch_size=25`.

Rows/sec ranking:

- `w=6` -> `1107.633`
- `w=8` -> `1006.114`
- `w=4` -> `975.226`
- `w=2` -> `918.830`
- `w=1` -> `903.454`
- `w=10` -> `899.580`

Interpretation:

- benefit rises through moderate worker counts
- best observed setting for this smaller workload was `6`
- `8` still good
- `10` already reversed

### B. Larger three-model job

Historical, `1985-2014`, `3` models, `10` sites, `chunk_days=365`,
`point_batch_size=25`.

Rows/sec ranking:

- `w=16` -> `3082.351`
- `w=12` -> `3041.319`
- `w=20` -> `3039.433`
- `w=24` -> `2889.091`
- `w=32` -> `2834.296`
- `w=8`  -> `2711.763`
- `w=10` -> `2659.120`
- `w=6`  -> `1863.862`
- `w=4`  -> `1484.741`

Observed service signals across these runs:

- quota lines: `0`
- retry lines: `0`

Interpretation:

- larger jobs continue to benefit past `8`
- practical plateau appears around `12-20`
- pushing to `24-32` did not crash or trigger quota warnings, but throughput
  no longer improved

### C. Policy-style regional checks

Single-site, long-window policy-style tests also improved strongly with higher
workers:

Cusco, all-18 style sweep, `1985-2014`:

- `w=16` -> `1881.081`
- `w=12` -> `1610.685`
- `w=8`  -> `1208.882`

Nairobi policy-style sweep, `1985-2014`:

- `w=16` -> `1190.048`
- `w=12` -> `1146.429`
- `w=8`  -> `779.952`

Interpretation:

- worker gains are still visible even for narrow-site policy workloads
- higher worker counts can help if model count is large enough

## Recommended guidance

### Toolkit default

Keep CLI default:

- `--model-workers 8`

Reason:

- safe middle ground
- clearly beneficial relative to low-worker serial-ish settings
- does not depend on chasing top-end plateau

### User guidance

- `1`: serial debug / constrained environments
- `4-6`: smaller jobs or conservative shared-machine use
- `8`: recommended general default
- `12-16`: heavier workstation / long-period multi-model runs
- `20+`: experimental; tested without quota signals here, but not recommended as
  normal default

### Explicit warning

These findings do **not** prove:

- all Earth Engine projects have same headroom
- `20+` is universally safe
- same scaling holds for many simultaneous users or mixed historical/SSP jobs

Absence of `429` in these runs means only:

- tested workload stayed below quota threshold for this project and timing

## Design implications

- chunking still matters more than worker count
- worker tuning is second-order, but now evidence-backed
- bounded parallelism belongs in higher-level NEX ensemble CLIs
- retry/backoff logic still needed even though current benchmark set stayed clean

## Repo hygiene choice

Keep:

- benchmark harness script
- benchmark summary `.csv` / `.json`
- this memo

Ignore:

- raw worker-run folders under `analysis/nex_parallel_opt_*_runs/`

That keeps reproducible summaries in repo while avoiding large noisy per-worker
log trees.
