"""
Climatology Module

Long-term climate analysis including 30-year normal periods and trends.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "compute_monthly_spei",
    "compute_monthly_spi",
    "prepare_monthly_climatic_water_balance",
    "prepare_monthly_precipitation_totals",
    "assess_xclim_precip_annual_readiness",
    "compare_xclim_precip_indices",
    "compute_xclim_core_period_metrics",
    "compute_xclim_hazard_count_metrics",
    "compute_xclim_precip_indices",
    "compute_xclim_spei_reference",
    "compute_xclim_spi_reference",
    "XCLIM_AVAILABLE",
]


def __getattr__(name: str):
    if name in {
        "compute_monthly_spei",
        "compute_monthly_spi",
        "prepare_monthly_climatic_water_balance",
        "prepare_monthly_precipitation_totals",
    }:
        module = import_module(".spei", __name__)
        return getattr(module, name)
    if name in {
        "assess_xclim_precip_annual_readiness",
        "compare_xclim_precip_indices",
        "compute_xclim_core_period_metrics",
        "compute_xclim_hazard_count_metrics",
        "compute_xclim_precip_indices",
        "compute_xclim_spei_reference",
        "compute_xclim_spi_reference",
        "XCLIM_AVAILABLE",
    }:
        module = import_module(".xclim_reference", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
