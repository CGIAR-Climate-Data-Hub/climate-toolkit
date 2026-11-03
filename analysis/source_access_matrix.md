# Source access matrix

Audit: 2026-11-02. Narrow routing audit; architecture authority remains
[package_architecture_summary.md](package_architecture_summary.md).
This replaces stale June statements about synthetic NEX and interactive GEE auth.

| Source | Actual dispatched backend | GEE required for uncached fetch? | Backup/status |
| --- | --- | --- | --- |
| `chirps_v3_daily_rnl` | Dynamical final/RNL Icechunk → Hugging Face Zarr → permitted GEE/Xee | No with Python 3.12+ cloud extra | Two direct providers; explicit selection supported; complete cache preferred |
| `chirts_era5` | Hugging Face Zarr | No with Python 3.12+ cloud extra | One provider; original CHC backup investigation remains open |
| `chirts` | GEE/Xee CHIRTS-daily | Yes | Deprecated compatibility only; use `chirts_era5` for new temperature workflows |
| `chirps_v2` / `chirps` | GEE/Xee | Yes | No integrated direct backup; v3 is a different scientific source |
| `agera_5` | Thin adapter over GEE/Xee `ECMWF/ERA5_LAND/DAILY_AGGR` | Yes | Product is ERA5-Land, despite source key; no integrated direct backup |
| `era_5` | Thin adapter over GEE/Xee `ECMWF/ERA5/DAILY` | Yes | Normal dispatch does not use CDS |
| `nex_gddp` | Real NEX-GDDP GEE/Xee single/batch paths | Yes | Not synthetic; version/source investigation #1 |
| `cmip_6` | GEE/Xee | Yes | Keep distinct from the richer NEX workflow; no new backup |
| `terraclimate`, `imerg` | GEE/Xee | Yes | Standalone source modules do not establish alternate runtime routes |
| `soil_grid`, `hwsd` | Static shared GEE downloader | Yes | No integrated independent backup |
| `nasa_power` | NASA POWER HTTP API | No | Existing direct path; Zarr investigation #54 |
| `tamsat` | JASMIN daily NetCDF | No | Existing optional path; earlier failures/slow access not resolved in this change |
| `ghcn_daily`, `gsod` | NOAA direct downloads | No | Station-specific products; not substitutes for gridded datasets |

## Policy and remaining gaps

Single-site and multi-site CHIRPS/CHIRTS requests share direct dispatch. Historical
`auto` with GEE disabled chooses CHIRPS v3 + CHIRTS-ERA5. Other products keep their
existing routes and fail clearly when GEE is prohibited. GEE initialization is
non-interactive; users must configure credentials/project separately.

Do not confuse CHIRTS-ERA5 with AgERA5 or ERA5-Land. New access hosts do not make
scientific products interchangeable. No universal redundancy is claimed.

Priority next investigations:

1. Independent CHIRTS-ERA5 original archive access ([#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179)): sample Tmax ranged reads work,
   but CHIRPS/Tmin raster reads failed in this environment. Establish robust sparse
   reads or a supported subset service before automatic fallback.
2. Credential-free **ERA5-Land** companion variables ([#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180)), preserving daily aggregation,
   units and grid identity. Official CDS ARCO and EDH metadata rejected anonymous
   access; the configured CDS key was also rejected. EDH daily means omit Tmax/Tmin.
   [Investigation and repeatable probes](issues/issue_180_era5_land_access.md) record
   required aggregation semantics and outstanding value/performance validation.
3. Reuse #54 for NASA POWER Zarr and #1 for NEX version sourcing. Do not substitute
   a reanalysis or projection product merely because its host is accessible.

## Code evidence and validation

- Dispatch: `fetch_data/fetch_data.py`, `fetch_data/source_data/source_data.py`.
- Direct adapters/policy: `fetch_data/direct_cloud.py`, `fetch_data/backend_policy.py`.
- Product IDs: `fetch_data/source_data/sources/utils/config.yaml`.
- GEE wrappers: `agera_5.py`, `era_5.py`, `gee_xee.py`, `nex_gddp_xee.py`.
- [Direct access guide](../docs/direct_cloud_access.md).
- [Implementation/benchmark evidence](issues/issue_176_178_direct_cloud_access.md).
