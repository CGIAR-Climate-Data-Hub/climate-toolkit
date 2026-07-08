"""Weather-station package API.

Stable package-level helpers are exposed lazily here to keep import costs low
and avoid dragging backend modules into unrelated workflows. Lower-level GHCN
and GSOD helpers remain importable from their concrete submodules for advanced
development use, but they are not advertised as stable package-root API.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "compare_station_to_grids",
    "dem",
    "download_station_data",
    "render_compare_report",
]


def __getattr__(name: str):
    if name == "dem":
        return import_module(".dem", __name__)
    if name == "download_station_data":
        from .download import download_station_data as _download_station_data

        return _download_station_data
    if name in {"compare_station_to_grids", "render_compare_report"}:
        from .compare import (
            compare_station_to_grids as _compare_station_to_grids,
            render_compare_report as _render_compare_report,
        )

        exports = {
            "compare_station_to_grids": _compare_station_to_grids,
            "render_compare_report": _render_compare_report,
        }
        return exports[name]
    if name in {
        "DEFAULT_GHCN_CACHE_ROOT",
        "fetch_ghcn_daily_records",
        "load_ghcn_inventory",
        "load_ghcn_stations",
        "select_ghcn_station",
    }:
        from .ghcn_daily import (
            DEFAULT_GHCN_CACHE_ROOT as _DEFAULT_GHCN_CACHE_ROOT,
            fetch_ghcn_daily_records as _fetch_ghcn_daily_records,
            load_ghcn_inventory as _load_ghcn_inventory,
            load_ghcn_stations as _load_ghcn_stations,
            select_ghcn_station as _select_ghcn_station,
        )

        exports = {
            "DEFAULT_GHCN_CACHE_ROOT": _DEFAULT_GHCN_CACHE_ROOT,
            "fetch_ghcn_daily_records": _fetch_ghcn_daily_records,
            "load_ghcn_inventory": _load_ghcn_inventory,
            "load_ghcn_stations": _load_ghcn_stations,
            "select_ghcn_station": _select_ghcn_station,
        }
        return exports[name]
    if name in {"DEFAULT_GSOD_CACHE_ROOT", "fetch_gsod_records"}:
        from .gsod import (
            DEFAULT_GSOD_CACHE_ROOT as _DEFAULT_GSOD_CACHE_ROOT,
            fetch_gsod_records as _fetch_gsod_records,
        )

        exports = {
            "DEFAULT_GSOD_CACHE_ROOT": _DEFAULT_GSOD_CACHE_ROOT,
            "fetch_gsod_records": _fetch_gsod_records,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
