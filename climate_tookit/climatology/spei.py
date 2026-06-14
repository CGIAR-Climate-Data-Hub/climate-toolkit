"""
SPEI helpers built on monthly climatic water balance.

This module computes a monthly precipitation minus ET0 series and an
empirical-normal standardized index grouped by calendar month. It is intended
as a practical package foundation for SPEI-style drought analysis without
requiring SciPy's parametric log-logistic fitting.
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Optional, Tuple

import pandas as pd

DEFAULT_MIN_POINTS_PER_MONTH = 8
_PRECIP_COLS = ("precipitation", "precip", "pr", "rainfall")
_TMAX_COLS = ("max_temperature", "tmax", "tasmax", "temperature_max")
_TMIN_COLS = ("min_temperature", "tmin", "tasmin", "temperature_min")
_MONTHLY_PRECIP_TOTAL_COLS = ("precipitation_mm", "precip_mm", "monthly_precipitation_mm")
_MONTHLY_ET0_TOTAL_COLS = ("et0_mm", "monthly_et0_mm", "pet_mm")


def _detect_column(df: pd.DataFrame, candidates: Tuple[str, ...]) -> Optional[str]:
    return next((col for col in candidates if col in df.columns), None)


def _ensure_datetime(frame: pd.DataFrame, date_col: str) -> pd.DataFrame:
    out = frame.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    return out.sort_values(date_col).reset_index(drop=True)


def _infer_input_resolution(frame: pd.DataFrame, date_col: str) -> str:
    month_keys = frame[date_col].dt.to_period("M")
    return "daily" if int(month_keys.nunique()) < len(frame) else "monthly"


def _daily_with_et0(
    frame: pd.DataFrame,
    lat: Optional[float],
    precip_col: str,
    et0_col: Optional[str],
    tmax_col: Optional[str],
    tmin_col: Optional[str],
) -> pd.DataFrame:
    if et0_col and et0_col in frame.columns:
        return frame.rename(columns={precip_col: "precipitation", et0_col: "ET0_mm_day"})

    if lat is None or not tmax_col or not tmin_col:
        raise ValueError(
            "Daily SPEI preparation needs ET0_mm_day or lat+tmax+tmin so ET0 can be derived."
        )

    from climate_tookit.season_analysis.seasons import add_et0

    renamed = frame.rename(
        columns={
            precip_col: "precip",
            tmax_col: "tmax",
            tmin_col: "tmin",
        }
    )
    with_et0 = add_et0(renamed, lat)
    return with_et0.rename(columns={"precip": "precipitation"})


def prepare_monthly_climatic_water_balance(
    df: pd.DataFrame,
    lat: Optional[float] = None,
    date_col: str = "date",
    precip_col: Optional[str] = None,
    et0_col: Optional[str] = None,
    tmax_col: Optional[str] = None,
    tmin_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Aggregate daily or monthly climate inputs into monthly water balance totals.

    Daily inputs:
    - precipitation column required
    - ET0_mm_day preferred, otherwise lat+tmax+tmin are used to derive ET0

    Monthly inputs:
    - precipitation total and ET0 total must already be present
    """
    if date_col not in df.columns:
        raise ValueError(f"Missing required date column: {date_col}")
    if "site" in df.columns and df["site"].nunique(dropna=True) > 1:
        raise ValueError(
            "SPEI helpers currently expect a single site per call. Split multi-site frames first."
        )

    frame = _ensure_datetime(df, date_col)
    resolution = _infer_input_resolution(frame, date_col)

    precip_col = precip_col or _detect_column(frame, _PRECIP_COLS) or _detect_column(frame, _MONTHLY_PRECIP_TOTAL_COLS)
    et0_col = et0_col or _detect_column(frame, ("ET0_mm_day",)) or _detect_column(frame, _MONTHLY_ET0_TOTAL_COLS)
    tmax_col = tmax_col or _detect_column(frame, _TMAX_COLS)
    tmin_col = tmin_col or _detect_column(frame, _TMIN_COLS)

    if not precip_col:
        raise ValueError("Could not find a precipitation column for SPEI preparation.")

    if resolution == "daily":
        daily = _daily_with_et0(
            frame,
            lat=lat,
            precip_col=precip_col,
            et0_col=et0_col,
            tmax_col=tmax_col,
            tmin_col=tmin_col,
        )
        daily["month_start"] = daily[date_col].dt.to_period("M").dt.to_timestamp()
        monthly = (
            daily.groupby("month_start", as_index=False)
            .agg(
                precipitation_mm=("precipitation", "sum"),
                et0_mm=("ET0_mm_day", "sum"),
            )
            .rename(columns={"month_start": "date"})
        )
    else:
        monthly_et0_col = et0_col
        if not monthly_et0_col:
            raise ValueError(
                "Monthly SPEI preparation needs an ET0 total column when daily data are not supplied."
            )
        monthly = pd.DataFrame(
            {
                "date": frame[date_col].dt.to_period("M").dt.to_timestamp(),
                "precipitation_mm": frame[precip_col].astype(float),
                "et0_mm": frame[monthly_et0_col].astype(float),
            }
        )

    monthly["water_balance_mm"] = monthly["precipitation_mm"] - monthly["et0_mm"]
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month
    monthly.attrs["spei_metadata"] = {
        "input_resolution": resolution,
        "et0_source": "existing_column" if et0_col else "season_analysis.add_et0_hargreaves",
        "water_balance_definition": "monthly precipitation total minus monthly ET0 total",
    }
    return monthly


def _empirical_normal_scores(series: pd.Series, min_points: int) -> pd.Series:
    non_null = series.dropna()
    if len(non_null) < min_points:
        return pd.Series(index=series.index, dtype=float)

    ranks = non_null.rank(method="average")
    probs = ((ranks - 0.44) / (len(non_null) + 0.12)).clip(1e-6, 1 - 1e-6)
    dist = NormalDist()
    transformed = probs.map(dist.inv_cdf)
    return transformed.reindex(series.index)


def compute_monthly_spei(
    df: pd.DataFrame,
    scale_months: int = 3,
    lat: Optional[float] = None,
    min_points_per_calendar_month: int = DEFAULT_MIN_POINTS_PER_MONTH,
    date_col: str = "date",
    precip_col: Optional[str] = None,
    et0_col: Optional[str] = None,
    tmax_col: Optional[str] = None,
    tmin_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Compute a monthly SPEI-style index from daily or monthly climate inputs.

    The returned `spei` values use empirical normal scores by calendar month.
    This is suitable as a package-level drought indicator foundation while a
    future parametric SPEI fit is evaluated separately.
    """
    if scale_months < 1:
        raise ValueError("scale_months must be >= 1")

    monthly = prepare_monthly_climatic_water_balance(
        df,
        lat=lat,
        date_col=date_col,
        precip_col=precip_col,
        et0_col=et0_col,
        tmax_col=tmax_col,
        tmin_col=tmin_col,
    ).copy()
    monthly["water_balance_accumulated_mm"] = (
        monthly["water_balance_mm"]
        .rolling(window=scale_months, min_periods=scale_months)
        .sum()
    )
    monthly["spei"] = (
        monthly.groupby("month", group_keys=False)["water_balance_accumulated_mm"]
        .apply(lambda s: _empirical_normal_scores(s, min_points=min_points_per_calendar_month))
    )
    monthly.attrs["spei_metadata"] = {
        **monthly.attrs.get("spei_metadata", {}),
        "scale_months": scale_months,
        "index_name": "SPEI",
        "standardization_method": "empirical_normal_by_calendar_month",
        "min_points_per_calendar_month": min_points_per_calendar_month,
        "note": (
            "Uses empirical normal scores rather than a fitted log-logistic distribution. "
            "Keep this distinction explicit in user-facing interpretation."
        ),
    }
    return monthly
