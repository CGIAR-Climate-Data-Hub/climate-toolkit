# Issue 179: independent CHIRTS-ERA5 backup investigation

Date: 2026-11-02. Status: investigation; no additional production provider enabled.
Architecture authority: [package architecture summary](../package_architecture_summary.md).
Issue: [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179).
Previous integration evidence: [issues 176–178](issue_176_178_direct_cloud_access.md).

## Decision

Keep Hugging Face as the only integrated CHIRTS-ERA5 provider. CHC originals are
scientifically relevant, but available routes have unresolved completeness and
latency problems. Do not replace daily data with pentadal/monthly aggregates,
legacy CHIRTS, or ERA5-Land. Issue 179 remains open; forced-outage redundancy has
not been demonstrated.

## Routes examined

- The [producer page](https://www.chc.ucsb.edu/data/chirts-era5) links the original
  daily GeoTIFF/NetCDF archives and EWX. It describes 0.05-degree daily Tmax/Tmin
  and provides attribution guidance. Archive availability must be checked
  separately from the product's nominal processing latency.
- The [EWX live catalogue](https://chc-ewx3.chc.ucsb.edu/api/rest/version/5.0/config)
  contains CHIRTS-ERA5 Tmax/Tmin periods `pentad`, `month`, and `3month`; no daily
  Tmax/Tmin entries were found. This is evidence about this catalogue snapshot,
  not proof that no other daily subset service exists. Snapshot:
  [chc_ewx_catalog.json](direct_cloud_evidence_2026-11-02/chc_ewx_catalog.json).
- The [Tmax annual archive](https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/tmax/netcdf/daily/)
  lists historical files around 6.7 GiB, an empty 2026 file, and an empty
  `by_month/` directory. The live 2026 Tmax request returned HTTP 200 instead of
  a range response; the probe rejected it without consuming its body.
- The 2026 Tmin NetCDF was readable: 273 daily entries, 2026-01-01–2026-09-30,
  shape `(273, 2600, 7200)`, compressed chunks `(15, 145, 424)`. It cannot cover
  the mirror's verified October dates. A 20-second probe stopped after five
  requests and 589,824 response-body bytes. Evidence:
  [current-year probes](direct_cloud_evidence_2026-11-02/chc_netcdf_2026_probe.json).
- Historical 2020 Tmax/Tmin NetCDF arrays have shape `(366, 2600, 7200)`, float32
  values, gzip chunks `(19, 137, 379)`, and missing sentinel -9999. Their literal
  units attribute is `C/day`; producer documentation describes temperature.
  That metadata discrepancy requires explicit treatment before integration.
- An exploratory 2020 Tmax Nairobi series completed in 69.85 seconds, 43 range
  requests and 46,913,764 response-body bytes. First values were 27.347185,
  26.500080 and 26.003042. This exploratory reader did not enforce the final
  probe's ETag checks; treat it as feasibility evidence, not a release benchmark.
- The bounded final probe for 2020 Tmin at Nairobi exceeded its 90-second budget:
  18 requests, 14,995,378 response-body bytes, no complete point series. Evidence:
  [historical probe](direct_cloud_evidence_2026-11-02/chc_netcdf_2020_probe.json).

These shared-network measurements were partly concurrent with other validation;
they do not establish controlled throughput or comparative provider speed.
The 1/10/100-site by 1/30-year acceptance matrix and broad scientific comparison
remain outstanding. Running that expensive matrix is not justified before the
current-year coverage and single-site latency problems are resolved.

## Reproducible bounded probe

`scripts/probe_chc_backup.py` uses investigation-only `h5py`; no package runtime
dependency was added. Example:

```sh
uv run --with h5py python scripts/probe_chc_backup.py \
  --year 2020 --variables Tmin --sites 1 --seconds 90 \
  --output outputs/chc_backup_probe.json
```

The reader rejects ignored ranges before downloading their bodies, requires a
strong ETag, sends If-Match on later reads, validates byte intervals and file
size, and bounds transfer/time. It records response-body bytes, excluding
HTTP/TLS overhead. It does not retry, cache production values, or register a new
toolkit backend. It is a diagnostic, not a supported fallback adapter.

## Long-window read improvement

Direct cloud fetching now loads consecutive missing years in batches of at most
five years, reducing repeated reads of source chunks that straddle calendar
boundaries. Persistence stays annual, with exact provenance and revision checks.
Cached intervening years are skipped. Completed batches survive later outages.

Regression tests count actual delayed source-chunk loads, check exact cache
round trips, preserve intervening cached years, and inject a later-batch outage
to verify resumability. This proves elimination of redundant loads within a
batch; it does not establish a wall-clock speedup for all long-window requests.
Multi-decade latency remains an open performance limitation.

A fresh real HF request spanning 2019-12-30–2020-01-03 completed in 6.825 seconds,
using one extraction and producing two annual cache records. Offline replay took
0.013 seconds, opened no provider, and returned exactly identical values. Evidence:
[cross-year live check](direct_cloud_evidence_2026-11-02/live_cross_year_batch.json).

Validation: full suite 679 passed (104 subtests); after adding the final bounded
batch/outage regression, all 51 direct-provider and pipeline tests passed. Ruff,
diff whitespace checks, lock validation, wheel build and source build passed.

The complete six-stage pipeline also passed against real cached provider data:
366 daily records, both providers preserved, zero GEE calls, exact warm values,
and zero warm provider opens. First run 4.339 seconds; warm replay 0.714 seconds.
Existing caches were reused, so this is not a clean cold benchmark. Evidence:
[pipeline verification](direct_cloud_evidence_2026-11-02/pipeline_verification_batched.json).
