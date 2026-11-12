# Descarga de datos {#fetching-data}

Función pública: `climate_toolkit.fetch_climate_data`.

## Ejemplo {#example}

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",                       # sin credenciales
    location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation,
               ClimateVariable.max_temperature,
               ClimateVariable.min_temperature],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print("rows:", df.shape[0], "| columns:", df.columns.tolist())
print(df.head())
```

`fetch_climate_data` devuelve un **DataFrame de pandas**. Las fuentes que utilizan Earth Engine (`era5_land`, `nex_gddp`, etc.) admiten la misma llamada una vez realizada la configuración inicial. Consulte la guía [Primeros pasos](../getting_started.md#2-google-earth-engine-credentials). La referencia completa de parámetros figura a continuación.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.fetch_data.fetch_data.fetch_data

<!-- source-sha256: 0204f0d3f4feb567b0610034aa2e044165df385574fdc67af5dbe051f5d08232 -->
