"""
Climatology Module

Long-term climate analysis including 30-year normal periods and trends.
"""

from .spei import compute_monthly_spei, prepare_monthly_climatic_water_balance

__all__ = [
    "compute_monthly_spei",
    "prepare_monthly_climatic_water_balance",
]
