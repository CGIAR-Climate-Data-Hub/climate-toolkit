"""Optional xclim-backed reference indicators for standard climate metrics."""

from __future__ import annotations

from importlib.util import find_spec
import logging
import os
import sys
import warnings
from contextlib import contextmanager
from typing import Any, List, Optional

import pandas as pd
import typer

from ._cli_common import (
    build_frame_payload,
    build_status_payload,
    fetch_standardized_climate_frame,
    parse_location,
    render_frame_text,
    render_status_text,
    save_payload,
)


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
dry_days = None
precip_accumulation = None
max_1day_precipitation_amount = None
max_n_day_precipitation_amount = None
maximum_consecutive_dry_days = None
maximum_consecutive_wet_days = None
tg_mean = None
tn_mean = None
tn_min = None
tx_days_above = None
tx_max = None
tx_mean = None
standardized_index = None
wetdays = None
_XCLIM_RUNTIME_LOADED = False
XCLIM_AVAILABLE = bool(find_spec("xarray")) and bool(find_spec("xclim"))


def _load_xclim_runtime() -> None:
    global xr, xclim, daily_pr_intensity, dry_days, precip_accumulation
    global max_1day_precipitation_amount
    global max_n_day_precipitation_amount, maximum_consecutive_dry_days
    global maximum_consecutive_wet_days, tg_mean, tn_mean, tn_min, tx_days_above
    global tx_max, tx_mean, wetdays, standardized_index
    global _XCLIM_RUNTIME_LOADED, XCLIM_AVAILABLE

    if _XCLIM_RUNTIME_LOADED:
        return
    if not XCLIM_AVAILABLE:
        raise RuntimeError("xclim is not installed in this environment.")

    try:
        with _suppress_xclim_import_noise():
            import xarray as _xr
            import xclim as _xclim
            from xclim.indices.stats import standardized_index as _standardized_index
            from xclim.indicators.atmos import (
                daily_pr_intensity as _daily_pr_intensity,
                dry_days as _dry_days,
                precip_accumulation as _precip_accumulation,
                max_1day_precipitation_amount as _max_1day_precipitation_amount,
                max_n_day_precipitation_amount as _max_n_day_precipitation_amount,
                maximum_consecutive_dry_days as _maximum_consecutive_dry_days,
                maximum_consecutive_wet_days as _maximum_consecutive_wet_days,
                tg_mean as _tg_mean,
                tn_mean as _tn_mean,
                tn_min as _tn_min,
                tx_days_above as _tx_days_above,
                tx_max as _tx_max,
                tx_mean as _tx_mean,
                wetdays as _wetdays,
            )
    except Exception as exc:  # pragma: no cover - optional dependency runtime
        XCLIM_AVAILABLE = False
        raise RuntimeError("xclim is not installed in this environment.") from exc

    xr = _xr
    xclim = _xclim
    daily_pr_intensity = _daily_pr_intensity
    dry_days = _dry_days
    precip_accumulation = _precip_accumulation
    max_1day_precipitation_amount = _max_1day_precipitation_amount
    max_n_day_precipitation_amount = _max_n_day_precipitation_amount
    maximum_consecutive_dry_days = _maximum_consecutive_dry_days
    maximum_consecutive_wet_days = _maximum_consecutive_wet_days
    tg_mean = _tg_mean
    tn_mean = _tn_mean
    tn_min = _tn_min
    tx_days_above = _tx_days_above
    tx_max = _tx_max
    tx_mean = _tx_mean
    standardized_index = _standardized_index
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


def _build_series_dataarray(
    frame: pd.DataFrame,
    *,
    value_column: str,
    units: str,
    standard_name: str | None = None,
):
    _ensure_xclim()
    working = frame[["date", value_column]].copy()
    if working.empty:
        return None
    working["date"] = pd.to_datetime(working["date"])
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = (
        working.dropna(subset=[value_column])
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )
    if working.empty:
        return None
    attrs = {"units": units}
    if standard_name:
        attrs["standard_name"] = standard_name
    return xr.DataArray(
        working[value_column].astype(float).to_numpy(),
        coords={"time": working["date"].to_numpy()},
        dims="time",
        attrs=attrs,
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


def _series_from_indicator_skip_missing(data_array, indicator, **kwargs) -> pd.Series:
    previous_disable = logging.root.manager.disable
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            logging.disable(logging.CRITICAL)
            with xclim.set_options(
                check_missing="skip",
                cf_compliance="log",
                data_validation="log",
            ):
                result = indicator(data_array, **kwargs)
        finally:
            logging.disable(previous_disable)
    index = pd.to_datetime(result["time"].values) if "time" in result.coords else range(len(result.values))
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


def compute_xclim_core_period_metrics(
    frame: pd.DataFrame,
    *,
    precip_column: str = "precip",
    tmax_column: str = "tmax",
    tmin_column: str = "tmin",
    freq: str = "YS",
    wet_day_threshold: str = "1 mm/day",
    dry_day_threshold: str = "1 mm/day",
) -> pd.DataFrame:
    precip_da = _build_series_dataarray(
        frame,
        value_column=precip_column,
        units="mm/day",
        standard_name="lwe_thickness_of_precipitation_amount",
    )
    tmax_da = _build_series_dataarray(
        frame,
        value_column=tmax_column,
        units="degC",
        standard_name="air_temperature",
    )
    tmin_da = _build_series_dataarray(
        frame,
        value_column=tmin_column,
        units="degC",
        standard_name="air_temperature",
    )
    if precip_da is None or tmax_da is None or tmin_da is None:
        return pd.DataFrame()

    tavg_frame = frame[["date", tmax_column, tmin_column]].copy()
    tavg_frame["tavg"] = (
        pd.to_numeric(tavg_frame[tmax_column], errors="coerce")
        + pd.to_numeric(tavg_frame[tmin_column], errors="coerce")
    ) / 2.0
    tavg_da = _build_series_dataarray(
        tavg_frame,
        value_column="tavg",
        units="degC",
        standard_name="air_temperature",
    )
    if tavg_da is None:
        return pd.DataFrame()

    index_series = {
        "total_mm": _series_from_indicator_skip_missing(
            precip_da,
            precip_accumulation,
            freq=freq,
        ),
        "rainy_days": _series_from_indicator_skip_missing(
            precip_da,
            wetdays,
            thresh=wet_day_threshold,
            freq=freq,
        ),
        "dry_days": _series_from_indicator_skip_missing(
            precip_da,
            dry_days,
            thresh=dry_day_threshold,
            op="<",
            freq=freq,
        ),
        "max_daily": _series_from_indicator_skip_missing(
            precip_da,
            max_1day_precipitation_amount,
            freq=freq,
        ),
        "intensity": _series_from_indicator_skip_missing(
            precip_da,
            daily_pr_intensity,
            thresh=wet_day_threshold,
            freq=freq,
        ),
        "mean_tmax": _series_from_indicator_skip_missing(
            tmax_da,
            tx_mean,
            freq=freq,
        ),
        "mean_tmin": _series_from_indicator_skip_missing(
            tmin_da,
            tn_mean,
            freq=freq,
        ),
        "mean_tavg": _series_from_indicator_skip_missing(
            tavg_da,
            tg_mean,
            freq=freq,
        ),
        "max_tmax": _series_from_indicator_skip_missing(
            tmax_da,
            tx_max,
            freq=freq,
        ),
        "min_tmin": _series_from_indicator_skip_missing(
            tmin_da,
            tn_min,
            freq=freq,
        ),
    }

    result = pd.DataFrame(index_series)
    if result.empty:
        return result
    result.index.name = "period_start"
    result = result.reset_index()
    result["period_start"] = pd.to_datetime(result["period_start"]).astype(str)
    temperature_columns = {
        "mean_tmax",
        "mean_tmin",
        "mean_tavg",
        "max_tmax",
        "min_tmin",
    }
    for column in result.columns:
        if column == "period_start":
            continue
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if column in temperature_columns:
            result[column] = result[column].where(result[column] < 150.0, result[column] - 273.15)
        if column in {"rainy_days", "dry_days"}:
            result[column] = result[column].round(0)
        else:
            result[column] = result[column].round(4)
    return result


def compute_xclim_hazard_count_metrics(
    frame: pd.DataFrame,
    *,
    precip_column: str = "precip",
    tmax_column: str = "tmax",
    freq: str = "YS",
    dry_day_threshold: str = "1 mm/day",
    hot_day_threshold_35: str = "35 degC",
    hot_day_threshold_40: str = "40 degC",
) -> pd.DataFrame:
    precip_da = _build_series_dataarray(
        frame,
        value_column=precip_column,
        units="mm/day",
        standard_name="lwe_thickness_of_precipitation_amount",
    )
    tmax_da = _build_series_dataarray(
        frame,
        value_column=tmax_column,
        units="degC",
        standard_name="air_temperature",
    )
    if precip_da is None or tmax_da is None:
        return pd.DataFrame()

    index_series = {
        "NDD": _series_from_indicator_skip_missing(
            precip_da,
            dry_days,
            thresh=dry_day_threshold,
            op="<",
            freq=freq,
        ),
        "NTx35": _series_from_indicator_skip_missing(
            tmax_da,
            tx_days_above,
            thresh=hot_day_threshold_35,
            op=">=",
            freq=freq,
        ),
        "NTx40": _series_from_indicator_skip_missing(
            tmax_da,
            tx_days_above,
            thresh=hot_day_threshold_40,
            op=">=",
            freq=freq,
        ),
    }
    result = pd.DataFrame(index_series)
    if result.empty:
        return result
    result.index.name = "period_start"
    result = result.reset_index()
    result["period_start"] = pd.to_datetime(result["period_start"]).astype(str)
    for column in ("NDD", "NTx35", "NTx40"):
        result[column] = pd.to_numeric(result[column], errors="coerce").round(0)
    return result


def _compute_xclim_standardized_index_reference(
    monthly: pd.DataFrame,
    *,
    value_column: str,
    output_column: str,
    scale_months: int,
    dist: str = "fisk",
    method: str = "ML",
    ref_start: object | None = None,
    ref_end: object | None = None,
) -> pd.DataFrame:
    data_array = _build_series_dataarray(
        monthly,
        value_column=value_column,
        units="mm",
    )
    if data_array is None:
        return pd.DataFrame()

    previous_disable = logging.root.manager.disable
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            logging.disable(logging.CRITICAL)
            reference = standardized_index(
                data_array,
                freq="MS",
                window=scale_months,
                dist=dist,
                method=method,
                zero_inflated=False,
                fitkwargs=None,
                cal_start=None if ref_start is None else str(pd.Timestamp(ref_start).date()),
                cal_end=None if ref_end is None else str(pd.Timestamp(ref_end).date()),
            )
        finally:
            logging.disable(previous_disable)

    result = monthly[["date", "month"]].copy()
    result[output_column] = pd.Series(reference.values, index=result.index).astype(float)
    result.attrs["xclim_reference_metadata"] = {
        "distribution": dist,
        "fit": method,
        "scale_months": scale_months,
        "reference_period": {
            "start": None if ref_start is None else str(pd.Timestamp(ref_start).date()),
            "end": None if ref_end is None else str(pd.Timestamp(ref_end).date()),
        },
        "note": (
            "Nearest xclim standardized-index reference. "
            "Not exact parity with toolkit generalized-logistic ub-pwm method."
        ),
    }
    return result


def compute_xclim_spi_reference(
    frame: pd.DataFrame,
    *,
    scale_months: int = 3,
    date_col: str = "date",
    precip_col: str | None = None,
    dist: str = "fisk",
    method: str = "ML",
    ref_start: object | None = None,
    ref_end: object | None = None,
) -> pd.DataFrame:
    monthly = frame.copy()
    if "precipitation_mm" not in monthly.columns or "month" not in monthly.columns:
        from .spei import prepare_monthly_precipitation_totals

        monthly = prepare_monthly_precipitation_totals(
            frame,
            date_col=date_col,
            precip_col=precip_col,
        )
    return _compute_xclim_standardized_index_reference(
        monthly,
        value_column="precipitation_mm",
        output_column="spi_xclim",
        scale_months=scale_months,
        dist=dist,
        method=method,
        ref_start=ref_start,
        ref_end=ref_end,
    )


def compute_xclim_spei_reference(
    frame: pd.DataFrame,
    *,
    scale_months: int = 3,
    lat: float | None = None,
    date_col: str = "date",
    precip_col: str | None = None,
    et0_col: str | None = None,
    tmax_col: str | None = None,
    tmin_col: str | None = None,
    dist: str = "fisk",
    method: str = "ML",
    ref_start: object | None = None,
    ref_end: object | None = None,
) -> pd.DataFrame:
    monthly = frame.copy()
    if "water_balance_mm" not in monthly.columns or "month" not in monthly.columns:
        from .spei import prepare_monthly_climatic_water_balance

        monthly = prepare_monthly_climatic_water_balance(
            frame,
            lat=lat,
            date_col=date_col,
            precip_col=precip_col,
            et0_col=et0_col,
            tmax_col=tmax_col,
            tmin_col=tmin_col,
        )
    return _compute_xclim_standardized_index_reference(
        monthly,
        value_column="water_balance_mm",
        output_column="spei_xclim",
        scale_months=scale_months,
        dist=dist,
        method=method,
        ref_start=ref_start,
        ref_end=ref_end,
    )


__all__ = [
    "XCLIM_AVAILABLE",
    "assess_xclim_precip_annual_readiness",
    "compare_xclim_precip_indices",
    "compute_xclim_core_period_metrics",
    "compute_xclim_hazard_count_metrics",
    "compute_xclim_precip_indices",
    "compute_xclim_spei_reference",
    "compute_xclim_spi_reference",
]


app = typer.Typer(
    add_completion=False,
    help="Run xclim-backed reference and readiness helpers on toolkit climate inputs.",
)


@app.command()
def xclim_reference_cli(
    location: str = typer.Option(
        ...,
        "--location",
        help='Location as "lat,lon" (e.g., "-1.286,36.817")',
    ),
    source: str = typer.Option(
        ...,
        "--source",
        help="Input source (e.g., agera_5, paired, nasa_power, nex_gddp).",
    ),
    start: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", help="End date (YYYY-MM-DD)"),
    mode: str = typer.Option(
        "annual-readiness",
        "--mode",
        help=(
            "Reference helper mode: annual-readiness, precip-indices, core-period, "
            "hazard-counts, spi-reference, or spei-reference."
        ),
    ),
    scale_months: int = typer.Option(3, "--scale-months", help="SPI/SPEI scale in months."),
    freq: str = typer.Option(
        "YS",
        "--freq",
        help="Aggregation frequency for annual/period metrics (e.g., YS, QS-DEC, MS).",
    ),
    min_days_per_year: int = typer.Option(
        330,
        "--min-days-per-year",
        help="Minimum daily rows per year for annual precipitation readiness.",
    ),
    precip_source: Optional[str] = typer.Option(
        None,
        "--precip-source",
        help="Paired mode only. Precipitation source.",
    ),
    temp_source: Optional[str] = typer.Option(
        None,
        "--temp-source",
        help="Paired mode only. Temperature source.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="NEX-GDDP only. Single model name.",
    ),
    scenario: Optional[str] = typer.Option(
        None,
        "--scenario",
        help="NEX-GDDP only. Scenario name.",
    ),
    ref_start: Optional[str] = typer.Option(
        None,
        "--ref-start",
        help="Optional calibration/reference period start (YYYY-MM-DD).",
    ),
    ref_end: Optional[str] = typer.Option(
        None,
        "--ref-end",
        help="Optional calibration/reference period end (YYYY-MM-DD).",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, or csv.",
    ),
    output_path: Optional[str] = typer.Option(
        None,
        "--output",
        help="Optional output path for json/csv export.",
    ),
) -> None:
    normalized_mode = str(mode).strip().lower()
    normalized_format = str(output_format).strip().lower()
    valid_modes = {
        "annual-readiness",
        "precip-indices",
        "core-period",
        "hazard-counts",
        "spi-reference",
        "spei-reference",
    }
    if normalized_mode not in valid_modes:
        raise typer.BadParameter(
            f"Invalid mode '{mode}'. Valid options: {', '.join(sorted(valid_modes))}.",
            param_hint="--mode",
        )
    if normalized_format not in {"text", "json", "csv"}:
        raise typer.BadParameter(
            f"Invalid format '{output_format}'. Use 'text', 'json', or 'csv'.",
            param_hint="--format",
        )

    frame = fetch_standardized_climate_frame(
        location=location,
        source=source,
        start=start,
        end=end,
        precip_source=precip_source,
        temp_source=temp_source,
        model=model,
        scenario=scenario,
    )
    lat, _ = parse_location(location)
    metadata = {
        "frequency": freq,
        "scale_months": scale_months,
        "min_days_per_year": min_days_per_year,
        "precip_source": precip_source,
        "temp_source": temp_source,
        "model": model,
        "scenario": scenario,
        "ref_start": ref_start,
        "ref_end": ref_end,
    }

    if normalized_mode == "annual-readiness":
        message = assess_xclim_precip_annual_readiness(
            frame.rename(columns={"precip": "precipitation"}),
            value_column="precipitation",
            min_days_per_year=min_days_per_year,
        )
        ready = message is None
        payload = build_status_payload(
            tool="xclim-reference",
            mode=normalized_mode,
            ready=ready,
            message=message,
            location=location,
            source=source,
            start=start,
            end=end,
            extra={"parameters": metadata},
        )
        if normalized_format == "text":
            print(
                render_status_text(
                    title="xclim annual precipitation readiness",
                    ready=ready,
                    message=message,
                    extra={"parameters": metadata},
                )
            )
            return
        if not output_path:
            output_path = os.path.join(
                "outputs",
                "climatology",
                f"xclim_reference_{normalized_mode}_{source}_{start}_{end}.{normalized_format}",
            )
        saved_path = save_payload(
            payload=payload,
            frame=None,
            output_format=normalized_format,
            output_path=output_path,
        )
        print(f"xclim reference output saved: {saved_path}")
        return

    if normalized_mode == "precip-indices":
        result = compute_xclim_precip_indices(
            frame.rename(columns={"precip": "precipitation"}),
            value_column="precipitation",
            freq=freq,
            min_days_per_year=min_days_per_year,
        )
    elif normalized_mode == "core-period":
        result = compute_xclim_core_period_metrics(
            frame,
            precip_column="precip",
            tmax_column="tmax",
            tmin_column="tmin",
            freq=freq,
        )
    elif normalized_mode == "hazard-counts":
        result = compute_xclim_hazard_count_metrics(
            frame,
            precip_column="precip",
            tmax_column="tmax",
            freq=freq,
        )
    elif normalized_mode == "spi-reference":
        result = compute_xclim_spi_reference(
            frame,
            scale_months=scale_months,
            precip_col="precip",
            ref_start=ref_start,
            ref_end=ref_end,
        )
    else:
        result = compute_xclim_spei_reference(
            frame,
            scale_months=scale_months,
            lat=lat,
            precip_col="precip",
            tmax_col="tmax",
            tmin_col="tmin",
            ref_start=ref_start,
            ref_end=ref_end,
        )

    payload = build_frame_payload(
        tool="xclim-reference",
        mode=normalized_mode,
        frame=result,
        metadata=getattr(result, "attrs", {}).get("xclim_reference_metadata", {}),
        location=location,
        source=source,
        start=start,
        end=end,
        extra={"parameters": metadata},
    )
    if normalized_format == "text":
        print(
            render_frame_text(
                title=f"xclim reference output: {normalized_mode}",
                frame=result,
                metadata=getattr(result, "attrs", {}).get("xclim_reference_metadata", {}),
            )
        )
        return

    if not output_path:
        output_path = os.path.join(
            "outputs",
            "climatology",
            f"xclim_reference_{normalized_mode}_{source}_{start}_{end}.{normalized_format}",
        )
    saved_path = save_payload(
        payload=payload,
        frame=result,
        output_format=normalized_format,
        output_path=output_path,
    )
    print(f"xclim reference output saved: {saved_path}")


def main(argv: Optional[List[str]] = None) -> int:
    """Command-line entry point for xclim reference helpers."""
    command = typer.main.get_command(app)
    args = list(sys.argv[1:] if argv is None else argv)
    prog_name = os.path.basename(sys.argv[0]) if sys.argv else "climate-toolkit-xclim-reference"
    try:
        command.main(args=args, prog_name=prog_name, standalone_mode=False)
    except Exception as exc:
        if hasattr(exc, "show") and hasattr(exc, "exit_code"):
            exc.show()
            return int(exc.exit_code)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
