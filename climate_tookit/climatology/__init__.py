"""
Climatology Module

Long-term climate analysis including 30-year normal periods and trends.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "build_thi_hazard_thresholds",
    "classify_thi_values",
    "compute_monthly_spei",
    "compute_monthly_spi",
    "compute_daily_thi",
    "DEFAULT_LIVESTOCK_CLIMATE_PROFILE",
    "DEFAULT_LIVESTOCK_TYPE",
    "describe_thi_source_support",
    "infer_livestock_climate_profile",
    "list_thi_livestock_profiles",
    "prepare_monthly_climatic_water_balance",
    "prepare_monthly_precipitation_totals",
    "resolve_thi_profile",
    "summarize_thi_periods",
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
        "build_thi_hazard_thresholds",
        "classify_thi_values",
        "compute_daily_thi",
        "DEFAULT_LIVESTOCK_CLIMATE_PROFILE",
        "DEFAULT_LIVESTOCK_TYPE",
        "describe_thi_source_support",
        "infer_livestock_climate_profile",
        "list_thi_livestock_profiles",
        "resolve_thi_profile",
        "summarize_thi_periods",
    }:
        module = import_module(".heat_stress", __name__)
        return getattr(module, name)
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
