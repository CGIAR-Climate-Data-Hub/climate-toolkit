# Evaluar el estrés térmico del ganado con el THI {#livestock-thi-workflow}

Estado: método operativo vigente<br>
Actualización: 2026-06-24

Esta guía explica cómo se evalúa el estrés térmico del ganado mediante el `THI` diario (índice de temperatura y humedad).

## Funciones disponibles {#what-toolkit-does-now}

El programa ofrece actualmente:

- el `THI` diario para el ganado
- la categoría de estrés correspondiente al THI de cada día
- resúmenes por período que incluyen:
  - THI medio
  - THI máximo
  - número de días por categoría de estrés
  - número total de días de estrés
- integración en la evaluación de riesgos mediante `calculate_hazards`

La metodología del THI **sigue en revisión**. Esta implementación corresponde a la incidencia `#30`. Quedan pendientes la revisión de los umbrales y otras mejoras para el ganado.

## Fórmula actual {#current-formula}

El programa aplica la fórmula siguiente:

`THI = (1.8*T + 32) - ((0.55 - 0.0055*RH) * ((1.8*T) - 26))`

donde:

- `T` es la temperatura media diaria del aire de bulbo seco, en grados Celsius
- `RH` es la humedad relativa diaria expresada en porcentaje

Criterio predeterminado:

- calcular el THI con la temperatura media y la humedad relativa
- no usar por defecto la temperatura máxima en esta etapa

Motivos:

- en la literatura sobre proyecciones para el ganado, el THI basado en temperatura diaria y humedad relativa cuenta actualmente con mayor respaldo
- este método se ajusta mejor a los datos de humedad disponibles en las fuentes históricas y futuras
- la humedad disponible no siempre corresponde a la hora de `Tmax`. Usar `Tmax` sin considerar ese desfase puede exagerar o distorsionar el estrés estimado

## Selección de la temperatura {#temperature-input-rule}

El programa determina la temperatura en este orden:

1. columna explícita de temperatura media, si existe
2. otros nombres reconocidos para la media: `mean_temperature`, `tavg`, `tmean`, `temperature`, `temp`
3. en su defecto, media diaria calculada como `(tmax + tmin) / 2`

El programa **no ofrece** un método predeterminado independiente basado en la temperatura máxima diaria. Esta posibilidad sigue en estudio.

## Humedad necesaria {#humidity-requirement}

El THI requiere la humedad relativa diaria en porcentaje.

Condiciones actuales:

- intervalo válido de humedad: `0..100`
- si falta la humedad no se puede calcular el THI
- no se admiten proyecciones sin una fuente fiable de humedad

## Selección del perfil climático {#climate-profile-logic}

Perfiles disponibles:

- `auto`
- `temperate`
- `tropical`

Funcionamiento de `auto`:

- usar primero la latitud
- en la franja tropical (`|lat| <= 23.5`), a partir de `1500 m` de altitud, usar el perfil templado como aproximación para las tierras altas
- las tierras bajas tropicales conservan el perfil tropical

La altitud puede obtenerse de:

- un valor indicado por el usuario
- un modelo digital de elevación (MDE), si la consulta está habilitada

## Perfiles ganaderos {#livestock-profiles}

Perfiles incluidos actualmente:

- `cattle_dairy`
- `cattle_general`
- `cattle_beef`
- `goats`
- `sheep`
- `pigs`
- `poultry_broilers`
- `poultry_layers`
- `poultry_general`

Origen de los umbrales:

- Thornton et al. (2021), tabla 1, para los umbrales operativos de base
- Thornton et al. (2021), tabla 2, para ajustar el umbral extremo en climas tropicales cuando corresponde

Tenga en cuenta lo siguiente:

- los valores predeterminados sirven para una evaluación preliminar y no describen la fisiología de cada raza
- el programa combina umbrales por grupo de animales con una regla sencilla para el contexto tropical o de tierras altas
- algunos umbrales y orientaciones de interpretación podrían cambiar

## Limitaciones por raza y sistema de producción {#breed-and-production-context-limits}

Estos resultados sirven para detectar indicios de estrés térmico y no constituyen un diagnóstico veterinario.

Limitaciones actuales:

- un mismo perfil bovino **no distingue** entre Bos indicus, Bos taurus, Sanga y bovinos cruzados
- el programa **no deduce** la adaptación de una raza a partir de la genética, el pelaje, el tamaño corporal o el sistema de manejo
- la regla `auto` es solo una aproximación geográfica basada en la latitud y la altitud
- los umbrales pueden no ser transferibles entre razas adaptadas localmente, sistemas de producción o condiciones de manejo

Orientaciones para la interpretación:

- use las categorías predeterminadas para una primera evaluación
- si el proyecto dispone de umbrales específicos para la raza u orientaciones veterinarias, dé prioridad a esos umbrales personalizados
- documente cualquier cambio en los resultados o en una nota metodológica

Situaciones que requieren mayor cautela:

- sistemas lecheros tropicales con ganado cruzado
- bovinos africanos adaptados localmente y poco representados por los perfiles generales de leche o carne
- sistemas de tierras altas donde la exposición climática y la adaptación genética pueden diferir

Consultar el método en Python:

```python
from climate_toolkit.climatology import describe_thi_method

method = describe_thi_method()
print(method["profiles"]["cattle_dairy"])
print(method["profiles"]["pigs"])
```

## Fuentes compatibles {#source-support}

Fuentes admitidas actualmente:

- `era5_land`
  - humedad calculada a partir del punto de rocío y la temperatura del aire durante la descarga
- `nasa_power`
  - humedad disponible mediante el acceso actual a POWER
- `ghcn_daily`
  - si la estación elegida proporciona humedad durante el período solicitado
- `gsod`
  - si la estación elegida proporciona humedad durante el período solicitado
- `custom_station`
  - si el archivo aportado contiene una columna de humedad relativa
- `nex_gddp`
  - siempre que `hurs` esté disponible en Earth Engine para el modelo, el escenario y el período elegidos

Disponibilidad incierta o limitada:

- `era_5`
  - la configuración actual de descarga de ERA5 no define una banda de humedad para el cálculo operativo del THI
  - considere incierta esta vía hasta que se integre explícitamente y se compruebe su funcionamiento

Fuentes no admitidas:

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts_era5` (solo Tmax y Tmin) y el producto anterior `chirts`

Consultar el método en Python:

```python
from climate_toolkit.climatology import describe_thi_method, describe_thi_source_support

print(describe_thi_source_support())
print(describe_thi_method()["source_support"]["nex_gddp"])
```

## Interfaz de línea de comandos {#cli-surface}

Varios análisis ofrecen opciones para el THI del ganado:

- `climate-toolkit-seasons`
- `climate-toolkit-stats`
- `climate-toolkit-periods`
- `climate-toolkit-periods-ensemble`
- `climate-toolkit-hazards`
- variantes de conjuntos de modelos correspondientes

Argumentos principales:

- `--livestock-type`
- `--livestock-climate-profile`
- `--livestock-elevation-override-m`

Ejemplo:

```bash
climate-toolkit-periods-ensemble \
  --location="-1.286,36.817" \
  --baseline-start=1995 \
  --baseline-end=2013 \
  --future-start=2041 \
  --future-end=2060 \
  --scenarios=ssp245 \
  --fixed-season="03-01:05-31" \
  --livestock-type cattle_dairy \
  --livestock-climate-profile auto
```

## Personalizar los umbrales {#threshold-override-path}

Las categorías predeterminadas de THI dependen del perfil ganadero y del contexto climático.

El análisis de riesgos permite sustituir estos umbrales mediante `--thresholds-file`.

Así puede definir categorías de riesgo por THI distintas de las predeterminadas para ese tipo de animal.

Fragmento JSON:

```json
{
  "THI": {
    "none": [null, 70],
    "mild": [70, 76],
    "moderate": [76, 84],
    "severe": [84, null]
  }
}
```

Ejemplo de uso:

```bash
climate-toolkit-hazards \
  --crop maize \
  --location="-1.286,36.817" \
  --date-from 2020-03-01 \
  --date-to 2020-05-31 \
  --source paired \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --livestock-type cattle_dairy \
  --thresholds-file custom_thresholds.json
```

Tenga en cuenta lo siguiente:

- esta sustitución cambia las categorías usadas para evaluar el riesgo
- no modifica la fórmula del THI
- documente los umbrales personalizados, ya que difieren de los valores operativos del paquete

## Cuestiones pendientes {#still-open}

Trabajo pendiente para `#30`:

1. contrastar los umbrales con más publicaciones y decidir si conviene conservarlos
2. decidir si conviene añadir una variante de evaluación por temperatura máxima además del THI basado en temperatura media
3. mejorar el tratamiento de las proyecciones de humedad más allá de los límites documentados para `hurs`
4. ampliar las orientaciones para interpretar los resultados según la especie y la raza

<!-- source-sha256: 10698da7de75290e8a438b7f861999bd878a5f7f78c7c1c0ac4636f80054af45 -->
