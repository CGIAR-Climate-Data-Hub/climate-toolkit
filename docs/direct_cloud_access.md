# Direct cloud access and provider fallback

Architecture reference: [package architecture](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/package_architecture_summary.md).
Implementation tracks issues [#176](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/176), [#177](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/177) and [#178](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/178).

## Install and fetch

Direct backends require **Python 3.12+** and the optional cloud dependencies:

```sh
pip install 'climate-toolkit[cloud]'
# From a checkout:
uv sync --extra cloud
```

The base toolkit still supports Python 3.10+. On older Python versions, direct
cloud fetches report the requirement; existing explicit GEE paths remain available.

```python
from datetime import date
import climate_toolkit as ct

rain = ct.fetch_climate_data(
    "chirps_v3_daily_rnl",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
temperature = ct.fetch_climate_data(
    "chirts_era5",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
print(rain.attrs["data_provenance"])
```

`sites=[("Nairobi", -1.286, 36.817), ...]` or `sites_csv=...` uses the same
provider policy and groups lazy point reads into shared storage chunks.
`workers` bounds concurrency (1–8 for direct access).

## Products and providers

| Source | Automatic provider order | Coverage discovery |
| --- | --- | --- |
| `chirps_v3_daily_rnl` | Complete compatible cache first; Dynamical final, Hugging Face, permitted GEE | Actual time coordinates; full requested range required |
| `chirts_era5` | Complete cache first; Hugging Face | Actual time coordinates; hosted archive starts 1981 |

Dynamical's smaller chunks reduce read amplification for long/dispersed requests
and its final archive was more current at validation. Hugging Face can be faster
for short requests. Select `backend="huggingface"` or `backend="dynamical"`
explicitly when needed. An explicit backend does not silently switch providers.

The CHIRPS adapters both read **v3 final/RNL**. Dynamical preliminary is SAT and
is excluded. Neither CHIRPS v2 nor another rainfall product is a mirror fallback.

Dynamical stores a daily-average precipitation rate; the adapter converts it to
mm/day. Hugging Face CF scaling is decoded once by xarray. The mirrors apply
different rounding: comparisons must allow documented packing error, and daily
threshold counts can differ. One returned request uses a single provider revision;
there is no per-day stitching across providers.

CHIRTS-ERA5 is the successor for new temperature workflows. The old `chirts`
key (CHIRTS-daily, 1983–2016) is **deprecated** and warns when selected. Its
existing adapter is retained only for explicit legacy reproduction; automatic
fallback now uses CHIRTS-ERA5. Existing keys/caches are never relabeled or combined.
The `chirps_v2+chirts` shorthand retains its historical meaning.

CHIRTS-ERA5 improves temporal coverage, not guaranteed accuracy at every site.
Its producer publishes ongoing monitoring data at approximately five-day latency;
the mirror can lag. Both old CHIRTS-daily and CHIRTS-ERA5 use ERA5 information,
with different constructions. Do not interpret this as a simple file-host change.

## Paired workflows and GEE controls

```python
with ct.backend_policy(allow_gee=False):
    result = ct.analyze_climate_statistics(
        location_coord=(-1.286, 36.817), start_year=2020, end_year=2020,
        source="paired", precip_source="chirps_v3_daily_rnl",
        temp_source="chirts_era5", fixed_season="03-01:05-31",
    )
```

```sh
climate-toolkit fetch --source chirps_v3_daily_rnl --no-gee \
  --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-12-31

climate-toolkit stats --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2020 --end-year 2020 \
  --fixed-season 03-01:05-31
```

The unified CLI accepts `--backend` and `--no-gee` on all commands; standalone
fetch accepts them too. Other standalone commands can use
`CLIMATE_TOOLKIT_ALLOW_GEE=false` and `CLIMATE_TOOLKIT_BACKEND=auto` environment
settings. Python contexts nest and library model-worker processes inherit policy.
User-created threads/processes should enter their own context.

Normal historical `auto` retains CHIRPS v3 + the existing `agera_5` source
(**ERA5-Land**, not the distinct AgERA5 product) for companion variables. Its
final temperature fallback is now CHIRTS-ERA5. With GEE prohibited, historical
`auto` directly selects CHIRPS v3 + CHIRTS-ERA5. This pair supplies precipitation
and Tmax/Tmin only: it does not supply humidity, wind, radiation or soil data.
Existing workflow requirements for those inputs still apply. Human-heat metadata
marks absent companion inputs as null rather than attributing them to CHIRTS-ERA5.

Explicit backend selection applies to cloud-enabled sources; other datasets keep
existing routes, subject to the global GEE prohibition. Choosing `dynamical`
for a CHIRTS-ERA5 request fails because no such adapter exists. Use `auto` for
mixed-source paired workflows. Automatic GEE fallback never opens an interactive
authentication flow; pre-existing setup is required.

## Full pipeline

`run_pipeline` carries one explicit pair and provider policy through daily fetch,
climatology, source comparison, seasonal statistics, crop hazards and period
comparison. This short verification example uses a two-year climatology; use an
appropriate longer baseline for scientific normals, subject to the performance
limits below.

```python
result = ct.run_pipeline(
    name="Nairobi", location_coord=(-1.286, 36.817),
    source="paired", precip_source="chirps_v3_daily_rnl", temp_source="chirts_era5",
    allow_gee=False, workers=2,
    start_year=2020, end_year=2020,
    climatology_baseline=(2019, 2020),
    fixed_season="03-01:05-31", crop_name="maize",
    run_compare_sources=True,
    compare_sources_list=["paired", "chirps_v3_daily_rnl", "chirts_era5"],
    run_compare_periods=True,
    baseline_start=2019, baseline_end=2019, focal_year=2020,
    output_dir="outputs/nairobi_pipeline",
)
print(result.summary)
assert not result.errors, result.errors
```

`source="auto", allow_gee=False` selects this pair too. `backend="auto"` is
appropriate for mixed rainfall/temperature sources; Dynamical has no temperature
adapter. `ee_project_id`, when supplied for permitted GEE paths, is forwarded
rather than discarded.

Each site's directory contains `daily.csv` with its metadata sidecar, JSON stage
reports and `status.json`; run root contains `summary.csv` and `metadata.json`.
Daily source-comparison exports live in that site's `source_comparison/` folder.
Check status and `completed_steps` before consuming a report. Returned errors and
partial source comparisons fail the stage; unsuccessful reruns remove obsolete
pipeline JSON reports. Individual source-comparison exports may remain as diagnostic
partial output and are not proof that the stage completed.

Direct climatology requires all requested years and rejects QC failures; it does
not silently compute a shortened baseline. Paired climatology is also available
through the CLI:

```sh
climate-toolkit climatology --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2019 --end-year 2020 \
  --format json --output outputs/climatology.json --output-dir ""
```

## Data integrity, caches and limits

- Raw frames expose decoded source-native columns, QC summaries and provenance.
  Transformed/preprocessed frames use canonical names. Direct data retains its
  precision; existing generic filling and heuristic unit conversions are bypassed.
- Missing/infinite values, negative precipitation, temperatures outside -90 to
  60 °C, or Tmin greater than Tmax prevent direct data from entering analysis.
  Inspect `stage="raw"` to diagnose. These gross screening limits do not establish
  scientific accuracy. Invalid scientific values are not treated as outages.
- Transport/provider failures, stale coverage, missing dates/variables or incompatible
  metadata can trigger another eligible mirror. Partial date ranges are never
  silently accepted. Ocean/out-of-domain points do not become nearby land points.
- Annual request chunks live under
  `outputs/cache/direct_cloud/v2/<source>/<backend>/` (or the supplied root).
  Checksummed JSON preserves float precision, column order, requested coordinates,
  selected cells, units, provider revision and dates. Writes are atomic. Complete
  cache hits need no metadata/authentication calls, even when the cached provider
  was a fallback. An interrupted read can reuse matching-revision chunks; a new
  revision causes replacement rather than mixing revisions. `refresh_cache=True`
  opts into current upstream data. Existing GEE caches are separate and untouched.
  Consecutive missing years load in batches of at most five years, sharing source
  chunks across calendar boundaries. Each completed batch saves separate annual
  records, so a later outage can resume from those records at the same revision.
- Fetch and dataset-comparison CSV/JSON exports write a `.metadata.json` sidecar.
  Statistics, period comparisons, hazard assessments and station diagnostics carry
  additive `data_provenance` fields. Cache inventory includes `direct_cloud`.
- Metadata HTTP calls use bounded timeouts and retries; data transports have bounded
  request timeouts. Default estimated source-chunk work budget is 4 GiB per provider
  request. This is decoded source size, **not measured network bytes**. Exceeding it
  skips that provider. Set `CLIMATE_TOOLKIT_MAX_DECODED_BYTES` explicitly to change
  the budget. Long or widely dispersed jobs can still take minutes.

Reproduce live measurements with `scripts/benchmark_direct_cloud.py`. Its default
90-second per-case deadline is a benchmark gate, not the library's whole-job timeout.
Ordinary tests use offline fixtures; live benchmarking is opt-in.

CHIRTS-ERA5 currently has **one integrated direct provider**. CHC GeoTIFF/NetCDF
archives are independent originals, but daily files and observed partial-read
failures need further work before they qualify as efficient automatic backups.
The 2026-11-02 probe found a rejected current-year Tmax NetCDF and a Tmin file
ending in September; the EWX catalogue exposed only pentadal/monthly aggregates.
Historical NetCDF point reads also exceeded the short-query performance target.
Reproduce bounded range probes with `scripts/probe_chc_backup.py` (requires the
investigation-only `h5py` dependency). See the
[backup investigation](../analysis/issues/issue_179_chc_backup_investigation.md).
Tracked in [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179);
credential-free ERA5-Land companion variables are tracked in
[#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180).
The [ERA5-Land access audit](../analysis/issues/issue_180_era5_land_access.md) found
authenticated CDS ARCO stores as a candidate, but live metadata access rejected
the configured key. No ERA5-Land cloud backend is enabled. CDS hourly flow fields
also need explicit day-boundary aggregation to match existing GEE results.

## References

- [CHIRTS-ERA5 producer documentation](https://www.chc.ucsb.edu/data/chirts-era5)
- [Hugging Face CHIRTS-ERA5](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily)
- [Hugging Face CHIRPS v3 RNL](https://huggingface.co/datasets/aaguilar90/chirps-v3-daily-rnl)
- [Dynamical final/RNL](https://dynamical.org/catalog/ucsb-chc-chirps-analysis-final/)

Full live workflow verification: `python scripts/verify_direct_pipeline.py`.
It checks all six stages, exported provenance and a cache-only replay with provider
opens and GEE initialization blocked. It uses short verification baselines, not
scientific climate normals.
