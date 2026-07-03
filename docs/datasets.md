# Datasets

All datasets accepted by the `source` argument of
[`fetch_climate_data`](api/fetching.md) and the other API functions.

**Auth**: "EE" sources are served through Google Earth Engine and need a
one-time free [setup](getting_started.md#2-google-earth-engine-credentials).
"None" sources work with no credentials.

| `source` | Dataset | Type | Native resolution | Coverage | Variables | Auth |
|----------|---------|------|-------------------|----------|-----------|------|
| `agera_5` | ERA5-Land daily aggregates | Reanalysis | 0.1° (~11 km) | 1979–present | precip, tmax/tmin/tmean, humidity, wind, solar | EE |
| `era_5` | ERA5 daily | Reanalysis | 0.25° (~28 km) | 1979-01-02 – 2020-07-09 (static asset; live coverage checked at runtime) | precip, tmax/tmin, wind | EE |
| `terraclimate` | TerraClimate | Monthly climate & water balance | 1/24° (~4 km) | 1958–present, monthly | precip, tmax/tmin, wind, solar, soil moisture | EE |
| `imerg` | GPM IMERG v07 | Satellite precipitation | 0.1° (~11 km) | 2000–present | precip | EE |
| `chirps_v2` (alias `chirps`) | CHIRPS v2 daily | Blended satellite–gauge precipitation | 0.05° (~5.5 km) | 1981–present | precip | EE |
| `chirps_v3_daily_rnl` | CHIRPS v3 daily (RNL) | Blended satellite–gauge precipitation | 0.05° (~5.5 km) | 1981–present | precip | EE |
| `chirts` | CHIRTS daily | Satellite–station temperature | 0.05° (~5.5 km) | 1983–2016 | tmax/tmin | EE |
| `cmip_6` | NASA GDDP-CMIP6 | Downscaled projections | 0.25° (~27 km) | historical + scenarios | precip, tmax/tmin | EE |
| `nex_gddp` | NEX-GDDP-CMIP6 | Downscaled projections (per GCM × SSP) | 0.25° (~27 km) | historical to 2014-12-31; scenarios from 2015-01-01 | precip, tmax/tmin, humidity | EE |
| `nasa_power` | NASA POWER daily | Reanalysis-derived point API | ~0.5° | 1984–present | precip, tmax/tmin/tmean, humidity | None |
| `tamsat` | TAMSAT v3.1 | African rainfall (satellite) | 0.05° (~4 km), Africa only | 1983–present | precip, soil moisture | None |
| `ghcn_daily` | GHCN-Daily | Weather station observations | point | station-dependent | precip, tmax/tmin | None |
| `gsod` | NOAA GSOD | Weather station observations | point | station-dependent | precip, tmax/tmin | None |
| `soil_grid` | ISRIC SoilGrids / OpenLandMap | Static soil properties | 250 m | static | texture, bulk density, pH, organic carbon, CEC | EE |
| `hwsd` | FAO HWSD v2 | Static soil properties | ~1 km | static | root depth, AWC, drainage, bulk density | EE |

!!! note "`agera_5` is backed by ERA5-Land"
    The `agera_5` source reads the Earth Engine asset
    `ECMWF/ERA5_LAND/DAILY_AGGR` (ERA5-Land daily aggregates), which shares
    ERA5-Land's 0.1° grid. It is the recommended default for recent daily
    data because of its variable breadth and continuously updated coverage.

## Choosing a source

- **Recent daily data, most variables** → `agera_5` (needs EE).
- **Zero-setup start** → `nasa_power` (no credentials, coarser grid).
- **Best precipitation detail** → `chirps_v3_daily_rnl` (0.05°, precip only);
  pair with a temperature source via `precip_source` / `temp_source`.
- **Future climate** → `nex_gddp` with `model` (e.g. `'GFDL-ESM4'`) and
  `scenario` (e.g. `'ssp245'`); pass `models="all"` on the CLI for ensembles.
- **Ground truth / validation** → `ghcn_daily` or `gsod` stations, then
  [`compare_station_to_grids`](api/comparison.md).
- **Soil inputs for water balance** → fetched automatically by the hazard
  and statistics functions; request explicitly via `SoilVariable` members.

## Variables

Request variables with `ClimateVariable` enum members:

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    SoilVariable,
)
```

`ClimateVariable`: `precipitation`, `max_temperature`, `min_temperature`,
`mean_temperature`, `rainfall`, `wind_speed`, `solar_radiation`,
`humidity`, `soil_moisture`.

`SoilVariable` (for `soil_grid` / `hwsd`): `root_depth`,
`available_water_capacity`, `drainage`, `bulk_density`, `coarse_fragments`,
`field_capacity`, `wilting_point`, `ph`, `sand_content`, `clay_content`,
`silt_content`, `organic_carbon`, `organic_carbon_stock`,
`cation_exchange_capacity`, `soil_moisture`.

Not every source provides every variable (see the table above). Requests
outside a source's coverage window are clipped with a warning, or raise
`ValueError` when there is no overlap.
