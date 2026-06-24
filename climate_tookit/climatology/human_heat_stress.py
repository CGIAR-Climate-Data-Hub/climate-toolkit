"""Human heat-stress helpers.

Phase 1 chooses xclim-backed Humidex as first operational human heat metric.

Why Humidex first:
- works from mean temperature plus humidity or dewpoint
- aligns with current package source coverage better than WBGT / UTCI
- available through xclim

Why not WBGT / UTCI first:
- both need broader input support, especially wind and radiation / mean radiant
  temperature, than package currently has across future workflows
- current NEX-GDDP path can provide temperature plus conditional humidity, but
  not coherent wind / radiation support for operational human heat metrics
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any, Optional, Sequence

import pandas as pd

XCLIM_AVAILABLE = bool(find_spec("xarray")) and bool(find_spec("xclim"))

_TMEAN_COLS = ("mean_temperature", "tavg", "tmean", "temperature", "temp", "tas")
_TMAX_COLS = ("max_temperature", "tmax", "tasmax")
_TMIN_COLS = ("min_temperature", "tmin", "tasmin")
_HUMIDITY_COLS = ("humidity", "relative_humidity", "hurs", "RHAV", "rh")
_DEWPOINT_COLS = (
    "dewpoint",
    "dewpoint_temperature",
    "dewpoint_temperature_2m",
    "tdew",
    "tdps",
)

_HUMAN_HEAT_SOURCE_SUPPORT = {
    "agera_5": (
        "supported: humidity available via current dewpoint + air-temperature derivation; "
        "best first-pass historical source"
    ),
    "nasa_power": "supported: humidity available in current POWER fetch path",
    "ghcn_daily": "supported when RHAV humidity field exists for chosen station and window",
    "gsod": "supported when humidity field exists for chosen station and window",
    "custom_station": "supported when uploaded file includes humidity / RH or dewpoint column",
    "nex_gddp": (
        "conditionally supported for humidex only: can use hurs when present, but some GEE "
        "model/scenario combinations lack that band"
    ),
    "era_5": (
        "uncertain: current toolkit ERA5 fetch configuration does not expose operational humidity "
        "support for human heat workflow"
    ),
    "chirps_v2": "not supported: precipitation-only source",
    "chirps_v3_daily_rnl": "not supported: precipitation-only source",
    "imerg": "not supported: precipitation-only source",
    "tamsat": "not supported: precipitation-only source",
    "chirts": "not supported: temperature-only source",
}


def _ensure_xclim():
    if not XCLIM_AVAILABLE:
        raise RuntimeError("xclim is not installed in this environment.")
    import xarray as xr  # local import to avoid import-time side effects
    import xclim.indices as xci

    return xr, xci


def _detect_column(frame: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    return next((column for column in candidates if column in frame.columns), None)


def _to_numeric_celsius(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    clean = values.dropna()
    if not clean.empty and float(clean.mean()) > 100.0:
        return values - 273.15
    return values


def _build_data_array(dates: pd.Series, values: pd.Series, *, units: str):
    xr, _ = _ensure_xclim()
    return xr.DataArray(
        pd.to_numeric(values, errors="coerce").astype(float).to_numpy(),
        coords={"time": pd.to_datetime(dates).to_numpy()},
        dims="time",
        attrs={"units": units},
    )


def _resolve_temperature(
    frame: pd.DataFrame,
    *,
    tmean_col: Optional[str] = None,
    tmax_col: Optional[str] = None,
    tmin_col: Optional[str] = None,
) -> tuple[pd.Series, str]:
    mean_column = tmean_col or _detect_column(frame, _TMEAN_COLS)
    if mean_column:
        return _to_numeric_celsius(frame[mean_column]), mean_column

    max_column = tmax_col or _detect_column(frame, _TMAX_COLS)
    min_column = tmin_col or _detect_column(frame, _TMIN_COLS)
    if max_column and min_column:
        tmax = _to_numeric_celsius(frame[max_column])
        tmin = _to_numeric_celsius(frame[min_column])
        return (tmax + tmin) / 2.0, "derived_from_tmax_tmin"

    raise ValueError(
        "Human heat workflow needs mean temperature or both tmax and tmin."
    )


def _resolve_humidity(
    frame: pd.DataFrame,
    *,
    humidity_col: Optional[str] = None,
) -> tuple[pd.Series, str]:
    column = humidity_col or _detect_column(frame, _HUMIDITY_COLS)
    if not column:
        raise ValueError("Missing required humidity column for humidex workflow.")
    humidity = pd.to_numeric(frame[column], errors="coerce")
    valid = humidity.between(0.0, 100.0) | humidity.isna()
    if not bool(valid.all()):
        raise ValueError("Humidity values for humidex must be between 0 and 100 percent.")
    return humidity, column


def _resolve_dewpoint(
    frame: pd.DataFrame,
    *,
    dewpoint_col: Optional[str] = None,
) -> tuple[pd.Series, str]:
    column = dewpoint_col or _detect_column(frame, _DEWPOINT_COLS)
    if not column:
        raise ValueError("Missing required dewpoint column for humidex workflow.")
    return _to_numeric_celsius(frame[column]), column


def compute_daily_humidex(
    frame: pd.DataFrame,
    *,
    date_col: str = "date",
    method: str = "auto",
    humidity_col: Optional[str] = None,
    dewpoint_col: Optional[str] = None,
    tmean_col: Optional[str] = None,
    tmax_col: Optional[str] = None,
    tmin_col: Optional[str] = None,
) -> pd.DataFrame:
    """Compute daily Humidex using xclim.

    Auto mode prefers dewpoint when available, else relative humidity.
    """
    if date_col not in frame.columns:
        raise ValueError(f"Missing required date column: {date_col}")

    _, xci = _ensure_xclim()
    out = frame.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out = out.sort_values(date_col).reset_index(drop=True)

    resolved_method = str(method or "auto").strip().lower()
    if resolved_method == "auto":
        if dewpoint_col or _detect_column(out, _DEWPOINT_COLS):
            resolved_method = "dewpoint"
        elif humidity_col or _detect_column(out, _HUMIDITY_COLS):
            resolved_method = "relative_humidity"
        else:
            raise ValueError(
                "Humidex auto mode needs humidity or dewpoint inputs."
            )

    temperature_c, temperature_source = _resolve_temperature(
        out,
        tmean_col=tmean_col,
        tmax_col=tmax_col,
        tmin_col=tmin_col,
    )
    tas_da = _build_data_array(out[date_col], temperature_c, units="degC")
    metadata: dict[str, Any] = {
        "backend": "xclim",
        "metric": "humidex",
        "temperature_source": temperature_source,
        "phase1_scope": "continuous_metric_only",
    }

    if resolved_method == "dewpoint":
        dewpoint_c, dewpoint_source = _resolve_dewpoint(out, dewpoint_col=dewpoint_col)
        dew_da = _build_data_array(out[date_col], dewpoint_c, units="degC")
        humidex = xci.humidex(tas_da, tdps=dew_da)
        metadata.update(
            {
                "path": "dewpoint",
                "dewpoint_source_column": dewpoint_source,
            }
        )
    elif resolved_method == "relative_humidity":
        humidity, humidity_source = _resolve_humidity(out, humidity_col=humidity_col)
        hurs_da = _build_data_array(out[date_col], humidity, units="%")
        humidex = xci.humidex(tas_da, hurs=hurs_da)
        metadata.update(
            {
                "path": "relative_humidity",
                "humidity_source_column": humidity_source,
            }
        )
    else:
        raise ValueError(
            "Unsupported humidex method. Use auto, dewpoint, or relative_humidity."
        )

    out["temperature_c"] = temperature_c
    out["humidex"] = pd.Series(humidex.values, index=out.index, dtype=float)
    out.attrs["human_heat_metadata"] = metadata
    return out


def summarize_humidex_period(frame: pd.DataFrame, **kwargs) -> Optional[dict[str, Any]]:
    try:
        humidex_df = compute_daily_humidex(frame, **kwargs)
    except (RuntimeError, ValueError):
        return None

    if "humidex" not in humidex_df.columns or humidex_df["humidex"].notna().sum() == 0:
        return None

    return {
        "mean_humidex": round(float(humidex_df["humidex"].mean()), 3),
        "max_humidex": round(float(humidex_df["humidex"].max()), 3),
        "method": humidex_df.attrs.get("human_heat_metadata", {}).get("path"),
        "phase1_scope": "continuous_metric_only",
    }


def describe_human_heat_source_support() -> dict[str, str]:
    """Return current source-support notes for phase 1 human heat metric."""
    return dict(_HUMAN_HEAT_SOURCE_SUPPORT)


def describe_human_heat_method() -> dict[str, Any]:
    """Return phase 1 human heat method choice and rationale."""
    return {
        "metric": "humidex",
        "backend": "xclim",
        "phase1_status": "selected_for_initial_support",
        "phase1_scope": "continuous_metric_only",
        "default_daily_workflow": "daily mean temperature plus humidity or dewpoint",
        "source_support": describe_human_heat_source_support(),
        "candidate_review": {
            "humidex": (
                "chosen for first pass because xclim supports it directly and package can "
                "supply required inputs across historical workflows and conditional future humidity paths"
            ),
            "heat_index": (
                "not chosen as phase-1 default because xclim notes validity only above 20C and "
                "equation assumes instantaneous temperature and humidity values"
            ),
            "utci": (
                "deferred because operational workflow needs wind plus mean-radiant-temperature or "
                "radiation inputs not coherently available across current future source paths"
            ),
            "wbgt": (
                "deferred because operational workflow needs broader radiation / wind treatment than "
                "current package future workflows support"
            ),
        },
        "input_requirements": {
            "temperature": "mean temperature, or derived mean from tmax+tmin",
            "moisture": "relative humidity in percent or dewpoint temperature",
        },
        "interpretation_caveats": [
            "Phase 1 provides continuous human heat metric support, not hazard-band semantics.",
            "Humidex is more feasible than UTCI/WBGT for current package source coverage, not necessarily universally superior physiologically.",
            "Future-path support depends on humidity availability; current NEX-GDDP path remains conditional on hurs presence.",
        ],
        "next_steps": [
            "review whether phase 2 should add generic humidex screening classes or skip directly to UTCI/WBGT where inputs allow",
            "add package-surface integration into climate_statistics, compare_periods, and hazards after method choice is accepted",
            "revisit UTCI / WBGT when coherent wind and radiation support exists across intended workflows",
        ],
    }


__all__ = [
    "XCLIM_AVAILABLE",
    "compute_daily_humidex",
    "describe_human_heat_method",
    "describe_human_heat_source_support",
    "summarize_humidex_period",
]
