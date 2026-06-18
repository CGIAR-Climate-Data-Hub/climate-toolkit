"""
Climatology Module

Long-term climate analysis including 30-year normal periods and trends.
"""

__all__ = []

from .spei import compute_monthly_spei, prepare_monthly_climatic_water_balance

__all__.extend(
    [
        "compute_monthly_spei",
        "prepare_monthly_climatic_water_balance",
    ]
)

from .xclim_reference import (
    XCLIM_AVAILABLE,
    assess_xclim_precip_annual_readiness,
    compare_xclim_precip_indices,
    compute_xclim_precip_indices,
)

__all__.extend(
    [
        "assess_xclim_precip_annual_readiness",
        "compare_xclim_precip_indices",
        "compute_xclim_precip_indices",
        "XCLIM_AVAILABLE",
    ]
)
