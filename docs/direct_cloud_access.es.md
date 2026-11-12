# Acceso directo a los datos y proveedores alternativos {#direct-cloud-access-and-provider-fallback}

Referencia: [arquitectura del paquete](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/package_architecture_summary.md). El desarrollo se documenta en [#176](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/176), [#177](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/177) y [#178](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/178).

## Instalar y descargar {#install-and-fetch}

El acceso directo requiere **Python 3.12 o posterior** y las dependencias opcionales de la nube:

```sh
pip install 'climate-toolkit[cloud]'
# Desde una copia del repositorio:
uv sync --extra cloud
```

El paquete base sigue siendo compatible con Python 3.10 o posterior. En versiones anteriores a 3.12, las solicitudes directas indican este requisito. Las vías de GEE configuradas explícitamente siguen disponibles.

```python
from datetime import date
import climate_toolkit as ct

rain = ct.fetch_climate_data(
    "chirps_v3_daily_rnl",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
temperature = ct.fetch_climate_data(
    "chirts_era5",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
print(rain.attrs["data_provenance"])
```

Con `sites=[("Nairobi", -1.286, 36.817), ...]` o `sites_csv=...` se aplican las mismas reglas de selección del proveedor. Las lecturas diferidas de puntos se agrupan por bloques de almacenamiento compartidos. `workers` limita la concurrencia (de 1 a 8 en el acceso directo).

## Productos y proveedores {#products-and-providers}

| Fuente | Orden de selección automática | Comprobación de la cobertura |
| --- | --- | --- |
| `chirps_v3_daily_rnl` | Caché compatible completa, producto definitivo de Dynamical, Hugging Face y por último GEE si está permitido | Fechas disponibles: se requiere todo el período solicitado |
| `chirts_era5` | Caché completa y después Hugging Face | Fechas disponibles: el archivo alojado empieza en 1981 |

Dynamical consumió menos ancho de banda en todas las configuraciones de CHIRPS de un año evaluadas. Para Nairobi en 2020, Dynamical transfirió 3,39 MB en 20 solicitudes y Hugging Face 21,54 MB en 26 solicitudes. En ambos casos, repetir la consulta desde la caché no generó solicitudes remotas. En la validación, el archivo definitivo de Dynamical también cubría fechas más recientes. Hugging Face puede ser más rápido para períodos cortos. Véanse las [mediciones de transferencia de CHIRPS](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirps-http-benchmark-2026-11-09) para cargas mayores y límites. Si es necesario, seleccione `backend="huggingface"` o `backend="dynamical"`: una elección explícita impide el cambio automático de proveedor.

Ambos adaptadores CHIRPS leen la **v3 definitiva/RNL**. El producto preliminar de Dynamical es SAT y queda excluido. Ni CHIRPS v2 ni ningún otro producto de precipitación se usa como espejo alternativo.

Dynamical almacena una tasa media diaria de precipitación que el adaptador convierte en mm/día. Para Hugging Face, xarray aplica una sola vez la escala de decodificación CF. Los espejos redondean de forma distinta: tenga en cuenta el error de cuantificación documentado, especialmente al contar días que alcanzan un umbral. Cada solicitud devuelve datos de una sola revisión de un proveedor, sin combinar días de proveedores distintos.

Para CHIRPS v3 se compararon 543 valores diarios por espejo con la malla nativa de Earth Engine en Nairobi, Uagadugú y Cusco, de diciembre a febrero de 2019/20 y 2025/26. Las diferencias diarias máximas, redondeadas hacia arriba, fueron de 0,041 mm para Dynamical y 0,050 mm para Hugging Face. Con el umbral estricto de `>1 mm`, la clasificación de días de lluvia difirió en cero y tres observaciones sitio-día, respectivamente. En comparaciones sensibles al umbral, seleccione un único proveedor y registre su revisión junto con los resultados. Véanse la [comparación de referencia y las instrucciones para reproducirla](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirps-finalrnl-reference-comparison-2026-11-08).

Use CHIRTS-ERA5 para nuevos análisis de temperatura. La clave anterior `chirts` (CHIRTS-daily, 1983–2016) está **en desuso** y genera una advertencia. Su adaptador sigue disponible mediante selección explícita para reproducir resultados anteriores. La alternativa automática ahora utiliza CHIRTS-ERA5. Las claves y cachés existentes conservan su identidad y no se combinan. El atajo `chirps_v2+chirts` mantiene su significado histórico.

CHIRTS-ERA5 amplía la cobertura temporal sin garantizar una mayor exactitud en cada sitio. El productor publica los datos de seguimiento con unos cinco días de retraso y el espejo puede tardar más. Tanto CHIRTS-daily como CHIRTS-ERA5 usan información de ERA5, pero se construyen de forma distinta. La migración implica más que cambiar el alojamiento de los archivos.

El [espejo de Hugging Face](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily) almacena Tmax y Tmin en incrementos de 0,1 °C. El recuento de días calurosos utiliza la temperatura decodificada e incluye los días en que Tmax alcanza exactamente 35 °C (NTx35) o 40 °C (NTx40). Por ejemplo, una Tmax original de 34,96 °C se redondea a 35,0 °C y cuenta para NTx35 en el espejo. Las medias estacionales también usan los valores decodificados.

Antes de aplicar umbrales absolutos, compruebe el sesgo respecto de una estación local. En las fechas coincidentes de 1994–95 y 2023–24, las mínimas diarias de CHIRTS-ERA5 superaron en promedio las de la estación de Nairobi entre 3,2 y 4,3 °C y las de Cusco entre 3,3 y 3,8 °C. En Uagadugú, en 2023–24, la malla omitió 30 de los 349 días en que la estación alcanzó o superó los 35 °C y añadió seis falsos positivos. La cobertura de las observaciones depende del sitio y de la variable.

Prevea el ancho de banda necesario para series largas. En Nairobi, la primera lectura de treinta años de Tmax y Tmin diarias tardó 137 segundos y transfirió 1,47 GB. La repetición desde la caché tardó 0,07 segundos sin solicitudes de red. En el mismo período, 10 o 100 sitios dispersos superaron el límite predeterminado de 4 GiB de datos decodificados. Agrupe sitios cercanos o solicite períodos más cortos para sitios dispersos. Véanse las [comparaciones con estaciones y las mediciones de transferencia](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirts-era5-station-comparison-and-transport-benchmark-2026-11-10).

## Combinar dos fuentes y controlar el acceso a GEE {#paired-workflows-and-gee-controls}

```python
with ct.backend_policy(allow_gee=False):
    result = ct.analyze_climate_statistics(
        location_coord=(-1.286, 36.817), start_year=2020, end_year=2020,
        source="paired", precip_source="chirps_v3_daily_rnl",
        temp_source="chirts_era5", fixed_season="03-01:05-31",
    )
```

```sh
climate-toolkit fetch --source chirps_v3_daily_rnl --no-gee \
  --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-12-31

climate-toolkit stats --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2020 --end-year 2020 \
  --fixed-season 03-01:05-31
```

La interfaz unificada admite `--backend` y `--no-gee` en todos los comandos, al igual que el comando independiente de descarga. Los demás comandos independientes pueden usar las variables de entorno `CLIMATE_TOOLKIT_ALLOW_GEE=false` y `CLIMATE_TOOLKIT_BACKEND=auto`. Los contextos de Python se pueden anidar y los procesos de cálculo de modelos iniciados por la biblioteca heredan las reglas de acceso. Cada hilo o proceso creado por el usuario debe entrar en su propio contexto.

En modo histórico `auto` se combina CHIRPS v3 con la fuente `era5_land` (**ERA5-Land**, distinta de AgERA5) para las variables complementarias. CHIRTS-ERA5 es ahora la última alternativa para temperatura. Si se prohíbe GEE, `auto` selecciona directamente CHIRPS v3 y CHIRTS-ERA5. Esta combinación solo proporciona precipitación y Tmax/Tmin. No proporciona humedad, viento, radiación ni datos del suelo; los análisis que los requieren siguen necesitándolos. Los metadatos de estrés térmico humano marcan como nulas las variables complementarias ausentes, sin atribuirlas a CHIRTS-ERA5.

La elección explícita del proveedor se aplica a las fuentes con acceso directo en la nube. Las demás conservan sus vías de acceso, sujetas a la prohibición general de GEE. Elegir `dynamical` para CHIRTS-ERA5 falla porque ese adaptador no existe. Use `auto` al combinar fuentes distintas. La alternativa automática de GEE requiere configuración previa y nunca abre un proceso de autenticación interactivo.

## Flujo de trabajo completo {#full-pipeline}

`run_pipeline` aplica la misma pareja de fuentes y las mismas reglas de acceso a la descarga diaria, la climatología, la comparación de fuentes, las estadísticas estacionales, los riesgos agrícolas y la comparación de períodos. Esta prueba usa una climatología de dos años. Para obtener normales científicas, elija un período de referencia más largo y adecuado, teniendo en cuenta los límites siguientes.

```python
result = ct.run_pipeline(
    name="Nairobi", location_coord=(-1.286, 36.817),
    source="paired", precip_source="chirps_v3_daily_rnl", temp_source="chirts_era5",
    allow_gee=False, workers=2,
    start_year=2020, end_year=2020,
    climatology_baseline=(2019, 2020),
    fixed_season="03-01:05-31", crop_name="maize",
    run_compare_sources=True,
    compare_sources_list=["paired", "chirps_v3_daily_rnl", "chirts_era5"],
    run_compare_periods=True,
    baseline_start=2019, baseline_end=2019, focal_year=2020,
    output_dir="outputs/nairobi_pipeline",
)
print(result.summary)
assert not result.errors, result.errors
```

`source="auto", allow_gee=False` también selecciona esta pareja. `backend="auto"` es apropiado para combinar fuentes de precipitación y temperatura, ya que Dynamical no tiene adaptador de temperatura. Si se indica `ee_project_id` para una vía de GEE permitida, se transmite a las etapas correspondientes.

El directorio de cada sitio contiene `daily.csv`, su archivo de metadatos, los informes JSON por etapa y `status.json`. En la raíz se encuentran `summary.csv` y `metadata.json`. Las exportaciones diarias de la comparación de fuentes se guardan en `source_comparison/` para cada sitio. Compruebe el estado y `completed_steps` antes de usar un informe. Un error devuelto o una comparación parcial hace fallar la etapa. Una nueva ejecución fallida elimina los informes JSON obsoletos. Pueden quedar exportaciones parciales para diagnóstico sin que ello acredite que la etapa terminó correctamente.

La climatología de acceso directo exige todos los años solicitados y rechaza datos que no superan los controles de calidad. No acorta silenciosamente el período de referencia. También se puede calcular una climatología con dos fuentes desde la línea de comandos:

```sh
climate-toolkit climatology --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2019 --end-year 2020 \
  --format json --output outputs/climatology.json --output-dir ""
```

## Integridad de los datos, cachés y límites {#data-integrity-caches-and-limits}

- Las tablas sin procesar contienen las columnas decodificadas con los nombres de origen, los resultados del control de calidad y la procedencia. Las tablas transformadas o preprocesadas usan los nombres normalizados. Los datos directos conservan su precisión: se omiten el relleno genérico y las conversiones heurísticas de unidades.
- Un valor ausente o infinito, precipitación negativa, temperaturas fuera del intervalo de −90 a 60 °C o Tmin superior a Tmax impiden el uso de los datos directos en el análisis. Examine `stage="raw"` para diagnosticar la causa. Estos controles básicos no garantizan la exactitud científica. Un valor físicamente inválido no se trata como una caída del servicio.
- Un fallo de transferencia o del proveedor, una cobertura desactualizada, fechas o variables ausentes o metadatos incompatibles pueden llevar a consultar otro espejo admisible. Nunca se acepta silenciosamente una cobertura parcial. Los puntos en el océano o fuera del dominio no se trasladan a una celda terrestre cercana.
- Los bloques anuales se guardan en `outputs/cache/direct_cloud/v2/<source>/<backend>/` o en la raíz indicada. Los archivos JSON, con suma de comprobación, conservan la precisión numérica, el orden de columnas, las coordenadas solicitadas, las celdas elegidas, las unidades, la revisión y las fechas. Las escrituras son atómicas. Una respuesta completa en caché evita toda consulta de metadatos o autenticación, incluso para un proveedor alternativo. Una lectura interrumpida puede reutilizar los bloques de la misma revisión; una revisión nueva sustituye los datos sin mezclar revisiones. `refresh_cache=True` solicita los datos actuales del proveedor. Las cachés de GEE existentes se mantienen separadas. Los años consecutivos ausentes se cargan en lotes de hasta cinco años, compartiendo bloques de origen entre años. Cada lote completado guarda por separado los registros anuales, lo que permite reanudar la misma revisión tras un fallo.
- Las exportaciones CSV/JSON de las descargas y comparaciones de fuentes escriben un archivo complementario `.metadata.json`. Las estadísticas, comparaciones de períodos, evaluaciones de riesgos y diagnósticos de estaciones incluyen campos adicionales `data_provenance`. El inventario de caché incluye `direct_cloud`.
- Las consultas HTTP de metadatos tienen límites de tiempo y de reintentos. Las transferencias también tienen un tiempo máximo por solicitud. El límite estimado predeterminado es de 4 GiB de bloques de origen decodificados por solicitud a un proveedor. Es el tamaño decodificado, **no el tráfico de red medido**. Si se supera el límite, se omite el proveedor. Ajuste `CLIMATE_TOOLKIT_MAX_DECODED_BYTES` para cambiarlo. Una solicitud larga o geográficamente dispersa puede tardar varios minutos.

Para reproducir las mediciones en línea, use `scripts/benchmark_direct_cloud.py`. El límite de 90 segundos por caso es un criterio de la prueba y no limita la duración total de un análisis con la biblioteca. Las pruebas habituales usan datos de prueba sin conexión; las mediciones en línea son opcionales.

CHIRTS-ERA5 cuenta actualmente con **un único proveedor directo integrado**. Los archivos GeoTIFF/NetCDF del CHC son originales independientes. Los archivos diarios y los fallos observados en lecturas parciales requieren más trabajo antes de usarlos como alternativa automática eficiente. El 2026-11-02 se rechazó el NetCDF de Tmax del año en curso, el de Tmin terminaba en septiembre y el catálogo EWX solo ofrecía agregados de cinco días o mensuales. Las lecturas puntuales del NetCDF histórico también excedieron el tiempo previsto para consultas cortas. El 10 de noviembre se observaron diferencias de 0,20 a 2,18 °C en las Tmin del 21 de octubre para las mismas celdas entre el original del CHC y la revisión fijada del espejo de Hugging Face. Superan la tolerancia de cuantificación del espejo (0,05 °C). Debe comprobarse la equivalencia de las revisiones antes de recurrir automáticamente al original. Reproduzca las pruebas de lectura por rangos de bytes con `scripts/probe_chc_backup.py` (requiere `h5py` solo para la investigación). Véanse el [estudio de la fuente alternativa](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_179_chc_backup_investigation.md) y [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179). El acceso sin credenciales a las variables complementarias de ERA5-Land se sigue en [#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180). La [auditoría de acceso a ERA5-Land](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_180_era5_land_access.md) identificó los archivos autenticados de CDS ARCO, pero la consulta en línea de los metadatos rechazó la clave configurada. La integración del CDS está aplazada porque requiere credenciales. No se ha habilitado el acceso directo a ERA5-Land en la nube. Para reproducir los resultados de GEE también hay que agregar los flujos horarios del CDS delimitando explícitamente cada día.

## Referencias {#references}

- [Documentación del productor de CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5)
- [CHIRTS-ERA5 en Hugging Face](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily)
- [CHIRPS v3 RNL en Hugging Face](https://huggingface.co/datasets/aaguilar90/chirps-v3-daily-rnl)
- [Producto definitivo/RNL de Dynamical](https://dynamical.org/catalog/ucsb-chc-chirps-analysis-final/)

Verificación completa en línea: `python scripts/verify_direct_pipeline.py`. El programa comprueba las seis etapas, la procedencia exportada y una segunda ejecución desde la caché con la apertura de proveedores y la inicialización de GEE bloqueadas. Utiliza períodos de prueba cortos, inadecuados para obtener normales climáticas científicas.

<!-- source-sha256: c39cbc8080809be30231fbc7817ac7ac6ee9d3f9e68fef1a64b140458fde5e21 -->
