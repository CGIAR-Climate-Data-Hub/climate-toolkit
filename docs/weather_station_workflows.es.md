# Trabajar con datos de estaciones meteorológicas {#weather-station-workflows}

Estado de la guía: vigente<br>
Actualización: 2026-06-21

Esta guía explica cómo usar las observaciones de estaciones en `climate_toolkit`.

## ¿Para qué sirven los datos de estaciones? {#what-weather-station-support-is-for}

El módulo de estaciones sirve para dos tareas:

1. utilizar directamente las observaciones diarias de una estación
2. comparar las observaciones con productos históricos en malla

Este módulo **no valida** directamente las proyecciones futuras de `nex_gddp`. La evaluación de modelos de circulación general (GCM) para el futuro requiere un trabajo metodológico aparte.

## Principales puntos de entrada {#main-entry-points}

Línea de comandos:

- `climate-toolkit-weather-station-download`
- `climate-toolkit-weather-station-compare`
- `climate-toolkit-stats`
- `climate-toolkit-seasons`

API de Python:

- `climate_toolkit.download_station_data`
- `climate_toolkit.compare_station_to_grids`

## Antes de empezar {#before-you-run}

Distinga dos pares de coordenadas:

- coordenadas del sitio de estudio: `--station-lat`, `--station-lon`
- coordenadas de la estación de observación: se obtienen de la NOAA o del archivo del usuario

Tenga en cuenta lo siguiente:

- `--station-lat` y `--station-lon` identifican el sitio de estudio
- **pueden diferir** de las coordenadas de la estación seleccionada
- los límites de distancia y diferencia de altitud se calculan respecto del sitio de estudio

Datos mínimos que debe aportar según el análisis:

### Examinar estaciones candidatas o descargar datos de la NOAA {#candidate-review-or-noaa-download}

Parámetros obligatorios:

- `--station-source`
- `--station-lat`
- `--station-lon`
- `--start`
- `--end`

Parámetros que suele convenir indicar:

- `--variables`
- `--selection-mode`

### Comparar la estación con la malla {#station-vs-grid-comparison}

Parámetros obligatorios:

- `--station-source`
- `--station-lat`
- `--station-lon`
- `--start`
- `--end`
- al menos una opción `--grid-source`

Parámetros que suele convenir indicar:

- `--variables`
- `--selection-mode`
- `--selection-strategy`
- `--precip-source` y `--temp-source` si la comparación utiliza `paired` o `auto`

### Usar un archivo de estación propio {#custom-station-file-workflows}

Parámetros obligatorios:

- `--station-source custom_csv`
- `--custom-station-file`
- `--start`
- `--end`
- al menos una variable que se desea obtener

Parámetros que suele convenir indicar:

- `--custom-temp-unit`
- `--custom-precip-unit`
- `--custom-station-name`
- las coordenadas del sitio `--station-lat` y `--station-lon` si se usará la ubicación al comparar o sustituir datos más adelante

## Fuentes de observaciones {#station-backends}

`--station-source` indica de dónde se obtienen las observaciones.

### `ghcn_daily` {#ghcn_daily}

Utiliza únicamente GHCN-Daily de la NOAA.

Conviene para:

- la precipitación diaria
- las temperaturas mínimas y máximas diarias, cuando estén disponibles

### `gsod` {#gsod}

Utiliza únicamente GSOD de la NOAA.

Conviene para:

- obtener mayor cobertura de temperaturas diarias en algunas regiones
- obtener más años de datos coincidentes en algunas estaciones de aeropuerto

### `auto` {#auto}

Clasifica las estaciones de ambos archivos de la NOAA y devuelve las mejores candidatas según los criterios vigentes.

Conviene para:

- una primera exploración
- sitios con poca cobertura en uno de los archivos de la NOAA

### `custom_csv` {#custom_csv}

Utiliza un archivo CSV o JSON aportado por el usuario.

Conviene para:

- las mediciones de estaciones locales
- los datos de socios que no figuran en los archivos de la NOAA
- la sustitución de valores históricos por observaciones

## Modos de selección {#selection-modes}

`--selection-mode` determina cómo se tratan las estaciones candidatas.

### `list` {#list}

Permite examinar las candidatas sin descargar observaciones.

Este modo:

- clasifica las estaciones
- calcula la proporción de datos disponibles para cada variable
- guarda los archivos de revisión de candidatas si se indica `--report-prefix`
- se detiene antes de la selección automática habitual

Úselo para:

- examinar primero las estaciones cercanas
- obtener el mapa y los archivos CSV y JSON para revisarlos

### `specified` {#specified}

Indique el identificador exacto de la estación mediante `--station-id`.

Úselo para:

- usar una estación de la NOAA cuyo identificador ya conoce

### `auto` {#auto_1}

El programa selecciona las mejores estaciones que cumplen los criterios.

Úselo para:

- seleccionar automáticamente la mejor estación según las reglas vigentes
- aplicar los mismos criterios en cada ejecución

## Número de estaciones seleccionadas automáticamente {#auto-selection-scope}

`--auto-select` controla cuántas estaciones puede conservar el programa.

Valores admitidos:

- `auto-1`
- `auto-2`
- `auto-3`
- `auto-<n>`
- `auto-all`

Comportamiento que conviene conocer:

- `auto-all` también respeta el límite `--max-auto-stations`
- el valor predeterminado de `--max-auto-stations` es `10`
- `auto-1` selecciona la mejor estación que cumple los criterios
- `auto-2` y los valores superiores permiten comparar varias estaciones

## Estrategia de selección para la comparación {#compare-selection-strategy}

`climate-toolkit-weather-station-compare` también admite `--selection-strategy`.

### `all_vars_single_station` {#all_vars_single_station}

Una misma estación debe proporcionar todas las variables solicitadas.

Conviene para:

- una interpretación más sencilla
- una comparación entre una estación y una celda de la malla

Limitación:

- puede descartarse una estación útil para precipitación si carece de temperaturas

### `best_per_variable` {#best_per_variable}

El programa puede utilizar una estación distinta para cada variable.

Ejemplo:

- una estación para la precipitación
- otra para las temperaturas mínimas y máximas

Conviene para:

- las zonas con poca cobertura
- los casos en que ninguna estación tiene todas las variables

Limitación:

- la interpretación es más compleja porque los indicadores proceden de varias estaciones físicas

## Criterios de selección predeterminados {#default-guardrails}

Se aplican los siguientes criterios predeterminados:

- radio de búsqueda: `50 km`
- diferencia máxima de altitud: `500 m`
- fracción mínima de datos disponibles: `0.70`
- máximo de estaciones seleccionadas automáticamente: `10`
- máximo de candidatas retenidas: `10`
- máximo de estaciones evaluadas: `25`

La disponibilidad se evalúa **para cada variable**. Una puntuación global por estación es insuficiente.

Por ejemplo, si solicita:

- `precipitation,max_temperature,min_temperature`

El programa comprueba si cada variable solicitada alcanza el umbral de disponibilidad.

## Flexibilización de los criterios {#guard-relaxation-behavior}

Umbral estricto de disponibilidad aplicado por defecto:

- `0.70`

Si ninguna estación cumple el criterio, el programa reduce progresivamente el umbral:

- `0.50`
- `0.30`
- `0.10`

Si ninguna estación cumple todavía los criterios para todas las variables, el programa puede recurrir a candidatas que solo cubran algunas, cuando se permita esa opción.

Consecuencias:

- según el análisis y las variables solicitadas, `auto` puede seleccionar una estación útil que solo mida precipitación o solo temperatura
- el modo `list` suele ser la mejor manera de ver qué estaciones cumplen cada criterio

## Altitud del sitio de referencia {#anchor-elevation}

El programa puede estimar la altitud del sitio de estudio mediante un modelo digital de elevación (MDE).

Objetivos:

- comparar la altitud de cada candidata con la del sitio de estudio
- aplicar el límite `--max-elevation-diff-m`

Opciones:

- `--target-elevation-m`: indicar directamente una altitud conocida
- `--no-auto-anchor-elevation`: desactivar la consulta automática del MDE

Si la consulta automática no está disponible:

- el programa continúa sin aplicar el filtro de altitud
- el terminal informa de este cambio

## Revisar las estaciones candidatas {#candidate-review-workflow}

Primer paso recomendado:

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nairobi_auto_candidates \
  --open-report
```

Archivos generados:

- CSV
- JSON
- Mapa HTML

El mapa de candidatas muestra:

- las coordenadas del sitio de estudio
- las estaciones candidatas cercanas
- las líneas de distancia entre el sitio y las estaciones
- la posición en la clasificación
- las estaciones, con símbolos proporcionales a la disponibilidad de datos
- el número de estaciones por fuente y el alcance de la búsqueda

Limitación del mapa base:

- el mapa base utiliza teselas en línea y necesita conexión a Internet

Este mapa facilita la revisión visual y no constituye un producto SIG:

- úselo para una primera revisión rápida
- para consultarlo de nuevo, abra el archivo HTML guardado
- el tamaño de los símbolos refleja la disponibilidad de datos
- el mapa indica el sitio de estudio, la posición de cada candidata, su distancia y su fuente

## Descargar las observaciones {#download-workflow}

Ejemplo:

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --stage preprocessed
```

Opciones útiles:

- `--stage raw`
- `--stage transformed`
- `--stage preprocessed`
- `--station-id ...` con `--selection-mode specified`
- `--disable-completeness-guard`
- `--refresh-cache`

Significado de las etapas:

- `raw`: valores y nombres más próximos a los de origen
- `transformed`: unidades y nombres armonizados
- `preprocessed`: se aplican la depuración y los controles de calidad

Resumen de los datos descargados de la NOAA:

- el terminal indica las estaciones seleccionadas, su distancia, altitud y la disponibilidad de cada variable
- el modo de lista muestra las candidatas en lugar de las observaciones diarias
- `--output` permite guardar un archivo de resultados

## Archivos de estaciones del usuario {#custom-station-files}

Ejemplo:

```bash
climate-toolkit-weather-station-download \
  --station-source custom_csv \
  --custom-station-file path/to/station.csv \
  --custom-station-name "My station" \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Tipos de archivo admitidos:

- `.csv`
- `.json`

Datos mínimos:

- `date`
- al menos una variable climática solicitada

También se aceptan los siguientes nombres de variables:

- precipitación:
  - `precipitation`
  - `precip`
  - `rain`
  - `rainfall`
  - `prcp`
- temperatura máxima:
  - `max_temperature`
  - `tmax`
  - `max`
- temperatura mínima:
  - `min_temperature`
  - `tmin`
  - `min`
- temperatura media:
  - `mean_temperature`
  - `tmean`
  - `tavg`
  - `temp`
- humedad:
  - `humidity`
  - `relative_humidity`
  - `rh`
- viento:
  - `wind_speed`
  - `wind`
  - `wdsp`
- radiación solar:
  - `solar_radiation`
  - `solar`
  - `radiation`

Columnas de metadatos opcionales:

- `station_id`
- `station_name`
- `station_lat`
- `station_lon`
- `station_elevation_m`

Si faltan metadatos:

- el programa completa los valores en la medida de lo posible con los parámetros de la línea de comandos y el nombre del archivo

Unidades:

- `--custom-temp-unit c|f|k`
- `--custom-precip-unit mm|inch|tenth_mm`

Tipos de archivo admitidos:

- `.csv`
- `.json`

Tratamiento:

- normalización de las columnas
- lectura de fechas y recorte al período solicitado
- conversión de unidades
- cálculo de la temperatura media si falta y se dispone de Tmin y Tmax
- almacenamiento del resultado normalizado en caché para reutilizarlo

Si faltan metadatos en el archivo propio:

- `station_id` toma el identificador indicado en la línea de comandos o el nombre del archivo sin extensión
- `station_name` toma el nombre indicado o el nombre del archivo sin extensión
- se pueden usar las coordenadas del sitio indicadas en la línea de comandos
- la altitud puede quedar sin especificar

Si el archivo no contiene filas dentro del período solicitado:

- la descarga devuelve un error
- los análisis históricos usan los valores de la malla y muestran una advertencia

## Comparar la estación con la malla {#station-vs-grid-comparison_1}

Ejemplo:

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --selection-mode auto \
  --auto-select auto-1 \
  --selection-strategy all_vars_single_station \
  --grid-source paired \
  --grid-source nasa_power \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid_2011_2020.json
```

Objetivos actuales de la comparación:

- comparar las observaciones de estaciones con productos climáticos históricos en malla
- determinar qué fuente en malla parece más representativa del sitio

Fuera del alcance actual:

- validación directa de proyecciones futuras de los modelos de circulación general
- evaluación directa de `nex_gddp` con estaciones desde esta interfaz de línea de comandos

### Familias de productos en malla admitidas {#supported-grid-source-family}

La comparación histórica admite, entre otros, los siguientes productos en malla y reanálisis:

- `era5_land`
- `era_5`
- `nasa_power`
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `chirts_era5` (Tmax y Tmin)
- `imerg`
- `paired`
- `auto`
- `terraclimate`

Fuentes excluidas de la comparación:

- `nex_gddp`
- los propios archivos de estaciones
- `tamsat`

### Independencia de la validación {#independence-caveat}

Algunos productos en malla incorporan observaciones de estaciones.

Ejemplos:

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `chirts_era5` y el producto anterior `chirts`
- `paired` si una de las fuentes combinadas utiliza observaciones de estaciones
- `terraclimate`

Una buena concordancia **no garantiza** la independencia de la validación.

Para una comparación histórica más independiente se suelen considerar:

- `era5_land`
- `era_5`
- `nasa_power`
- `imerg`

El programa avisa cuando la validación de una fuente no es totalmente independiente.

Elección práctica de fuentes:

- dé prioridad a `nasa_power`, `era5_land`, `era_5` o `imerg` si la independencia es prioritaria
- use `paired` para evaluar un análisis histórico en condiciones de uso cuando no se requiere independencia estricta
- si los componentes incorporan observaciones de estaciones, una buena clasificación de `paired` no constituye una prueba independiente

## Resultados de la comparación {#comparison-outputs}

Los resultados en texto o JSON pueden incluir:

- resumen de estaciones
- fallos en la descarga de productos en malla
- indicadores diarios por estación
- indicadores mensuales agregados
- indicadores estacionales agregados
- resumen de la coincidencia temporal anual
- indicadores globales agrupados cuando intervienen varias estaciones
- índices anuales de precipitación de referencia de xclim si hay suficientes fechas coincidentes
- reglas de clasificación por caso de uso para una evaluación inicial

### Interpretar los resultados {#how-to-read-them}

Indicadores diarios:

- útiles para evaluar las fechas de los eventos y la ocurrencia de días de lluvia
- la correlación de la precipitación diaria suele ser baja incluso si el producto sigue siendo útil

Indicadores mensuales y estacionales:

- suelen ser más informativos para evaluar la aptitud climática y planificar
- más adecuados para detectar sesgos sistemáticos hacia condiciones demasiado húmedas o secas

Resumen anual:

- solo es útil si la cobertura de fechas coincidentes es suficiente
- si hay pocas fechas coincidentes, los resultados son descriptivos y su capacidad de validación es limitada

Índices anuales de precipitación de referencia de xclim:

- se calculan únicamente si la cobertura común permite una estimación anual defendible
- se omiten si hay demasiadas lagunas en el período común con la estación

Opciones útiles para la comparación:

- `--wet-day-threshold-mm`: cambia el umbral utilizado al evaluar los aciertos en la detección de días de lluvia
- `--min-overlap-days`: con menos días coincidentes, los indicadores se marcan como de baja confianza
- `--report-prefix`: guarda también los archivos de revisión de candidatas durante la comparación
- `--open-report`: intenta abrir automáticamente el informe HTML de candidatas

Precaución al interpretar:

- con `best_per_variable`, los indicadores de precipitación y temperatura pueden proceder de estaciones distintas
- revise el resumen de estaciones antes de clasificar los productos

## Sustituir datos históricos por observaciones {#historical-override-workflow}

Un archivo de estación puede sustituir valores de variables históricas seleccionadas en:

- `climate-toolkit-stats`
- `climate-toolkit-seasons`

Ejemplo:

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=era5_land \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation,max_temperature,min_temperature \
  --custom-station-name "My station" \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Funcionamiento actual:

- las observaciones sustituyen los valores históricos seleccionados en las fechas correspondientes
- se mantienen los valores de la malla para las variables ausentes del archivo de estación
- si el archivo no contiene filas dentro del período solicitado, el programa usa los valores en malla y muestra una advertencia

Alcance actual de la sustitución:

- solo análisis históricos
- sin sustitución directa para proyecciones futuras de `nex_gddp`
- especialmente útil si la estación proporciona una o dos variables fiables y los datos en malla pueden completar las demás

## Organización de la caché {#cache-layout}

Directorios raíz de la caché local del proyecto:

- `outputs/cache/weather_stations/ghcn_daily`
- `outputs/cache/weather_stations/gsod`
- `outputs/cache/weather_stations/custom`
- `outputs/cache/weather_stations/dem_anchor`

Contenido habitual:

- metadatos e inventarios de estaciones
- archivos de estaciones descargados de la NOAA
- archivos CSV propios tras la normalización
- manifiestos JSON de los datos de estaciones propias
- altitudes de los sitios obtenidas del MDE

Ubicaciones detalladas:

- índices de metadatos GHCN en `outputs/cache/weather_stations/ghcn_daily/index`
- archivos de estaciones GHCN en `outputs/cache/weather_stations/ghcn_daily/stations`
- historial de estaciones GSOD y archivos anuales en `outputs/cache/weather_stations/gsod`
- archivos propios normalizados en subdirectorios identificados por una huella en `outputs/cache/weather_stations/custom`
- caché de altitudes de referencia del MDE en subdirectorios versionados de `outputs/cache/weather_stations/dem_anchor`

Caché de archivos propios:

- el programa calcula una huella a partir de la ruta, el tamaño y la fecha de modificación del archivo fuente
- cada archivo propio tiene un directorio de caché independiente
- se reutilizan los resultados CSV y JSON para la misma etapa y el mismo período salvo que se active `--refresh-cache`

Efecto de `--refresh-cache`:

- fuerza una nueva descarga o regeneración cuando el análisis lo admite
- útil después de cambiar el código, si una ejecución quedó incompleta o si los resultados locales están desactualizados
- innecesario para repetir un análisis normal con la caché existente

## Orden práctico de las operaciones {#practical-workflow-order}

Secuencia recomendada:

1. ejecute `selection-mode list`
2. revise el mapa, el CSV y la disponibilidad por variable
3. decida si conviene usar una o varias estaciones
4. ejecute `weather-station-download` o `weather-station-compare`
5. solo entonces, si procede, use sus observaciones para sustituir valores históricos

Para tomar la decisión:

1. empiece con `--selection-mode list`
2. revise la disponibilidad **para cada variable**
3. determine si basta con una estación
4. si no basta, determine si `best_per_variable` es aceptable
5. desactive el filtro de disponibilidad solo en análisis exploratorios y manténgalo para los informes habituales

## Limitaciones actuales {#current-limitations}

- cobertura escasa de estaciones en algunas regiones
- ningún archivo proporciona cobertura diaria mundial completa
- en algunos sitios hay suficientes registros de precipitación y pocos de temperatura, o viceversa
- la comparación se aplica a productos históricos y excluye las proyecciones futuras de NEX-GDDP
- el modo automático se limita a las fuentes NOAA admitidas y a los archivos propios
- el mapa HTML facilita la revisión visual; un análisis SIG completo requiere otras herramientas
- elegir una estación por variable mejora la cobertura pero complica la interpretación

## Problemas frecuentes {#common-failure-modes}

`Error: No ... station passed per-variable completeness threshold`

- empiece con `--selection-mode list`
- aumente `--max-distance-km`
- solicite menos variables
- reduzca `--min-completeness-ratio`
- considere `best_per_variable`

`Anchor elevation unavailable; continuing without elevation guard`

- Consulta de altitud del MDE en Earth Engine no disponible
- indique `--target-elevation-m` si conoce la altitud del sitio
- o autentíquese en Earth Engine e indique un `GCP_PROJECT_ID` válido

`Project 'projects/your-ee-project-id' not found or deleted`

- El entorno aún contiene un identificador de proyecto de Earth Engine de ejemplo
- sustitúyalo por el identificador real del proyecto

`Custom station file has no rows in requested window`

- compruebe la lectura de las fechas
- compruebe los valores solicitados para `--start` y `--end`
- compruebe la coherencia de las zonas horarias y del formato de fechas del archivo

`Skipped xclim annual precipitation reference indices ... overlap is too gappy`

- hay muy pocas fechas coincidentes para obtener índices anuales de referencia fiables
- dé más peso a los resúmenes mensuales o estacionales para esa combinación de estación y producto

## Ejemplos prácticos breves {#minimal-worked-examples}

### 1. Descubrir estaciones cercanas y guardar el mapa {#1-discover-nearby-stations-and-save-map}

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --report-prefix outputs/weather_station/nairobi_candidates \
  --open-report
```

### 2. Comparar una estación seleccionada con dos productos en malla {#2-compare-one-selected-station-against-two-grid-products}

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --grid-source nasa_power \
  --grid-source paired \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid.json
```

### 3. Sustituir la precipitación histórica por observaciones propias {#3-override-historical-precipitation-with-custom-observed-data}

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=era5_land \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation \
  --custom-precip-unit mm
```

## Archivos relacionados {#related-files}

- `README.md`
- `analysis/weather_station_module_design_2026-06-15.md`
- `analysis/weather_station_data_access_research_2026-06-15.md`
- `analysis/issues/weather_station_compare_window_guidance.md`

<!-- source-sha256: 50cb70c6e72ac3421887dd577c98ff7da1605c6f212352b440e3c3175125770b -->
