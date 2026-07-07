"""Basic usage of climate_toolkit as a regular Python package.

Demonstrates the four main entry points exposed at the top level:

    1. fetch_climate_data          — download daily climate data for a site
    2. analyze_climate_statistics  — seasonal climatology + indices
    3. evaluate_hazards            — crop hazard assessment for a season
    4. compare_climate_periods     — focal year vs. baseline comparison

Prerequisites
-------------

**1. Install the package**

Straight from GitHub, no clone needed (run in a terminal)::

    pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

From inside a Jupyter notebook, prefix with ``%``::

    %pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

Or, for development, clone the repository first (preferred, uses ``uv``)::

    git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
    cd climate-toolkit
    uv sync

**2. Google Earth Engine credentials (needed for most data sources)**

The GEE-backed sources — ``agera_5``, ``era_5``, ``chirps_v3_daily_rnl``,
``nex_gddp`` — require a one-time authentication plus a Cloud project id.
``nasa_power`` needs neither, which is why this script starts with it.

a. Sign up at https://earthengine.google.com and create (or reuse) a
   Google Cloud project with the Earth Engine API enabled.

   **This can be completely free.** Earth Engine is free for noncommercial
   use (research, academia, nonprofit, education). When registering your
   project at https://code.earthengine.google.com/register choose:

   - "Register a Noncommercial or Commercial Cloud project"
   - Usage type: **Unpaid usage** (do NOT pick "Paid usage")
   - Category: e.g. **Academia & Research** or **Nonprofit**

   No billing account or credit card is required for this path. Paid
   registration is only needed for commercial/operational use.

b. Authenticate once on this machine (stores a token under
   ``~/.config/earthengine/``)::

       uv run earthengine authenticate

c. Tell the toolkit which Cloud project your Earth Engine requests run
   under (free for unpaid/noncommercial projects — see step a).
   Any one of ``GCP_PROJECT_ID``, ``GOOGLE_CLOUD_PROJECT``, or
   ``EE_PROJECT_ID`` works; the toolkit checks them in that order.

   macOS / Linux::

       export GCP_PROJECT_ID=your-ee-project-id

   Windows PowerShell::

       $env:GCP_PROJECT_ID = "your-ee-project-id"

   Or keep it in a ``.env`` file (copy ``.env.example`` in the repo root)
   and pass it explicitly — the toolkit does NOT auto-load ``.env``::

       uv run --env-file .env python examples/basic_usage.py

d. Verify the setup with the bundled preflight check::

       uv run climate-toolkit-gee-check

**3. Run this script** (from the repo root)::

    uv run python examples/basic_usage.py
"""

from datetime import date

import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

# Nairobi, Kenya — swap in your own site
LAT, LON = -1.286, 36.817


def demo_fetch() -> None:
    """1. Fetch daily climate data -> pandas DataFrame.

    Uses nasa_power, which needs no Earth Engine auth. The GEE-backed
    sources (agera_5, era_5, chirps_v3_daily_rnl, nex_gddp) require
    ``earthengine authenticate`` + ``GCP_PROJECT_ID``.
    """
    df = ct.fetch_climate_data(
        source="nasa_power",  # or: agera_5, era_5, chirps_v3_daily_rnl, nex_gddp
        location_coord=(LAT, LON),
        variables=[
            ClimateVariable.precipitation,
            ClimateVariable.max_temperature,
            ClimateVariable.min_temperature,
        ],
        date_from=date(2020, 1, 1),
        date_to=date(2020, 12, 31),
    )
    print(df.head())
    print(f"{len(df)} daily rows fetched")


def demo_statistics() -> None:
    """2. Seasonal climatology and statistics over a multi-year window."""
    stats = ct.analyze_climate_statistics(
        location_coord=(LAT, LON),
        start_year=2015,
        end_year=2020,
        source="agera_5",
        crop_name="maize",
    )
    print(sorted(stats.keys()))


def demo_hazards() -> None:
    """3. Crop hazard assessment (heat, drought, waterlogging...) for a season."""
    hazards = ct.evaluate_hazards(
        crop_name="maize",
        location_coord=(LAT, LON),
        date_from="2020-01-01",
        date_to="2020-12-31",
        source="auto",  # picks recommended precip/temp sources
    )
    print(sorted(hazards.keys()))


def demo_compare_periods() -> None:
    """4. How did a focal year differ from the local baseline?"""
    diff = ct.compare_climate_periods(
        location=(LAT, LON),
        baseline_start=1991,
        baseline_end=2020,
        focal_year=2023,
        source="agera_5",
        crop_name="maize",
    )
    print(sorted(diff.keys()))


if __name__ == "__main__":
    import os

    print(f"climate_toolkit v{ct.__version__}\n")
    demo_fetch()

    # The remaining demos fetch multi-year data from GEE-backed sources.
    if os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"):
        demo_statistics()
        demo_hazards()
        demo_compare_periods()
    else:
        print(
            "\nSkipping statistics/hazards/period demos: set GCP_PROJECT_ID "
            "(and run `earthengine authenticate`) to enable Earth Engine sources."
        )
