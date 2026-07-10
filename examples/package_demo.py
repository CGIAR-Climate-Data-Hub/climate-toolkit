"""Credential-free tour of climate_toolkit as a Python package.

A broader companion to ``basic_usage.py`` that touches most of the toolkit's
main capabilities using only sources that need **no credentials** — NASA POWER
(gridded) and NOAA GHCN (weather stations). No Earth Engine, no API keys.

Covered:

    1. fetch_climate_data          — daily data -> pandas DataFrame
    2. analyze_climate_statistics  — seasonal climatology + water balance
    3. ... with spei_scale_months  — SPEI drought index
    4. download_station_data       — nearest NOAA GHCN station observations

Earth Engine-backed sources (agera_5, era_5, nex_gddp, ...) and comparison /
hazard workflows use the same functions after a one-time
``earthengine authenticate`` + ``GCP_PROJECT_ID`` — see the "Use as a package"
docs page.

Install (into your own env)::

    pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

Run::

    python examples/package_demo.py         # or: uv run python examples/package_demo.py
"""

from datetime import date

import pandas as pd

import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

SITE = (-1.286, 36.817)  # Nairobi, (lat, lon)


def main() -> None:
    print("climate_toolkit", ct.__version__, "| public functions:")
    print("  ", [n for n in ct.__all__ if not n.startswith("__")])

    # 1) Fetch daily climate data -> pandas DataFrame.
    df = ct.fetch_climate_data(
        source="nasa_power",
        location_coord=SITE,
        variables=[
            ClimateVariable.precipitation,
            ClimateVariable.max_temperature,
            ClimateVariable.min_temperature,
        ],
        date_from=date(2020, 1, 1),
        date_to=date(2020, 3, 31),
        verbose=False,
    )
    print("\n[1] fetch_climate_data ->", df.shape, "DataFrame")
    print(df.head().to_string())

    # 2) Seasonal climatology + water balance for a pinned March-May season.
    stats = ct.analyze_climate_statistics(
        location_coord=SITE,
        start_year=2016,
        end_year=2020,
        source="nasa_power",
        fixed_season="03-01:05-31",
    )
    season_rows = [
        {
            "year": s["year"],
            "length_days": s["length_days"],
            "rain_mm": (s["precipitation"] or {}).get("total_mm"),
            "NDWS": (s["water_balance"] or {}).get("NDWS"),
            "WRSI": (s["water_balance"] or {}).get("WRSI"),
        }
        for s in stats["season_statistics"]
    ]
    print("\n[2] analyze_climate_statistics (fixed MAM season):")
    print(pd.DataFrame(season_rows).to_string(index=False))

    # 3) SPEI drought index.
    spei = ct.analyze_climate_statistics(
        location_coord=SITE,
        start_year=2016,
        end_year=2020,
        source="nasa_power",
        fixed_season="03-01:05-31",
        spei_scale_months=3,
    )["spei"]
    print("\n[3] SPEI-3 ->", spei["config"])

    # 4) Weather-station observations (NOAA GHCN) -- also credential-free.
    station = ct.download_station_data(
        station_source="ghcn_daily",
        station_coord=SITE,
        date_from=date(2020, 1, 1),
        date_to=date(2020, 3, 31),
    )
    print(
        f"\n[4] download_station_data -> {station['station_name'].iloc[0]} "
        f"({station['station_distance_km'].iloc[0]:.1f} km), {station.shape}"
    )

    print("\nExplore any function with help(ct.fetch_climate_data).")


if __name__ == "__main__":
    main()
