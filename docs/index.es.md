# Climate Toolkit

A partir de la latitud y la longitud de un sitio, puede descargar datos climáticos diarios, calcular climatologías estacionales e índices de sequía, evaluar riesgos para los cultivos y el ganado, y comparar resultados entre períodos, fuentes y estaciones meteorológicas.

!!! tip "Probar en el navegador"
    El [cuaderno de Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb) instala el paquete en un entorno alojado por Google y ejecuta los ejemplos que no requieren credenciales.

## Instalación

```bash
pip install climate-toolkit
```

## Inicio rápido

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",              # Acceso sin credenciales
    location_coord=(-1.286, 36.817),  # Nairobi
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
)
df.head()
```

Para obtener precipitaciones de CHIRPS v3 y temperaturas diarias de CHIRTS-ERA5, instale `climate-toolkit[cloud]` con Python 3.12 o posterior. Para ERA5-Land, ERA5 y NEX-GDDP, configure Earth Engine. [Guía de instalación y primer análisis](getting_started.md) · [Acceso directo a los datos](direct_cloud_access.md)

## Funciones principales

| Función | Resultado |
|---|---|
| [`fetch_climate_data`](api/fetching.md) | Datos climáticos diarios de un sitio en un DataFrame de pandas |
| [`analyze_climate_statistics`](api/analysis.md) | Climatología estacional, balance hídrico e índices SPI/SPEI |
| [`evaluate_hazards`](api/analysis.md) | Evaluación de riesgos para los cultivos y el ganado durante una temporada |
| [`compare_climate_periods`](api/analysis.md) | Comparación de un año con la climatología de referencia |
| [`compare_climate_sources`](api/comparison.md) | Comparación de conjuntos de datos en malla |
| [`download_station_data`](api/comparison.md) | Observaciones diarias de estaciones meteorológicas cercanas |
| [`compare_station_to_grids`](api/comparison.md) | Comparación de los valores de la malla con observaciones de estaciones |

También puede ejecutar estos análisis desde la línea de comandos con `climate-toolkit <comando>`.

## Financiación y agradecimientos

La [Fundación McKnight](https://www.mcknight.org/) financió el proyecto *Advancing Climate Data Integration in Agroecological Research* por medio de su programa [Global Collaboration for Resilient Food Systems](https://www.mcknight.org/programs/global-foods/). La [Alianza de Bioversity International y el CIAT](https://alliancebioversityciat.org/) dirigió el trabajo en colaboración con el [Centro de Investigación e Innovación de AIMS](https://www.aimsric.org/).

El [programa Climate Action del CGIAR](https://www.cgiar.org/cgiar-research-portfolio-2025-2030/climate-action/) apoyó este trabajo a través de su primera área de trabajo, el *Climate Data Hub*, que financia y coordina la infraestructura de datos climáticos. Agradecemos al Fondo Fiduciario del CGIAR y a [sus contribuyentes](https://www.cgiar.org/funders/).

<p style="display:flex; align-items:center; gap:1.5em; flex-wrap:nowrap; margin-top:1.5em;">
  <a href="https://www.mcknight.org/programs/global-foods/">
    <img src="../assets/logos/mcknight.jpg" alt="The McKnight Foundation" style="height:44px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.cgiar.org/news-events/news/the-world-has-changed-so-has-climate-action-at-cgiar">
    <img src="../assets/logos/cgiar-climate-action.png" alt="CGIAR Climate Action" style="height:56px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.aimsric.org/">
    <img src="../assets/logos/aims.png" alt="AIMS Research and Innovation Centre (AIMS RIC)" style="height:52px; width:auto; background:#fff; padding:4px;">
  </a>
</p>
