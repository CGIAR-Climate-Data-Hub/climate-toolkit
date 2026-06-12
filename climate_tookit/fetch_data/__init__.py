__all__ = [
    "Site",
    "fetch_gee_xee_batch_data",
    "load_sites",
    "parse_site_spec",
    "fetch_data",
    "fetch_nex_gddp_batch_data",
    "run_gee_xee_batch_extraction",
    "run_batch_extraction",
]


def __getattr__(name):
    if name == "fetch_data":
        from .fetch_data import fetch_data as _fetch_data

        return _fetch_data
    if name in {"Site", "load_sites", "parse_site_spec"}:
        from .multi_site import (
            Site as _Site,
            load_sites as _load_sites,
            parse_site_spec as _parse_site_spec,
        )

        exports = {
            "Site": _Site,
            "load_sites": _load_sites,
            "parse_site_spec": _parse_site_spec,
        }
        return exports[name]
    if name in {"fetch_gee_xee_batch_data", "run_gee_xee_batch_extraction"}:
        from .gee_xee_batch import (
            fetch_gee_xee_batch_data as _fetch_gee_xee_batch_data,
            run_gee_xee_batch_extraction as _run_gee_xee_batch_extraction,
        )

        exports = {
            "fetch_gee_xee_batch_data": _fetch_gee_xee_batch_data,
            "run_gee_xee_batch_extraction": _run_gee_xee_batch_extraction,
        }
        return exports[name]
    if name in {"fetch_nex_gddp_batch_data", "run_batch_extraction"}:
        from .nex_gddp_batch import (
            fetch_nex_gddp_batch_data as _fetch_nex_gddp_batch_data,
            run_batch_extraction as _run_batch_extraction,
        )

        exports = {
            "fetch_nex_gddp_batch_data": _fetch_nex_gddp_batch_data,
            "run_batch_extraction": _run_batch_extraction,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
