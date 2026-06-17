"""Weather-station helpers and backends.

Keep imports here lightweight to avoid package cycles with fetch_data.
Higher-level compare helpers are exposed through lazy wrappers.
"""

from .ghcn_daily import (
    DEFAULT_GHCN_CACHE_ROOT,
    fetch_ghcn_daily_records,
    load_ghcn_inventory,
    load_ghcn_stations,
    select_ghcn_station,
)
from .gsod import DEFAULT_GSOD_CACHE_ROOT, fetch_gsod_records


def compare_station_to_grids(*args, **kwargs):
    from .compare import compare_station_to_grids as _compare_station_to_grids

    return _compare_station_to_grids(*args, **kwargs)


def render_compare_report(*args, **kwargs):
    from .compare import render_compare_report as _render_compare_report

    return _render_compare_report(*args, **kwargs)


__all__ = [
    "DEFAULT_GHCN_CACHE_ROOT",
    "DEFAULT_GSOD_CACHE_ROOT",
    "compare_station_to_grids",
    "fetch_ghcn_daily_records",
    "fetch_gsod_records",
    "load_ghcn_inventory",
    "load_ghcn_stations",
    "render_compare_report",
    "select_ghcn_station",
]
