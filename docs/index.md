# Climate Toolkit

Location-based climate analysis for agriculture: fetch daily climate data,
compute seasonal climatologies and drought indices, assess crop and livestock
hazards, and compare periods, data sources, and weather stations — for any
point location.

!!! tip "Try it in your browser — no install"
    [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)

    The [companion Colab notebook](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)
    installs the package and runs the credential-free examples end-to-end
    on a free Google-hosted runtime.

## Install

```bash
pip install climate-toolkit
```

## Quick start

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",              # needs no credentials
    location_coord=(-1.286, 36.817),  # Nairobi
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
)
df.head()
```

`nasa_power` works with zero setup. For CHIRPS v3 rainfall and CHIRTS-ERA5 daily temperatures, use
[direct cloud access](direct_cloud_access.md) on Python 3.12+ with `climate-toolkit[cloud]`.
For ERA5-Land, ERA5 and NEX-GDDP, follow [Earth Engine setup](getting_started.md#2-google-earth-engine-credentials).

## What's in the box

| Function | Purpose |
|----------|---------|
| [`fetch_climate_data`](api/fetching.md) | Daily climate data for a site as a pandas DataFrame |
| [`analyze_climate_statistics`](api/analysis.md) | Seasonal climatology, water balance, SPI/SPEI |
| [`evaluate_hazards`](api/analysis.md) | Crop & livestock hazard assessment for a season |
| [`compare_climate_periods`](api/analysis.md) | Focal year vs. baseline climatology |
| [`compare_climate_sources`](api/comparison.md) | Side-by-side gridded dataset comparison |
| [`download_station_data`](api/comparison.md) | Daily observations from nearby weather stations |
| [`compare_station_to_grids`](api/comparison.md) | Validate gridded data against stations |

These seven analyses also have CLI commands. The [Python API overview](api/index.md) includes `run_pipeline` for running a whole workflow and `backend_policy` for controlling data access.

## Funding & acknowledgements

This toolkit was developed as part of the project *Advancing Climate Data
Integration in Agroecological Research*, funded by the
[McKnight Foundation](https://www.mcknight.org/) through its
[Global Collaboration for Resilient Food Systems (CRFS)](https://www.mcknight.org/programs/global-foods/)
programme. The work was led by the
[Alliance of Bioversity International and CIAT](https://alliancebioversityciat.org/),
in partnership with [AIMS Research and Innovation Centre (AIMS RIC)](https://www.aimsric.org/).

This work was supported by the
[CGIAR Climate Action Program](https://www.cgiar.org/cgiar-research-portfolio-2025-2030/climate-action/)
through its **Area of Work 1 (AoW1) — the Climate Data Hub (CDH)**, which
funds and coordinates the climate-data infrastructure this toolkit is part of.
We acknowledge the CGIAR Trust Fund and its
[contributors](https://www.cgiar.org/funders/).

<p style="display:flex; align-items:center; gap:1.5em; flex-wrap:nowrap; margin-top:1.5em;">
  <a href="https://www.mcknight.org/programs/global-foods/">
    <img src="assets/logos/mcknight.jpg" alt="The McKnight Foundation" style="height:44px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.cgiar.org/news-events/news/the-world-has-changed-so-has-climate-action-at-cgiar">
    <img src="assets/logos/cgiar-climate-action.png" alt="CGIAR Climate Action" style="height:56px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.aimsric.org/">
    <img src="assets/logos/aims.png" alt="AIMS Research and Innovation Centre (AIMS RIC)" style="height:52px; width:auto; background:#fff; padding:4px;">
  </a>
</p>
