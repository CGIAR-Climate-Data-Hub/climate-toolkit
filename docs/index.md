# Climate Toolkit

Location-based climate analysis for agriculture: fetch daily climate data,
compute seasonal climatologies and drought indices, assess crop and livestock
hazards, and compare periods, data sources, and weather stations — for any
point location.

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
