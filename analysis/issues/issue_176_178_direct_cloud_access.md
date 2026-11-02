# Issues 176–178: direct access implementation and evidence

Date: 2026-11-02. Status: local implementation; not merged or released.
Architecture authority: [package architecture summary](../package_architecture_summary.md).
User guide: [direct cloud access](../../docs/direct_cloud_access.md).
Issues: [#176](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/176),
[#177](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/177),
[#178](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/178).

Follow-up: [issue 179 investigation](issue_179_chc_backup_investigation.md) records
CHC archive/subset-service limitations and bounded cross-year read batching.
Missing years now load in batches of at most five years while keeping annual
cache records, revision isolation and resumability after later-batch outages.

## Decisions

- CHIRPS v3 final/RNL defaults to Dynamical, then Hugging Face, then permitted GEE.
  Complete compatible cached requests are preferred before network access. Provider
  order reflects smaller chunks, lower measured memory and newer final coverage;
  HF was faster on some one-year clustered queries. Explicit provider overrides
  remain available. Preliminary/SAT, v2 and unrelated rainfall are excluded.
- CHIRTS-ERA5 replaces legacy CHIRTS-daily for new temperature workflows. User
  authorized deprecation after comparing temporal coverage. The old explicit
  source key keeps its historical meaning and warns; it is not silently aliased.
  No second legacy cloud adapter/archive is introduced.
- With GEE disabled, historical auto uses CHIRPS v3 + CHIRTS-ERA5. Normal auto
  retains ERA5-Land companion variables where configured. Direct input QC cannot
  be bypassed by silently trying a different scientific dataset.
- Direct backends require Python 3.12+ plus the cloud extra (Zarr 3, Icechunk 2.3,
  HTTP fsspec and Dask). Base Python support remains 3.10+. This environment tested
  Python 3.12.10, xarray 2025.6.1, Zarr 3.4.2, Icechunk 2.3.1 on macOS ARM64.
  Python 3.10/3.11 were not executed; dependency markers exclude cloud packages.

## Product identity and coverage

| Product/provider | Live coordinate coverage | Pinned revision |
| --- | --- | --- |
| CHIRPS v3 HF | 1981-01-01–2026-08-31 | `e9466d3109c6d087c6cf60c19ca6ae20873d358a` |
| CHIRPS v3 Dynamical final | 1981-01-01–2026-09-30 | `YPS4QK3KM752R5XT8740` |
| CHIRTS-ERA5 HF | 1981-01-01–2026-10-21 | `35669afbbd1c6ab84dcc496f2f95b7cbbf75867f` |
| Legacy CHIRTS-daily GEE | 1983–2016 | Existing product; no new mirror |

HF CHIRTS documentation had older end dates and mentioned a 1959 underlying
start. Actual hosted coordinates start 1981; original CHC directories extend
further back. Runtime reads coordinates rather than promising card dates.
[CHC describes CHIRTS-ERA5 as extending CHIRTS-daily beyond 2016](https://www.chc.ucsb.edu/data/chirts-era5)
and publishes Tmax/Tmin with about five-day latency. Mirror lag is separate.
Broader coverage does not establish uniformly better local accuracy.

## Live correctness checks

1. Compared full 2020 (including leap day), three matching grid cells: Nairobi,
   Ouagadougou and Cusco, HF versus Dynamical CHIRPS. 1,098 records; no missing
   values; maximum daily absolute difference **0.081519 mm**, mean **0.016619 mm**.
   Three classifications differed at the strict `>1 mm` wet-day threshold.
2. Annual Dynamical/HF totals: Nairobi **1344.9899/1345.4 mm**;
   Ouagadougou **933.7631/933.6 mm**; Cusco **720.7990/720.3 mm**. These are mirror
   packing differences, not evidence of scientific equivalence at every threshold.
3. HF uses 0.1 mm quantization; Dynamical's
   [upstream configuration](https://github.com/dynamical-org/reformatters/blob/main/src/reformatters/ucsb_chc/chirps/template_config.py)
   retains eight float mantissa bits. A conservative diagnostic tolerance is
   `0.05 mm + abs(Dynamical value)/256 + 1e-5 mm`; it covers HF half-step and
   a full retained-bit relative step. It is not a universal threshold-equivalence
   guarantee, and no such tolerance is used to silently alter observations.
4. Original CHC Tmax for 2020-01-01 versus HF at those three cells differed by
   **0.047185, 0.026995 and 0.008651 degrees C**, within 0.05-degree packing error.
   Original CHIRPS and Tmin raster range reads failed in this environment. A
   subsequent Tmin HTTP range returned 206/TIFF, so absence is not established.
   Broad original-product, recent-year and station validation remains outstanding.
5. Deliberately disabled Dynamical, used a fresh cache, and fetched real HF CHIRPS
   with `allow_gee=False`: three complete dates returned, failed/successful attempts
   retained. This validates live fallback, not only mocks.
6. CHIRPS v3 + CHIRTS-ERA5 paired seasonal statistics for Nairobi March–May 2020
   completed without GEE (27.4 seconds), preserving both provider histories.

Evidence files: [cross-provider comparison](direct_cloud_evidence_2026-11-02/cross_provider_validation.json),
[original-file comparison](direct_cloud_evidence_2026-11-02/original_validation.json),
[live failover](direct_cloud_evidence_2026-11-02/live_failover.json).

## Performance protocol and results

Reproduce with `scripts/benchmark_direct_cloud.py --deadline 60`. Each case has
its own subprocess and temporary empty toolkit cache, two workers, a cold request
then an exact warm-cache comparison. One-year window is 2020; thirty-year window
is 1991–2020. Clustered coordinates vary near Nairobi; dispersed coordinates vary
around Nairobi/Ouagadougou/Cusco, not uniformly across the globe. One-site dispersed
is identical to one-site clustered and omitted. There are 30 distinct cases.

This exploratory run used a **60-second whole-case deadline** and **4 GiB estimated
source chunk-work budget**. Runtime defaults enforce the latter; transport timeouts
apply per request, not to the whole library call. Deadline failures mean work did
not finish in this benchmark, not that all long requests are impossible.

Network conditions were an ordinary shared development connection, not controlled.
Some independent validation ran concurrently. Cold means empty toolkit cache, not
empty upstream/CDN/OS caches. Actual transferred bytes, request counts and retry
counts were not instrumented; source-chunk work estimates are explicitly separate.
GEE comparison could not run because the environment had no configured project ID;
initialization failed before authentication. No interactive auth was attempted.

| Product/provider | Sites | Layout | Years | Cold seconds | Warm seconds | Peak RSS MiB | Status |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| chirps_v3_daily_rnl / dynamical | 1 | clustered | 1 | 9.01 | 0.011 | 285 | ok |
| chirps_v3_daily_rnl / dynamical | 10 | clustered | 1 | 8.333 | 0.018 | 295 | ok |
| chirps_v3_daily_rnl / dynamical | 10 | dispersed | 1 | 10.236 | 0.018 | 325 | ok |
| chirps_v3_daily_rnl / dynamical | 100 | clustered | 1 | 8.952 | 0.079 | 303 | ok |
| chirps_v3_daily_rnl / dynamical | 100 | dispersed | 1 | 15.342 | 0.081 | 384 | ok |
| chirps_v3_daily_rnl / dynamical | 1 | clustered | 30 | 36.009 | 0.065 | 537 | ok |
| chirps_v3_daily_rnl / dynamical | 10 | clustered | 30 | 36.325 | 0.28 | 554 | ok |
| chirps_v3_daily_rnl / dynamical | 10 | dispersed | 30 | — | — | — | deadline_exceeded |
| chirps_v3_daily_rnl / dynamical | 100 | clustered | 30 | 40.921 | 2.621 | 1120 | ok |
| chirps_v3_daily_rnl / dynamical | 100 | dispersed | 30 | — | — | — | deadline_exceeded |
| chirps_v3_daily_rnl / huggingface | 1 | clustered | 1 | 7.432 | 0.011 | 527 | ok |
| chirps_v3_daily_rnl / huggingface | 10 | clustered | 1 | 7.157 | 0.018 | 521 | ok |
| chirps_v3_daily_rnl / huggingface | 10 | dispersed | 1 | 12.365 | 0.045 | 582 | ok |
| chirps_v3_daily_rnl / huggingface | 100 | clustered | 1 | 6.86 | 0.101 | 546 | ok |
| chirps_v3_daily_rnl / huggingface | 100 | dispersed | 1 | 17.929 | 0.111 | 619 | ok |
| chirps_v3_daily_rnl / huggingface | 1 | clustered | 30 | — | — | — | deadline_exceeded |
| chirps_v3_daily_rnl / huggingface | 10 | clustered | 30 | — | — | — | deadline_exceeded |
| chirps_v3_daily_rnl / huggingface | 10 | dispersed | 30 | 2.537 | — | 205 | chunk-work budget exceeded |
| chirps_v3_daily_rnl / huggingface | 100 | clustered | 30 | — | — | — | deadline_exceeded |
| chirps_v3_daily_rnl / huggingface | 100 | dispersed | 30 | 3.121 | — | 206 | chunk-work budget exceeded |
| chirts_era5 / huggingface | 1 | clustered | 1 | 10.254 | 0.01 | 742 | ok |
| chirts_era5 / huggingface | 10 | clustered | 1 | 9.941 | 0.018 | 577 | ok |
| chirts_era5 / huggingface | 10 | dispersed | 1 | 21.774 | 0.018 | 755 | ok |
| chirts_era5 / huggingface | 100 | clustered | 1 | 10.164 | 0.105 | 581 | ok |
| chirts_era5 / huggingface | 100 | dispersed | 1 | 25.353 | 0.108 | 823 | ok |
| chirts_era5 / huggingface | 1 | clustered | 30 | — | — | — | deadline_exceeded |
| chirts_era5 / huggingface | 10 | clustered | 30 | — | — | — | deadline_exceeded |
| chirts_era5 / huggingface | 10 | dispersed | 30 | 3.008 | — | 208 | chunk-work budget exceeded |
| chirts_era5 / huggingface | 100 | clustered | 30 | — | — | — | deadline_exceeded |
| chirts_era5 / huggingface | 100 | dispersed | 30 | 2.617 | — | 209 | chunk-work budget exceeded |

All 18 completed cases had exact cold/warm values, coordinates and column order.
Initial development exposed a float/column-order cache serialization issue; those
cases were rerun after fixing it. The table and JSON retain the corrected reruns.
[Full measurements](direct_cloud_evidence_2026-11-02/benchmarks_2026-11-02.json).

One-year access is useful across tested workloads. Dynamical supports clustered
30-year rainfall extraction within the gate; dispersed long requests and HF long
requests need more work. JSON warm cache for 1.1 million rows takes 2.6 seconds and
peak memory can reach 1.1 GiB. Do not advertise all 30-year workloads as fast.

## Remaining issue acceptance and follow-ups

Implementation includes backend/no-GEE controls, strict provider identity/coverage,
QC, revision-safe cache, provenance, paired integrations and offline regression
coverage. Tests exercise explicit versus automatic routing, forced outages,
429/503/timeouts, missing coverage/units, QC, cache corruption/isolation/revisions,
exact coordinates, leap-day/grid ties and spawned-worker policy.

The broader validation items remain open: full original/GEE comparison across
historical/recent seasons, station evaluation, transfer/request instrumentation,
coastal/nodata integration coverage and improvements to long-window performance.
These are not replaced by mocked tests or by the successful three-site samples.

- [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179): independent
  CHC CHIRTS-ERA5 backup; one integrated provider until validated.
- [#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180): exact
  ERA5-Land companion-variable access without GEE; actual AgERA5 is a different product.
- Existing #54 and #1 retain NASA POWER Zarr and NEX version sourcing scope.

Validation: full suite **660 passed, 104 subtests passed** (14 dependency/test
warnings, 143.76 seconds). A final GEE setup-error reporting regression was added
afterward; all **35 direct-provider tests passed**. Ruff and `uv lock --check`
passed. Live tests are separate from the offline suite.

Issues 176–178 remain open while implementation is local and outstanding validation
is visible. No claim of universal redundancy, merged code or released support.


## End-to-end pipeline hardening follow-up

User requested stability from start to finish after the initial integration.
Additional integration tests execute real calculations, replacing only external
cloud/elevation inputs. They cover the complete explicit pair and no-GEE auto
workflow, forced provider outage, offline repeat, per-site failure isolation,
invalid-temperature rejection, complete-year climatology, CLI exit codes,
station comparison, CSV provenance round-trip and stale report cleanup.

Found and fixed wrapper gaps: paired/auto requests were sent to an exact-source
fetch API; pair parameters and some controls were not forwarded; returned error
dictionaries could be labeled completed; date-only runs skipped statistics;
climatology could discard unavailable/QC-failed years; CLI could exit successfully
on an error result; and saved reports could lose provenance on reload. Pipeline
now uses existing shared ingestion for paired/auto requests and exports complete
per-site report/status bundles.

Live verification ran Nairobi's full 2020 chain, 2019–2020 climatology and 2019
baseline versus 2020 comparison with real Dynamical/HF data. All six stages
completed, 366 daily records, both product histories preserved. First run took
26.29 seconds with some existing cache available; fully cached replay took
0.72 seconds, made zero cloud-provider/GEE calls and reproduced daily values
exactly. This is a functional verification, not a fresh cold-cache benchmark.

[Verification record](direct_cloud_evidence_2026-11-02/pipeline_verification.json).
Full local reports: `outputs/direct_pipeline_validation_2026-11-02/`.
The two-year climatology and one-year comparison baseline deliberately exercise
routing and reductions; they are not scientifically adequate long-term normals.


The live chain was repeated after correcting human-heat metadata: CHIRTS-ERA5
is identified as the temperature provider; absent humidity, dewpoint, wind and
radiation sources are null. Metadata changes do not alter scientific values.
The reproducible live check is `scripts/verify_direct_pipeline.py`.
Source/wheel distributions build successfully. Ruff, dependency lock and whitespace
checks pass. The first complete regression run passed 677 tests and 104 subtests;
135 targeted tests then passed after the metadata correction.

Final confirmation on the completed code: **677 tests passed, 104 subtests passed**
(18 warnings, 159.00 seconds). Final live report metadata and cached replay passed;
source/wheel builds and static/dependency checks passed. No GEE/provider credentials
were needed for the direct integration or its live end-to-end verification.
