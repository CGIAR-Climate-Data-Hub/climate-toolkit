"""
Real NEX-GDDP adapter.

This module is main package entry point for NEX-GDDP access. It delegates to
Earth Engine + Xee implementation in `nex_gddp_xee.py` and exposes stable
symbols used elsewhere in toolkit.
"""

from .nex_gddp_xee import (
    DEFAULT_DATASET_VERSION,
    SCENARIO_MAPPING,
    DownloadData,
    _normalize_scenario,
    _validate_period_against_scenario,
)

AVAILABLE_MODELS = [
    "ACCESS-CM2",
    "ACCESS-ESM1-5",
    "CanESM5",
    "CMCC-ESM2",
    "EC-Earth3",
    "EC-Earth3-Veg-LR",
    "GFDL-ESM4",
    "INM-CM4-8",
    "INM-CM5-0",
    "IPSL-CM6A-LR",
    "KACE-1-0-G",
    "MIROC6",
    "MPI-ESM1-2-HR",
    "MPI-ESM1-2-LR",
    "MRI-ESM2-0",
    "NorESM2-LM",
    "NorESM2-MM",
    "TaiESM1",
]

AFRICA_DEFAULT_ENSEMBLE_MODELS = [
    model for model in AVAILABLE_MODELS if model != "CanESM5"
]


def is_africa_coordinate(lat: float, lon: float) -> bool:
    return -35.0 <= lat <= 38.0 and -20.0 <= lon <= 55.0


def default_ensemble_models_for_location(
    location_coord,
    models=None,
    exclude_models=None,
):
    if models:
        active = list(models)
    else:
        lat, lon = location_coord
        active = (
            list(AFRICA_DEFAULT_ENSEMBLE_MODELS)
            if is_africa_coordinate(lat, lon)
            else list(AVAILABLE_MODELS)
        )

    if exclude_models:
        excluded = {model.upper() for model in exclude_models}
        active = [model for model in active if model.upper() not in excluded]
    return active

__all__ = [
    "AVAILABLE_MODELS",
    "AFRICA_DEFAULT_ENSEMBLE_MODELS",
    "DEFAULT_DATASET_VERSION",
    "SCENARIO_MAPPING",
    "DownloadData",
    "default_ensemble_models_for_location",
    "is_africa_coordinate",
    "_normalize_scenario",
    "_validate_period_against_scenario",
]
