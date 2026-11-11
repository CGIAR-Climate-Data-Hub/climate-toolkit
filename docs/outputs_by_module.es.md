# Resultados por módulo {#outputs-by-module}

Consulte las **tablas y figuras que genera cada módulo**, sus formatos y los archivos y columnas que puede esperar antes de ejecutar un análisis. Las firmas y los parámetros de las funciones se detallan en la [referencia de la API de Python](api/index.md).

---

## 🌾 fetch_data — obtención de datos climáticos {#fetch_data-climate-data-ingestion}

**Formatos:** CSV, JSON

**Tablas:**

- Series diarias con las columnas `date`, `precipitation`, `max_temperature`, `min_temperature`, `humidity`, `solar_radiation`, `wind_speed` según la fuente.

**Figuras:** ninguna (solo datos sin procesar).

---

## 📅 season_analysis — detección de temporadas de lluvia {#season_analysis-rainy-season-detection}

**Formatos:** CSV, JSON

**Tablas:**

- **Resumen por temporada (CSV):** `year`, `season_number`, `onset`, `cessation`, `regime`, `length_days`, `total_rainfall_mm`, `rainy_days`, `dry_days`, `dry_spells`, `annual_rain_mm`, `humid_result`.
    - Indicadores para el ganado cuando se activa este modo: `mean_thi`, `max_thi`, `thi_stress_days`.
- **Medias a largo plazo (JSON):** agregados por temporada, entre ellos fecha media de inicio, duración media y precipitación media.

**Figuras:** ninguna.

---

## 📊 climate_statistics — indicadores y agregación {#climate_statistics-climate-metrics-aggregation}

**Formatos:** principalmente JSON, con exportación a CSV

**Tablas:**

- **`raw_climate_summary`:** media, mínimo, máximo y desviación estándar por variable y temporada.
- **`overall_statistics`** por temporada: totales y estadísticas de precipitación, temperaturas media, máxima y mínima, evapotranspiración de referencia (ET0), balance hídrico (NDWS, NDWL0, WRSI), déficit de presión de vapor (VPD) y estrés térmico (Humidex, THI).
- **`season_statistics`:** principales indicadores por temporada.
- **`monthly_series` (CSV):** datos diarios agregados por mes.
- **`spei` / `spi` (CSV):** índices de sequía con fecha, valor y categoría.
- **`annual_summary`:** resultados de la prueba de humedad por año.

**Figuras:** ninguna.

---

## 📈 compare_periods — comparación de períodos históricos {#compare_periods-historical-period-comparison}

**Formatos:** JSON y texto en la consola

**Tablas:**

- **Comparación** por variable y temporada: `focal` (valor del año de estudio), `baseline_avg` (media de referencia), `diff` (año de estudio menos referencia), `pct_change` (`diff / baseline × 100`).
- Las comparaciones abarcan precipitación, temperatura, estrés hídrico y estrés térmico.

**Figuras:** ninguna.

---

## ⚠️ calculate_hazards — evaluación de riesgos agrícolas {#calculate_hazards-crop-hazard-assessment}

Con `fixed_season`, la fecha de inicio de la temporada debe caer dentro del período solicitado, con ambos extremos incluidos. Así, de `2010-01-01` a `2010-12-31`, la ventana `10-01:01-31` incluye toda la temporada de octubre de 2010 a enero de 2011. Para una sola temporada, `season_info` y `season_statistics` aparecen en el primer nivel del resultado. Para varias, la lista `assessments` contiene una entrada por temporada. Consulte `error` si ninguna temporada empieza en el período o si la cobertura es incompleta.

**Formatos:** JSON, texto en consola y CSV opcional

**Tablas:**

- **`hazard_indicators`** incluye por riesgo `focal_value`, `baseline_avg`, `diff`, `stress_category` (estrés ausente, moderado, severo o extremo) y `reasoning`.

| Indicador | Significado |
|--------|---------|
| Precipitación | Total de lluvia de la temporada |
| TAVG | Temperatura media |
| NDD | Número de días secos (precipitación < 1 mm) |
| NTx35 | Días con Tmax ≥ 35 °C |
| NTx40 | Días con Tmax ≥ 40 °C |
| NDWS | Días de estrés hídrico |
| NDWL0 | Días de anegamiento |
| WRSI | Satisfacción de las necesidades hídricas (%) |
| THI | Índice de estrés térmico del ganado |
| HUMIDEX | Índice de calor para personas |

**Figuras:** ninguna.

---

## 🌦️ weather_station (descarga) — búsqueda de estaciones {#weather_station-download-station-discovery}

**Formatos:** CSV, JSON y HTML interactivo

**Tablas:**

- **Estaciones candidatas (CSV):** `station_id`, `station_name`, `distance_km`, `elevation_diff_m`, disponibilidad por variable (`precip_complete_%`, `temp_complete_%`), `data_years`, `selection_status`, `selection_rank`, `selection_reason`.

**Figuras:** ninguna. La tabla HTML permite filtrar y ordenar los resultados.

---

## 🔄 weather_station (comparación) — validación de mallas con estaciones {#weather_station-compare-station-vs-grid-validation}

**Formatos:** JSON, CSV opcional, HTML y PNG opcionales

**Tablas:**

- **Indicadores de validación (JSON)** por pareja (fuente en malla, variable): `n_overlap_days`, `correlation`, `rmse`, `bias`, `mae`, `annual_total_grid`, `annual_total_station`, `pct_diff`, `wet_day_agreement_%`.
- **Comparación diaria (CSV opcional):** `date`, `grid_source`, `variable`, `station_value`, `grid_value`, `diff`, `pct_diff`, `quality_flag`.

**Figuras (PNG opcionales):**

- Comparación de las series temporales de la malla y de la estación.
- Diagrama de dispersión de los valores de la malla y de la estación.
- Diagramas de caja por variable y fuente.

---

## 🌍 climatology — normales e índices climáticos {#climatology-climatic-normals-indices}

**Formatos:** JSON, CSV por índice y PNG opcional

**Tablas:**

- **Normales mensuales de la OMM (`ltm_monthly`):** `month`, `precip_mm`, `tmax_c`, `tmin_c`, `humidity_%`, `solar_rad`, `et0_mm`.
- **Índices de sequía (`spei` / `spi`, CSV):** `date`, `spei_value` / `spi_value`, `classification` (húmedo, normal, sequía moderada, severa o extrema).
- **Estadísticas de VPD (`vpd`):** déficit mensual de presión de vapor.
- **Estrés térmico del ganado (THI, CSV):** `date`, `daily_thi`, `thi_classification` (cool / thermal_comfort / heat_stress / severe_heat_stress).
- **Estrés térmico en personas (Humidex, CSV):** `date`, `daily_humidex`, `humidex_classification` (comfortable / warm / very_warm / hot / very_hot / dangerous / extreme_caution).

**Figuras (PNG opcionales):**

- Curvas de climatología mensual.
- Series temporales de índices de sequía.
- Evolución de las categorías de estrés térmico.

---

## 🔗 compare_datasets — comparación de varias fuentes {#compare_datasets-multi-source-comparison}

**Formatos:** CSV y PNG por fuente, PNG conjunto para varias fuentes

**Tablas:**

- **`{source}_annual_timeseries.csv`:** `year`, totales o medias anuales por variable.
- **`{source}_monthly_climatology.csv`:** `month`, medias mensuales por variable.
- **Tabla de resumen en la consola:** media, mínimo, máximo, desviación estándar y coeficiente de variación por fuente.

**Figuras (PNG a 150 ppp):**

- Por fuente: `{source}_annual_timeseries.png` (tendencias anuales) y `{source}_monthly_climatology.png` (ciclo estacional).
- Varias fuentes: `multisource_annual_{variable}.png` y `multisource_monthly_climatology_{variable}.png` (curvas superpuestas).

---

## Resumen {#quick-summary}

| Módulo | Formato principal | Tablas | Figuras | Informe |
|--------|----------------|--------|---------|--------|
| **fetch_data** | CSV / JSON | Series diarias | ❌ | ❌ |
| **season_analysis** | CSV + JSON | Resumen estacional y estadísticas a largo plazo | ❌ | Texto en la consola |
| **climate_statistics** | JSON + CSV | Resúmenes sin procesar, globales, estacionales y mensuales, SPEI/SPI | ❌ | JSON y consola |
| **compare_periods** | JSON | Referencia y año de estudio, diferencias absolutas y en % | ❌ | JSON y consola |
| **calculate_hazards** | JSON | Indicadores de riesgo y categorías de estrés | ❌ | JSON y consola |
| **weather_station (descarga)** | CSV + JSON + HTML | Estaciones candidatas e indicadores de calidad | ❌ | HTML interactivo |
| **weather_station (comparación)** | JSON + CSV opcional | Indicadores de validación (correlación, RMSE, sesgo…) | ⚠️ Opcionales | JSON y HTML opcional |
| **climatology** | JSON + CSV | Normales mensuales a largo plazo e índices de sequía y calor | ⚠️ Opcionales | JSON y consola |
| **compare_datasets** | CSV por fuente y PNG | Tablas anuales y mensuales por fuente | ✅ Gráficos PNG | Estadísticas en la consola |

**Leyenda:** ❌ sin figuras · ⚠️ figuras opcionales · ✅ figuras incluidas.

<!-- source-sha256: 1f7101684228d6a8cd147ddaee6b0f58398147374f458f332be5a0bf1120eba3 -->
