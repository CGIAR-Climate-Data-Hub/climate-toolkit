"""
SPEI / SPI helpers built on monthly climate aggregates.

Standard SPEI workflow follows Vicente-Serrano et al. (2010) and the CRAN
SPEI package defaults:
1. Monthly climatic water balance = precipitation - PET/ET0
2. Aggregate to requested scale
3. Fit month-wise log-logistic / generalized logistic distribution
4. Transform fitted cumulative probability to standard normal z-scores

This module defaults to unbiased PWM fitting of the generalized logistic
distribution, which is much closer to established SPEI practice than an
empirical z-score shortcut. An explicit empirical fallback is still available.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Dict, Optional, Tuple

import pandas as pd

DEFAULT_MIN_POINTS_PER_MONTH = 4
_CDF_EPSILON = 1e-12
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

    precip_col = (
        precip_col
        or _detect_column(frame, _PRECIP_COLS)
        or _detect_column(frame, _MONTHLY_PRECIP_TOTAL_COLS)
    )
    et0_col = (
        et0_col
        or _detect_column(frame, ("ET0_mm_day",))
        or _detect_column(frame, _MONTHLY_ET0_TOTAL_COLS)
    )
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
        if not et0_col:
            raise ValueError(
                "Monthly SPEI preparation needs an ET0 total column when daily data are not supplied."
            )
        monthly = pd.DataFrame(
            {
                "date": frame[date_col].dt.to_period("M").dt.to_timestamp(),
                "precipitation_mm": frame[precip_col].astype(float),
                "et0_mm": frame[et0_col].astype(float),
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


def prepare_monthly_precipitation_totals(
    df: pd.DataFrame,
    date_col: str = "date",
    precip_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Aggregate daily or monthly precipitation inputs into monthly totals for SPI.
    """
    if date_col not in df.columns:
        raise ValueError(f"Missing required date column: {date_col}")
    if "site" in df.columns and df["site"].nunique(dropna=True) > 1:
        raise ValueError(
            "SPI helpers currently expect a single site per call. Split multi-site frames first."
        )

    frame = _ensure_datetime(df, date_col)
    resolution = _infer_input_resolution(frame, date_col)
    precip_col = (
        precip_col
        or _detect_column(frame, _PRECIP_COLS)
        or _detect_column(frame, _MONTHLY_PRECIP_TOTAL_COLS)
    )
    if not precip_col:
        raise ValueError("Could not find a precipitation column for SPI preparation.")

    if resolution == "daily":
        working = frame.rename(columns={precip_col: "precipitation"})
        working["month_start"] = working[date_col].dt.to_period("M").dt.to_timestamp()
        monthly = (
            working.groupby("month_start", as_index=False)
            .agg(precipitation_mm=("precipitation", "sum"))
            .rename(columns={"month_start": "date"})
        )
    else:
        monthly = pd.DataFrame(
            {
                "date": frame[date_col].dt.to_period("M").dt.to_timestamp(),
                "precipitation_mm": frame[precip_col].astype(float),
            }
        )

    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month
    monthly.attrs["spei_metadata"] = {
        "input_resolution": resolution,
        "aggregation_definition": "monthly precipitation total",
    }
    return monthly


def _unbiased_pwm(values: pd.Series) -> Optional[Tuple[float, float, float]]:
    clean = [float(v) for v in values if pd.notna(v)]
    clean.sort()
    n = len(clean)
    if n < 4:
        return None

    betas = []
    for order in range(3):
        denom = math.comb(n - 1, order)
        weighted_sum = 0.0
        for idx, value in enumerate(clean):
            weight = math.comb(idx, order) / denom if idx >= order else 0.0
            weighted_sum += weight * value
        betas.append(weighted_sum / n)
    return tuple(betas)


def _lmoments_from_pwms(pwms: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    beta0, beta1, beta2 = pwms
    l1 = beta0
    l2 = 2.0 * beta1 - beta0
    if l2 == 0 or not math.isfinite(l2):
        return None
    l3 = 6.0 * beta2 - 6.0 * beta1 + beta0
    t3 = l3 / l2
    if not all(math.isfinite(v) for v in (l1, l2, t3)):
        return None
    return l1, l2, t3


def _fit_generalized_logistic_ub_pwm(values: pd.Series) -> Optional[Dict[str, float]]:
    pwms = _unbiased_pwm(values)
    if pwms is None:
        return None
    lmom = _lmoments_from_pwms(pwms)
    if lmom is None:
        return None

    l1, l2, t3 = lmom
    kappa = -t3
    if abs(kappa) >= 1:
        return None

    if abs(kappa) <= 1e-6:
        xi = l1
        alpha = l2
        kappa = 0.0
    else:
        kk = kappa * math.pi / math.sin(kappa * math.pi)
        alpha = l2 / kk
        xi = l1 - alpha * (1.0 - kk) / kappa

    if not math.isfinite(alpha) or alpha <= 0:
        return None
    if not all(math.isfinite(v) for v in (xi, alpha, kappa)):
        return None

    return {"xi": xi, "alpha": alpha, "kappa": kappa}


def _cdf_generalized_logistic(values: pd.Series, params: Dict[str, float]) -> pd.Series:
    xi = params["xi"]
    alpha = params["alpha"]
    kappa = params["kappa"]
    out = []
    for raw in values:
        if pd.isna(raw):
            out.append(float("nan"))
            continue
        x = float(raw)
        y = (x - xi) / alpha
        if kappa == 0:
            cdf = 1.0 / (1.0 + math.exp(-y))
        else:
            arg = 1.0 - kappa * y
            if arg <= 0:
                cdf = 0.0 if kappa < 0 else 1.0
            else:
                transformed = -math.log(arg) / kappa
                cdf = 1.0 / (1.0 + math.exp(-transformed))
        out.append(min(max(cdf, _CDF_EPSILON), 1.0 - _CDF_EPSILON))
    return pd.Series(out, index=values.index, dtype=float)


def _ppf_generalized_logistic(probability: float, params: Dict[str, float]) -> float:
    p = min(max(float(probability), _CDF_EPSILON), 1.0 - _CDF_EPSILON)
    xi = params["xi"]
    alpha = params["alpha"]
    kappa = params["kappa"]
    if kappa == 0:
        return xi + alpha * math.log(p / (1.0 - p))
    return xi + (alpha / kappa) * (1.0 - ((1.0 - p) / p) ** kappa)


def _empirical_normal_scores(series: pd.Series, min_points: int) -> pd.Series:
    non_null = series.dropna()
    if len(non_null) < min_points:
        return pd.Series(index=series.index, dtype=float)

    ranks = non_null.rank(method="average")
    probs = ((ranks - 0.44) / (len(non_null) + 0.12)).clip(_CDF_EPSILON, 1 - _CDF_EPSILON)
    dist = NormalDist()
    transformed = probs.map(dist.inv_cdf)
    return transformed.reindex(series.index)


def _normalize_reference_bound(bound: Optional[object]) -> Optional[pd.Timestamp]:
    if bound is None:
        return None
    return pd.Timestamp(bound).to_period("M").to_timestamp()


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
    fit: str = "ub-pwm",
    ref_start: Optional[object] = None,
    ref_end: Optional[object] = None,
) -> pd.DataFrame:
    """
    Compute monthly SPEI from daily or monthly climate inputs.

    Default behavior follows established SPEI practice:
    - month-wise fitting
    - generalized logistic / "log-Logistic" distribution
    - unbiased PWM parameter estimation

    `fit="empirical"` remains available as explicit fallback, but is not
    canonical SPEI.
    """
    if scale_months < 1:
        raise ValueError("scale_months must be >= 1")
    if fit not in {"ub-pwm", "empirical"}:
        raise ValueError("fit must be one of {'ub-pwm', 'empirical'}")
    if min_points_per_calendar_month < 4:
        raise ValueError("min_points_per_calendar_month must be >= 4")

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

    ref_start_ts = _normalize_reference_bound(ref_start)
    ref_end_ts = _normalize_reference_bound(ref_end)
    reference_mask = pd.Series(True, index=monthly.index)
    if ref_start_ts is not None:
        reference_mask &= monthly["date"] >= ref_start_ts
    if ref_end_ts is not None:
        reference_mask &= monthly["date"] <= ref_end_ts

    monthly["spei"] = pd.Series(float("nan"), index=monthly.index, dtype=float)
    fit_parameters: Dict[int, Optional[Dict[str, float]]] = {}
    dist = NormalDist()

    for month_number in range(1, 13):
        month_mask = monthly["month"] == month_number
        target_values = monthly.loc[month_mask, "water_balance_accumulated_mm"]
        ref_values = monthly.loc[month_mask & reference_mask, "water_balance_accumulated_mm"]

        if fit == "empirical":
            monthly.loc[month_mask, "spei"] = _empirical_normal_scores(
                target_values,
                min_points=min_points_per_calendar_month,
            )
            fit_parameters[month_number] = None
            continue

        if ref_values.dropna().shape[0] < min_points_per_calendar_month:
            fit_parameters[month_number] = None
            continue

        params = _fit_generalized_logistic_ub_pwm(ref_values)
        fit_parameters[month_number] = params
        if params is None:
            continue

        cdf = _cdf_generalized_logistic(target_values, params)
        monthly.loc[month_mask, "spei"] = cdf.map(dist.inv_cdf)

    monthly.attrs["spei_metadata"] = {
        **monthly.attrs.get("spei_metadata", {}),
        "scale_months": scale_months,
        "index_name": "SPEI",
        "distribution": "generalized_logistic",
        "fit": fit,
        "reference_period": {
            "start": None if ref_start_ts is None else ref_start_ts.strftime("%Y-%m-%d"),
            "end": None if ref_end_ts is None else ref_end_ts.strftime("%Y-%m-%d"),
        },
        "min_points_per_calendar_month": min_points_per_calendar_month,
        "standardization_method": (
            "generalized_logistic_ub_pwm_by_calendar_month"
            if fit == "ub-pwm"
            else "empirical_normal_by_calendar_month"
        ),
        "fit_parameters_by_month": fit_parameters,
        "references": [
            "Vicente-Serrano et al. (2010) SPEI",
            "Begueria et al. (2014) SPEI revisited",
            "CRAN SPEI package default: log-Logistic + ub-pwm",
        ],
    }
    return monthly


def compute_monthly_spi(
    df: pd.DataFrame,
    scale_months: int = 3,
    min_points_per_calendar_month: int = DEFAULT_MIN_POINTS_PER_MONTH,
    date_col: str = "date",
    precip_col: Optional[str] = None,
    fit: str = "ub-pwm",
    ref_start: Optional[object] = None,
    ref_end: Optional[object] = None,
) -> pd.DataFrame:
    """
    Compute monthly SPI from daily or monthly precipitation inputs.

    Uses same month-wise generalized logistic + unbiased PWM default used in
    current SPEI helper so SPI and SPEI stay method-aligned where possible.
    """
    if scale_months < 1:
        raise ValueError("scale_months must be >= 1")
    if fit not in {"ub-pwm", "empirical"}:
        raise ValueError("fit must be one of {'ub-pwm', 'empirical'}")
    if min_points_per_calendar_month < 4:
        raise ValueError("min_points_per_calendar_month must be >= 4")

    monthly = prepare_monthly_precipitation_totals(
        df,
        date_col=date_col,
        precip_col=precip_col,
    ).copy()
    monthly["precipitation_accumulated_mm"] = (
        monthly["precipitation_mm"]
        .rolling(window=scale_months, min_periods=scale_months)
        .sum()
    )

    ref_start_ts = _normalize_reference_bound(ref_start)
    ref_end_ts = _normalize_reference_bound(ref_end)
    reference_mask = pd.Series(True, index=monthly.index)
    if ref_start_ts is not None:
        reference_mask &= monthly["date"] >= ref_start_ts
    if ref_end_ts is not None:
        reference_mask &= monthly["date"] <= ref_end_ts

    monthly["spi"] = pd.Series(float("nan"), index=monthly.index, dtype=float)
    fit_parameters: Dict[int, Optional[Dict[str, float]]] = {}
    dist = NormalDist()

    for month_number in range(1, 13):
        month_mask = monthly["month"] == month_number
        target_values = monthly.loc[month_mask, "precipitation_accumulated_mm"]
        ref_values = monthly.loc[month_mask & reference_mask, "precipitation_accumulated_mm"]

        if fit == "empirical":
            monthly.loc[month_mask, "spi"] = _empirical_normal_scores(
                target_values,
                min_points=min_points_per_calendar_month,
            )
            fit_parameters[month_number] = None
            continue

        if ref_values.dropna().shape[0] < min_points_per_calendar_month:
            fit_parameters[month_number] = None
            continue

        params = _fit_generalized_logistic_ub_pwm(ref_values)
        fit_parameters[month_number] = params
        if params is None:
            continue

        cdf = _cdf_generalized_logistic(target_values, params)
        monthly.loc[month_mask, "spi"] = cdf.map(dist.inv_cdf)

    monthly.attrs["spei_metadata"] = {
        **monthly.attrs.get("spei_metadata", {}),
        "scale_months": scale_months,
        "index_name": "SPI",
        "distribution": "generalized_logistic",
        "fit": fit,
        "reference_period": {
            "start": None if ref_start_ts is None else ref_start_ts.strftime("%Y-%m-%d"),
            "end": None if ref_end_ts is None else ref_end_ts.strftime("%Y-%m-%d"),
        },
        "min_points_per_calendar_month": min_points_per_calendar_month,
        "standardization_method": (
            "generalized_logistic_ub_pwm_by_calendar_month"
            if fit == "ub-pwm"
            else "empirical_normal_by_calendar_month"
        ),
        "fit_parameters_by_month": fit_parameters,
        "references": [
            "McKee et al. (1993) SPI",
            "month-wise generalized-logistic alignment for toolkit SPI/SPEI consistency",
        ],
    }
    return monthly
