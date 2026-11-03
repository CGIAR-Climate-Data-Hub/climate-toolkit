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

Most gridded sources (`agera_5`, `era_5`, `chirps_v3_daily_rnl`, `nex_gddp`)
are served through Google Earth Engine. `nasa_power` and the weather-station
sources (`ghcn_daily`, `gsod`) need no credentials at all.

!!! tip "This can be completely free"
    Earth Engine is free for noncommercial use (research, academia,
    nonprofit, education). When registering at
    [code.earthengine.google.com/register](https://code.earthengine.google.com/register)
    choose:

    - "Register a Noncommercial or Commercial Cloud project"
    - Usage type: **Unpaid usage** (do NOT pick "Paid usage")
    - Category: e.g. **Academia & Research** or **Nonprofit**

    No billing account or credit card is required for this path.

Setup steps:

1. Sign up at [earthengine.google.com](https://earthengine.google.com) and
   register a Cloud project (see tip above).
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
