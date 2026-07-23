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
pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"
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

`nasa_power` works with zero setup. The Earth Engine-backed sources
(`agera_5`, `era_5`, `chirps_v3_daily_rnl`, `nex_gddp`) need a free
one-time authentication — see [Getting started](getting_started.md).

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

Every function is also available as a CLI command (`climate-toolkit <command>`);
see the workflow guides in the navigation.

## Funding & acknowledgements

This toolkit was developed as part of the project *Advancing Climate Data
Integration in Agroecological Research*, funded by the
[McKnight Foundation](https://www.mcknight.org/) through its
[Global Collaboration for Resilient Food Systems (CRFS)](https://www.mcknight.org/programs/global-foods/)
programme. The work was led by the
[Alliance of Bioversity International and CIAT](https://alliancebioversityciat.org/),
in partnership with [AIMS Rwanda](https://aims.ac.rw/).

This work was supported by the CGIAR Climate Data Hub (CDH), part of the
[CGIAR Climate Action Program](https://www.cgiar.org/cgiar-research-portfolio-2025-2030/climate-action/)
(Area of Work 1). We acknowledge the CGIAR Trust Fund and its
[contributors](https://www.cgiar.org/funders/).

<p style="display:flex; align-items:center; gap:1.5em; flex-wrap:nowrap; margin-top:1.5em;">
  <a href="https://www.mcknight.org/programs/global-foods/">
    <img src="assets/logos/mcknight.jpg" alt="The McKnight Foundation" style="height:44px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.cgiar.org/news-events/news/the-world-has-changed-so-has-climate-action-at-cgiar">
    <img src="assets/logos/cgiar-climate-action.png" alt="CGIAR Climate Action" style="height:56px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://aims.ac.rw/">
    <img src="assets/logos/aims.png" alt="AIMS Rwanda" style="height:52px; width:auto; background:#fff; padding:4px;">
  </a>
</p>
