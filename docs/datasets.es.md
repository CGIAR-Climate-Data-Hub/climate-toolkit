# Conjuntos de datos {#datasets}

Fuentes que admite el argumento `source` de [`fetch_climate_data`](api/fetching.md) y de las demás funciones de la API.

**Autenticación**: las fuentes «EE» se consultan mediante Google Earth Engine y requieren una [configuración inicial](getting_started.md#2-google-earth-engine-credentials). «Ninguna» indica que se puede acceder sin credenciales.

| `source` | Conjunto de datos | Tipo | Resolución nativa | Cobertura | Variables | Autenticación |
|----------|---------|------|-------------------|----------|-----------|------|
| `era5_land` | Agregados diarios de ERA5-Land | Reanálisis | 0,1° (≈11 km) | Desde 1950-01-02 hasta fechas recientes | Precipitación, Tmax/Tmin/Tmedia, humedad, viento, radiación solar | EE |
| `era_5` | ERA5 diario | Reanálisis | 0,25° (≈28 km) | De 1979-01-02 a 2020-07-09 (archivo estático, cobertura comprobada al ejecutar) | Precipitación, Tmax/Tmin, viento | EE |
| `terraclimate` | TerraClimate | Clima y balance hídrico mensuales | 1/24° (≈4 km) | Desde 1958, mensual | Precipitación, Tmax/Tmin, viento, radiación solar, humedad del suelo | EE |
| `imerg` | GPM IMERG v07 | Precipitación por satélite | 0,1° (≈11 km) | Desde 2000 | Precipitación | EE |
| `chirps_v2` (alias `chirps`) | CHIRPS v2 diario | Precipitación combinada de satélites y pluviómetros | 0,05° (≈5,5 km) | Desde 1981 | Precipitación | EE |
| `chirps_v3_daily_rnl` | CHIRPS v3 diario definitivo/RNL | Precipitación combinada de satélites y pluviómetros | 0,05° (≈5,5 km) | De 1981 a la última fecha del proveedor | Precipitación | Ninguna con la opción cloud, EE como alternativa opcional |
| `chirts_era5` | CHIRTS-ERA5 diario | Temperatura de ERA5 calibrada con CHIRTS | 0,05° (≈5,5 km) | Archivo alojado desde 1981 hasta la última fecha disponible | Tmax/Tmin | Ninguna con la opción cloud |
| `chirts` (en desuso) | CHIRTS diario | Temperatura combinada de satélites y estaciones | 0,05° (≈5,5 km) | 1983–2016 | Tmax/Tmin | EE |
| `cmip_6` | NASA GDDP-CMIP6 | Proyecciones regionalizadas | 0,25° (≈27 km) | Período histórico y escenarios | Precipitación, Tmax/Tmin | EE |
| `nex_gddp` | NEX-GDDP-CMIP6 | Proyecciones regionalizadas por combinación GCM × SSP | 0,25° (≈27 km) | Histórico hasta 2014-12-31, escenarios desde 2015-01-01 | Precipitación, Tmax/Tmin, humedad | EE |
| `nasa_power` | NASA POWER diario | API de datos puntuales derivados de reanálisis | ≈0,5° | Desde 1984 | Precipitación, Tmax/Tmin/Tmedia, humedad | Ninguna |
| `tamsat` | TAMSAT v3.1 | Lluvia en África (satélite) | 0,05° (≈4 km), solo África | Desde 1983 | Precipitación, humedad del suelo | Ninguna |
| `ghcn_daily` | GHCN-Daily | Observaciones de estaciones | Puntual | Según la estación | Precipitación, Tmax/Tmin | Ninguna |
| `gsod` | NOAA GSOD | Observaciones de estaciones | Puntual | Según la estación | Precipitación, Tmax/Tmin | Ninguna |
| `soil_grid` | ISRIC SoilGrids / OpenLandMap | Propiedades estáticas del suelo | 250 m | Estática | Textura, densidad aparente, pH, carbono orgánico, capacidad de intercambio catiónico | EE |
| `hwsd` | FAO HWSD v2 | Propiedades estáticas del suelo | ≈1 km | Estática | Profundidad radicular, capacidad de agua disponible, drenaje, densidad aparente | EE |

!!! note "`era5_land` proporciona datos de ERA5-Land"
    Los nombres antiguos `agera_5` y `agera5` siguen como alias en desuso en las versiones 0.2.x. Al usarlos aparece una advertencia y se obtienen los mismos datos ERA5-Land. Use `era5_land` en las solicitudes nuevas. Las cachés existentes siguen siendo compatibles. La fuente `era5_land` consulta la colección de Earth Engine `ECMWF/ERA5_LAND/DAILY_AGGR` (agregados diarios) en la malla de ERA5-Land de 0,1°. Es la opción recomendada para datos diarios recientes por su variedad de variables y su actualización continua. AgERA5 de Copernicus es un producto distinto. La fecha inicial procede del [catálogo de GEE](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR). Compruebe la cobertura de cada solicitud. El acceso oficial a CDS ARCO requiere una clave de CDS. Su integración está [aplazada](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_180_era5_land_access.md) y aún no se ha integrado otra vía de acceso.

Dependencias de la nube, elección del proveedor y migración desde CHIRTS: [acceso directo a los datos](direct_cloud_access.md).

## Elegir una fuente {#choosing-a-source}

- **Datos diarios recientes, numerosas variables** → `era5_land` (requiere EE).
- **Inicio sin configuración** → `nasa_power` (sin credenciales, malla de menor resolución).
- **Precipitación de alta resolución** → `chirps_v3_daily_rnl` (0,05°, solo precipitación). Combine una fuente de temperatura mediante `precip_source` y `temp_source`.
- **Clima futuro** → `nex_gddp` con `model` (p. ej., `'GFDL-ESM4'`) y `scenario` (p. ej., `'ssp245'`). Para un conjunto de modelos, indique `models="all"` en la línea de comandos.
- **Validación con observaciones terrestres** → estaciones `ghcn_daily` o `gsod` y después [`compare_station_to_grids`](api/comparison.md).
- **Datos de suelo para el balance hídrico** → las funciones de evaluación de riesgos y de estadística los obtienen automáticamente. Para solicitarlos explícitamente, use los miembros de `SoilVariable`.

## Variables {#variables}

Para solicitar variables, use los miembros de la enumeración `ClimateVariable`:

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    SoilVariable,
)
```

`ClimateVariable`: `precipitation`, `max_temperature`, `min_temperature`, `mean_temperature`, `rainfall`, `wind_speed`, `solar_radiation`, `humidity`, `soil_moisture`.

`SoilVariable` (para `soil_grid` y `hwsd`): `root_depth`, `available_water_capacity`, `drainage`, `bulk_density`, `coarse_fragments`, `field_capacity`, `wilting_point`, `ph`, `sand_content`, `clay_content`, `silt_content`, `organic_carbon`, `organic_carbon_stock`, `cation_exchange_capacity`, `soil_moisture`.

Las variables disponibles dependen de la fuente (véase la tabla). En las fuentes anteriores, una solicitud que exceda el período disponible puede recortarse con una advertencia. El acceso directo requiere todo el período solicitado: si la cobertura es incompleta, el programa prueba otra vía admitida o devuelve un error.

<!-- source-sha256: 87d5c9f03caa8d6f328073e3fabb052d94d4fa8a4f56cf1f730ea7f6f0701b49 -->
