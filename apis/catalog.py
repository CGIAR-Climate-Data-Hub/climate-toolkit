"""Canonical option catalogs shared by the HTML UI.

Kept in one place so every page offers the same valid, current source keys
instead of drifting per-template hardcoded lists. Source keys here must match
``ClimateDataset`` in the toolkit.
"""

from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS as NEX_GDDP_MODELS,
)

# (value, label). `value` must be a valid toolkit source key (or 'auto', the
# recommended module mode that picks CHIRPS v3 + AgERA5 with fallbacks).
_SRC = {
    "auto": "Auto (recommended — CHIRPS v3 + AgERA5, with fallbacks)",
    "agera_5": "AgERA5 (temperature + precipitation)",
    "era_5": "ERA5 (reanalysis)",
    "nasa_power": "NASA POWER (temperature + precipitation)",
    "chirps_v3_daily_rnl": "CHIRPS v3 daily (precipitation)",
    "chirps_v2": "CHIRPS v2 (precipitation)",
    "chirts": "CHIRTS (temperature)",
    "terraclimate": "TerraClimate (monthly)",
    "imerg": "IMERG (precipitation)",
    "tamsat": "TAMSAT (precipitation)",
    "cmip_6": "CMIP6",
    "nex_gddp": "NEX-GDDP-CMIP6 (projections)",
}


def _opts(*keys):
    return [{"value": k, "label": _SRC[k]} for k in keys]


# The higher-level analysis modules (statistics/seasons/hazards/compare_periods)
# need daily temperature + precipitation together. Their recommended mode is
# 'auto'; standalone daily temp+precip sources also work. 'paired' is omitted
# here because it needs explicit --precip-source/--temp-source, which these
# forms do not yet collect. TerraClimate (monthly) is excluded from the daily
# analysis modules.
ANALYSIS_SOURCES = _opts("auto", "agera_5", "era_5", "nasa_power", "nex_gddp")

# Per-module source options (order = display order; first is the default).
SOURCES = {
    # Raw fetch needs an exact source key (no 'auto'/'paired').
    "fetch": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "chirts", "terraclimate", "imerg", "tamsat", "cmip_6", "nex_gddp",
    ),
    "statistics": ANALYSIS_SOURCES,
    "seasons": ANALYSIS_SOURCES,
    "hazards": ANALYSIS_SOURCES,
    "compare_periods": ANALYSIS_SOURCES,
    # Climatology takes a single source and works with partial data
    # (precip-only / temp-only allowed), so it lists concrete sources.
    "climatology": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "chirts", "terraclimate", "imerg", "nex_gddp",
    ),
    # Dataset comparison compares concrete individual sources.
    "compare_datasets": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "chirts", "terraclimate", "imerg", "nex_gddp",
    ),
}

# NEX-GDDP ensemble controls.
MODELS = list(NEX_GDDP_MODELS)
SCENARIOS = ["ssp245", "ssp585", "ssp126", "ssp370"]
