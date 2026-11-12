# Getting started

!!! tip "No local setup? Use Colab"
    [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)
    — follow this whole page interactively in the
    [companion notebook](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb):
    install, first fetch, and the optional Earth Engine setup, all in the browser.

## 1. Install

From PyPI, no clone needed:

```bash
pip install climate-toolkit
```

For CHIRPS v3 final rainfall (`chirps_v3_daily_rnl`) and CHIRTS-ERA5 daily
minimum and maximum temperatures (`chirts_era5`), install the cloud extra on
Python 3.12+ for [access without Google credentials](direct_cloud_access.md):

```bash
pip install "climate-toolkit[cloud]"
```

From a Jupyter notebook, prefix with `%`:

```
%pip install climate-toolkit
```

For the latest unreleased code, install from GitHub instead:
`pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"`

For development, clone and use [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
cd climate-toolkit
uv sync
```

## 2. Google Earth Engine credentials

Complete this step for `era5_land`, `era_5`, `nex_gddp`, CHIRPS v2
(`chirps_v2` or `chirps`), or the optional CHIRPS v3 Earth Engine fallback.
For direct CHIRPS v3 and CHIRTS-ERA5, skip this step. `nasa_power` and the weather-station
sources (`ghcn_daily`, `gsod`) need no credentials at all.

!!! tip "Noncommercial Earth Engine access"
    Eligible projects can register for unpaid Earth Engine access. Complete the
    eligibility questionnaire and choose the appropriate tier. Billing-account
    requirements depend on the tier. See Google's [noncommercial tier guide](https://developers.google.com/earth-engine/guides/noncommercial_tiers).

Setup steps:

1. [Register a Google Cloud project for Earth Engine](https://code.earthengine.google.com/register).
2. Authenticate once on your machine:

    ```bash
    earthengine authenticate
    ```

3. Tell the toolkit which Cloud project to use. Any one of
    `GCP_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT`, or `EE_PROJECT_ID` works:

    ```bash
    # macOS / Linux
    export GCP_PROJECT_ID=your-ee-project-id
    ```

    ```powershell
    # Windows PowerShell
    $env:GCP_PROJECT_ID = "your-ee-project-id"
    ```

4. Verify the setup:

    ```bash
    climate-toolkit-gee-check
    ```

## 3. First analysis

Fetch daily data (NASA POWER needs no credentials) and confirm what came back:

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),   # Nairobi (lat, lon)
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print("rows:", df.shape[0], "| columns:", df.columns.tolist())
df.head()
```

`fetch_climate_data` returns a **pandas DataFrame**. NASA POWER carries no soil
fields, so you'll see a note that those were skipped — the climate columns are
still returned.

### Seasonal statistics as a table

`analyze_climate_statistics` returns a nested dict. Pin the season with
`fixed_season="MM-DD:MM-DD"` for stable, comparable multi-year output, then
tabulate the per-season results:

```python
import pandas as pd

stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2016, end_year=2020,
    source="nasa_power",
    fixed_season="03-01:05-31",        # March–May long rains
)

pd.DataFrame([
    {
        "year": s["year"],
        "rain_mm": (s["precipitation"] or {}).get("total_mm"),
        "NDWS": (s["water_balance"] or {}).get("NDWS"),
        "WRSI": (s["water_balance"] or {}).get("WRSI"),
    }
    for s in stats["season_statistics"]
])
```

!!! note "Why `fixed_season`?"
    With automatic detection, different years can have different season counts,
    and the toolkit warns that it can't build comparable multi-year windows.
    Passing `fixed_season="MM-DD:MM-DD"` (one or two comma-separated windows)
    pins the season so results line up year to year.

## Getting help

Every public function has full parameter documentation:

```python
help(ct)                        # package overview
help(ct.fetch_climate_data)     # any function
```

In Jupyter/IPython: `ct.fetch_climate_data?`. In VSCode: hover over the
function name.
