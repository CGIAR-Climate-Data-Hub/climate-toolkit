# Issue 179: independent CHIRTS-ERA5 backup investigation

Updated 2026-11-12. Independent daily backup remains under investigation.
Architecture authority: [package architecture summary](../package_architecture_summary.md).
Issue: [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179).
Previous integration evidence: [issues 176–178](issue_176_178_direct_cloud_access.md).

## Decision

Keep Hugging Face as the only integrated CHIRTS-ERA5 provider. CHC originals are
scientifically relevant, but available routes have unresolved completeness and
latency problems. Do not replace daily data with pentadal/monthly aggregates,
legacy CHIRTS, or ERA5-Land. Issue 179 remains open; forced-outage redundancy has
not been demonstrated.

## Why Tmin differed on 21 October 2026

The Hugging Face mirror took its 21 October Tmin from a 26 October CHC file. CHC subsequently rewrote the GeoTIFF at the same daily URL. The pinned mirror still has the earlier values. The two releases therefore disagree at identical cells by more than the mirror's 0.05 °C packing tolerance. The available provenance identifies the file revisions involved. It does not identify the specific change in CHC's inputs or algorithm.

| Evidence for the same 21 October Tmin | Finding |
| --- | --- |
| Mirror revision `35669afb` | Its per-day ingestion manifest records the source URL and signature `27158118:2026-Oct-26 09:04`. The integer is consistent with the directory's rounded 25.9 MiB size. The signature contains no source checksum or recoverable object version. |
| CHC file sampled 10 November | ETag `"6aecb32f-19bb7fe"`. Independent GDAL and xarray reads reproduced the provider differences documented below. |
| CHC file sampled 12 November | Same URL, 26,982,398 bytes, HTTP Last-Modified 11 November 23:07:57 GMT, ETag `"6af4f54d-19bb7fe"`. ETag-pinned, bounded strip reads recovered the same three land values as the 10 November file. A changing ETag alone would have been insufficient evidence of changed temperatures. |

| Site | Pinned mirror Tmin °C | CHC Tmin °C on 12 November | Mirror minus CHC °C |
| --- | ---: | ---: | ---: |
| Nairobi | 18.5 | 18.3045 | +0.1955 |
| Ouagadougou | 26.7 | 24.5183 | +2.1817 |
| Cusco | 12.1 | 11.1390 | +0.9610 |

Comparing three immutable mirror commits gives a separate check on recent-day revisions. We read the same land cells and Pacific nodata cell directly with xarray. From 28 September through 3 October, the 8 and 12 October builds overlapped on six days. Only 2 and 3 October changed at these sites, in both Tmin and Tmax. At Cusco, 3 October Tmin went from 11.3 to 7.6 °C. The 12 and 26 October builds overlapped on ten sampled days. Only 7 October changed, again in both variables. At Cusco, Tmin went from 10.2 to 7.9 °C. September 28–30 stayed identical across all three builds. The 12 October array contains 7 October even though its per-day manifest lacks an entry for that date. Use the actual time coordinates when auditing coverage. [Pinned 8 October build](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily/tree/a4be603034d0a32d4a827295bbad8c617626b5ab) · [12 October build](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily/tree/c44a0b58772e32f7cbb2b5a740d5e6586ceeb054) · [26 October manifest](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily/blob/35669afbbd1c6ab84dcc496f2f95b7cbbf75867f/chirts_daily_era5.zarr.chirts-state.json)

A fresh original-provider control for 3 October gave 7.5642 °C at Cusco. That rounds to 7.6 °C in the later mirror and differs from the earlier mirror by 3.7358 °C. Three ETag-pinned ranges transferred 28,654 bytes for this control. Agreement on this earlier day cannot establish coverage for 21 October.

CHC documents that it derives Tmin from corrected Tmax and the daily ERA5 temperature range. The close-to-publication changes are consistent with revision of recent inputs or processing. CHC's methods description supplies no date-specific processing log, and the mirror manifest supplies no immutable link to its October input. We could not independently replay the exact October TIFF to isolate the mechanism within CHC's pipeline. [CHC production notes](https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/aaa.readme.txt)

**Decision for #179.** The revision-equivalence condition failed. The long-window CHC benchmark and forced Hugging Face outage test remain pending. A dated CHC archive with matching content, or a refreshed mirror and a verified equivalent original for the requested window, would allow those tests to proceed. Intermittent HTTP 429 responses also occurred during the bounded investigation.

[Machine-readable mirror history and original samples](chirts_revision_audit_2026-11-12.json). To reproduce the historical mirror comparison, run `python scripts/audit_chirts_revisions.py` in a toolkit environment with the cloud dependencies. To resample the live original, use the existing strip probe below. Record its ETag because the URL is mutable.

## Daily GeoTIFF range and revision checks, 2026-11-10

The CHC daily TIFFs have one compressed scanline per latitude. We fetched just
the TIFF metadata and requested rows with anonymous HTTP ranges, a strong ETag,
and an If-Match condition after the first response. The probe has a 1 MiB body
budget and a 45-second time budget per file. Four historical file reads passed
in 4.8–20.5 s each, transferring 118–177 kB in 6–7 requests per file. Each
covered Nairobi, Ouagadougou, Cusco and an open Pacific Ocean cell. Repeated
sites in one scanline share the compressed row. No whole global image was needed.

| Date | Tmax | Tmin |
|---|---|---|
| 1981-07-15 | Within packing tolerance | Within packing tolerance |
| 2000-02-29 | Within packing tolerance | Rate limited |
| 2024-12-31 | Within packing tolerance | Rate limited |
| 2026-10-21 | Read failed | Exceeded tolerance at all three land sites |

For the four historical files with complete reads, all 12 land comparisons
agreed within 0.05 °C (maximum 0.049916 °C). The ocean cell was missing in
each original and mirror. The same strip decoder reproduced all 12 published
land reference values exactly when run against the locally available original
TIFFs for 2020-01-01 and 2020-02-29.

On 2026-10-21, published toolkit 0.2.1 read the following daily Tmin from
Hugging Face revision `35669afbbd1c6ab84dcc496f2f95b7cbbf75867f`. The CHC
file had ETag `"6aecb32f-19bb7fe"`. Both grids selected the same cell centres.

| Site | CHC original °C | Pinned mirror °C | Absolute difference °C |
|---|---:|---:|---:|
| Nairobi | 18.3045 | 18.5 | 0.1955 |
| Ouagadougou | 24.5183 | 26.7 | 2.1817 |
| Cusco | 11.1390 | 12.1 | 0.9610 |
| Pacific Ocean | missing | missing | — |

A second read pinned the same CHC ETag and retrieved the four scanlines in
four requests (30,430 body bytes) using the previously read TIFF header.
Rasterio/GDAL independently decoded the same land values and ocean sentinel.
Opening the pinned Zarr directly with xarray reproduced all four toolkit values.

The check establishes a difference between these specific snapshots. It does
not determine which input changed or which better represents the temperature.
Before automatic failover, identify the upstream original revision used to
build the mirror and verify equivalence across the requested window.

The annual files and EWX still do not cover the same daily request.
The 2026 Tmax NetCDF returned HTTP 200 to a range request and the reader
rejected it before downloading the body. The 2026 Tmin time coordinate had
273 consecutive dates ending September 30. Separate one-site 2020 annual
Tmax and Tmin probes both stopped on HTTP 429. The published EWX CHIRTSERA5
catalogue advertised only pentadal, monthly and three-month periods.

Daily files also pose a scaling limit. One complete leap year of both variables
needs 732 distinct files. The 1991–2020 window needs 21,916, even for one
site. Those are file counts, not measured request counts or timings. Given
the observed 429s and scientific discrepancy, the 1/10/100-site long-window
matrix and forced-outage production test remain open.

The final probe supports pacing between range requests and stops on HTTP 429.
Initial unpaced measurements overlapped annual diagnostics on a shared
connection. Later paced trials ran separately. The [machine-readable record](chirts_original_ranges_2026-11-10.json)
includes dates, grid centres, original URLs and ETags, mirror revision,
partial body counts, elapsed times and failures.

Run with Python 3.12+, `climate-toolkit[cloud]==0.2.1`, `tifffile` and
`imagecodecs`. Mismatch or transport failure returns a nonzero exit status.

```sh
python scripts/probe_chirts_strips.py 2026-10-21 --variables Tmin
```

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
