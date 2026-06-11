__all__ = [
    "Site",
    "fetch_data",
    "fetch_nex_gddp_batch_data",
    "run_batch_extraction",
]


def __getattr__(name):
    if name == "fetch_data":
        from .fetch_data import fetch_data as _fetch_data

        return _fetch_data
    if name in {"Site", "fetch_nex_gddp_batch_data", "run_batch_extraction"}:
        from .nex_gddp_batch import (
            Site as _Site,
            fetch_nex_gddp_batch_data as _fetch_nex_gddp_batch_data,
            run_batch_extraction as _run_batch_extraction,
        )

        exports = {
            "Site": _Site,
            "fetch_nex_gddp_batch_data": _fetch_nex_gddp_batch_data,
            "run_batch_extraction": _run_batch_extraction,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
