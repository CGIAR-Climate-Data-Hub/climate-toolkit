"""Location-based climate analysis toolkit for agriculture.

Fetch daily climate data, compute seasonal climatologies and drought
indices, assess crop and livestock hazards, and compare periods, data
sources, and weather stations — for any point location.

Public functions
----------------
fetch_climate_data(source, location_coord, ...)
    Download daily climate data for a site as a pandas DataFrame.
analyze_climate_statistics(location_coord, start_year, end_year, source, ...)
    Seasonal climatology, water balance, and indices (SPI/SPEI) over a
    multi-year window.
evaluate_hazards(crop_name, location_coord, date_from, date_to, ...)
    Crop/livestock hazard assessment (heat, drought, waterlogging, ...)
    for a growing season.
compare_climate_periods(location, baseline_start, baseline_end, focal_year, ...)
    Diff a focal year against a baseline climatology.
compare_climate_sources(sources, lat, lon, start, end, ...)
    Side-by-side comparison of gridded datasets for one site.
download_station_data(station_source, station_coord, date_from, date_to, ...)
    Fetch daily observations from nearby weather stations.
compare_station_to_grids(station_source, station_coord, ..., grid_sources)
    Validate gridded datasets against station observations.

Getting started
---------------
>>> import climate_tookit as ct
>>> from datetime import date
>>> df = ct.fetch_climate_data(
...     source="nasa_power",              # needs no credentials
...     location_coord=(-1.286, 36.817),  # Nairobi
...     date_from=date(2020, 1, 1),
...     date_to=date(2020, 12, 31),
... )

Use ``help(ct.fetch_climate_data)`` (or any function above) for full
parameter documentation.

Data sources
------------
``nasa_power`` works with no setup. Earth Engine-backed sources
(``agera_5``, ``era_5``, ``chirps_v3_daily_rnl``, ``nex_gddp``) require
``earthengine authenticate`` and a ``GCP_PROJECT_ID`` environment
variable (free for noncommercial use). See ``examples/basic_usage.py``
in the repository for a full walkthrough.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = [
    "__version__",
    "analyze_climate_statistics",
    "compare_climate_periods",
    "compare_climate_sources",
    "compare_station_to_grids",
    "download_station_data",
    "evaluate_hazards",
    "fetch_climate_data",
]


try:
    __version__ = version("climate-tookit")
except PackageNotFoundError:  # pragma: no cover - local source tree before install
    __version__ = "0.0.0"


def __getattr__(name: str):
    if name == "fetch_climate_data":
        from .fetch_data.fetch_data import fetch_data as _fetch_data

        return _fetch_data
    if name == "analyze_climate_statistics":
        from .climate_statistics.statistics import (
            analyze_climate_statistics as _analyze_climate_statistics,
        )

        return _analyze_climate_statistics
    if name == "compare_climate_periods":
        from .compare_periods.periods import compare as _compare_periods

        return _compare_periods
    if name == "compare_climate_sources":
        from .compare_datasets.compare_datasets import compare_sources as _compare_sources

        return _compare_sources
    if name == "evaluate_hazards":
        from .calculate_hazards.hazards import calculate_hazards as _calculate_hazards

        return _calculate_hazards
    if name == "download_station_data":
        from .weather_station.download import download_station_data as _download_station_data

        return _download_station_data
    if name == "compare_station_to_grids":
        from .weather_station.compare import (
            compare_station_to_grids as _compare_station_to_grids,
        )

        return _compare_station_to_grids
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
