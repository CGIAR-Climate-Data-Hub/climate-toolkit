# Issue 180: ERA5-Land companion access without GEE

Date: 2026-11-02. Status: access investigation; no new runtime backend enabled.
Architecture authority: [package architecture summary](../package_architecture_summary.md).
Issue: [#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180).

## Decision and access evidence

The official CDS ARCO geo-chunked stores are the strongest candidate for the
existing `agera_5` product: ERA5-Land, with hourly inputs covering the required
variables. They avoid GEE, but require a CDS key. Anonymous metadata requests
returned HTTP 401. Requests using the existing local CDS configuration also
returned HTTP 401 / `AUTHENTICATION_FAILED`. No climate arrays were downloaded;
live coverage, speed and equivalence remain unverified.

The evidence files contain only fixed endpoint URLs, credential-presence flags,
status codes, timing and byte counts. They contain no key or response error body:
[anonymous probes](direct_cloud_evidence_2026-11-02/era5_land_anonymous_access.json),
[configured-key probes](direct_cloud_evidence_2026-11-02/era5_land_authenticated_access.json).
Byte counts cover bodies actually consumed by the diagnostic; rejected responses
are closed before body consumption, so zero does not mean zero wire traffic.

| Candidate | Identity and authentication | Decision |
| --- | --- | --- |
| CDS ARCO geo-chunked hourly | ERA5-Land; CDS bearer key; temperature/dewpoint, wind, precipitation, radiation groups | Preferred next validation target; current key rejected |
| CDS time-series API | Same hourly ARCO product; account/key and accepted terms | Potential alternative interface, not an independent archive |
| Earth Data Hub daily UTC | Derived ERA5-Land daily means/accumulations; separate EDH key; anonymous probe 401 | Listed variables omit Tmax/Tmin; cannot replace full existing source |
| Earth Data Hub hourly | ERA5-Land hourly; separate EDH key | Further candidate; no configured EDH credentials, no value benchmark |
| Open-Meteo | Explicit ERA5-Land selection supports surface temperature/humidity; broader wind/radiation bundle uses ERA5 through ERA5-Seamless | Not an exact all-variable mirror of existing source |
| Google ARCO / Earthmover ERA5 | ERA5, not ERA5-Land | Different scientific source; excluded from automatic mirror fallback |
| Small HF ERA5-Land datasets found in search | Regional or otherwise unvalidated subsets | No verified global, complete replacement established |

Provider references:

- [CDS analysis-ready access](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=analysis_ready_data)
  documents required CDS key, dual chunking and CC-BY licence.
- [ECMWF working notebook](https://github.com/ecmwf-training/dss-notebooks/blob/main/datasets/reanalysis-era5-land/arco-access.ipynb)
  gives the four geo-chunked endpoints and bearer-header access. Retrieved file
  blob SHA: `0cae6dd6868e3fe71c444b58d5918b1f17ac0a89`.
- [ERA5-Land ARCO guide, version 13](https://confluence.ecmwf.int/pages/viewpage.action?navigatingVersions=true&pageId=737545913)
  documents de-accumulation and grid conventions. The current-version page was
  unavailable to the web reader; this July 2026 snapshot is supporting evidence,
  not a guarantee that the live schema has remained unchanged.
- [EDH daily catalogue](https://earthdatahub.destine.eu/collections/era5/datasets/era5-land-daily)
  lists daily means, required credentials, CC-BY, and 75 × 150 × 300 chunks.
  Advertised coverage was 1950-01-01–2026-10-15; live coordinates were not read.
- [Open-Meteo variable table](https://open-meteo.com/en/docs/historical-weather-api)
  distinguishes ERA5-Land variables from ERA5-Seamless companion inputs.
- [GEE ERA5-Land daily catalogue](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
  defines the existing daily aggregation and advertises coverage beginning
  1950-01-02. Corrected the toolkit dataset table's stale 1979 start accordingly.

## Required daily contract

The existing `agera_5` key must retain ERA5-Land meaning. The distinct
agrometeorological AgERA5 dataset is not an interchangeable mirror. Remaining
CLI/help/docstring labels now say ERA5-Land; source keys, aliases and routing are
unchanged.

| Toolkit output | Required calculation from CDS hourly fields |
| --- | --- |
| Tmax/Tmin/Tmean | Maximum/minimum/mean of `t2m` at 00:00–23:00 UTC; Kelvin to Celsius |
| Precipitation, mm/day | Sum de-accumulated `tp` at 01:00 through following 00:00 UTC; multiply metres by 1000 |
| Solar radiation, W/m² | Sum de-accumulated `ssrd` over the same flow window; divide J/m² by 86400 |
| Wind, m/s | Magnitude of daily mean `u10` and `v10`, matching current toolkit; not mean hourly scalar speed |
| Humidity, percent | Apply current Magnus formula to daily mean `t2m` and `d2m`, then clip 0–100; not mean hourly RH |

The flow-window rule is an inference from the producer's hourly de-accumulation
description and GEE's use of following-day 00:00 accumulated values. A value at
00:00 describes the preceding hour. Summing 00:00–23:00 would include the previous
day's final hour and omit the current day's final hour. Validate this against
original/GEE values, particularly month/year boundaries and leap days, before
enabling dispatch. Fetch one extra midnight for each requested final day.

Local implementation references: `fetch_data/source_data/sources/gee.py`,
`fetch_data/gee_xee_batch.py`, `fetch_data/source_data/sources/utils/config.yaml`,
and `fetch_data/preprocess_data/preprocess_data.py`. The current solar scaling
is approximately `1/86400`; current humidity derives from daily air/dewpoint
means. Reordering these nonlinear calculations would change results.

Additional validation requirements:

- Verify live units, dimensions, hourly completeness, selected cell/grid origin,
  longitude wrapping, ties and land masks. Do not fill missing hours or relocate
  ocean points to land.
- Distinguish stable archive versions from mutable metadata fingerprints; the
  latter alone cannot establish immutable data revisions. Define cross-group
  consistency and cache invalidation before production integration.
- Benchmark all required groups together for 1/10/100 clustered/dispersed sites,
  short and 30-year periods, cold/warm caches, response bytes and memory.
- Compare existing GEE values across regions/seasons, not only provider metadata.
  Existing local GEE cache samples can help, after checking their provenance.
- Preserve no-interactive-auth policy, complete-request failure behavior and
  provider provenance throughout the package pipeline.

## Reproduce access checks

```sh
python scripts/probe_era5_land_access.py
python scripts/probe_era5_land_access.py --cds-auth
```

The second command uses `CDSAPI_KEY` or `~/.cdsapirc`. Update credentials locally
from the [CDS profile](https://cds.climate.copernicus.eu/profile), then rerun; do
not put credentials in command arguments or evidence files. The script requests
metadata only, rejects redirects, caps successful metadata bodies at 2 MiB,
and retries transient errors at most once. It never forwards the CDS key to EDH
or inherits `.netrc` credentials for anonymous probes. A nonzero exit means at
least one candidate failed its metadata check. A successful metadata check alone
does not validate scientific values, full date coverage or performance.

The production no-GEE auto pair remains CHIRPS v3 + CHIRTS-ERA5. It does not gain
humidity, wind or radiation from this investigation. Issue 180 remains open.

## Validation of this change

- Full package suite: **691 passed**, 104 subtests, 18 warnings; includes wheel
  and source-distribution builds and installation smoke checks in fresh environments.
- Focused access-probe, source-policy and pipeline tests: **72 passed**.
- Season and hazard CLI help checks show ERA5-Land under the unchanged `agera_5` key.
- Ruff, lock consistency and diff whitespace checks passed.
- Live access probes verified the reported HTTP failures; no live climate-value
  equivalence or performance claim is made.
