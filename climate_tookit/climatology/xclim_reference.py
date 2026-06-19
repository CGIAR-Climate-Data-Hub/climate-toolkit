"""Optional xclim-backed reference indicators for standard climate metrics."""

from __future__ import annotations

from importlib.util import find_spec
import logging
import warnings
from contextlib import contextmanager
from typing import Any

import pandas as pd


@contextmanager
def _suppress_xclim_import_noise():
    previous_disable = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Redefining .*")
            yield
    finally:
        logging.disable(previous_disable)


xr = None
xclim = None
daily_pr_intensity = None
max_1day_precipitation_amount = None
max_n_day_precipitation_amount = None
maximum_consecutive_dry_days = None
maximum_consecutive_wet_days = None
wetdays = None
_XCLIM_RUNTIME_LOADED = False
XCLIM_AVAILABLE = bool(find_spec("xarray")) and bool(find_spec("xclim"))


def _load_xclim_runtime() -> None:
    global xr, xclim, daily_pr_intensity, max_1day_precipitation_amount
    global max_n_day_precipitation_amount, maximum_consecutive_dry_days
    global maximum_consecutive_wet_days, wetdays, _XCLIM_RUNTIME_LOADED, XCLIM_AVAILABLE

    if _XCLIM_RUNTIME_LOADED:
        return
    if not XCLIM_AVAILABLE:
        raise RuntimeError("xclim is not installed in this environment.")

    try:
        with _suppress_xclim_import_noise():
            import xarray as _xr
            import xclim as _xclim
            from xclim.indicators.atmos import (
                daily_pr_intensity as _daily_pr_intensity,
                max_1day_precipitation_amount as _max_1day_precipitation_amount,
                max_n_day_precipitation_amount as _max_n_day_precipitation_amount,
                maximum_consecutive_dry_days as _maximum_consecutive_dry_days,
                maximum_consecutive_wet_days as _maximum_consecutive_wet_days,
                wetdays as _wetdays,
            )
    except Exception as exc:  # pragma: no cover - optional dependency runtime
        XCLIM_AVAILABLE = False
        raise RuntimeError("xclim is not installed in this environment.") from exc

    xr = _xr
    xclim = _xclim
    daily_pr_intensity = _daily_pr_intensity
    max_1day_precipitation_amount = _max_1day_precipitation_amount
    max_n_day_precipitation_amount = _max_n_day_precipitation_amount
    maximum_consecutive_dry_days = _maximum_consecutive_dry_days
    maximum_consecutive_wet_days = _maximum_consecutive_wet_days
    wetdays = _wetdays
    _XCLIM_RUNTIME_LOADED = True


def _ensure_xclim() -> None:
    if not XCLIM_AVAILABLE:
        raise RuntimeError("xclim is not installed in this environment.")
    _load_xclim_runtime()


def _build_precip_dataarray(
    frame: pd.DataFrame,
    *,
    value_column: str,
):
    _ensure_xclim()
    working = frame[["date", value_column]].copy()
    if working.empty:
        return None
    working["date"] = pd.to_datetime(working["date"])
    working = working.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    full_index = pd.date_range(working["date"].min(), working["date"].max(), freq="D")
    working = (
        working.set_index("date")
        .reindex(full_index)
        .rename_axis("date")
        .reset_index()
    )
    if value_column in working.columns:
        working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna(subset=[value_column]).reset_index(drop=True)
    if working.empty:
        return None
    full_series = (
        frame[["date", value_column]]
        .copy()
    )
    full_series["date"] = pd.to_datetime(full_series["date"])
    full_series = (
        full_series.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .set_index("date")
        .reindex(full_index)
    )
    return xr.DataArray(
        full_series[value_column].astype(float).to_numpy(),
        coords={"time": full_index.to_numpy()},
        dims="time",
        attrs={"units": "mm/day"},
    )


def _series_from_indicator(data_array, indicator, **kwargs) -> pd.Series:
    previous_disable = logging.root.manager.disable
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            logging.disable(logging.CRITICAL)
            with xclim.set_options(
                check_missing="pct",
                missing_options={"pct": {"tolerance": kwargs.pop("_missing_tolerance", 0.0)}},
                cf_compliance="log",
                data_validation="log",
            ):
                result = indicator(data_array, **kwargs)
        finally:
            logging.disable(previous_disable)
    index = pd.to_datetime(result["time"].values).date if "time" in result.coords else range(len(result.values))
    return pd.Series(result.values, index=index)


def _missing_tolerance_from_min_days(min_days_per_year: int) -> float:
    # Use leap-year denominator so threshold is conservative across mixed year lengths.
    return max(0.0, min(1.0, 1.0 - (float(min_days_per_year) / 366.0)))


def assess_xclim_precip_annual_readiness(
    frame: pd.DataFrame,
    *,
    value_column: str = "precipitation",
    min_days_per_year: int = 330,
) -> str | None:
    """Return None when annual xclim precip indices are safe to compute."""
    working = frame[["date", value_column]].copy()
    if working.empty:
        return "no non-null precipitation overlap"
    working["date"] = pd.to_datetime(working["date"])
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna(subset=[value_column]).sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    if len(working) < 3:
        return "fewer than 3 daily overlap rows"
    year_counts = working.groupby(working["date"].dt.year).size()
    sparse_years = year_counts[year_counts < int(min_days_per_year)]
    if not sparse_years.empty:
        parts = [f"{int(year)}={int(days)}d" for year, days in sparse_years.items()]
        return (
            "annual overlap too sparse for xclim reference indices; "
            f"need >= {int(min_days_per_year)} daily rows/year, got {', '.join(parts)}"
        )
    return None


def compute_xclim_precip_indices(
    frame: pd.DataFrame,
    *,
    value_column: str = "precipitation",
    freq: str = "YS",
    min_days_per_year: int = 330,
    dry_day_threshold: str = "1 mm/day",
    wet_day_threshold: str = "1 mm/day",
    heavy_day_threshold: str = "10 mm/day",
    very_heavy_day_threshold: str = "20 mm/day",
) -> pd.DataFrame:
    data_array = _build_precip_dataarray(frame, value_column=value_column)
    if data_array is None:
        return pd.DataFrame()
    missing_tolerance = _missing_tolerance_from_min_days(min_days_per_year)

    index_series = {
        "rx1day_mm": _series_from_indicator(
            data_array,
            max_1day_precipitation_amount,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "rx5day_mm": _series_from_indicator(
            data_array,
            max_n_day_precipitation_amount,
            window=5,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "cdd_days": _series_from_indicator(
            data_array,
            maximum_consecutive_dry_days,
            thresh=dry_day_threshold,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "cwd_days": _series_from_indicator(
            data_array,
            maximum_consecutive_wet_days,
            thresh=wet_day_threshold,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "r10mm_days": _series_from_indicator(
            data_array,
            wetdays,
            thresh=heavy_day_threshold,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "r20mm_days": _series_from_indicator(
            data_array,
            wetdays,
            thresh=very_heavy_day_threshold,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
        "sdii_mm_per_day": _series_from_indicator(
            data_array,
            daily_pr_intensity,
            thresh=wet_day_threshold,
            freq=freq,
            _missing_tolerance=missing_tolerance,
        ),
    }
    result = pd.DataFrame(index_series)
    if result.empty:
        return result
    result.index.name = "period_start"
    result = result.reset_index()
    for column in result.columns:
        if column != "period_start":
            result[column] = result[column].astype(float).round(4)
    result["period_start"] = result["period_start"].astype(str)
    return result


def compare_xclim_precip_indices(
    overlap: pd.DataFrame,
    *,
    station_column: str = "precipitation_station",
    grid_column: str = "precipitation_grid",
    freq: str = "YS",
    min_days_per_year: int = 330,
) -> list[dict[str, Any]]:
    station = compute_xclim_precip_indices(
        overlap.rename(columns={station_column: "precipitation"}),
        value_column="precipitation",
        freq=freq,
        min_days_per_year=min_days_per_year,
    )
    grid = compute_xclim_precip_indices(
        overlap.rename(columns={grid_column: "precipitation"}),
        value_column="precipitation",
        freq=freq,
        min_days_per_year=min_days_per_year,
    )
    if station.empty or grid.empty:
        return []
    merged = pd.merge(
        station,
        grid,
        on="period_start",
        how="inner",
        suffixes=("_station", "_grid"),
    )
    records: list[dict[str, Any]] = []
    for row in merged.to_dict(orient="records"):
        record: dict[str, Any] = {"period_start": row["period_start"]}
        for key, value in row.items():
            if key == "period_start":
                continue
            record[key] = value
        for metric in [
            "rx1day_mm",
            "rx5day_mm",
            "cdd_days",
            "cwd_days",
            "r10mm_days",
            "r20mm_days",
            "sdii_mm_per_day",
        ]:
            s_key = f"{metric}_station"
            g_key = f"{metric}_grid"
            if s_key in row and g_key in row:
                s_val = row[s_key]
                g_val = row[g_key]
                if pd.notna(s_val) and pd.notna(g_val):
                    record[f"{metric}_delta"] = round(float(g_val - s_val), 4)
        records.append(record)
    return records


__all__ = [
    "XCLIM_AVAILABLE",
    "assess_xclim_precip_annual_readiness",
    "compare_xclim_precip_indices",
    "compute_xclim_precip_indices",
]
