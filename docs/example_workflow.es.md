# Ejemplo de análisis de principio a fin {#example-end-to-end-workflow}

Este ejemplo permite conocer el programa desde la descarga de datos sin procesar hasta la proyección de riesgos para los cultivos.

> [!IMPORTANT]
> **Los comandos siguientes empiezan con `uv run` para poder copiarlos tal como aparecen.** Ejecútelos desde la raíz del repositorio después de `uv sync`.
>
> - Los comandos `climate-toolkit-*` solo están disponibles después de instalar el paquete (`uv sync` o `pip install -e .`). Ejecutar `climate-toolkit-fetch ...` directamente, sin `uv run` o desde un repositorio sin instalar, puede producir el error «command not recognized».
> - Desde un repositorio sin instalar puede llamar al módulo: cada `climate-toolkit-<name>` corresponde a `python -m climate_toolkit.<module>` (p. ej., `python -m climate_toolkit.season_analysis.seasons ...`).
> - Sustituya las coordenadas, las fechas y cualquier `<PLACEHOLDER>` por sus propios valores.

## Requisitos {#prerequisites}

1. **Google Earth Engine** (para las fuentes que usan GEE):
   - Cree una cuenta en [earthengine.google.com](https://earthengine.google.com)
   - Autentíquese una vez: `earthengine authenticate`
   - Indique su proyecto de Cloud para inicializar Earth Engine. El programa lee el identificador del entorno y **no carga** automáticamente el archivo `.env`:
     ```bash
     # macOS / Linux
     export GCP_PROJECT_ID=your-ee-project-id
     ```
     ```powershell
     # Windows PowerShell
     $env:GCP_PROJECT_ID = "your-ee-project-id"
     ```
     (O use `uv run --env-file .env ...` si guarda ese valor en un archivo `.env`).
2. **Instalación:** `uv sync` (recomendado) o `pip install -e .`
3. **Datos de entrada:** latitud y longitud. Más adelante se indican el cultivo y las fechas.

---

## Paso 1 — Descargar los datos climáticos {#step-1-fetch-raw-climate-data}

`climate-toolkit-fetch` utiliza `--lat` y `--lon` para un sitio y `--start` y `--end` para las fechas.

```bash
uv run climate-toolkit-fetch \
  --source era5_land \
  --lat -1.286 --lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/climate_data.csv
```

- Descarga desde la fuente, normalización de los nombres de variables y preprocesamiento (unidades y control de calidad).
- **Cobertura de las fuentes:** ERA5-Land desde 1950, con humedad derivada; archivo ERA5 de 1979 a 2020-07-09; CHIRPS v3 `chirps_v3_daily_rnl` desde 1981 para precipitación; NASA POWER desde 1984; proyecciones NEX-GDDP con `--scenario` y `--model` o `--models`.
- **Varios modelos NEX-GDDP en una ejecución:** indique una lista separada por comas o `all` mediante `--models` o `--model`. Se guarda un archivo por modelo:
  ```bash
  uv run climate-toolkit-fetch --source nex_gddp --lat -1.286 --lon 36.817 \
    --start 2050-01-01 --end 2050-12-31 \
    --variables precipitation,max_temperature,min_temperature \
    --models ACCESS-CM2,EC-Earth3,MRI-ESM2-0 --scenario ssp245 \
    --format csv -o outputs/nex_2050.csv
  ```

---

## Paso 2 — Validar con observaciones de estaciones (opcional) {#step-2-validate-against-weather-stations-optional}

Buscar estaciones cercanas:

```bash
uv run climate-toolkit-weather-station-download \
  --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nearby_candidates \
  --open-report
```

Comparar datos en malla y observaciones:

```bash
uv run climate-toolkit-weather-station-compare \
  --grid-source era5_land \
  --station-source gsod \
  --station-id <STATION_ID> \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --format json
```

---

## Paso 3 — Climatología (la «normal» local) {#step-3-climatology-the-local-normal}

```bash
uv run climate-toolkit-climatology \
  --location "-1.286,36.817" \
  --source era5_land \
  --start-year 1991 --end-year 2020
```

Para NEX-GDDP, `--source nex_gddp` utiliza el conjunto CMIP6 y calcula la media de los modelos. Añada `--model-workers` para paralelizar.

---

## Paso 4 — Detectar temporadas de lluvia {#step-4-detect-rainy-seasons}

```bash
uv run climate-toolkit-seasons \
  --location "-1.286,36.817" \
  --source era5_land \
  --start-year 2015 --end-year 2020
```

- Detección anual del inicio y el final de la temporada a partir del balance hídrico (ET0 de Hargreaves).
- Guarde las figuras y los archivos de resultados con `--output-dir outputs/seasons`.
- **Si la detección automática es poco fiable** (clima muy húmedo o irregular), defina una ventana fija de calendario con `--fixed-season`, como en el paso 5.

---

## Paso 5 — Estadísticas climáticas por temporada {#step-5-climate-statistics-by-season}

Temporadas detectadas automáticamente:

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/climate_stats_2015_2020.json
```

Temporadas fijas (p. ej., marzo–mayo y octubre–diciembre):

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --fixed-season "03-01:05-31,10-01:12-31" \
  --output outputs/climate_stats_fixed.json
```

Los resultados incluyen precipitación estacional, temperaturas extremas, indicadores de balance hídrico (NDWS, NDWL0), índices de estrés térmico y, si se solicita, SPEI.

---

## Paso 6 — Comparar períodos {#step-6-compare-periods}

`climate-toolkit-periods` admite `--baseline-start`, `--baseline-end` y `--focal-year`. Las dos primeras opciones no llevan el sufijo `*-year`.

```bash
uv run climate-toolkit-periods \
  --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/2020_vs_2001_2015.json
```

Para comparar períodos con NEX-GDDP, añada `--uncertainty-html ensemble.html` a `climate-toolkit periods-ensemble`. Para cada escenario, el informe muestra, por año y por estación, la precipitación, las medias de las temperaturas máximas y mínimas diarias y la precipitación menos la evapotranspiración de referencia. Cada punto representa un modelo. La mediana y los intervalos entre los percentiles 25 y 75 y entre los percentiles 10 y 90 resumen la dispersión de los modelos con datos para ambos períodos. El cambio se calcula dentro de cada modelo. La tabla de contribuciones y el CSV identifican los datos faltantes y los modelos que fallaron. Los intervalos describen la dispersión entre modelos y no representan probabilidades de pronóstico. Para crear las figuras a partir de un archivo JSON guardado sin descargar datos climáticos:

```python
import json
from pathlib import Path
from climate_toolkit.visualization.ensemble import write_ensemble_uncertainty

result = json.loads(Path("ensemble.json").read_text())
write_ensemble_uncertainty(result, "ensemble.html")
```

---

## Paso 7 — Evaluar riesgos para los cultivos {#step-7-crop-hazards}

`climate-toolkit-hazards` recibe el **cultivo como argumento posicional**. Para las fechas use `--date-from` y `--date-to` y evite `--start-date` y `--end-date`.

```bash
uv run climate-toolkit-hazards Maize \
  --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/maize_hazards_2020.json
```

Cultivos admitidos: frijol (Beans), yuca (Cassava), maní (Groundnuts), maíz (Maize), mijo (Millet), arroz (Rice) y sorgo (Sorghum). Los indicadores incluyen NDWS, NDWL0, NTx35/NTx40, NDD y umbrales de precipitación y temperatura específicos de cada cultivo.

---

## Paso 8 — Proyectar riesgos (conjunto NEX-GDDP) {#step-8-project-hazards-nex-gddp-ensemble}

`climate-toolkit-hazards-ensemble` recibe el cultivo como argumento posicional. Indique `--start-year` y `--end-year`, `--models` (lista separada por comas o `all`), `--scenarios` (lista separada por comas) y `--model-workers` para la ejecución en paralelo.

```bash
uv run climate-toolkit-hazards-ensemble Maize \
  --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 \
  --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245,ssp585 \
  --model-workers 8 \
  --output outputs/maize_hazards_2050_2060.json
```

---

## Ejemplo completo: aptitud para el cultivo de maíz cerca de Nairobi {#complete-walkthrough-maize-suitability-near-nairobi}

```bash
# 1. Descargar los datos climáticos
uv run climate-toolkit-fetch --source era5_land --lat -1.286 --lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/nairobi_climate.csv

# 2. Buscar estaciones cercanas (opcional)
uv run climate-toolkit-weather-station-download --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --report-prefix outputs/nairobi_stations --open-report

# 3. Climatología de referencia
uv run climate-toolkit-climatology --location "-1.286,36.817" --source era5_land \
  --start-year 1991 --end-year 2020

# 4. Detectar las temporadas de lluvia
uv run climate-toolkit-seasons --location "-1.286,36.817" --source era5_land \
  --start-year 2015 --end-year 2020

# 5. Estadísticas climáticas
uv run climate-toolkit-stats --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_stats.json

# 6. Comparar 2020 con el período de referencia
uv run climate-toolkit-periods --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_2020_vs_baseline.json

# 7. Evaluar riesgos para el maíz en 2020
uv run climate-toolkit-hazards Maize --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_maize_2020.json

# 8. Proyectar riesgos para el maíz en 2050-2060
uv run climate-toolkit-hazards-ensemble Maize --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245 --model-workers 8 \
  --output outputs/nairobi_maize_2050_2060.json
```

---

## Aclaraciones y problemas frecuentes {#notes-gotchas}

- **Los comandos del paquete requieren instalación** (`uv sync` o `pip install -e .`). Instalar solo las dependencias de `requirements.txt` no los crea. En ese caso use `python -m climate_toolkit.<module>`.
- El **identificador de proyecto de Earth Engine** debe definirse en el entorno (`GCP_PROJECT_ID`) o facilitarse con `uv run --env-file .env`. El archivo `.env` no se carga automáticamente.
- **Fuente histórica diaria**: el modo automático estándar combina `chirps_v3_daily_rnl` para precipitación y `era5_land` para temperatura. En el modo emparejado se indican ambas fuentes.
- **Nombres de CHIRPS:** `chirps_v3_daily_rnl` es la v3 recomendada. La anterior `chirps_v2` es un producto distinto. La fecha final de 2016 corresponde a las temperaturas de la versión anterior de CHIRTS-daily. Use `chirts_era5` para nuevos análisis de temperatura.
- **Acceso sin GEE:** instale las dependencias de la nube e indique `--no-gee`. El modo histórico `auto` combinará CHIRPS v3 con CHIRTS-ERA5. Consulte el [acceso directo](direct_cloud_access.md).
- La **primera consulta a GEE** es lenta por el intercambio de autenticación. Las siguientes ejecuciones reutilizan la caché.
- **Las opciones dependen del comando.** Compruébelas con `--help`. Por ejemplo, `fetch` utiliza `--lat/--lon`; `stats`, `seasons` y `hazards` usan `--location`; `hazards` recibe el cultivo como argumento posicional y las fechas mediante `--date-from` y `--date-to`; `periods` usa `--baseline-start` y `--baseline-end`.

<!-- source-sha256: 25c651b76dfbc54c9c8458822a7d2eb00fe44cc741e8c6dafe4e1155ed090547 -->
