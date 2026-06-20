## Title

Record live NEX-GDDP parallel optimization findings and worker guidance

## Summary

Live Earth Engine benchmarks now support practical worker guidance for NEX-GDDP
parallel runs.

Main findings:

- annual chunking remains first optimization lever
- bounded workers help materially after chunking is sane
- small jobs peaked around `6` workers
- larger long-period multi-model jobs improved through about `12-20` workers
- no quota / `429` / retry signal appeared in tested matrices up to `32` workers

This is strong enough to document default guidance and stop treating worker
count as guesswork.

## Existing issue check

Best fit:

- `#7` runtime profiling / bottleneck optimization

Distinct contribution:

- converts profiling work into concrete operator guidance
- adds live benchmark evidence beyond stage-timing discussion
- includes higher-worker ceiling tests, not only `<=8`

## Benchmark artifacts

Harness:

- `analysis/run_nex_parallel_optimization_benchmark.py`

Primary result files:

- `analysis/nex_parallel_opt_historical_1991_3models_w1246.json`
- `analysis/nex_parallel_opt_historical_1991_3models_w810.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w468.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w101216.json`
- `analysis/nex_parallel_opt_historical_1985_2014_3models_w202432.json`
- `analysis/nex_parallel_opt_cusco_all18_1985_2014_w816.json`
- `analysis/nex_parallel_opt_nairobi_policy_1985_2014_w816.json`

Curated repo memo:

- `analysis/nex_parallel_optimization_findings.md`

## What was observed

### Smaller three-model workload

Historical `1991`, `3` models, `10` sites, `chunk_days=365`,
`point_batch_size=25`.

Rows/sec:

- `w=6` -> `1107.633`
- `w=8` -> `1006.114`
- `w=4` -> `975.226`
- `w=2` -> `918.830`
- `w=1` -> `903.454`
- `w=10` -> `899.580`

Interpretation:

- moderate workers help
- optimum for this smaller shape landed around `6`
- `10` was already too high for this job

### Larger three-model workload

Historical `1985-2014`, `3` models, `10` sites, `chunk_days=365`,
`point_batch_size=25`.

Rows/sec:

- `w=16` -> `3082.351`
- `w=12` -> `3041.319`
- `w=20` -> `3039.433`
- `w=24` -> `2889.091`
- `w=32` -> `2834.296`
- `w=8`  -> `2711.763`
- `w=10` -> `2659.120`
- `w=6`  -> `1863.862`
- `w=4`  -> `1484.741`

Signals:

- quota lines: `0`
- retry lines: `0`

Interpretation:

- larger jobs continue to benefit beyond `8`
- plateau appears around `12-20`
- more workers eventually flatten or reverse

### Policy-style long-window checks

Cusco, `1985-2014`, all-18 style:

- `w=16` -> `1881.081`
- `w=12` -> `1610.685`
- `w=8`  -> `1208.882`

Nairobi, `1985-2014`, policy-style:

- `w=16` -> `1190.048`
- `w=12` -> `1146.429`
- `w=8`  -> `779.952`

Interpretation:

- higher workers still help when model count is large enough

## Recommended guidance

- keep toolkit default at `--model-workers 8`
- advise `4-6` for smaller/conservative jobs
- advise `12-16` for heavier workstation runs
- treat `20+` as experimental ceiling-testing, not default usage

## What this does not prove

- that all Earth Engine projects can safely use same worker counts
- that `20+` should become default
- that mixed multi-user / multi-job contention will stay quota-clean

## Suggested follow-on

1. post summary findings into `#7`
2. keep benchmark harness
3. keep summary `.csv/.json` outputs
4. ignore raw `analysis/nex_parallel_opt_*_runs/` folders
5. revisit worker defaults only if new larger-scale evidence changes plateau
