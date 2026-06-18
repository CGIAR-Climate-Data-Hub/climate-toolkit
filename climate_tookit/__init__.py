"""Top-level public API for climate_tookit."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = [
    "__version__",
    "analyze_climate_statistics",
    "compare_climate_periods",
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
