# Issues 176–178: direct access implementation and evidence

Implementation and initial evidence: 2026-11-02. Released in 0.2.0.
[Published-package sample validation, 2026-11-07](#published-package-sample-validation-2026-11-07).
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

- A November 2026 long-window CHIRTS run exposed an unhandled
  `aiohttp.ClientResponseError` during chunk loading. The Hugging Face adapter
  now reports these exceptions through the shared provider policy. Offline
  regressions exercise failures during open and load under explicit Hugging Face,
  automatic no-GEE, and automatic GEE-permitted CHIRPS selection.
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
  Python 3.10 base-package validation was subsequently completed below;
  Python 3.11 remains untested. Dependency markers exclude cloud packages below 3.12.

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

## CHIRPS final/RNL reference comparison, 2026-11-08

Published toolkit 0.2.0 sampled both direct providers with Earth Engine disabled.
A separate authenticated read used the native projection of
[`UCSB-CHC/CHIRPS/V3/DAILY_RNL`](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHC_CHIRPS_V3_DAILY_RNL).
Matched pixel centres, sites and dates before comparing daily rainfall. The sample
covers Nairobi, Ouagadougou and Cusco in Dec 2019–Feb 2020 (91 days, including
leap day) and Dec 2025–Feb 2026 (90 days). Reference seasonal rainfall ranged
from 0.42 to 548.04 mm. All three sources returned all 543 site-days.

| Compared with Earth Engine | Dynamical final/RNL | Hugging Face final/RNL |
|---|---:|---:|
| Maximum absolute daily difference (mm) | 0.040260 | 0.049711 |
| Mean absolute daily difference (mm) | 0.002195 | 0.016156 |
| Wet-day disagreements at `>1 mm` / `>=1 mm` | 0 / 0 | 3 / 2 |
| Maximum absolute monthly total difference (mm) | 0.066971 | 0.446225 |
| Maximum absolute three-month total difference (mm) | 0.077574 | 0.648424 |

All daily comparisons passed the preselected tolerances: half the Hugging Face
0.1 mm packing step, or `abs(reference_mm)/256` for Dynamical's eight retained
mantissa bits, each with 0.00001 mm for floating-point conversion. The observed
maxima describe these cells and dates. Source revisions were
`VXA0TT74FKZCYRX7TN30` (Dynamical) and
`e9466d3109c6d087c6cf60c19ca6ae20873d358a` (Hugging Face).

A separate cold read used an empty toolkit cache and a process with credential
environment variables cleared and access to user credentials blocked. On leap
day, both mirrors selected the same cells at Mombasa, offshore, on a shared
cell boundary and at the four geographic limits. Both preserved ocean nodata
in raw data and rejected it for analysis.

Reproduce with Python 3.12+ and the published cloud extra. Set `GCP_PROJECT_ID`
for the reference only. From the repository root:

```sh
python scripts/verify_chirps_reference.py
python scripts/verify_chirps_reference.py --grid-only
```

Daily pairs, monthly and seasonal totals, revision/coordinate records and the grid
report are written to `outputs/validation/issue-177/`. Repeated direct requests
can reuse that directory's cache. The earlier benchmark matrix estimated one-site,
one-year decoded chunk work of 10,512,000 bytes for Dynamical and 92,160,000
bytes for Hugging Face for the same 366 daily values. Measured HTTP traffic appears below.

## CHIRPS HTTP benchmark, 2026-11-09

We ran all 20 distinct CHIRPS cases serially with the published 0.2.0 cloud
extra, two workers, a fresh process and toolkit cache for each case, a
60-second whole-case deadline and the 4 GiB decoded-work limit. Both providers
read the same 2020 or 1991–2020 site sets as the November 2 matrix. One site
has only one layout. No Earth Engine account or provider token was used by
either direct adapter.

| Years | Sites | Layout | Dynamical MB / requests | Hugging Face MB / requests |
|---:|---:|---|---:|---:|
| 1 | 1 | Nairobi | 3.39 / 20 | 21.54 / 26 |
| 1 | 10 | clustered | 3.39 / 20 | 21.54 / 26 |
| 1 | 10 | dispersed | 8.15 / 28 | 71.41 / 42 |
| 1 | 100 | clustered | 3.39 / 20 | 21.54 / 26 |
| 1 | 100 | dispersed | 22.29 / 52 | 108.75 / 66 |
| 30 | 1 | Nairobi | 32.93 / 59 (deadline) | 217.11 / 118 (deadline) |
| 30 | 10 | clustered | 36.83 / 64 (deadline) | 262.08 / 138 (deadline) |
| 30 | 10 | dispersed | 28.68 / 59 (deadline) | 0.18 / 18 (budget) |
| 30 | 100 | clustered | 35.32 / 60 (deadline) | 270.34 / 140 (deadline) |
| 30 | 100 | dispersed | 34.75 / 71 (deadline) | 0.18 / 18 (budget) |

MB means one million **actual HTTP response-body bytes**. Counts include
catalogue, metadata, data, redirects and HTTP errors. Headers, TLS framing
and TCP retransmissions are excluded. Deadline entries show traffic observed
before cancellation. Budget entries include metadata read before refusal.
Both outcomes left the requested series incomplete. The machine used a shared
network with uncontrolled upstream and operating-system caches. The relay adds a local
hop and handles redirects, so use the November 2 uninstrumented timings alongside these results.

All 10 completed cases returned equal cold and warm frames and made **zero
upstream requests** on warm replay. Eight cases reached the deadline and two
were rejected by the decoded-work limit. For the one-site year, the 366
float64 rainfall values occupy 2,928 bytes. Dividing response-body bytes by
that common output size gives 1,158× for Dynamical and 7,356× for Hugging Face.
This ratio includes metadata and intentionally excludes site/date columns.
Dynamical used fewer bytes for every completed one-year layout. Keep Dynamical
first and Hugging Face as the independent fallback.

A separate one-site, 1991–2020 rerun allowed 240 seconds for each provider while keeping the same cache and decoded-work limits.

- Dynamical returned 10,958 daily values in 101.3 seconds, using 59.28 MB across 88 requests.
- Hugging Face returned 10,958 daily values in 87.7 seconds, using 416.48 MB across 202 requests.

Both completed 30-year reads returned identical frames from cache with zero upstream requests.

A separate authenticated toolkit GEE/Xee control retrieved the same 366 Nairobi
dates in 7.5 seconds with an empty toolkit cache. Its repeat took
7.15 seconds and returned the same frame. These are timings for one
site-year only. Authenticated GEE traffic did not pass through the relay.

The opt-in loopback relay counts upstream requests when headers are sent and
counts body chunks before decompression. It forwards anonymous byte-range
requests and includes CDN redirect hops. Each phase records HTTP status counts. A request may lack a response status if the deadline interrupted it. HTTP 404
responses also occur during successful storage lookups. Counts include repeated
requests. No HTTP 429 or 5xx responses appeared in either run.

Run from a checkout with an isolated Python 3.12+ environment containing the
published `climate-toolkit[cloud]==0.2.0` and `psutil` on macOS or Linux.

```sh
python scripts/benchmark_chirps_transport.py --deadline 60
python scripts/benchmark_chirps_transport.py --one-site-years 30 --deadline 240
```

[Full matrix with elapsed times, RSS, revisions, status counts, warm parity and software versions](chirps_transport_2026-11-09.json).
Local runs write under `outputs/validation/issue-177/transport/`.

## CHIRTS-ERA5 station comparison and transport benchmark, 2026-11-10

We compared the published 0.2.1 cloud extra against NOAA GHCN-Daily at three
stations in the benchmark regions. We selected 1994–95 for historical overlap
at all three and 2023–24 for a recent comparison that includes a leap day.
The grid returned both extremes on every requested day at each station. The
table uses only same-date pairs with a station observation for that variable.
Bias is grid minus station. MAE is mean absolute error. Both are in °C.

| Station | Window | Tmax pairs | Tmax bias | Tmax MAE | Tmin pairs | Tmin bias | Tmin MAE |
|---|---|---:|---:|---:|---:|---:|---:|
| Nairobi, Jomo Kenyatta Intl | 1994–95 | 616 | +1.37 | 1.50 | 558 | +4.28 | 4.28 |
| Nairobi, Jomo Kenyatta Intl | 2023–24 | 242 | +1.61 | 1.66 | 287 | +3.21 | 3.21 |
| Ouagadougou | 1994–95 | 593 | −0.60 | 1.05 | 562 | +1.29 | 1.49 |
| Ouagadougou | 2023–24 | 569 | −0.46 | 0.76 | 342 | +1.56 | 1.64 |
| Cusco, Velasco Astete | 1994–95 | 503 | −3.09 | 3.11 | 584 | +3.75 | 3.78 |
| Cusco, Velasco Astete | 2023–24 | 79 | −1.64 | 1.81 | 572 | +3.35 | 3.37 |

At Ouagadougou in 2023–24, daily Tmax correlated strongly with the station
(r = 0.972), but a small cool bias changed the heat-day count. On 569 matched
dates the station reached 35 °C on 349 days and the grid on 325. The grid
identified 319 events, missed 30 and added six. In 1994–95 it identified 235
of 283 events, missed 48 and added ten. Nairobi and Cusco had zero observed
or gridded exceedances on their paired dates. Recent Cusco Tmax coverage was
only 79 of 731 days. Inferring an annual exceedance rate from these pairs
would require information about the missing dates.

The script reads the nearest 0.05° cell at each station's published coordinates.
It joins nominal dates without filling gaps or shifting observation times,
converts NOAA tenths to °C, excludes missing and quality-flagged observations,
and screens for impossible or inverted temperatures. No matched station values
failed the additional screening. The only historical Nairobi source flag was
`I` (international collection). All other station windows used `S` (daily
summaries from hourly synoptic reports). Local observation-day boundaries,
point versus grid elevation and uneven seasonal coverage can affect comparisons.
The producer uses station information, and we did not establish whether these
stations contributed to its inputs. These six station-periods support local
bias checks before applying absolute heat or cold thresholds. They do not
establish global accuracy or a change in bias through time.
[NOAA format and flag definitions](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt)
and [CHC product methodology](https://www.chc.ucsb.edu/data/chirts-era5).

The station run read published CHIRTS-ERA5 with an empty process environment
apart from local run paths, an empty home, GEE disabled, and access to normal
user credentials and the macOS keychain blocked. The offline suite tests all
four geographic corners on leap day, boundary ties, a missing native variable,
incomplete dates, QC, provider failures and cache provenance. The base package
supports Python 3.10+. The cloud extra requires Python 3.12+ and Zarr 3.x.

### Measured HTTP traffic

Same sites, windows, two workers and 4 GiB decoded-work limit as the CHIRPS
benchmark. Each case started with an empty toolkit cache. Cold seconds below
measure the fetch. The 60-second gate applies to the whole case. MB counts
actual response-body bytes including redirects and metadata and excludes headers
and TLS. The shared network and upstream caches were uncontrolled.

| Sites | Layout | 2020 cold s | 2020 MB / requests | 1991–2020 at 60 s | MB / requests before stop |
|---:|---|---:|---:|---|---:|
| 1 | Nairobi | 14.43 | 64.28 / 34 | deadline | 449.03 / 134 |
| 10 | clustered | 10.61 | 64.28 / 34 | deadline | 633.40 / 180 |
| 10 | dispersed | 23.86 | 153.61 / 66 | decoded budget | 0.26 / 18 |
| 100 | clustered | 9.18 | 64.28 / 34 | deadline | 736.25 / 202 |
| 100 | dispersed | 24.33 | 193.15 / 82 | decoded budget | 0.26 / 18 |

All five one-year cases had exact cache parity and zero warm requests.
The 30-year dispersed reads estimated 11.20 GiB (10 sites) and 14.93 GiB
(100 sites) of decoded chunks. Both stopped after metadata, before returning
a series. Split dispersed workloads into shorter windows or smaller geographic
groups to keep within the default budget.

With a 240-second allowance, Nairobi returned both extremes on 10,958 dates in
136.825 seconds, with 1.473 GB across 386 requests. The cached read took 0.070
seconds, returned an identical frame and made zero requests.

Extended runs at the 10- and 100-site Nairobi cluster initially experienced
connection resets, timeouts or DNS failure. After connectivity returned:

| Sites | Outcome at 240 s | Cold s | Warm s | Rows | Cold MB / requests |
|---:|---|---:|---:|---:|---:|
| 10 | complete | 236.336 | 0.449 | 109,580 | 1,472.95 / 386 |
| 100 | deadline | — | — | — | 1,273.29 / 340 |

Every completed clustered replay reproduced the cold frame and made zero requests.
Interrupted attempts have no warm measurement. The evidence file retains all attempts.

Reproduce with the published `climate-toolkit[cloud]==0.2.1` on Python 3.12+
and install `psutil` for the transport benchmark. Validation writes under
`outputs/validation/issue-178/`. The station summary includes input URLs and
SHA-256 hashes, mirror revision, selected cells, RMSE, correlations and heat
event counts. The daily pairs CSV remains local.

```sh
python scripts/compare_chirts_stations.py
python scripts/benchmark_chirps_transport.py --source chirts_era5 --deadline 60
for n in 1 10 100; do
  python scripts/benchmark_chirps_transport.py --source chirts_era5 --years 30 --clustered-sites "$n" --deadline 240
done
```

[Station and transport results](chirts_validation_2026-11-10.json).

## Remaining issue acceptance and follow-ups at the 2026-11-02 checkpoint

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

## Integration with current main and distribution checks — 2026-11-03

Merged main through `e2900e3`, preserving both the optional API and cloud extras
and the released base version. CI now exercises Python 3.10 base and Python 3.12
cloud/API environments, with an explicit cloud dependency import gate to prevent
silently skipped provider tests. Distribution tests install base wheel/source
archives and a cloud wheel in separate fresh environments, outside the checkout.

Local macOS ARM64 results after the merge:

- Python 3.12.10 with cloud/API: **730 passed, 2 skipped, 104 subtests passed**
  (20 warnings, 267.17 seconds).
- Python 3.10.20 base: **692 passed, 40 skipped, 104 subtests passed**
  (15 warnings, 271.43 seconds). Optional cloud/API tests skip without their extras.
- Ruff, lock verification, whitespace checks, wheel/source builds and Twine
  artifact checks passed. Fresh cloud installation verifies its dependencies,
  public backend policy, pipeline import and installed fetch CLI.
- Repeated all six pipeline stages for Nairobi 2020 after the merge: 366 daily
  rows; GEE calls zero. First run 4.20 seconds using existing cache where available;
  replay 0.67 seconds with provider opens blocked and exactly matching daily values.
  [Verification record](direct_cloud_evidence_2026-11-02/pipeline_verification_merged.json).

Commands: `uv sync --locked --group dev --extra cloud --extra api --python 3.12`,
`uv run pytest -q`; a separate Python 3.10 environment ran the same suite with
base dependencies. Live workflow reproduction remains
`uv run python scripts/verify_direct_pipeline.py`.

These are package integration checks, not broader scientific validation. Existing
independent CHIRTS-provider and long-window efficiency gaps remain open. CDS work
is shelved because credentials are required; no NASA POWER changes were added.

## Published-package sample validation, 2026-11-07

PyPI `climate-toolkit[cloud]==0.2.0` fetched CHIRTS-ERA5 Tmin and Tmax from
Hugging Face with GEE disabled, using an empty temporary toolkit cache. Compared
Nairobi, Ouagadougou and Cusco on 2020-01-01 and 2020-02-29 against four daily
GeoTIFFs obtained from the [CHC product archive](https://www.chc.ucsb.edu/data/chirts-era5).
Checked grid centres before comparing values. All 12 pairs fell within the
[mirror's 0.05 °C packing tolerance](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily).
Maximum absolute differences were 0.048807 °C for Tmin and 0.047185 °C for Tmax.
These samples check decoding and spatial alignment. Station agreement,
long-window performance and independent fallback availability remain open. The
archive returned HTTP 429 on initial requests before allowing full downloads.

[Sample values, cell coordinates, original URLs and SHA-256 hashes, and mirror revision](direct_cloud_evidence_2026-11-07/chirts_originals.json).
To reproduce, download the four listed GeoTIFFs into one directory, keeping the
filenames. From the repository root run:

```sh
uv run --no-project --python 3.12 --with 'climate-toolkit[cloud]==0.2.0' --with rasterio \
  python scripts/compare_chirts_originals.py /path/to/tiffs 2020-01-01 2020-02-29 --output result.json
```

The offline packing regression exercises CF-decoded temperatures through
preprocessing and seasonal hazard statistics, including inclusive counts at
exactly 35 and 40 °C and seasonal means. The direct pipeline suite also
checks that invalid temperatures stop downstream analysis.
