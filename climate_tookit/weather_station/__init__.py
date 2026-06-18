"""Weather-station helpers and backends.

Keep imports here lightweight to avoid package cycles with fetch_data.
Public helpers resolve lazily from backend modules.
"""

from __future__ import annotations


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


def __getattr__(name: str):
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
