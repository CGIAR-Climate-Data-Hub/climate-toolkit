# Comparación y validación {#comparison-validation}

## Comparar fuentes en malla {#compare-gridded-sources}

Función pública: `climate_toolkit.compare_climate_sources`.

Indique una lista de fuentes, un sitio y un período común. El resultado asocia cada fuente con su DataFrame diario. Pase este diccionario a `print_report` para comparar las series.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.compare_datasets.compare_datasets.compare_sources

## Descargar observaciones de estaciones {#download-station-data}

Función pública: `climate_toolkit.download_station_data`.

Indique las coordenadas, las fechas y una fuente de observaciones. Use `selection_mode="list"` para revisar la clasificación de estaciones candidatas. La selección automática o por identificador devuelve observaciones diarias. Los archivos públicos de la NOAA se consultan sin credenciales de Earth Engine.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.weather_station.download.download_station_data

## Validar productos en malla con estaciones {#validate-grids-against-stations}

Función pública: `climate_toolkit.compare_station_to_grids`.

Indique la fuente de observaciones y los productos históricos en `grid_sources`. La comparación empareja por fecha las observaciones y los valores de la malla. Consulte `metrics` para conocer los días coincidentes, el sesgo, el error absoluto medio (MAE), la raíz del error cuadrático medio (RMSE) y la correlación. En `grid_failures` figuran las fuentes que no pudieron descargarse. Un producto que incorpore observaciones puede haber utilizado los datos de la estación de validación.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.weather_station.compare.compare_station_to_grids

<!-- source-sha256: 3b38ac7ceec93e28676ba8ef94529b4ac9104bd5ce713a561b3f4ac98421cd06 -->
