"""
Climatology Module

Long-term climate analysis including 30-year normal periods and trends.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "compute_monthly_spei",
    "prepare_monthly_climatic_water_balance",
    "assess_xclim_precip_annual_readiness",
    "compare_xclim_precip_indices",
    "compute_xclim_precip_indices",
    "XCLIM_AVAILABLE",
]


def __getattr__(name: str):
    if name in {"compute_monthly_spei", "prepare_monthly_climatic_water_balance"}:
        module = import_module(".spei", __name__)
        return getattr(module, name)
    if name in {
        "assess_xclim_precip_annual_readiness",
        "compare_xclim_precip_indices",
        "compute_xclim_precip_indices",
        "XCLIM_AVAILABLE",
    }:
        module = import_module(".xclim_reference", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
