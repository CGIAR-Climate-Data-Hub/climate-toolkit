# Usar climate-toolkit en un proyecto de Python {#using-climate-toolkit-as-a-python-package}

Esta guía explica cómo instalar `climate_toolkit` y usarlo como biblioteca en su propio código de Python. Todos los ejemplos sin credenciales se ejecutaron con el paquete y la API reales.

> **Nombre del paquete.** Importe `climate_toolkit` en Python. En PyPI se distribuye como `climate-toolkit`. El acceso directo a CHIRPS v3 y CHIRTS-ERA5 requiere la versión 0.2.0 o posterior.

[![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)
Para probar los ejemplos en el navegador, abra el cuaderno [`examples/climate_toolkit_colab.ipynb`](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb). Ejecuta de principio a fin los ejemplos sin credenciales de esta guía en Google Colab, sin instalación ni configuración local.

---

## Contenido {#table-of-contents}

1. [Funciones disponibles](#1-what-you-get)
2. [Requisitos](#2-requirements)
3. [Instalación](#3-installation)
4. [Comprobar la instalación](#4-verify-the-install)
5. [Credenciales por fuente](#5-credentials-by-data-source)
6. [Inicio rápido sin credenciales](#6-quick-start-no-credentials)
7. [Configurar Earth Engine](#7-earth-engine-setup)
8. [Siete funciones de análisis](#8-seven-analysis-functions)
9. [Fuentes de datos](#9-data-sources-reference)
10. [Variables](#10-variables-reference)
11. [Caché y resultados](#11-caching-and-outputs)
12. [Ejemplos prácticos](#12-recipes)
13. [Usar Jupyter o un proyecto propio](#13-using-it-in-jupyter-your-own-project)
14. [Resolver problemas](#14-troubleshooting)
15. [Obtener ayuda](#15-getting-more-help)

---

## 1. Funciones disponibles {#1-what-you-get}

!!! tip "¿Es la primera vez que usa el paquete?"
    La guía [Primeros pasos](getting_started.md) explica cómo instalar el paquete y ejecutar un primer análisis en cinco minutos. Aquí encontrará una referencia más completa sobre funciones públicas, fuentes y variables, caché, ejemplos y resolución de problemas.

`climate_toolkit` es una biblioteca de análisis climático por sitio. Una sola instrucción `import climate_toolkit as ct` da acceso a las siete funciones de análisis siguientes. La [descripción general de la API](api/index.md) también incluye `run_pipeline` y `backend_policy`.

| Función | Utilidad |
|----------|--------------|
| `fetch_climate_data` | Descargar datos diarios de un punto en un DataFrame de pandas |
| `analyze_climate_statistics` | Calcular la climatología estacional, el balance hídrico y SPI/SPEI durante varios años |
| `evaluate_hazards` | Evaluar riesgos para los cultivos o el ganado durante una temporada agrícola |
| `compare_climate_periods` | Calcular diferencias entre un año de estudio y la climatología de referencia |
| `compare_climate_sources` | Comparar varios productos en malla para un mismo sitio |
| `download_station_data` | Obtener las observaciones diarias de estaciones cercanas |
| `compare_station_to_grids` | Validar productos en malla con observaciones de estaciones |

Las fuentes incluyen CHIRPS, ERA5-Land, TerraClimate, IMERG, TAMSAT, CHIRTS-ERA5, ERA5, NEX-GDDP, NASA POWER, CMIP6, SoilGrids y las estaciones de GHCN-Daily y GSOD.

---

## 2. Requisitos {#2-requirements}

- **Python ≥ 3.10.** Python 3.9 no es compatible. Use un entorno virtual con 3.10 o posterior. [`uv`](https://docs.astral.sh/uv/) simplifica su creación y puede instalar Python 3.12 para el acceso directo a la nube.
- Las distribuciones de Python en formato wheel proporcionan lo necesario, sin paquetes adicionales del sistema ni compilador.
- Para las fuentes de Earth Engine se necesita un proyecto de Google Cloud y una autenticación inicial (sección 7). **NASA POWER y las estaciones no requieren ninguno de los dos.**

---

## 3. Instalación {#3-installation}

Consulte [Primeros pasos → Instalación](getting_started.md#1-install) para instalar desde GitHub, utilizar `%pip` en Jupyter y configurar el entorno de desarrollo con `uv`. En resumen:

```bash
# En su proyecto o cuaderno:
pip install climate-toolkit

# O instalar la versión en desarrollo desde Git:
pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

# O desarrollar desde una copia del repositorio:
cd climate-toolkit && uv sync
```

Una vez instalado, `import climate_toolkit` funciona desde cualquier directorio. Use `uv run python my_script.py` para ejecutar un script en el entorno del repositorio.

---

## 4. Comprobar la instalación {#4-verify-the-install}

```bash
uv run python -c "import climate_toolkit as ct; print(ct.__version__)"
# Ejemplo: 0.2.0
```

Compruebe los nombres que exporta el paquete:

```python
import climate_toolkit as ct
print([n for n in ct.__all__ if not n.startswith("__")])
# Incluye las funciones de análisis, backend_policy y run_pipeline.
```

---

<a id="5-credentials-nasa-power-vs-earth-engine"></a>

## 5. Credenciales por fuente {#5-credentials-by-data-source}

- **`nasa_power`** y las estaciones `ghcn_daily` y `gsod` usan HTTPS **sin credenciales**. Son buenos puntos de partida.
- **`chirps_v3_daily_rnl` y `chirts_era5`** permiten [acceso directo sin credenciales](direct_cloud_access.md). Con Python 3.12 o posterior, ejecute `pip install "climate-toolkit[cloud]"`. Indique `allow_gee=False` para impedir que se recurra a Earth Engine.
- Las **fuentes de Earth Engine** (`era5_land`, `era_5`, `chirps_v2` con el alias `chirps`, `chirts`, `imerg`, `terraclimate`, `cmip_6`, `nex_gddp`, `soil_grid` y `hwsd`) pasan por **Google Earth Engine**. Requieren autenticación inicial y un identificador de proyecto (sección 7).

---

## 6. Inicio rápido sin credenciales {#6-quick-start-no-credentials}

### Datos diarios en un DataFrame {#fetch-daily-data-dataframe}

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),      # (lat, lon), Nairobi
    variables=[ClimateVariable.precipitation,
               ClimateVariable.max_temperature,
               ClimateVariable.min_temperature],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print(df.head())
#         date  precipitation  max_temperature  min_temperature
# 0 2020-01-01           0.04            27.17            14.07
# ...
```

`fetch_climate_data` devuelve un **DataFrame de pandas**.

### Estadísticas estacionales en un diccionario {#seasonal-statistics-dict}

```python
stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2015, end_year=2020,
    source="nasa_power",
)
print(stats.keys())
# location, period, source, ..., season_statistics, ltm_season_summary, ...
```

`analyze_climate_statistics` devuelve un **diccionario anidado**. Para una climatología a largo plazo, use al menos unos veinte años. Una serie corta genera una advertencia.

---

## 7. Configurar Earth Engine {#7-earth-engine-setup}

Las fuentes de Earth Engine de la sección 5 requieren una configuración inicial. [Primeros pasos → Credenciales de Earth Engine](getting_started.md#2-google-earth-engine-credentials) explica el acceso **gratuito** para proyectos no comerciales que cumplan los requisitos. Ejecute `earthengine authenticate`, defina `GCP_PROJECT_ID` y compruebe la configuración con `climate-toolkit gee-check` (código de salida 0 si funciona).

A continuación, las funciones pueden utilizar las fuentes de EE:

```python
# ClimateVariable se importó en el ejemplo anterior.
vars3 = [ClimateVariable.precipitation,
         ClimateVariable.max_temperature,
         ClimateVariable.min_temperature]

df = ct.fetch_climate_data(
    source="era5_land",                       # Earth Engine
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
)

# Las proyecciones NEX-GDDP requieren un modelo y un escenario:
proj = ct.fetch_climate_data(
    source="nex_gddp", model="GFDL-ESM4", scenario="ssp245",
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2050, 1, 1), date_to=date(2050, 12, 31),
)
```

---

<a id="8-the-public-api-all-seven-functions"></a>

## 8. Siete funciones de análisis {#8-seven-analysis-functions}

Cada función tiene documentación detallada en formato NumPy, accesible con `help(ct.<function>)`.

### `fetch_climate_data` {#fetch_climate_data}

```python
ct.fetch_climate_data(
    source, location_coord=None, variables=None,
    date_from=None, date_to=None, model=None, scenario=None,
    stage="preprocessed", cache_dir=None, refresh_cache=False,
    sites=None, sites_csv=None, station_id=None, workers=1, verbose=True,
)
```
Devuelve un DataFrame. `stage` define la última etapa: `"raw"` → `"transformed"` → `"preprocessed"` (predeterminada). Para una descarga por lotes de varios sitios, indique `sites=` o `sites_csv=` (fuentes de GEE y NEX-GDDP).

### `analyze_climate_statistics` {#analyze_climate_statistics}

```python
ct.analyze_climate_statistics(
    location_coord, start_year, end_year, source,
    fixed_season=None, crop_name=None,
    spei_scale_months=None, spi_scale_months=None,
    workers=1, verbose=False,
)
```
Devuelve un diccionario con estadísticas por temporada, balance hídrico (ET0, NDWS, WRSI), bloques opcionales de SPI/SPEI y medias a largo plazo.

### `evaluate_hazards` {#evaluate_hazards}

```python
ct.evaluate_hazards(
    crop_name, location_coord, date_from, date_to,   # fechas como cadenas en formato ISO
    season_start=None, season_end=None, fixed_season=None,
    source="auto", custom_thresholds=None,
    soilcp=100.0, soilsat=100.0, workers=1,
)
```
Evalúa los riesgos para cultivos y ganado durante una temporada agrícola (calor, sequía, anegamiento…). `date_from` y `date_to` son cadenas de fecha en formato ISO, por ejemplo `"2020-03-01"`.

### `compare_climate_periods` {#compare_climate_periods}

```python
ct.compare_climate_periods(
    location, baseline_start, baseline_end, focal_year, source,
    fixed_season=None, crop_name=None, workers=1,
)
```
Compara el año de estudio con la climatología de referencia y devuelve las diferencias en un diccionario.

### `compare_climate_sources` {#compare_climate_sources}

```python
ct.compare_climate_sources(
    sources, lat=None, lon=None, start=None, end=None,
    output_dir="./outputs", nex_model=None, nex_scenario="ssp245",
    workers=1,
)
```
Compara varios productos en malla para un mismo sitio. `sources` es una lista, por ejemplo `["nasa_power", "era5_land"]`.

### `download_station_data` (solo argumentos por nombre) {#download_station_data-keyword-only-args}

```python
ct.download_station_data(
    station_source="ghcn_daily",            # o "gsod"
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    max_distance_km=50.0, auto_select="auto-1",
)
```
Busca estaciones cercanas y descarga sus observaciones. No requiere Earth Engine.

### `compare_station_to_grids` (solo argumentos por nombre) {#compare_station_to_grids-keyword-only-args}

```python
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power", "era5_land"],
)
```
Valida productos en malla mediante observaciones de estaciones y devuelve un diccionario.

---

## 9. Fuentes de datos {#9-data-sources-reference}

| Clave `source` | Datos | ¿Earth Engine? |
|--------------|------|:---:|
| `nasa_power` | Datos climáticos diarios puntuales desde 1984 | No |
| `tamsat` | Lluvia en África y humedad del suelo (acceso opcional, a veces inestable) | No (descarga directa) |
| `ghcn_daily`, `gsod` | Observaciones de estaciones meteorológicas | No |
| `era5_land` | Agregados diarios de ERA5-Land, numerosas variables, opción recomendada | Sí |
| `era_5` | Reanálisis diario de ERA5 | Sí |
| `chirps_v2` (alias `chirps`) | Precipitación CHIRPS v2 | Sí |
| `chirps_v3_daily_rnl` | Precipitación diaria definitiva de CHIRPS v3 | Alternativa opcional |
| `chirts_era5` | Tmax y Tmin diarias de CHIRTS-ERA5 | No (dependencias de la nube) |
| `chirts` (en desuso) | Temperaturas del producto anterior CHIRTS-daily, 1983–2016 | Sí |
| `imerg` | Precipitación GPM IMERG | Sí |
| `terraclimate` | Balance hídrico mensual | Sí |
| `cmip_6` | Proyecciones GDDP-CMIP6 | Sí |
| `nex_gddp` | Proyecciones NEX-GDDP-CMIP6 (requieren `model` y `scenario`) | Sí |
| `soil_grid`, `hwsd` | Propiedades estáticas del suelo | Sí |

Los alias anteriores (`era5`, `agera5`, `nasapower`, `nexgddp`, `ghcn`, etc.) se normalizan automáticamente.

---

## 10. Variables {#10-variables-reference}

`variables` admite una **lista de miembros de enumeración**, forma compatible con todas las versiones:

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

variables=[ClimateVariable.precipitation,
           ClimateVariable.max_temperature,
           ClimateVariable.min_temperature]
```

Las versiones recientes también admiten cadenas (p. ej., `["precipitation", "max_temperature"]` o `"precipitation,max_temperature"`), al igual que la línea de comandos. Si aparece `AttributeError: 'str' object has no attribute 'name'`, use los miembros de la enumeración anterior: está usando una versión antigua.

Nombres de `ClimateVariable`: `rainfall`, `precipitation`, `max_temperature`, `min_temperature`, `mean_temperature`, `wind_speed`, `solar_radiation`, `humidity`, `soil_moisture`. Las propiedades del suelo se encuentran en `SoilVariable`.

Si omite `variables`, cada fuente utiliza su selección predeterminada y descarta las variables ausentes, como la humedad del suelo en NASA POWER.

---

## 11. Caché y resultados {#11-caching-and-outputs}

- Las descargas se guardan en **`outputs/cache/<source>/...`**, según el sitio, el período y las variables. Las ejecuciones siguientes reutilizan las tablas en caché.
- Forzar una nueva lectura desde la fuente: `refresh_cache=True`.
- Cambiar la ubicación de la caché: `cache_dir="/some/stable/path"`.
- Las funciones de análisis y comparación guardan sus informes en `./outputs` de manera predeterminada.

Git excluye `outputs/` y `.tmp/`.

---

## 12. Ejemplos prácticos {#12-recipes}

### Ejecutar todo el flujo con `run_pipeline` {#one-call-for-the-whole-workflow-run_pipeline}

`run_pipeline` encadena la descarga, la climatología a largo plazo, la comparación opcional de fuentes, las estadísticas estacionales, los riesgos agrícolas y la comparación opcional de períodos para uno o varios sitios. Devuelve una tabla de resumen `summary` y todos los resultados intermedios. Por defecto, un fallo en un sitio no interrumpe el lote.

```python
import climate_toolkit as ct

# Un solo sitio
result = ct.run_pipeline(
    name="Nairobi", location_coord=(-1.286, 36.817),
    start_year=2019, end_year=2020, source="nasa_power",
    fixed_season="03-01:05-31", crop_name="maize",
)
result.summary                      # una fila de resumen por sitio (DataFrame)
result.site_results[0].climate_statistics   # resultado anidado completo por sitio

# Varios sitios (lista de diccionarios, sites_csv="..." o site_table=DataFrame)
batch = ct.run_pipeline(
    sites=[{"name": "A", "lat": -1.0, "lon": 36.0},
           {"name": "B", "lat": -2.0, "lon": 37.0}],
    start_year=2019, end_year=2020, source="nasa_power",
)
batch.summary            # una fila por sitio
batch.errors             # errores registrados por sitio, el lote continúa
```

La climatología usa de forma predeterminada el período de referencia 1991–2020 de la OMM (`climatology_baseline=(1991, 2020)`). Active las etapas opcionales con `run_compare_sources=True` y `compare_sources_list=[...]`, o con `run_compare_periods=True` y `baseline_start/baseline_end/focal_year`.

### Comparar dos fuentes para un sitio {#compare-two-sources-at-one-site}

```python
ct.compare_climate_sources(
    sources=["nasa_power", "era5_land"],       # era5_land requiere Earth Engine
    lat=-1.286, lon=36.817,
    start="2020-01-01", end="2020-12-31",
    output_dir="./outputs",
)
```

### Evaluar riesgos durante una temporada de maíz {#hazard-screen-for-a-maize-season}

```python
ct.evaluate_hazards(
    crop_name="Maize",
    location_coord=(-1.286, 36.817),
    date_from="2020-03-01", date_to="2020-08-31",
)
```

### Comparar el año de estudio con la climatología de referencia {#focal-year-vs-baseline-climatology}

```python
ct.compare_climate_periods(
    location=(-1.286, 36.817),
    baseline_start=1991, baseline_end=2020,
    focal_year=2023,
    source="era5_land",
)
```

### Validar un producto en malla con una estación cercana {#validate-a-grid-product-against-a-nearby-station}

```python
from datetime import date
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2019, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power"],
)
```

---

## 13. Usar Jupyter o un proyecto propio {#13-using-it-in-jupyter-your-own-project}

Una vez instalado el paquete en su entorno de Python, impórtelo de la forma habitual:

```python
import climate_toolkit as ct
from datetime import date

from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power", location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation],
    date_from=date(2022, 1, 1), date_to=date(2022, 3, 31),
)
df.set_index("date")["precipitation"].plot()   # graficar la serie de precipitación diaria
```

El cuaderno se inicia rápidamente porque las dependencias pesadas se cargan solo cuando se necesitan.

---

## 14. Resolver problemas {#14-troubleshooting}

| Síntoma | Causa o solución |
|---------|-------------|
| `SyntaxError` o error de importación con `python3` | Está usando Python 3.9. Use un entorno 3.10 o posterior (`uv sync`). |
| `Earth Engine project ID missing` | Defina `GCP_PROJECT_ID` (sección 7). |
| `Project 'projects/YOUR_PROJECT_ID' not found` | Sustituya el valor de ejemplo por el identificador real del proyecto. |
| Error de renovación de credenciales o de DNS en una fuente de EE | Vuelva a ejecutar `ee.Authenticate()` y compruebe la red. |
| `command not recognized: climate-toolkit-*` | Los comandos del paquete están disponibles después de `uv sync` o `pip install`. También puede ejecutar `python -m climate_toolkit.<module>`. |
| `OSError: File name too long` al consultar NASA POWER | Indique una lista `variables=[...]` en lugar de usar todas las variables predeterminadas. |
| `AttributeError: 'str' object has no attribute 'name'` con `variables=` | Pase miembros de la enumeración (`ClimateVariable.*`) en lugar de cadenas. |

Puede comprobar la configuración de Earth Engine en cualquier momento con:

```bash
uv run climate-toolkit gee-check
```

---

## 15. Obtener ayuda {#15-getting-more-help}

- Use `help(ct.fetch_climate_data)` (o el nombre de una de las siete funciones) para consultar la documentación completa de los parámetros.
- Los enlaces del archivo `pyproject.toml` y del README del proyecto llevan a la referencia de la API y a las páginas de conjuntos de datos.
- Use `uv run climate-toolkit --help` para ver los subcomandos equivalentes.

<!-- source-sha256: c81558de9ebbcd67f883a554df344ae2d19a2c5f625241968c626a68d817e9e7 -->
