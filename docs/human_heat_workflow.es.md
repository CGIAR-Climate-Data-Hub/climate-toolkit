# Evaluar el estrés térmico en personas {#human-heat-workflow}

Para esta primera evaluación, el programa calcula el índice `Humidex` con `xclim`.

El alcance es más limitado que el de una evaluación completa de la exposición al calor en el trabajo o al aire libre.

## Elección para la primera fase {#phase-1-choice}

Indicador elegido:
- `humidex`

Trabajo pospuesto:
- `WBGT`
- `UTCI`
- evaluaciones más detalladas de la exposición laboral al calor

## ¿Por qué empezar con `humidex`? {#why-humidex-first}

- solo requiere la temperatura y la humedad o el punto de rocío
- ya está disponible mediante `xclim` en el programa
- se ajusta mejor a las variables disponibles que `WBGT` o `UTCI`
- se puede usar en algunas proyecciones de `nex_gddp` si se dispone de `hurs`

## ¿Por qué posponer `WBGT`? {#why-not-wbgt-first}

El índice `WBGT` es importante, pero el programa aún no trata el viento y la radiación de manera coherente en todos los análisis históricos y futuros previstos.

## ¿Por qué posponer `UTCI`? {#why-not-utci-first}

El índice `UTCI` incorpora más procesos físicos. Para calcularlo se necesitan los siguientes datos:
- temperatura
- humedad
- viento
- temperatura radiante media o componentes de la radiación

Algunas fuentes históricas proporcionan estos datos, pero su disponibilidad no es uniforme para las proyecciones previstas.

## Fuentes compatibles {#source-support}

Fuentes adecuadas para esta primera evaluación:
- `era5_land`
- `nasa_power`
- `ghcn_daily` si hay datos de humedad
- `gsod` si hay datos de humedad
- `custom_station` si hay datos de humedad o de punto de rocío
- `paired`
  - si la fuente de temperatura aporta también la humedad o el punto de rocío
- `auto`
  - si la fuente de temperatura seleccionada aporta la humedad o el punto de rocío

Compatibilidad condicionada:
- `nex_gddp`
  - solo si Earth Engine dispone de la variable `hurs` para el modelo, el escenario y el período seleccionados

Fuentes actualmente inadecuadas:
- `era_5`
  - la vía de acceso actual no garantiza la disponibilidad de la humedad
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts_era5` (solo Tmax y Tmin) y el producto anterior `chirts`

## Funciones auxiliares disponibles {#current-helper-surface}

Funciones de Python:
- `climate_toolkit.climatology.build_human_heat_source_bundle`
- `climate_toolkit.climatology.compute_daily_humidex`
- `climate_toolkit.climatology.summarize_humidex_period`
- `climate_toolkit.climatology.describe_human_heat_method`
- `climate_toolkit.climatology.describe_human_heat_source_support`

Uso en los módulos:
- `climate_statistics`
  - añade un bloque opcional `human_heat_stress` si hay datos de humedad o de punto de rocío
- `compare_periods`
  - calcula las diferencias de los indicadores `human_heat_stress` si se puede calcular el humidex tanto en el período de referencia como en el de estudio
- `calculate_hazards`
  - genera una evaluación orientativa del humidex y recuentos de días si hay datos de humedad

## Limitaciones actuales {#current-limits}

- las categorías de humidex sirven para una evaluación preliminar y no constituyen pautas médicas ni de salud laboral
- no se afirma que `humidex` sea el mejor indicador de estrés térmico humano en todos los contextos

## Próximos pasos previstos {#likely-next-steps}

1. decidir qué enfoque utilizar en la segunda fase:
   - `WBGT`
   - `UTCI`
   - una combinación según las variables que ofrezca cada fuente
2. documentar los métodos y las condiciones de uso de las fuentes para distinguir la evaluación preliminar mediante humidex de una evaluación completa de la exposición mediante WBGT

<!-- source-sha256: 9fc411b38a405dfd4741a712be7681216a27aff6f7c2f99665651cf4a145e76b -->
