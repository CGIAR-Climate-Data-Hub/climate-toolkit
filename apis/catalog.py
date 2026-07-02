"""Canonical option catalogs shared by the HTML UI.

Kept in one place so every page offers the same valid, current source keys
instead of drifting per-template hardcoded lists. Source keys here must match
``ClimateDataset`` in the toolkit.
"""

from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS as NEX_GDDP_MODELS,
)

# (value, label). `value` must be a valid toolkit source key.
_SRC = {
    "agera_5": "AgERA5 (temperature + precipitation)",
    "era_5": "ERA5 (reanalysis)",
    "nasa_power": "NASA POWER",
    "chirps_v3_daily_rnl": "CHIRPS v3 daily (precipitation)",
    "chirps_v2": "CHIRPS v2 (precipitation)",
    "chirts": "CHIRTS (temperature)",
    "terraclimate": "TerraClimate",
    "imerg": "IMERG (precipitation)",
    "tamsat": "TAMSAT (precipitation)",
    "cmip_6": "CMIP6",
    "nex_gddp": "NEX-GDDP-CMIP6 (projections)",
}


def _opts(*keys):
    return [{"value": k, "label": _SRC[k]} for k in keys]


# Sources that expose both temperature and precipitation, so they work as a
# single standalone source for the higher-level analysis modules.
FULL_SOURCES = _opts("agera_5", "era_5", "nasa_power", "terraclimate")

# Per-module source options (order = display order; first is the default).
SOURCES = {
    # Raw fetch supports every source.
    "fetch": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "chirts", "terraclimate", "imerg", "tamsat", "cmip_6", "nex_gddp",
    ),
    # Analysis modules need temp+precip together; offer the full sources plus
    # NEX-GDDP for projection workflows.
    "statistics": FULL_SOURCES + _opts("nex_gddp"),
    "seasons": FULL_SOURCES + _opts("nex_gddp"),
    "hazards": FULL_SOURCES + _opts("nex_gddp"),
    "compare_periods": FULL_SOURCES + _opts("nex_gddp"),
    # Climatology works with partial data (precip-only / temp-only allowed).
    "climatology": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "chirts", "terraclimate", "imerg", "nex_gddp",
    ),
    # Dataset comparison: any gridded sources.
    "compare_datasets": _opts(
        "agera_5", "era_5", "nasa_power", "chirps_v3_daily_rnl", "chirps_v2",
        "terraclimate", "nex_gddp",
    ),
}

# NEX-GDDP ensemble controls.
MODELS = list(NEX_GDDP_MODELS)
SCENARIOS = ["ssp245", "ssp585", "ssp126", "ssp370"]
