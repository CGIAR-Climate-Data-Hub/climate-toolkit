"""Vapour pressure deficit helpers built on xclim.

Toolkit uses xclim for VPD thermodynamics while preferring moisture-informed
inputs consistent with CHC workflows where available: relative humidity or
dewpoint, not temperature-only proxies.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any, Iterable, Optional, Sequence

import pandas as pd

XCLIM_AVAILABLE = bool(find_spec("xarray")) and bool(find_spec("xclim"))

_TMEAN_COLS = ("mean_temperature", "tavg", "temperature_c", "tas")
_TMAX_COLS = ("max_temperature", "tmax", "tasmax")
_TMIN_COLS = ("min_temperature", "tmin", "tasmin")
_HUMIDITY_COLS = ("humidity", "relative_humidity", "hurs", "RHAV", "rh")
_DEWPOINT_COLS = (
    "dewpoint",
    "dewpoint_temperature",
    "dewpoint_temperature_2m",
    "tdew",
)


def _detect_column(frame: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    return next((column for column in candidates if column in frame.columns), None)


def _ensure_xclim():
    if not XCLIM_AVAILABLE:
        raise RuntimeError("xclim is not installed in this environment.")
    import xarray as xr  # local import to avoid import-time side effects
    import xclim.indices as xci

    return xr, xci


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
        "VPD workflow needs mean temperature or both tmax and tmin."
    )


def _resolve_humidity(
    frame: pd.DataFrame,
    *,
    humidity_col: Optional[str] = None,
) -> tuple[pd.Series, str]:
    column = humidity_col or _detect_column(frame, _HUMIDITY_COLS)
    if not column:
        raise ValueError("Missing required humidity column for VPD workflow.")
    humidity = pd.to_numeric(frame[column], errors="coerce")
    valid = humidity.between(0.0, 100.0) | humidity.isna()
    if not bool(valid.all()):
        raise ValueError("Humidity values for VPD must be between 0 and 100 percent.")
    return humidity, column


def _resolve_dewpoint(
    frame: pd.DataFrame,
    *,
    dewpoint_col: Optional[str] = None,
) -> tuple[pd.Series, str]:
    column = dewpoint_col or _detect_column(frame, _DEWPOINT_COLS)
    if not column:
        raise ValueError("Missing required dewpoint column for VPD workflow.")
    return _to_numeric_celsius(frame[column]), column


def _threshold_columns(vpd_kpa: pd.Series, thresholds_kpa: Iterable[float]) -> dict[str, pd.Series]:
    columns: dict[str, pd.Series] = {}
    for threshold in thresholds_kpa:
        label = str(threshold).replace(".", "p")
        columns[f"days_above_{label}_kpa"] = (vpd_kpa > float(threshold)).astype(float)
    return columns


def compute_daily_vpd(
    frame: pd.DataFrame,
    *,
    date_col: str = "date",
    method: str = "auto",
    humidity_col: Optional[str] = None,
    dewpoint_col: Optional[str] = None,
    tmean_col: Optional[str] = None,
    tmax_col: Optional[str] = None,
    tmin_col: Optional[str] = None,
    xclim_method: str = "sonntag90",
) -> pd.DataFrame:
    """
    Compute daily VPD in kPa.

    Canonical paths use xclim:
    - relative humidity path via xclim.indices.vapor_pressure_deficit
    - dewpoint path via xclim.indices.saturation_vapor_pressure

    This matches CHC method family direction: moisture-informed derivation from
    relative humidity or dewpoint-backed actual vapour pressure, not
    temperature-only proxy estimates.
    """
    if date_col not in frame.columns:
        raise ValueError(f"Missing required date column: {date_col}")

    xr, xci = _ensure_xclim()
    out = frame.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out = out.sort_values(date_col).reset_index(drop=True)

    resolved_method = method
    if method == "auto":
        if humidity_col or _detect_column(out, _HUMIDITY_COLS):
            resolved_method = "relative_humidity"
        elif dewpoint_col or _detect_column(out, _DEWPOINT_COLS):
            resolved_method = "dewpoint"
        else:
            raise ValueError(
                "VPD auto mode needs humidity or dewpoint inputs."
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
        "temperature_source": temperature_source,
        "units": "kPa",
    }

    if resolved_method == "relative_humidity":
        humidity, humidity_source = _resolve_humidity(out, humidity_col=humidity_col)
        hurs_da = xr.DataArray(
            humidity.astype(float).to_numpy(),
            coords={"time": pd.to_datetime(out[date_col]).to_numpy()},
            dims="time",
            attrs={"units": "%"},
        )
        vpd_pa = xci.vapor_pressure_deficit(
            tas_da,
            hurs_da,
            method=xclim_method,
        )
        metadata.update(
            {
                "path": "relative_humidity",
                "humidity_source_column": humidity_source,
                "saturation_vapor_pressure_method": xclim_method,
            }
        )
    elif resolved_method == "dewpoint":
        dewpoint_c, dewpoint_source = _resolve_dewpoint(out, dewpoint_col=dewpoint_col)
        dew_da = _build_data_array(out[date_col], dewpoint_c, units="degC")
        saturation = xci.saturation_vapor_pressure(tas_da, method=xclim_method)
        actual = xci.saturation_vapor_pressure(dew_da, method=xclim_method)
        vpd_pa = saturation - actual
        metadata.update(
            {
                "path": "dewpoint",
                "dewpoint_source_column": dewpoint_source,
                "saturation_vapor_pressure_method": xclim_method,
            }
        )
    else:
        raise ValueError(
            "Unsupported VPD method. Use auto, relative_humidity, or dewpoint."
        )

    vpd_series = pd.Series(vpd_pa.values, index=out.index, dtype=float).clip(lower=0.0) / 1000.0
    out["temperature_c"] = temperature_c
    out["vpd_kpa"] = vpd_series
    out.attrs["vpd_metadata"] = metadata
    return out


def summarize_vpd_period(
    frame: pd.DataFrame,
    *,
    thresholds_kpa: Sequence[float] = (),
    **kwargs,
) -> Optional[dict[str, Any]]:
    try:
        vpd_df = compute_daily_vpd(frame, **kwargs)
    except (RuntimeError, ValueError):
        return None

    if "vpd_kpa" not in vpd_df.columns or vpd_df["vpd_kpa"].notna().sum() == 0:
        return None

    summary: dict[str, Any] = {
        "mean_vpd_kpa": round(float(vpd_df["vpd_kpa"].mean()), 3),
        "max_vpd_kpa": round(float(vpd_df["vpd_kpa"].max()), 3),
        "method": vpd_df.attrs.get("vpd_metadata", {}).get("path"),
    }
    for column_name, mask in _threshold_columns(vpd_df["vpd_kpa"], thresholds_kpa).items():
        summary[column_name] = int(mask.sum())
    return summary


__all__ = [
    "XCLIM_AVAILABLE",
    "compute_daily_vpd",
    "summarize_vpd_period",
]
