# Getting started

!!! tip "No local setup? Use Colab"
    [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)
    — follow this whole page interactively in the
    [companion notebook](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb):
    install, first fetch, and the optional Earth Engine setup, all in the browser.

## 1. Install

Straight from GitHub, no clone needed:

```bash
pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"
```

From a Jupyter notebook, prefix with `%`:

```
%pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"
```

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

```python
import climate_toolkit as ct
from datetime import date

# Daily data — no credentials needed for nasa_power
df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
)

# Crop hazards for a season (uses Earth Engine sources by default)
hazards = ct.evaluate_hazards(
    crop_name="maize",
    location_coord=(-1.286, 36.817),
    date_from="2020-01-01",
    date_to="2020-12-31",
)
```

## Getting help

Every public function has full parameter documentation:

```python
help(ct)                        # package overview
help(ct.fetch_climate_data)     # any function
```

In Jupyter/IPython: `ct.fetch_climate_data?`. In VSCode: hover over the
function name.
