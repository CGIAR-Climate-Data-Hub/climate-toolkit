# Análisis {#analysis}

## Estadísticas climáticas {#climate-statistics}

Función pública: `climate_toolkit.analyze_climate_statistics`.

Para un sitio, una fuente y un intervalo de años, calcule estadísticas estacionales, balance hídrico y medias a largo plazo. Use `fixed_season` para comparar las mismas ventanas del calendario entre años. Solicite SPI o SPEI explícitamente si los necesita. Los registros por temporada se encuentran en `season_statistics`.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.climate_statistics.statistics.analyze_climate_statistics

## Riesgos {#hazards}

Función pública: `climate_toolkit.evaluate_hazards`.

Indique el cultivo, las coordenadas y el período. La evaluación compara las condiciones estacionales con los umbrales térmicos e hídricos del cultivo. Con `fixed_season` se seleccionan las temporadas por su fecha de inicio, incluso si terminan al año siguiente.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.calculate_hazards.hazards.calculate_hazards

## Comparación de períodos {#period-comparison}

Función pública: `climate_toolkit.compare_climate_periods`.

Elija un año de estudio y un período de referencia en el mismo sitio. El resultado compara cada temporada con su referencia e indica diferencias absolutas y porcentuales cuando están disponibles.

Referencia detallada generada a partir de la documentación de Python (en inglés).

::: climate_toolkit.compare_periods.periods.compare

<!-- source-sha256: 90adf66004980a6a2d2550ccc969e75fc6d986f940a565da49b76ac87d5ff1d0 -->
