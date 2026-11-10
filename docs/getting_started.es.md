# Primeros pasos

!!! tip "Seguir la guía en Colab"
    El [cuaderno de Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb) permite instalar el paquete, descargar los primeros datos y, si hace falta, configurar Earth Engine desde el navegador.

## 1. Instalar el paquete {#1-install}

Para instalar la versión publicada en PyPI, ejecute el siguiente comando.

```bash
pip install climate-toolkit
```

Para descargar directamente las precipitaciones diarias de CHIRPS v3 (`chirps_v3_daily_rnl`) y las temperaturas mínimas y máximas de CHIRTS-ERA5 (`chirts_era5`), use Python 3.12 o posterior e instale las dependencias `cloud`. Este método funciona sin cuenta de Earth Engine. [Acceso directo a los datos](direct_cloud_access.md)

```bash
pip install "climate-toolkit[cloud]"
```

En una celda de Jupyter, use `%pip`.

```
%pip install climate-toolkit
```

Para probar la versión en desarrollo, ejecute `pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"`. Para contribuir al código, clone el repositorio e instale sus dependencias con [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
cd climate-toolkit
uv sync
```

## 2. Configurar Google Earth Engine {#2-google-earth-engine-credentials}

Pase directamente al [primer análisis](#3-first-analysis) si usa NASA POWER, las estaciones `ghcn_daily` o `gsod`, o el acceso directo a CHIRPS v3 y CHIRTS-ERA5. Siga este paso para `era5_land`, `era_5`, `nex_gddp`, CHIRPS v2 (`chirps_v2` o `chirps`) o el acceso alternativo a CHIRPS v3 mediante Earth Engine.

1. [Registre su proyecto de Google Cloud](https://code.earthengine.google.com/register). Para un proyecto no comercial, complete el cuestionario de elegibilidad y elija el nivel apropiado. [Niveles de acceso no comercial](https://developers.google.com/earth-engine/guides/noncommercial_tiers)
2. Autentíquese una vez en su equipo.

    ```bash
    earthengine authenticate
    ```

3. Indique el identificador del proyecto de Cloud. Sustituya `your-ee-project-id` por el valor de su proyecto. El paquete admite `GCP_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT` o `EE_PROJECT_ID`.

    ```bash
    # macOS / Linux
    export GCP_PROJECT_ID=your-ee-project-id
    ```

    ```powershell
    # Windows PowerShell
    $env:GCP_PROJECT_ID = "your-ee-project-id"
    ```

4. Compruebe la configuración.

    ```bash
    climate-toolkit-gee-check
    ```

## 3. Realizar el primer análisis {#3-first-analysis}

Este ejemplo descarga los datos diarios de Nairobi para 2020 con NASA POWER. Compruebe el número de filas y las columnas obtenidas.

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),   # Nairobi (latitud, longitud)
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print("filas:", df.shape[0], "| columnas:", df.columns.tolist())
df.head()
```

La función devuelve un **DataFrame de pandas**. NASA POWER no incluye datos del suelo. Un aviso indica que se omitieron esas variables y la tabla contiene las variables climáticas disponibles.

### Mostrar las estadísticas estacionales en una tabla

En Nairobi, este ejemplo fija la temporada principal de lluvias del 1 de marzo al 31 de mayo y muestra los resultados de cada año. `analyze_climate_statistics` devuelve un diccionario anidado.

```python
import pandas as pd

stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2016, end_year=2020,
    source="nasa_power",
    fixed_season="03-01:05-31",        # Temporada principal de lluvias, de marzo a mayo
)

pd.DataFrame([
    {
        "year": s["year"],
        "rain_mm": (s["precipitation"] or {}).get("total_mm"),
        "NDWS": (s["water_balance"] or {}).get("NDWS"),
        "WRSI": (s["water_balance"] or {}).get("WRSI"),
    }
    for s in stats["season_statistics"]
])
```

!!! note "Comparar la misma temporada cada año"
    La detección automática puede identificar un número distinto de temporadas según el año. Para comparar períodos fijos, use `fixed_season="MM-DD:MM-DD"`. Puede indicar uno o dos períodos, separados por una coma.

## Consultar la ayuda

```python
help(ct)                        # Descripción del paquete
help(ct.fetch_climate_data)     # Ayuda de una función
```

En Jupyter o IPython, escriba `ct.fetch_climate_data?`. En VS Code, sitúe el puntero sobre el nombre de la función para consultar su documentación.
