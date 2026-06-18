# Source Access Matrix

Audit date: 2026-06-10

This matrix describes current package behavior from actual `SourceData`
dispatch and source implementation status, not aspirational module docstrings.

## Current Routing Basis

Primary dispatch:

- `climate_tookit/fetch_data/source_data/source_data.py`

Shared Earth Engine path:

- `climate_tookit/fetch_data/source_data/sources/gee.py`

Key observation:

- many advertised datasets route through shared Earth Engine downloader
- shared Earth Engine downloader calls `ee.Authenticate()` and
  `ee.Initialize(project=os.getenv("GCP_PROJECT_ID"))`
- therefore many "normal" local package uses currently require Earth Engine
  setup plus Google Cloud project ID

## Matrix

| Source | Current backend actually used | Real data today? | Needs GEE auth + `GCP_PROJECT_ID`? | Local-open friendly? | Status / note | Recommendation |
|---|---|---:|---:|---:|---|---|
| `nasa_power` | direct NASA POWER HTTP API | Yes | No | Yes | Best current local-open source | Keep as baseline local source |
| `tamsat` | direct JASMIN daily NetCDF download | Partly | No | Maybe technically, but not product-ready | Kept for completeness and Africa-focused precipitation comparison, but live runs showed slow access plus intermittent JASMIN SSL/download failures | Keep as optional fragile comparison source, not default user path |
| `nex_gddp` | synthetic placeholder module | No | No | Not meaningful | Current tests earlier in session hit this path, not live NEX | Do not present as real data source |
| `nex_gddp_xee` | Xee + Earth Engine PoC | Intended yes, not live-validated here | Yes | No | R&D only | Keep backend/operator R&D only |
| `chirps_v2` | shared Earth Engine downloader | Yes if EE works | Yes | No | Advertised as standard source, but local setup burden hidden | Either document burden or build direct non-GEE backend |
| `chirts` | shared Earth Engine downloader | Yes if EE works | Yes | No | Same issue as CHIRPS | Same |
| `agera_5` | shared Earth Engine downloader | Yes if EE works | Yes | No | Same issue | Same |
| `era_5` | shared Earth Engine downloader | Yes if EE works | Yes | No | Despite separate `era_5.py`, normal dispatch does not use CDS client | Decide: explicit `era_5_gee` vs real CDS-backed local path |
| `imerg` | shared Earth Engine downloader | Yes if EE works | Yes | No | Despite separate `imerg.py`, normal dispatch uses GEE path | Same split needed |
| `terraclimate` | shared Earth Engine downloader | Yes if EE works | Yes | No | Despite separate direct-download module, dispatch uses GEE | Same split needed |
| `soil_grid` | shared Earth Engine downloader | Yes if EE works | Yes | No | Static GEE path | Keep only if advanced mode accepted |
| `cmip_6` | shared Earth Engine downloader | Probably yes if EE works | Yes | No | Not common user-friendly local source as currently wired | Treat as advanced/operator mode |

## Immediate Conclusions

1. Current local-open source set is almost only `nasa_power`.
2. Current package README overstates frictionless local accessibility across
   many sources.
3. Real `nex_gddp` access does not create this problem from zero; it exposes a
   problem already present across much of source layer.
4. If package remains local-first, source access needs explicit product tiers:
   - local-open
   - local-advanced-with-auth
   - deprecated / unsupported

## Suggested Product Framing

### Local-open

- `nasa_power`
- maybe future direct-access sources once implemented and tested

### Local-advanced

- Earth Engine-backed sources requiring auth + project ID
- `chirps_v2`, `chirts`, `agera_5`, `era_5`, `imerg`, `terraclimate`,
  `soil_grid`, `cmip_6`
- future real `nex_gddp` if kept local

### Unsupported / R&D

- current synthetic `nex_gddp`
- `nex_gddp_xee` PoC
- `tamsat` as optional fragile comparison source, not recommended default

## Code Evidence

- Dispatch to shared GEE path:
  - `climate_tookit/fetch_data/source_data/source_data.py`
- Shared GEE initialization:
  - `climate_tookit/fetch_data/source_data/sources/gee.py`
- Current synthetic NEX placeholder:
  - `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`
- Current Xee PoC:
  - `climate_tookit/fetch_data/source_data/sources/nex_gddp_xee.py`
