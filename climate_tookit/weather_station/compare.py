"""Compare observed station records against historical gridded datasets."""

from __future__ import annotations

import argparse
import json
import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
try:
    from tabulate import tabulate
except ImportError:  # pragma: no cover
    tabulate = None

from climate_tookit.climate_statistics.statistics import (
    DEFAULT_AUTO_PRECIP_SOURCE,
    DEFAULT_AUTO_TEMP_SOURCE,
    PAIRED_SOURCE_SENTINEL,
    _fetch_auto,
    _fetch_chirps_chirts,
    _fetch_paired_sources,
    _validate_paired_sources,
)
from climate_tookit.climatology import (
    XCLIM_AVAILABLE,
    assess_xclim_precip_annual_readiness,
    compare_xclim_precip_indices,
)
from climate_tookit.fetch_data.fetch_data import parse_variables
from climate_tookit.fetch_data.preprocess_data.preprocess_data import preprocess_data
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    normalize_climate_dataset_name,
)
from climate_tookit.weather_station.dem import fetch_anchor_elevation
from climate_tookit.weather_station.custom_station import custom_station_format_help
from climate_tookit.weather_station.download import (
    _open_report_html,
    download_station_data,
    save_candidate_review_artifacts,
)
from climate_tookit.weather_station.ghcn_daily import (
    list_ghcn_station_candidates,
    select_ghcn_station_candidates,
)
from climate_tookit.weather_station.station_selector import (
    list_station_candidates,
    select_station_candidates,
    summarize_station_search_scope,
)


DEFAULT_COMPARE_VARIABLES = [
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
]
DEFAULT_WET_DAY_THRESHOLD_MM = 1.0
DEFAULT_SELECTION_STRATEGY = "all_vars_single_station"
DEFAULT_MIN_OVERLAP_DAYS = 30
SUPPORTED_SELECTION_STRATEGIES = {
    "all_vars_single_station",
    "best_per_variable",
}


def _compare_log(verbose: bool, message: str) -> None:
    if verbose:
        print(message)
HISTORICAL_GRID_SOURCES = {
    "agera_5",
    "auto",
    "chirts",
    "chirps",
    "chirps_v2",
    "chirps_v2+chirts",
    "chirps_v3_daily_rnl",
    "era_5",
    "imerg",
    "nasa_power",
    "paired",
    "terraclimate",
}
GRID_COMPARE_DISALLOWED = {
    "ghcn_daily",
    "gsod",
    "nex_gddp",
    "soil_grid",
    "tamsat",
}
GRID_SOURCE_METADATA = {
    "agera_5": {
        "product_class": "reanalysis",
        "station_informed": False,
        "validation_independence": "largely independent from local station comparison",
    },
    "auto": {
        "product_class": "composite_selector",
        "station_informed": True,
        "validation_independence": "mixed; depends on selected underlying products",
    },
    "chirts": {
        "product_class": "station_informed_temperature",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
    "chirps": {
        "product_class": "gauge_satellite_precipitation",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
    "chirps_v2": {
        "product_class": "gauge_satellite_precipitation",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
    "chirps_v2+chirts": {
        "product_class": "paired_gauge_satellite_plus_station_temperature",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
    "chirps_v3_daily_rnl": {
        "product_class": "gauge_satellite_precipitation",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
    "era_5": {
        "product_class": "reanalysis",
        "station_informed": False,
        "validation_independence": "largely independent from local station comparison",
    },
    "imerg": {
        "product_class": "satellite_precipitation",
        "station_informed": False,
        "validation_independence": "more independent, though some gauge adjustment may exist upstream",
    },
    "nasa_power": {
        "product_class": "api_derived_agrometeorology",
        "station_informed": False,
        "validation_independence": "largely independent from local station comparison",
    },
    "paired": {
        "product_class": "paired_composite",
        "station_informed": True,
        "validation_independence": "mixed; depends on chosen precip and temperature products",
    },
    "terraclimate": {
        "product_class": "climatologically_aided_interpolation",
        "station_informed": True,
        "validation_independence": "not fully independent from station-based validation",
    },
}


def _variable_name(variable: ClimateVariable | str) -> str:
    if hasattr(variable, "name"):
        return str(variable.name)
    return str(variable)


def _normalize_selection_strategy(selection_strategy: str | None) -> str:
    strategy = str(selection_strategy or DEFAULT_SELECTION_STRATEGY).strip().lower()
    if strategy not in SUPPORTED_SELECTION_STRATEGIES:
        raise ValueError(
            "selection_strategy must be one of: "
            f"{', '.join(sorted(SUPPORTED_SELECTION_STRATEGIES))}"
        )
    return strategy


def _format_optional_number(value, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def _short_text(value, max_len: int = 36) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _wrap_text(value, width: int = 40) -> str:
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "n/a"
        text = ", ".join(str(item) for item in value)
    else:
        if value is None or pd.isna(value):
            return "n/a"
        text = str(value)
    if not text:
        return "n/a"
    return textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)


def _round_frame_for_display(frame: pd.DataFrame, *, decimals: int = 4) -> pd.DataFrame:
    display = frame.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].round(decimals)
    return display


def _add_station_contribution_span(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    contrib_cols = [
        "stations_contributing_mean",
        "stations_contributing_min",
        "stations_contributing_max",
    ]
    if not any(column in display.columns for column in contrib_cols):
        return display

    def _span(row):
        values = [row.get(column) for column in contrib_cols if column in display.columns]
        values = [value for value in values if value is not None and not pd.isna(value)]
        if not values:
            return "n/a"
        ints = [int(round(float(value))) for value in values]
        unique = sorted(set(ints))
        if len(unique) == 1:
            return str(unique[0])
        return f"{min(unique)}-{max(unique)}"

    display["stations"] = display.apply(_span, axis=1)
    return display.drop(columns=[column for column in contrib_cols if column in display.columns])


def _drop_empty_display_columns(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    keep = []
    for column in display.columns:
        series = display[column]
        non_na = series.dropna()
        if non_na.empty:
            continue
        normalized = {
            str(value).strip().lower()
            for value in non_na.tolist()
        }
        if normalized <= {"n/a", "none", ""}:
            continue
        keep.append(column)
    return display[keep] if keep else display


def _drop_constant_display_columns(
    frame: pd.DataFrame,
    *,
    candidates: list[str],
) -> pd.DataFrame:
    display = frame.copy()
    for column in candidates:
        if column not in display.columns:
            continue
        values = display[column].dropna().astype(str).str.strip()
        if not values.empty and values.nunique() == 1:
            display = display.drop(columns=[column])
    return display


def _apply_terminal_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    if "variable" in display.columns:
        display["variable"] = display["variable"].replace(
            {
                "precipitation": "precip",
                "max_temperature": "tmax",
                "min_temperature": "tmin",
                "mean_temperature": "tmean",
            }
        )
    return display


def _render_display_table(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    maxcolwidths: list[int | None] | None = None,
) -> str:
    selected = frame[[column for column in columns if column in frame.columns]].fillna("n/a")
    selected = _apply_terminal_aliases(selected)
    selected = _drop_empty_display_columns(selected)
    if selected.empty:
        return "(no rows)"
    if tabulate is not None:
        return tabulate(
            selected.to_dict(orient="records"),
            headers="keys",
            tablefmt="plain",
            showindex=False,
            disable_numparse=True,
            maxcolwidths=maxcolwidths,
        )
    return selected.to_string(index=False)


def _render_metric_core_table(
    rows: list[dict[str, Any]],
    *,
    include_period_count: bool = False,
    include_confidence: bool = True,
) -> str:
    if not rows:
        return "(no comparison rows)"
    frame = _round_frame_for_display(pd.DataFrame(rows))
    preferred = [
        "station_id",
        "grid_source",
        "variable",
        "overlap_days",
        "period_count" if include_period_count else None,
        "confidence_class" if include_confidence else None,
        "bias",
        "mae",
        "rmse",
        "correlation",
    ]
    preferred = [column for column in preferred if column]
    frame = _drop_constant_display_columns(
        frame,
        candidates=["station_id", "confidence_class"],
    )
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 18, 10, 10, 10, 10, 10, 10],
    )


def _render_precip_skill_table(rows: list[dict[str, Any]]) -> str:
    precip_rows = [row for row in rows if row.get("variable") == "precipitation"]
    if not precip_rows:
        return "(no precipitation skill rows)"
    frame = _round_frame_for_display(pd.DataFrame(precip_rows))
    frame = _drop_constant_display_columns(frame, candidates=["station_id"])
    preferred = [
        "station_id",
        "grid_source",
        "overlap_days",
        "station_total_mm",
        "grid_total_mm",
        "wet_day_hit_rate",
        "false_alarm_ratio",
        "critical_success_index",
        "frequency_bias",
        "wet_day_agreement",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 10, 14, 14, 10, 10, 10, 10, 10],
    )


def _render_annual_core_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no annual rows)"
    frame = _round_frame_for_display(pd.DataFrame(rows))
    if "confidence_note" in frame.columns:
        frame["annual_flag"] = frame["confidence_note"].map(
            lambda value: (
                "annual_ok"
                if str(value).strip().lower().startswith("suitable for annual")
                else _short_text(value, max_len=18)
            )
        )
    frame = _drop_constant_display_columns(frame, candidates=["station_id"])
    preferred = [
        "station_id",
        "grid_source",
        "variable",
        "overlap_days",
        "coverage_ratio",
        "annual_flag",
        "bias",
        "mae",
        "rmse",
        "correlation",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 18, 10, 10, 12, 10, 10, 10, 10],
    )


def _render_annual_precip_totals_table(rows: list[dict[str, Any]]) -> str:
    precip_rows = [row for row in rows if row.get("variable") == "precipitation"]
    if not precip_rows:
        return "(no annual precipitation totals)"
    frame = _round_frame_for_display(pd.DataFrame(precip_rows))
    frame = _drop_constant_display_columns(frame, candidates=["station_id"])
    preferred = [
        "station_id",
        "grid_source",
        "overlap_days",
        "station_total_mm",
        "grid_total_mm",
        "bias",
        "mae",
        "rmse",
        "correlation",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 10, 14, 14, 10, 10, 10, 10],
    )


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _clamp01(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return max(0.0, min(1.0, float(value)))


def _score_inverse_relative(delta: float | None, reference: float | None) -> float | None:
    if delta is None or reference is None or pd.isna(delta) or pd.isna(reference):
        return None
    scale = max(abs(float(reference)), 1.0)
    return _clamp01(1.0 - abs(float(delta)) / scale)


def _score_inverse_target(value: float | None, *, target: float, tolerance: float) -> float | None:
    if value is None or pd.isna(value):
        return None
    return _clamp01(1.0 - abs(float(value) - float(target)) / float(tolerance))


def _average_score(parts: list[float | None]) -> float | None:
    valid = [float(part) for part in parts if part is not None and not pd.isna(part)]
    if not valid:
        return None
    return round(float(sum(valid) / len(valid)), 4)


def _classify_overlap_confidence(overlap_days: int) -> str:
    days = int(overlap_days)
    if days >= 300:
        return "high"
    if days >= 90:
        return "medium"
    if days >= 30:
        return "low"
    return "very_low"


def _build_overlap_warning(
    *,
    station_id: str,
    grid_source: str,
    variable: str,
    overlap_days: int,
    min_overlap_days: int,
) -> str | None:
    if int(overlap_days) >= int(min_overlap_days):
        return None
    confidence = _classify_overlap_confidence(overlap_days)
    return (
        f"Low overlap for station={station_id} source={grid_source} "
        f"variable={variable}: {overlap_days} day(s) "
        f"(confidence={confidence}; recommended >= {min_overlap_days})."
    )


def _aggregate_series(
    overlap: pd.DataFrame,
    *,
    variable: str,
    frequency: str,
) -> pd.DataFrame:
    station_col = f"{variable}_station"
    grid_col = f"{variable}_grid"
    working = overlap[["date", station_col, grid_col]].dropna().copy()
    if working.empty:
        return pd.DataFrame()
    working["date"] = pd.to_datetime(working["date"])
    if frequency == "seasonal":
        month = working["date"].dt.month
        season = np.select(
            [
                month.isin([12, 1, 2]),
                month.isin([3, 4, 5]),
                month.isin([6, 7, 8]),
                month.isin([9, 10, 11]),
            ],
            ["DJF", "MAM", "JJA", "SON"],
            default="UNK",
        )
        season_year = working["date"].dt.year + (month == 12).astype(int)
        working["period"] = season_year.astype(str) + "-" + pd.Series(season, index=working.index)
    else:
        working["period"] = working["date"].dt.to_period(frequency).astype(str)
    if variable == "precipitation":
        aggregated = (
            working.groupby("period", as_index=False)[[station_col, grid_col]]
            .sum()
        )
    else:
        aggregated = (
            working.groupby("period", as_index=False)[[station_col, grid_col]]
            .mean()
        )
    return aggregated


def _compute_aggregated_metrics(
    overlap: pd.DataFrame,
    *,
    variable: str,
    frequency: str,
) -> dict[str, Any] | None:
    aggregated = _aggregate_series(overlap, variable=variable, frequency=frequency)
    if aggregated.empty:
        return None
    station_col = f"{variable}_station"
    grid_col = f"{variable}_grid"
    station_values = aggregated[station_col].astype(float)
    grid_values = aggregated[grid_col].astype(float)
    delta = grid_values - station_values
    metrics: dict[str, Any] = {
        "variable": variable,
        "timescale": (
            "monthly"
            if frequency == "M"
            else ("annual" if frequency == "Y" else "seasonal")
        ),
        "period_count": int(len(aggregated)),
        "station_mean": round(float(station_values.mean()), 4),
        "grid_mean": round(float(grid_values.mean()), 4),
        "bias": round(float(delta.mean()), 4),
        "mae": round(float(delta.abs().mean()), 4),
        "rmse": round(float(np.sqrt(np.mean(np.square(delta)))), 4),
        "correlation": None,
    }
    correlation = _safe_corr(station_values, grid_values)
    if correlation is not None and not np.isnan(correlation):
        metrics["correlation"] = round(float(correlation), 4)
    if variable == "precipitation":
        metrics["station_total_mm"] = round(float(station_values.sum()), 4)
        metrics["grid_total_mm"] = round(float(grid_values.sum()), 4)
        metrics["delta_total_mm"] = round(float(grid_values.sum() - station_values.sum()), 4)
    return metrics


def _build_pooled_reference_overlap(
    overlap: pd.DataFrame,
    *,
    variable: str,
) -> pd.DataFrame:
    station_col = f"{variable}_station"
    grid_col = f"{variable}_grid"
    required = {"date", "station_id", station_col, grid_col}
    if not required.issubset(overlap.columns):
        return pd.DataFrame()
    working = overlap[["date", "station_id", station_col, grid_col]].dropna().copy()
    if working.empty:
        return pd.DataFrame()
    working["date"] = pd.to_datetime(working["date"])
    pooled = (
        working.groupby("date", as_index=False)
        .agg(
            {
                station_col: "mean",
                grid_col: "mean",
                "station_id": pd.Series.nunique,
            }
        )
        .rename(columns={"station_id": "stations_contributing"})
    )
    return pooled.sort_values("date").reset_index(drop=True)


def _annotate_pooled_metric_row(
    pooled_overlap: pd.DataFrame,
    metric_row: dict[str, Any],
) -> dict[str, Any]:
    if pooled_overlap.empty or "stations_contributing" not in pooled_overlap.columns:
        metric_row["stations_contributing_mean"] = None
        metric_row["stations_contributing_min"] = None
        metric_row["stations_contributing_max"] = None
        return metric_row
    counts = pooled_overlap["stations_contributing"].astype(int)
    metric_row["stations_contributing_mean"] = round(float(counts.mean()), 4)
    metric_row["stations_contributing_min"] = int(counts.min())
    metric_row["stations_contributing_max"] = int(counts.max())
    return metric_row


def _annotate_annual_overlap_summary(
    overlap: pd.DataFrame,
    *,
    variable: str,
    metric_row: dict[str, Any],
) -> dict[str, Any]:
    working = overlap[["date", f"{variable}_station", f"{variable}_grid"]].dropna().copy()
    if working.empty:
        metric_row["overlap_days"] = 0
        metric_row["calendar_span_days"] = 0
        metric_row["coverage_ratio"] = None
        metric_row["confidence_note"] = "no overlap"
        return metric_row
    working["date"] = pd.to_datetime(working["date"])
    overlap_days = int(len(working))
    calendar_span_days = int((working["date"].max() - working["date"].min()).days) + 1
    coverage_ratio = None if calendar_span_days <= 0 else float(overlap_days / calendar_span_days)
    metric_row["overlap_days"] = overlap_days
    metric_row["calendar_span_days"] = calendar_span_days
    metric_row["coverage_ratio"] = None if coverage_ratio is None else round(coverage_ratio, 4)
    if overlap_days >= 330 and coverage_ratio is not None and coverage_ratio >= 0.9:
        metric_row["confidence_note"] = "suitable for annual interpretation"
    elif overlap_days >= 180 and coverage_ratio is not None and coverage_ratio >= 0.5:
        metric_row["confidence_note"] = "partial-year overlap; interpret cautiously"
    else:
        metric_row["confidence_note"] = "sparse overlap; descriptive only"
    return metric_row


def _normalize_grid_sources(grid_sources: list[str] | None) -> list[str]:
    sources = [normalize_climate_dataset_name(source) for source in (grid_sources or [])]
    if not sources:
        raise ValueError("Provide at least one grid source to compare against.")
    unknown = sorted({source for source in sources if source not in HISTORICAL_GRID_SOURCES and source not in GRID_COMPARE_DISALLOWED})
    if unknown:
        valid = ", ".join(sorted(HISTORICAL_GRID_SOURCES | GRID_COMPARE_DISALLOWED))
        raise ValueError(f"Unknown grid source(s): {', '.join(unknown)}. Valid values: {valid}")
    disallowed = sorted({source for source in sources if source in GRID_COMPARE_DISALLOWED})
    if disallowed:
        raise ValueError(
            "Station-vs-grid comparison is historical-only. Unsupported here: "
            f"{', '.join(disallowed)}"
        )
    return sources


def _fetch_grid_source(
    *,
    source: str,
    lat: float,
    lon: float,
    date_from: date,
    date_to: date,
    variables,
    precip_source: str | None = None,
    temp_source: str | None = None,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    source_name = normalize_climate_dataset_name(source)
    if source_name == "auto":
        frame = _fetch_auto(lat, lon, date_from, date_to)
    elif source_name == PAIRED_SOURCE_SENTINEL:
        pair_error = _validate_paired_sources(
            precip_source,
            temp_source,
            start_year=date_from.year,
            end_year=date_to.year,
        )
        if pair_error:
            raise ValueError(pair_error)
        frame = _fetch_paired_sources(
            lat,
            lon,
            date_from,
            date_to,
            normalize_climate_dataset_name(precip_source),
            normalize_climate_dataset_name(temp_source),
        )
    elif source_name in {"chirps+chirts", "chirps_v2+chirts"}:
        frame = _fetch_chirps_chirts(lat, lon, date_from, date_to)
    else:
        frame = preprocess_data(
            source=source_name,
            location_coord=(lat, lon),
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            verbose=False,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
    if frame is None or frame.empty:
        raise RuntimeError(f"No data returned from grid source '{source_name}'")
    result = frame.copy()
    if "date" not in result.columns:
        raise RuntimeError(f"Grid source '{source_name}' returned no date column.")
    result["date"] = pd.to_datetime(result["date"])
    return result.sort_values("date").reset_index(drop=True)


def _safe_corr(station_values: pd.Series, grid_values: pd.Series) -> float | None:
    if len(station_values) < 2:
        return None
    if float(station_values.std(ddof=0)) == 0.0 or float(grid_values.std(ddof=0)) == 0.0:
        return None
    return float(station_values.corr(grid_values))


def _compute_variable_metrics(
    merged: pd.DataFrame,
    *,
    variable: str,
    wet_day_threshold_mm: float = DEFAULT_WET_DAY_THRESHOLD_MM,
    min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS,
) -> dict[str, Any] | None:
    station_col = f"{variable}_station"
    grid_col = f"{variable}_grid"
    if station_col not in merged.columns or grid_col not in merged.columns:
        return None

    overlap = merged[["date", station_col, grid_col]].dropna().copy()
    if overlap.empty:
        return None

    station_values = overlap[station_col].astype(float)
    grid_values = overlap[grid_col].astype(float)
    delta = grid_values - station_values
    metrics: dict[str, Any] = {
        "variable": variable,
        "overlap_days": int(len(overlap)),
        "confidence_class": _classify_overlap_confidence(len(overlap)),
        "low_confidence": bool(int(len(overlap)) < int(min_overlap_days)),
        "station_mean": round(float(station_values.mean()), 4),
        "grid_mean": round(float(grid_values.mean()), 4),
        "bias": round(float(delta.mean()), 4),
        "mae": round(float(delta.abs().mean()), 4),
        "rmse": round(float(np.sqrt(np.mean(np.square(delta)))), 4),
        "correlation": None,
    }
    correlation = _safe_corr(station_values, grid_values)
    if correlation is not None and not np.isnan(correlation):
        metrics["correlation"] = round(float(correlation), 4)

    if variable == "precipitation":
        station_wet = station_values >= float(wet_day_threshold_mm)
        grid_wet = grid_values >= float(wet_day_threshold_mm)
        wet_hits = int((station_wet & grid_wet).sum())
        wet_misses = int((station_wet & ~grid_wet).sum())
        wet_false_alarms = int((~station_wet & grid_wet).sum())
        station_wet_days = int(station_wet.sum())
        grid_wet_days = int(grid_wet.sum())
        precision = None if (wet_hits + wet_false_alarms) == 0 else round(float(wet_hits / (wet_hits + wet_false_alarms)), 4)
        false_alarm_ratio = None if (wet_hits + wet_false_alarms) == 0 else round(float(wet_false_alarms / (wet_hits + wet_false_alarms)), 4)
        critical_success_index = None if (wet_hits + wet_misses + wet_false_alarms) == 0 else round(float(wet_hits / (wet_hits + wet_misses + wet_false_alarms)), 4)
        frequency_bias = None if station_wet_days == 0 else round(float(grid_wet_days / station_wet_days), 4)
        metrics.update(
            {
                "station_total_mm": round(float(station_values.sum()), 4),
                "grid_total_mm": round(float(grid_values.sum()), 4),
                "delta_total_mm": round(float(grid_values.sum() - station_values.sum()), 4),
                "station_wet_days": station_wet_days,
                "grid_wet_days": grid_wet_days,
                "wet_day_hits": wet_hits,
                "wet_day_misses": wet_misses,
                "wet_day_false_alarms": wet_false_alarms,
                "wet_day_agreement": round(float((station_wet == grid_wet).mean()), 4),
                "wet_day_hit_rate": None if station_wet_days == 0 else round(float(wet_hits / station_wet_days), 4),
                "precision": precision,
                "false_alarm_ratio": false_alarm_ratio,
                "critical_success_index": critical_success_index,
                "frequency_bias": frequency_bias,
            }
        )
        station_wet_only = station_values[station_values >= float(wet_day_threshold_mm)]
        grid_wet_only = grid_values[grid_values >= float(wet_day_threshold_mm)]
        metrics["wet_day_intensity_station"] = None if station_wet_only.empty else round(float(station_wet_only.mean()), 4)
        metrics["wet_day_intensity_grid"] = None if grid_wet_only.empty else round(float(grid_wet_only.mean()), 4)
        if metrics["wet_day_intensity_station"] is not None and metrics["wet_day_intensity_grid"] is not None:
            metrics["wet_day_intensity_delta"] = round(
                float(metrics["wet_day_intensity_grid"] - metrics["wet_day_intensity_station"]),
                4,
            )
        for quantile in (0.5, 0.75, 0.9, 0.95, 0.99):
            q_label = f"p{int(round(quantile * 100)):02d}"
            station_quantile = round(float(station_values.quantile(quantile)), 4)
            grid_quantile = round(float(grid_values.quantile(quantile)), 4)
            metrics[f"{q_label}_mm_station"] = station_quantile
            metrics[f"{q_label}_mm_grid"] = grid_quantile
            metrics[f"{q_label}_mm_delta"] = round(float(grid_quantile - station_quantile), 4)
        metrics["rx1day_mm_station"] = round(float(station_values.max()), 4)
        metrics["rx1day_mm_grid"] = round(float(grid_values.max()), 4)
        metrics["rx1day_mm_delta"] = round(float(grid_values.max() - station_values.max()), 4)
        station_roll5 = station_values.rolling(window=5, min_periods=5).sum()
        grid_roll5 = grid_values.rolling(window=5, min_periods=5).sum()
        metrics["rx5day_mm_station"] = None if station_roll5.dropna().empty else round(float(station_roll5.max()), 4)
        metrics["rx5day_mm_grid"] = None if grid_roll5.dropna().empty else round(float(grid_roll5.max()), 4)
        if metrics["rx5day_mm_station"] is not None and metrics["rx5day_mm_grid"] is not None:
            metrics["rx5day_mm_delta"] = round(
                float(metrics["rx5day_mm_grid"] - metrics["rx5day_mm_station"]),
                4,
            )
        r10_station = int((station_values >= 10.0).sum())
        r10_grid = int((grid_values >= 10.0).sum())
        r20_station = int((station_values >= 20.0).sum())
        r20_grid = int((grid_values >= 20.0).sum())
        metrics["r10mm_days_station"] = r10_station
        metrics["r10mm_days_grid"] = r10_grid
        metrics["r10mm_days_delta"] = int(r10_grid - r10_station)
        metrics["r20mm_days_station"] = r20_station
        metrics["r20mm_days_grid"] = r20_grid
        metrics["r20mm_days_delta"] = int(r20_grid - r20_station)
    return metrics


def _grid_source_metadata_rows(grid_sources: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in grid_sources:
        meta = GRID_SOURCE_METADATA.get(
            source,
            {
                "product_class": "unknown",
                "station_informed": None,
                "validation_independence": "unknown",
            },
        )
        rows.append(
            {
                "grid_source": source,
                "product_class": meta["product_class"],
                "station_informed": meta["station_informed"],
                "validation_independence": meta["validation_independence"],
            }
        )
    return rows


def _build_use_case_rankings(
    *,
    metrics_rows: list[dict[str, Any]],
    monthly_metrics_rows: list[dict[str, Any]],
    seasonal_metrics_rows: list[dict[str, Any]],
    annual_metrics_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []

    def _row_lookup(rows: list[dict[str, Any]], grid_source: str, variable: str) -> dict[str, Any] | None:
        for row in rows:
            if row.get("grid_source") == grid_source and row.get("variable") == variable:
                return row
        return None

    grid_sources = sorted({row.get("grid_source") for row in metrics_rows if row.get("grid_source")})

    for grid_source in grid_sources:
        precip_daily = _row_lookup(metrics_rows, grid_source, "precipitation")
        precip_monthly = _row_lookup(monthly_metrics_rows, grid_source, "precipitation")
        precip_seasonal = _row_lookup(seasonal_metrics_rows, grid_source, "precipitation")
        precip_annual = _row_lookup(annual_metrics_rows, grid_source, "precipitation")
        if precip_daily is not None:
            rankings.append(
                {
                    "grid_source": grid_source,
                    "use_case": "daily_monitoring",
                    "variables_used": ["precipitation"],
                    "score": _average_score(
                        [
                            _clamp01(precip_daily.get("critical_success_index")),
                            _clamp01(precip_daily.get("wet_day_agreement")),
                            _clamp01(precip_daily.get("precision")),
                            _clamp01(
                                None
                                if precip_daily.get("false_alarm_ratio") is None
                                else 1.0 - float(precip_daily.get("false_alarm_ratio"))
                            ),
                            _clamp01(precip_daily.get("correlation")),
                        ]
                    ),
                    "notes": "Uses daily precipitation occurrence skill and daily overlap correlation.",
                }
            )
            rankings.append(
                {
                    "grid_source": grid_source,
                    "use_case": "heavy_rain_screening",
                    "variables_used": ["precipitation"],
                    "score": _average_score(
                        [
                            _score_inverse_relative(
                                precip_daily.get("rx1day_mm_delta"),
                                precip_daily.get("rx1day_mm_station"),
                            ),
                            _score_inverse_relative(
                                precip_daily.get("rx5day_mm_delta"),
                                precip_daily.get("rx5day_mm_station"),
                            ),
                            _score_inverse_relative(
                                precip_daily.get("p95_mm_delta"),
                                precip_daily.get("p95_mm_station"),
                            ),
                            _score_inverse_relative(
                                precip_daily.get("r10mm_days_delta"),
                                precip_daily.get("r10mm_days_station"),
                            ),
                            _score_inverse_relative(
                                precip_daily.get("r20mm_days_delta"),
                                precip_daily.get("r20mm_days_station"),
                            ),
                        ]
                    ),
                    "notes": "Uses overlap-period heavy-rain and upper-tail precipitation diagnostics.",
                }
            )
        if precip_daily is not None or precip_monthly is not None or precip_seasonal is not None:
            rankings.append(
                {
                    "grid_source": grid_source,
                    "use_case": "seasonal_totals",
                    "variables_used": ["precipitation"],
                    "score": _average_score(
                        [
                            _clamp01(None if precip_seasonal is None else precip_seasonal.get("correlation")),
                            _clamp01(None if precip_monthly is None else precip_monthly.get("correlation")),
                            _score_inverse_relative(
                                None if precip_daily is None else precip_daily.get("delta_total_mm"),
                                None if precip_daily is None else precip_daily.get("station_total_mm"),
                            ),
                        ]
                    ),
                    "notes": "Uses monthly and seasonal precipitation aggregation skill plus total-bias closeness.",
                }
            )
            rankings.append(
                {
                    "grid_source": grid_source,
                    "use_case": "drought_screening",
                    "variables_used": ["precipitation"],
                    "score": _average_score(
                        [
                            _clamp01(None if precip_monthly is None else precip_monthly.get("correlation")),
                            _clamp01(None if precip_seasonal is None else precip_seasonal.get("correlation")),
                            _score_inverse_target(
                                None if precip_daily is None else precip_daily.get("frequency_bias"),
                                target=1.0,
                                tolerance=1.0,
                            ),
                            _score_inverse_relative(
                                None if precip_annual is None else precip_annual.get("delta_total_mm"),
                                None if precip_annual is None else precip_annual.get("station_total_mm"),
                            ),
                        ]
                    ),
                    "notes": "Uses monthly and seasonal precipitation consistency plus occurrence balance.",
                }
            )

        temp_candidates = []
        for variable in ("mean_temperature", "min_temperature", "max_temperature"):
            daily = _row_lookup(metrics_rows, grid_source, variable)
            monthly = _row_lookup(monthly_metrics_rows, grid_source, variable)
            if daily is None and monthly is None:
                continue
            temp_candidates.append(
                _average_score(
                    [
                        _clamp01(None if monthly is None else monthly.get("correlation")),
                        _clamp01(None if daily is None else daily.get("correlation")),
                        _score_inverse_target(
                            None if daily is None else daily.get("bias"),
                            target=0.0,
                            tolerance=5.0,
                        ),
                        _score_inverse_target(
                            None if daily is None else daily.get("rmse"),
                            target=0.0,
                            tolerance=7.0,
                        ),
                    ]
                )
            )
        if temp_candidates:
            rankings.append(
                {
                    "grid_source": grid_source,
                    "use_case": "temperature_climatology",
                    "variables_used": [
                        variable
                        for variable in ("mean_temperature", "min_temperature", "max_temperature")
                        if _row_lookup(metrics_rows, grid_source, variable) is not None
                        or _row_lookup(monthly_metrics_rows, grid_source, variable) is not None
                    ],
                    "score": _average_score(temp_candidates),
                    "notes": "Uses temperature bias, RMSE, and daily/monthly correlation for available temperature variables.",
                }
            )

    if not rankings:
        return []

    ranking_frame = pd.DataFrame(rankings)
    ranking_frame["score_sort"] = ranking_frame["score"].fillna(-1.0)
    ranking_frame = ranking_frame.sort_values(
        ["use_case", "score_sort", "grid_source"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    ranking_frame["rank"] = (
        ranking_frame.groupby("use_case")["score_sort"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )
    ranking_frame = ranking_frame.drop(columns=["score_sort"])
    return ranking_frame.to_dict(orient="records")


def _build_station_summary(station_frame: pd.DataFrame) -> dict[str, Any]:
    first = station_frame.iloc[0]
    summary = {
        "station_id": first.get("station_id"),
        "station_name": first.get("station_name"),
        "station_source": first.get("station_source", "ghcn_daily"),
        "station_lat": float(first["station_lat"]) if "station_lat" in first and pd.notna(first["station_lat"]) else None,
        "station_lon": float(first["station_lon"]) if "station_lon" in first and pd.notna(first["station_lon"]) else None,
        "station_elevation_m": None if "station_elevation_m" not in first or pd.isna(first["station_elevation_m"]) else float(first["station_elevation_m"]),
        "distance_km": None if "station_distance_km" not in first or pd.isna(first["station_distance_km"]) else float(first["station_distance_km"]),
        "elevation_diff_m": None if "elevation_diff_m" not in first or pd.isna(first["elevation_diff_m"]) else float(first["elevation_diff_m"]),
        "selection_rank": None if "selection_rank" not in first or pd.isna(first["selection_rank"]) else int(first["selection_rank"]),
        "selection_status": first.get("selection_status"),
        "selection_threshold_used": None if "selection_threshold_used" not in first or pd.isna(first["selection_threshold_used"]) else float(first["selection_threshold_used"]),
        "date_start": pd.to_datetime(station_frame["date"]).min().date().isoformat(),
        "date_end": pd.to_datetime(station_frame["date"]).max().date().isoformat(),
        "rows": int(len(station_frame)),
    }
    available_columns = [
        column
        for column in (
            "precipitation",
            "max_temperature",
            "min_temperature",
            "mean_temperature",
            "wind_speed",
            "humidity",
        )
        if column in station_frame.columns
    ]
    summary["availability"] = {
        column: int(station_frame[column].notna().sum())
        for column in available_columns
    }
    return summary


def _augment_station_frame_with_candidate_metadata(
    station_frame: pd.DataFrame,
    *,
    candidate_row,
    variable_name: str,
    selection_strategy: str,
) -> pd.DataFrame:
    frame = station_frame.copy()
    frame["selection_variable"] = variable_name
    frame["selection_strategy"] = selection_strategy
    for column in (
        "selection_status",
        "selection_threshold_used",
        "threshold_status",
        "n_fields_passing_threshold",
        "requested_fields",
        "fields_passing_threshold",
        "fields_failing_threshold",
        "all_fields_meet_threshold",
        "distance_km",
        "elevation_diff_m",
    ):
        if column in candidate_row.index:
            frame[column] = pd.Series(
                [candidate_row[column]] * len(frame),
                index=frame.index,
                dtype=object,
            )
    if "distance_km" in candidate_row.index:
        frame["station_distance_km"] = pd.Series(
            [candidate_row["distance_km"]] * len(frame),
            index=frame.index,
            dtype=object,
        )
    return frame


def _selection_reason_from_row(
    row,
    *,
    variable_name: str,
    selection_mode: str,
) -> str:
    selection_status = str(row.get("selection_status") or "n/a")
    threshold_status = str(row.get("threshold_status") or "n/a")
    threshold_used = row.get("selection_threshold_used")
    rank = row.get("selection_rank")
    pass_fields = row.get("fields_passing_threshold")
    fail_fields = row.get("fields_failing_threshold")

    parts = [f"mode={selection_mode}", f"status={selection_status}"]
    if threshold_status and threshold_status != "n/a":
        parts.append(f"threshold={threshold_status}")
    if rank is not None and not pd.isna(rank):
        parts.append(f"rank={int(rank)}")
    if threshold_used is not None and not pd.isna(threshold_used):
        parts.append(f"min_ratio={float(threshold_used):.2f}")

    if isinstance(pass_fields, (list, tuple, set)) and pass_fields:
        parts.append("pass=" + ",".join(str(item) for item in pass_fields))
    if isinstance(fail_fields, (list, tuple, set)) and fail_fields:
        parts.append("fail=" + ",".join(str(item) for item in fail_fields))

    if variable_name != "all_variables":
        parts.append(f"selected_for={variable_name}")
    return " | ".join(parts)


def _split_station_frame_payloads(
    station_frame: pd.DataFrame,
    *,
    compare_variables: list[str],
) -> list[dict[str, Any]]:
    if station_frame.empty:
        return []
    working = station_frame.copy()
    group_columns = ["station_id"]
    if "selection_rank" in working.columns:
        group_columns.append("selection_rank")
    payloads: list[dict[str, Any]] = []
    for _, station_group in working.groupby(group_columns, dropna=False, sort=False):
        payloads.append(
            {
                "station_frame": station_group.reset_index(drop=True).copy(),
                "compare_variables": compare_variables,
            }
        )
    return payloads


def _select_variable_candidate(
    *,
    station_source: str,
    station_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variable,
    station_id: str | None,
    max_distance_km: float,
    target_elevation_m: float | None,
    max_elevation_diff_m: float,
    min_completeness_ratio: float,
    score_limit: int,
    cache_dir: str | None,
    refresh_cache: bool,
    disable_completeness_guard: bool,
    verbose: bool,
    custom_station_file: str | None = None,
    custom_station_name: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
):
    variable_list = [variable]
    if station_id:
        if station_source == "ghcn_daily":
            candidates = list_ghcn_station_candidates(
                location_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variables=variable_list,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
                max_distance_km=max_distance_km,
                target_elevation_m=target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=1,
                score_limit=score_limit,
                enforce_threshold=False,
                verbose=verbose,
            )
        else:
            candidates = list_station_candidates(
                station_source=station_source,
                location_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variables=variable_list,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
                max_distance_km=max_distance_km,
                target_elevation_m=target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=1,
                score_limit=score_limit,
                enforce_threshold=False,
                verbose=verbose,
                custom_station_file=custom_station_file,
                custom_temp_unit=custom_temp_unit,
                custom_precip_unit=custom_precip_unit,
                station_name=custom_station_name,
            )
        if candidates.empty:
            raise RuntimeError(f"No candidate station found for variable '{_variable_name(variable)}'.")
        candidate = candidates.iloc[0].copy()
        candidate["selection_status"] = "specified_station"
        return candidate

    if disable_completeness_guard:
        if station_source == "ghcn_daily":
            candidates = list_ghcn_station_candidates(
                location_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variables=variable_list,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=None,
                max_distance_km=max_distance_km,
                target_elevation_m=target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=1,
                score_limit=score_limit,
                enforce_threshold=False,
            )
        else:
            candidates = list_station_candidates(
                station_source=station_source,
                location_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variables=variable_list,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=None,
                max_distance_km=max_distance_km,
                target_elevation_m=target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=1,
                score_limit=score_limit,
                enforce_threshold=False,
                custom_station_file=custom_station_file,
                custom_temp_unit=custom_temp_unit,
                custom_precip_unit=custom_precip_unit,
                station_name=custom_station_name,
            )
        if candidates.empty:
            raise RuntimeError(f"No candidate station found for variable '{_variable_name(variable)}'.")
        candidate = candidates.iloc[0].copy()
        candidate["selection_status"] = "guard_disabled"
        candidate["selection_threshold_used"] = pd.NA
        candidate["threshold_status"] = "guard_disabled"
        return candidate

    if station_source == "ghcn_daily":
        candidates = select_ghcn_station_candidates(
            location_coord=station_coord,
            date_from=date_from,
            date_to=date_to,
            variables=variable_list,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=None,
            max_distance_km=max_distance_km,
            target_elevation_m=target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            min_completeness_ratio=min_completeness_ratio,
            candidate_limit=1,
            score_limit=score_limit,
            allow_partial_fallback=True,
            verbose=verbose,
        )
    else:
        candidates = select_station_candidates(
            station_source=station_source,
            location_coord=station_coord,
            date_from=date_from,
            date_to=date_to,
            variables=variable_list,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=None,
            max_distance_km=max_distance_km,
            target_elevation_m=target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            min_completeness_ratio=min_completeness_ratio,
            candidate_limit=1,
            score_limit=score_limit,
            allow_partial_fallback=True,
            custom_station_file=custom_station_file,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
            station_name=custom_station_name,
        )
    if candidates.empty:
        raise RuntimeError(f"No candidate station found for variable '{_variable_name(variable)}'.")
    return candidates.iloc[0].copy()


def _build_station_compare_payloads(
    *,
    station_source: str,
    station_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    requested_variables,
    station_id: str | None,
    selection_mode: str,
    selection_strategy: str,
    auto_select: str,
    max_distance_km: float,
    target_elevation_m: float | None,
    max_elevation_diff_m: float,
    min_completeness_ratio: float,
    candidate_limit: int,
    score_limit: int,
    auto_anchor_elevation: bool,
    disable_completeness_guard: bool,
    max_auto_stations: int,
    cache_dir: str | None,
    refresh_cache: bool,
    verbose: bool,
    custom_station_file: str | None = None,
    custom_station_name: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    strategy = _normalize_selection_strategy(selection_strategy)
    compare_variable_names = [_variable_name(variable) for variable in requested_variables]
    warnings: list[str] = []
    selected_station_map: list[dict[str, Any]] = []

    if strategy == "all_vars_single_station":
        _compare_log(verbose, "Building station payloads with all-vars single-station strategy")
        station_frame = download_station_data(
            station_source=station_source,
            station_coord=station_coord,
            date_from=date_from,
            date_to=date_to,
            variables=requested_variables,
            station_id=station_id,
            stage="preprocessed",
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            selection_mode=selection_mode,
            max_distance_km=max_distance_km,
            target_elevation_m=target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            min_completeness_ratio=min_completeness_ratio,
            candidate_limit=candidate_limit,
            score_limit=score_limit,
            auto_select=auto_select,
            auto_anchor_elevation=auto_anchor_elevation,
            disable_completeness_guard=disable_completeness_guard,
            max_auto_stations=max_auto_stations,
            custom_station_file=custom_station_file,
            custom_station_name=custom_station_name,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
        if station_frame is None or station_frame.empty:
            raise RuntimeError("No station observations available for comparison.")
        warnings.extend(
            [
                warning
                for warning in station_frame.attrs.get("selection_warnings", [])
                if str(warning) not in warnings
            ]
        )
        payloads = _split_station_frame_payloads(
            station_frame,
            compare_variables=compare_variable_names,
        )
        for payload in payloads:
            first = payload["station_frame"].iloc[0]
            selected_station_map.append(
                {
                    "variable": "all_variables",
                    "station_id": first.get("station_id"),
                    "station_name": first.get("station_name"),
                    "distance_km": None if pd.isna(first.get("station_distance_km")) else float(first.get("station_distance_km")),
                    "elevation_diff_m": None if pd.isna(first.get("elevation_diff_m")) else float(first.get("elevation_diff_m")),
                    "selection_status": first.get("selection_status"),
                    "selection_threshold_used": None if pd.isna(first.get("selection_threshold_used")) else float(first.get("selection_threshold_used")),
                    "threshold_status": first.get("threshold_status"),
                    "selection_rank": None if pd.isna(first.get("selection_rank")) else int(first.get("selection_rank")),
                    "selection_reason": _selection_reason_from_row(
                        first,
                        variable_name="all_variables",
                        selection_mode=selection_mode,
                    ),
                }
            )
        return payloads, warnings, selected_station_map

    payloads: list[dict[str, Any]] = []
    for variable in requested_variables:
        variable_name = _variable_name(variable)
        _compare_log(verbose, f"Selecting station for variable={variable_name}")
        try:
            candidate = _select_variable_candidate(
                station_source=station_source,
                station_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variable=variable,
                station_id=station_id if selection_mode == "specified" else None,
                max_distance_km=max_distance_km,
                target_elevation_m=target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                score_limit=score_limit,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                disable_completeness_guard=disable_completeness_guard,
                verbose=verbose,
                custom_station_file=custom_station_file,
                custom_station_name=custom_station_name,
                custom_temp_unit=custom_temp_unit,
                custom_precip_unit=custom_precip_unit,
            )
        except Exception as exc:
            warnings.append(
                f"No station selected for variable '{variable_name}': {exc}"
            )
            selected_station_map.append(
                {
                    "variable": variable_name,
                    "station_id": None,
                    "station_name": None,
                    "distance_km": None,
                    "elevation_diff_m": None,
                    "selection_status": "unavailable",
                    "selection_threshold_used": None,
                    "threshold_status": "unavailable",
                    "selection_reason": str(exc),
                }
            )
            continue

        _compare_log(
            verbose,
            f"Selected station for {variable_name}: {candidate.get('station_id')} | "
            f"{candidate.get('station_name') or 'unknown'} | "
            f"distance={_format_optional_number(candidate.get('distance_km'))} km",
        )

        selected_station_map.append(
            {
                "variable": variable_name,
                "station_id": candidate.get("station_id"),
                "station_name": candidate.get("station_name"),
                "distance_km": None if pd.isna(candidate.get("distance_km")) else float(candidate.get("distance_km")),
                "elevation_diff_m": None if pd.isna(candidate.get("elevation_diff_m")) else float(candidate.get("elevation_diff_m")),
                "selection_status": candidate.get("selection_status"),
                "selection_threshold_used": None if pd.isna(candidate.get("selection_threshold_used")) else float(candidate.get("selection_threshold_used")),
                "threshold_status": candidate.get("threshold_status"),
                "selection_reason": _selection_reason_from_row(
                    candidate,
                    variable_name=variable_name,
                    selection_mode=selection_mode,
                ),
            }
        )
        station_frame = download_station_data(
            station_source=str(candidate.get("station_source", station_source)),
            station_coord=station_coord,
            date_from=date_from,
            date_to=date_to,
            variables=[variable],
            station_id=str(candidate["station_id"]),
            stage="preprocessed",
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            selection_mode="specified",
            max_distance_km=max_distance_km,
            target_elevation_m=target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            min_completeness_ratio=min_completeness_ratio,
            candidate_limit=1,
            score_limit=score_limit,
            auto_select="auto-1",
            auto_anchor_elevation=auto_anchor_elevation,
            disable_completeness_guard=disable_completeness_guard,
            max_auto_stations=max_auto_stations,
            custom_station_file=custom_station_file,
            custom_station_name=custom_station_name,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
        if station_frame is None or station_frame.empty:
            warnings.append(
                f"Selected station '{candidate.get('station_id')}' returned no data for variable '{variable_name}'."
            )
            continue
        payloads.append(
            {
                "station_frame": _augment_station_frame_with_candidate_metadata(
                    station_frame,
                    candidate_row=candidate,
                    variable_name=variable_name,
                    selection_strategy=strategy,
                ),
                "compare_variables": [variable_name],
            }
        )

    if not payloads:
        raise RuntimeError("No station observations available for comparison after variable-wise selection.")
    return payloads, warnings, selected_station_map


def _render_metrics_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no comparison rows)"
    frame = _add_station_contribution_span(_round_frame_for_display(pd.DataFrame(rows)))
    preferred = [
        "station_id",
        "grid_source",
        "variable",
        "overlap_days",
        "period_count",
        "confidence_class",
        "bias",
        "mae",
        "rmse",
        "correlation",
        "station_total_mm",
        "grid_total_mm",
        "stations",
        "wet_day_hit_rate",
        "false_alarm_ratio",
        "critical_success_index",
        "frequency_bias",
        "wet_day_agreement",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 16, 10, 10, 9, 9, 11, 14, 14, 8, 10, 10, 10, 10],
    )


def _render_annual_metrics_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no annual rows)"
    frame = _add_station_contribution_span(_round_frame_for_display(pd.DataFrame(rows)))
    if "confidence_note" in frame.columns:
        frame["confidence_note"] = frame["confidence_note"].map(
            lambda value: _short_text(value, max_len=28)
        )
    preferred = [
        "station_id",
        "grid_source",
        "variable",
        "overlap_days",
        "coverage_ratio",
        "confidence_note",
        "bias",
        "mae",
        "rmse",
        "correlation",
        "station_total_mm",
        "grid_total_mm",
        "stations",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 16, 12, 10, 28, 10, 10, 10, 11, 14, 14, 8],
    )


def _render_precip_extremes_table(rows: list[dict[str, Any]]) -> str:
    precip_rows = [row for row in rows if row.get("variable") == "precipitation"]
    if not precip_rows:
        return "(no precipitation rows)"
    frame = _round_frame_for_display(pd.DataFrame(precip_rows))
    preferred = [
        "station_id",
        "grid_source",
        "overlap_days",
        "confidence_class",
        "wet_day_intensity_station",
        "wet_day_intensity_grid",
        "wet_day_intensity_delta",
        "p90_mm_station",
        "p90_mm_grid",
        "p90_mm_delta",
        "p95_mm_station",
        "p95_mm_grid",
        "p95_mm_delta",
        "p99_mm_station",
        "p99_mm_grid",
        "p99_mm_delta",
        "rx1day_mm_station",
        "rx1day_mm_grid",
        "rx1day_mm_delta",
        "rx5day_mm_station",
        "rx5day_mm_grid",
        "rx5day_mm_delta",
        "r10mm_days_station",
        "r10mm_days_grid",
        "r10mm_days_delta",
        "r20mm_days_station",
        "r20mm_days_grid",
        "r20mm_days_delta",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 10, 10] + [10] * 24,
    )


def _render_grid_source_metadata(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no metadata rows)"
    frame = pd.DataFrame(rows)
    if "validation_independence" in frame.columns:
        frame["validation_independence"] = frame["validation_independence"].map(
            lambda value: _short_text(value, max_len=42)
        )
    preferred = [
        "grid_source",
        "product_class",
        "station_informed",
        "validation_independence",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 22, 10, 42],
    )


def _render_use_case_rankings(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no ranking rows)"
    frame = _round_frame_for_display(pd.DataFrame(rows))
    if "notes" in frame.columns:
        frame["notes"] = frame["notes"].map(lambda value: _wrap_text(value, width=38))
    if "variables_used" in frame.columns:
        frame["variables_used"] = frame["variables_used"].map(
            lambda value: _wrap_text(value, width=28)
        )
    preferred = [
        "use_case",
        "rank",
        "grid_source",
        "score",
        "variables_used",
        "notes",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[24, 5, 12, 8, 28, 38],
    )


def _render_xclim_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no xclim rows)"
    frame = _round_frame_for_display(pd.DataFrame(rows))
    preferred = [
        "station_id",
        "grid_source",
        "variable",
        "timescale",
        "period_start",
        "rx1day_mm_station",
        "rx1day_mm_grid",
        "rx1day_mm_delta",
        "rx5day_mm_station",
        "rx5day_mm_grid",
        "rx5day_mm_delta",
        "cdd_days_station",
        "cdd_days_grid",
        "cdd_days_delta",
        "cwd_days_station",
        "cwd_days_grid",
        "cwd_days_delta",
        "r10mm_days_station",
        "r10mm_days_grid",
        "r10mm_days_delta",
        "r20mm_days_station",
        "r20mm_days_grid",
        "r20mm_days_delta",
        "sdii_mm_per_day_station",
        "sdii_mm_per_day_grid",
        "sdii_mm_per_day_delta",
    ]
    return _render_display_table(
        frame,
        columns=preferred,
        maxcolwidths=[14, 12, 14, 14, 12] + [10] * 18,
    )


def render_compare_report(result: dict[str, Any]) -> str:
    unique_station_ids = {
        summary.get("station_id")
        for summary in result["station_summary"]
        if summary.get("station_id")
    }
    lines = [
        "Weather station vs grid comparison",
        f"Anchor location : {result['anchor_location']['lat']:.4f}, {result['anchor_location']['lon']:.4f}",
        f"Period          : {result['date_from']} .. {result['date_to']}",
        f"Strategy        : {result.get('selection_strategy', DEFAULT_SELECTION_STRATEGY)}",
        f"Grid sources    : {', '.join(result['grid_sources'])}",
        f"Stations used   : {len(unique_station_ids)} unique station(s) across {len(result['station_summary'])} variable-selection payload(s)",
        "",
        "Station summary",
    ]
    for summary in result["station_summary"]:
        lines.extend(
            [
                (
                    f"- {summary['station_id']} | {summary.get('station_name') or 'unknown'} | "
                    f"distance={_format_optional_number(summary.get('distance_km'))} km | "
                    f"elev_diff={_format_optional_number(summary.get('elevation_diff_m'), 1)} m | "
                    f"rows={summary['rows']} | dates={summary['date_start']}..{summary['date_end']}"
                ),
                f"  availability={summary.get('availability', {})}",
            ]
        )
    if result.get("selected_stations_by_variable"):
        lines.extend(["", "Selected stations by variable"])
        for row in result["selected_stations_by_variable"]:
            if not row.get("station_id"):
                lines.append(
                    f"- {row['variable']}: no station selected | reason={row.get('selection_reason', 'n/a')}"
                )
                continue
            rank_label = (
                f" [rank {row.get('selection_rank')}]"
                if row.get("selection_rank") is not None
                else ""
            )
            lines.extend(
                [
                    (
                f"- {row['variable']}{rank_label}: "
                f"{row.get('station_id')} | {row.get('station_name') or 'unknown'} | "
                f"distance={_format_optional_number(row.get('distance_km'))} km | "
                f"elev_diff={_format_optional_number(row.get('elevation_diff_m'), 1)} m | "
                f"selection={row.get('selection_status', 'n/a')}"
                    ),
                    f"  reason={row.get('selection_reason', 'n/a')}",
                ]
            )
    if result.get("candidate_review_artifacts"):
        artifacts = result["candidate_review_artifacts"]
        lines.extend(
            [
                "",
                "Candidate review artifacts",
                f"- csv: {artifacts.get('csv')}",
                f"- json: {artifacts.get('json')}",
                f"- html: {artifacts.get('html')}",
            ]
        )
    if result["grid_failures"]:
        lines.extend(["", "Grid fetch failures"])
        for failure in result["grid_failures"]:
            lines.append(
                f"- station={failure['station_id']} source={failure['grid_source']} error={failure['error']}"
            )
    if result.get("grid_source_metadata"):
        lines.extend(
            [
                "",
                "Grid source metadata",
                _render_grid_source_metadata(result["grid_source_metadata"]),
            ]
        )
    if result.get("use_case_rankings"):
        lines.extend(
            [
                "",
                "Use-case rankings (heuristic overlap-based scores)",
                _render_use_case_rankings(result["use_case_rankings"]),
            ]
        )
    if result.get("warnings"):
        lines.extend(["", "Warnings"])
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "Daily station-level metrics (core)",
            _render_metric_core_table(result["metrics"]),
            "",
            "Daily precipitation skill metrics",
            _render_precip_skill_table(result["metrics"]),
            "",
            "Precipitation intensity and extremes (overlap-period summaries)",
            _render_precip_extremes_table(result["metrics"]),
            "",
            "Monthly aggregated metrics (calendar-month overlap summaries)",
            _render_metric_core_table(result.get("monthly_metrics", []), include_period_count=True, include_confidence=False),
            "",
            "Seasonal aggregated metrics (DJF/MAM/JJA/SON overlap summaries)",
            _render_metric_core_table(result.get("seasonal_metrics", []), include_period_count=True, include_confidence=False),
            "",
            "Annual overlap summary (core)",
            _render_annual_core_table(result.get("annual_metrics", [])),
            "",
            "Annual precipitation totals",
            _render_annual_precip_totals_table(result.get("annual_metrics", [])),
            "",
            "xclim annual precipitation reference indices",
            _render_xclim_table(result.get("xclim_precip_indices", [])),
            "",
            "Pooled daily reference metrics (core)",
            _render_metric_core_table(result.get("pooled_daily_metrics", [])),
            "",
            "Pooled daily precipitation skill metrics",
            _render_precip_skill_table(result.get("pooled_daily_metrics", [])),
            "",
            "Pooled monthly reference metrics (core)",
            _render_metric_core_table(result.get("pooled_monthly_metrics", []), include_period_count=True, include_confidence=False),
            "",
            "Pooled seasonal reference metrics (core)",
            _render_metric_core_table(result.get("pooled_seasonal_metrics", []), include_period_count=True, include_confidence=False),
            "",
            "Pooled annual reference metrics (core)",
            _render_annual_core_table(result.get("pooled_annual_metrics", [])),
            "",
            "Pooled annual precipitation totals",
            _render_annual_precip_totals_table(result.get("pooled_annual_metrics", [])),
            "",
            "Stacked station-day overall metrics (core)",
            _render_metric_core_table(result["overall_metrics"]),
            "",
            "Stacked station-day precipitation skill metrics",
            _render_precip_skill_table(result["overall_metrics"]),
        ]
    )
    return "\n".join(lines)


def compare_station_to_grids(
    *,
    station_source: str,
    station_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    grid_sources: list[str],
    variables=None,
    station_id: str | None = None,
    selection_mode: str = "auto",
    selection_strategy: str = DEFAULT_SELECTION_STRATEGY,
    auto_select: str = "auto-1",
    max_distance_km: float = 50.0,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = 500.0,
    min_completeness_ratio: float = 0.7,
    candidate_limit: int = 10,
    score_limit: int = 25,
    auto_anchor_elevation: bool = True,
    disable_completeness_guard: bool = False,
    max_auto_stations: int = 10,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
    precip_source: str | None = None,
    temp_source: str | None = None,
    wet_day_threshold_mm: float = DEFAULT_WET_DAY_THRESHOLD_MM,
    min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS,
    verbose: bool = True,
    custom_station_file: str | None = None,
    custom_station_name: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    candidate_report_prefix: str | None = None,
) -> dict[str, Any]:
    normalized_grid_sources = _normalize_grid_sources(grid_sources)
    requested_variables = variables or DEFAULT_COMPARE_VARIABLES
    resolved_strategy = _normalize_selection_strategy(selection_strategy)
    resolved_target_elevation_m = target_elevation_m
    warnings: list[str] = []
    grid_source_metadata = _grid_source_metadata_rows(normalized_grid_sources)
    for meta in grid_source_metadata:
        if meta.get("station_informed") is True:
            warning = (
                f"Grid source '{meta['grid_source']}' is station-informed "
                f"({meta['product_class']}); validation may be partly non-independent."
            )
            if warning not in warnings:
                warnings.append(warning)
    if resolved_target_elevation_m is None and auto_anchor_elevation:
        try:
            resolved_target_elevation_m = fetch_anchor_elevation(
                lat=float(station_coord[0]),
                lon=float(station_coord[1]),
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            )
            if verbose:
                print(
                    "Anchor elevation resolved from DEM "
                    f"for {station_coord[0]:.4f}, {station_coord[1]:.4f}: "
                    f"{resolved_target_elevation_m:.1f} m"
                )
        except Exception as exc:
            warning = (
                "Anchor elevation unavailable; continuing without elevation guard. "
                f"Reason: {exc}"
            )
            warnings.append(warning)
            if verbose:
                print(warning)
    compare_payloads, payload_warnings, selected_station_map = _build_station_compare_payloads(
        station_source=station_source,
        station_coord=station_coord,
        date_from=date_from,
        date_to=date_to,
        requested_variables=requested_variables,
        station_id=station_id,
        selection_mode=selection_mode,
        selection_strategy=resolved_strategy,
        auto_select=auto_select,
        max_distance_km=max_distance_km,
        target_elevation_m=resolved_target_elevation_m,
        max_elevation_diff_m=max_elevation_diff_m,
        min_completeness_ratio=min_completeness_ratio,
        candidate_limit=candidate_limit,
        score_limit=score_limit,
        auto_anchor_elevation=False,
        disable_completeness_guard=disable_completeness_guard,
        max_auto_stations=max_auto_stations,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        verbose=verbose,
        custom_station_file=custom_station_file,
        custom_station_name=custom_station_name,
        custom_temp_unit=custom_temp_unit,
        custom_precip_unit=custom_precip_unit,
    )
    warnings.extend(payload_warnings)
    _compare_log(
        verbose,
        f"Station payloads ready: {len(compare_payloads)} payload(s) | "
        f"selected variable mappings={len(selected_station_map)}",
    )
    candidate_review_artifacts = None
    if candidate_report_prefix:
        _compare_log(verbose, f"Building candidate review artifacts: {candidate_report_prefix}")
        candidate_frame = download_station_data(
            station_source=station_source,
            station_coord=station_coord,
            date_from=date_from,
            date_to=date_to,
            variables=requested_variables,
            station_id=station_id,
            stage="preprocessed",
            verbose=False,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            selection_mode="list",
            max_distance_km=max_distance_km,
            target_elevation_m=resolved_target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            min_completeness_ratio=min_completeness_ratio,
            candidate_limit=candidate_limit,
            score_limit=score_limit,
            auto_select=auto_select,
            auto_anchor_elevation=False,
            disable_completeness_guard=disable_completeness_guard,
            max_auto_stations=max_auto_stations,
            custom_station_file=custom_station_file,
            custom_station_name=custom_station_name,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
        scope_summary = summarize_station_search_scope(
            station_source=station_source,
            location_coord=(float(station_coord[0]), float(station_coord[1])),
            max_distance_km=max_distance_km,
            target_elevation_m=resolved_target_elevation_m,
            max_elevation_diff_m=max_elevation_diff_m,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            displayed_candidates=candidate_frame,
        )
        csv_path, json_path, html_path = save_candidate_review_artifacts(
            candidates=candidate_frame,
            report_prefix=candidate_report_prefix,
            anchor_lat=float(station_coord[0]),
            anchor_lon=float(station_coord[1]),
            station_source=station_source,
            period_start=date_from.isoformat(),
            period_end=date_to.isoformat(),
            scope_summary=scope_summary,
        )
        candidate_review_artifacts = {
            "csv": str(csv_path),
            "json": str(json_path),
            "html": str(html_path),
        }
        _compare_log(
            verbose,
            f"Candidate review artifacts saved: html={candidate_review_artifacts['html']}",
        )

    metrics_rows: list[dict[str, Any]] = []
    monthly_metrics_rows: list[dict[str, Any]] = []
    seasonal_metrics_rows: list[dict[str, Any]] = []
    annual_metrics_rows: list[dict[str, Any]] = []
    xclim_precip_rows: list[dict[str, Any]] = []
    overall_overlap_frames: list[pd.DataFrame] = []
    pooled_daily_metrics: list[dict[str, Any]] = []
    pooled_monthly_metrics: list[dict[str, Any]] = []
    pooled_seasonal_metrics: list[dict[str, Any]] = []
    pooled_annual_metrics: list[dict[str, Any]] = []
    grid_failures: list[dict[str, Any]] = []
    grid_fetch_summary: list[dict[str, Any]] = []
    station_summary = []
    fetch_cache: dict[tuple[str, float, float], pd.DataFrame] = {}

    for payload_index, payload in enumerate(compare_payloads, start=1):
        station_group = payload["station_frame"].copy()
        station_group["date"] = pd.to_datetime(station_group["date"])
        station_group = station_group.sort_values("date").reset_index(drop=True)
        compare_variable_names = payload["compare_variables"]
        station_meta = _build_station_summary(station_group)
        station_summary.append(station_meta)
        _compare_log(
            verbose,
            f"Comparing payload {payload_index}/{len(compare_payloads)} | "
            f"station={station_meta['station_id']} | vars={','.join(compare_variable_names)} | "
            f"rows={station_meta['rows']}",
        )
        station_lat = (
            float(station_meta["station_lat"])
            if station_meta["station_lat"] is not None
            else float(station_coord[0])
        )
        station_lon = (
            float(station_meta["station_lon"])
            if station_meta["station_lon"] is not None
            else float(station_coord[1])
        )

        station_subset = station_group[["date"] + [column for column in compare_variable_names if column in station_group.columns]].copy()

        for grid_index, grid_source in enumerate(normalized_grid_sources, start=1):
            cache_key = (grid_source, round(station_lat, 5), round(station_lon, 5))
            cache_state = "hit" if cache_key in fetch_cache else "miss"
            _compare_log(
                verbose,
                f"  Grid {grid_index}/{len(normalized_grid_sources)} | source={grid_source} | cache={cache_state}",
            )
            try:
                if cache_key not in fetch_cache:
                    fetch_cache[cache_key] = _fetch_grid_source(
                        source=grid_source,
                        lat=station_lat,
                        lon=station_lon,
                        date_from=date_from,
                        date_to=date_to,
                        variables=requested_variables,
                        precip_source=precip_source,
                        temp_source=temp_source,
                        cache_dir=cache_dir,
                        refresh_cache=refresh_cache,
                    )
                grid_frame = fetch_cache[cache_key].copy()
            except Exception as exc:
                grid_failures.append(
                    {
                        "station_id": station_meta["station_id"],
                        "grid_source": grid_source,
                        "error": str(exc),
                    }
                )
                continue

            grid_fetch_summary.append(
                {
                    "station_id": station_meta["station_id"],
                    "grid_source": grid_source,
                    "grid_lat": station_lat,
                    "grid_lon": station_lon,
                    "rows": int(len(grid_frame)),
                    "date_start": pd.to_datetime(grid_frame["date"]).min().date().isoformat(),
                    "date_end": pd.to_datetime(grid_frame["date"]).max().date().isoformat(),
                }
            )
            grid_subset = grid_frame[["date"] + [column for column in compare_variable_names if column in grid_frame.columns]].copy()
            merged = pd.merge(
                station_subset,
                grid_subset,
                on="date",
                how="inner",
                suffixes=("_station", "_grid"),
            )
            if merged.empty:
                continue

            for variable_name in compare_variable_names:
                metric_row = _compute_variable_metrics(
                    merged,
                    variable=variable_name,
                    wet_day_threshold_mm=wet_day_threshold_mm,
                    min_overlap_days=min_overlap_days,
                )
                if metric_row is None:
                    continue
                metric_row.update(
                    {
                        "station_id": station_meta["station_id"],
                        "station_name": station_meta["station_name"],
                        "grid_source": grid_source,
                        "station_lat": station_lat,
                        "station_lon": station_lon,
                    }
                )
                metrics_rows.append(metric_row)
                overlap_warning = _build_overlap_warning(
                    station_id=str(station_meta["station_id"]),
                    grid_source=grid_source,
                    variable=variable_name,
                    overlap_days=metric_row["overlap_days"],
                    min_overlap_days=min_overlap_days,
                )
                if overlap_warning and overlap_warning not in warnings:
                    warnings.append(overlap_warning)
                overlap = merged[["date", f"{variable_name}_station", f"{variable_name}_grid"]].dropna().copy()
                overlap["station_id"] = station_meta["station_id"]
                overlap["grid_source"] = grid_source
                overlap["variable"] = variable_name
                overall_overlap_frames.append(overlap)
                monthly_metric = _compute_aggregated_metrics(
                    overlap,
                    variable=variable_name,
                    frequency="M",
                )
                if monthly_metric is not None:
                    monthly_metric.update(
                        {
                            "station_id": station_meta["station_id"],
                            "station_name": station_meta["station_name"],
                            "grid_source": grid_source,
                        }
                    )
                    monthly_metrics_rows.append(monthly_metric)
                seasonal_metric = _compute_aggregated_metrics(
                    overlap,
                    variable=variable_name,
                    frequency="seasonal",
                )
                if seasonal_metric is not None:
                    seasonal_metric.update(
                        {
                            "station_id": station_meta["station_id"],
                            "station_name": station_meta["station_name"],
                            "grid_source": grid_source,
                        }
                    )
                    seasonal_metrics_rows.append(seasonal_metric)
                annual_metric = _compute_aggregated_metrics(
                    overlap,
                    variable=variable_name,
                    frequency="Y",
                )
                if annual_metric is not None:
                    annual_metric.update(
                        {
                            "station_id": station_meta["station_id"],
                            "station_name": station_meta["station_name"],
                            "grid_source": grid_source,
                        }
                    )
                    annual_metric = _annotate_annual_overlap_summary(
                        overlap,
                        variable=variable_name,
                        metric_row=annual_metric,
                    )
                    annual_metrics_rows.append(annual_metric)
                if variable_name == "precipitation" and XCLIM_AVAILABLE:
                    xclim_readiness = assess_xclim_precip_annual_readiness(
                        overlap,
                        value_column=f"{variable_name}_station",
                    )
                    if xclim_readiness is not None:
                        warning = (
                            "Skipped xclim annual precipitation reference indices for "
                            f"station={station_meta['station_id']} source={grid_source}: "
                            f"{xclim_readiness}."
                        )
                        if warning not in warnings:
                            warnings.append(warning)
                    else:
                        try:
                            xclim_rows = compare_xclim_precip_indices(
                                overlap,
                                station_column=f"{variable_name}_station",
                                grid_column=f"{variable_name}_grid",
                                freq="YS",
                            )
                        except Exception as exc:
                            warning = (
                                "Skipped xclim annual precipitation reference indices for "
                                f"station={station_meta['station_id']} source={grid_source}: "
                                f"{exc}."
                            )
                            if warning not in warnings:
                                warnings.append(warning)
                        else:
                            for xrow in xclim_rows:
                                xrow.update(
                                    {
                                        "station_id": station_meta["station_id"],
                                        "station_name": station_meta["station_name"],
                                        "grid_source": grid_source,
                                        "variable": "precipitation",
                                        "timescale": "annual_xclim",
                                    }
                                )
                                xclim_precip_rows.append(xrow)

    overall_metrics: list[dict[str, Any]] = []
    if overall_overlap_frames:
        _compare_log(
            verbose,
            f"Building pooled summaries from {len(overall_overlap_frames)} overlap frame(s)",
        )
        pooled = pd.concat(overall_overlap_frames, ignore_index=True)
        for (grid_source, variable_name), overlap_group in pooled.groupby(["grid_source", "variable"], sort=False):
            pooled_reference = _build_pooled_reference_overlap(
                overlap_group,
                variable=variable_name,
            )
            if not pooled_reference.empty:
                pooled_metric_row = _compute_variable_metrics(
                    pooled_reference,
                    variable=variable_name,
                    wet_day_threshold_mm=wet_day_threshold_mm,
                    min_overlap_days=min_overlap_days,
                )
                if pooled_metric_row is not None:
                    pooled_metric_row.update(
                        {
                            "station_id": "POOLED_REF",
                            "grid_source": grid_source,
                            "timescale": "daily",
                        }
                    )
                    pooled_metric_row = _annotate_pooled_metric_row(
                        pooled_reference,
                        pooled_metric_row,
                    )
                    pooled_daily_metrics.append(pooled_metric_row)

                pooled_monthly_metric = _compute_aggregated_metrics(
                    pooled_reference,
                    variable=variable_name,
                    frequency="M",
                )
                if pooled_monthly_metric is not None:
                    pooled_monthly_metric.update(
                        {
                            "station_id": "POOLED_REF",
                            "grid_source": grid_source,
                        }
                    )
                    pooled_monthly_metric = _annotate_pooled_metric_row(
                        pooled_reference,
                        pooled_monthly_metric,
                    )
                    pooled_monthly_metrics.append(pooled_monthly_metric)

                pooled_seasonal_metric = _compute_aggregated_metrics(
                    pooled_reference,
                    variable=variable_name,
                    frequency="seasonal",
                )
                if pooled_seasonal_metric is not None:
                    pooled_seasonal_metric.update(
                        {
                            "station_id": "POOLED_REF",
                            "grid_source": grid_source,
                        }
                    )
                    pooled_seasonal_metric = _annotate_pooled_metric_row(
                        pooled_reference,
                        pooled_seasonal_metric,
                    )
                    pooled_seasonal_metrics.append(pooled_seasonal_metric)

                pooled_annual_metric = _compute_aggregated_metrics(
                    pooled_reference,
                    variable=variable_name,
                    frequency="Y",
                )
                if pooled_annual_metric is not None:
                    pooled_annual_metric.update(
                        {
                            "station_id": "POOLED_REF",
                            "grid_source": grid_source,
                        }
                    )
                    pooled_annual_metric = _annotate_annual_overlap_summary(
                        pooled_reference,
                        variable=variable_name,
                        metric_row=pooled_annual_metric,
                    )
                    pooled_annual_metric = _annotate_pooled_metric_row(
                        pooled_reference,
                        pooled_annual_metric,
                    )
                    pooled_annual_metrics.append(pooled_annual_metric)

            metric_row = _compute_variable_metrics(
                overlap_group.rename(
                    columns={
                        f"{variable_name}_station": f"{variable_name}_station",
                        f"{variable_name}_grid": f"{variable_name}_grid",
                    }
                ),
                variable=variable_name,
                wet_day_threshold_mm=wet_day_threshold_mm,
                min_overlap_days=min_overlap_days,
            )
            if metric_row is None:
                continue
            metric_row.update(
                {
                    "station_id": "ALL",
                    "grid_source": grid_source,
                    "timescale": "daily",
                }
            )
            overall_metrics.append(metric_row)

    use_case_rankings = _build_use_case_rankings(
        metrics_rows=metrics_rows,
        monthly_metrics_rows=monthly_metrics_rows,
        seasonal_metrics_rows=seasonal_metrics_rows,
        annual_metrics_rows=annual_metrics_rows,
    )
    _compare_log(
        verbose,
        f"Compare complete | station_metrics={len(metrics_rows)} | "
        f"monthly={len(monthly_metrics_rows)} | seasonal={len(seasonal_metrics_rows)} | "
        f"annual={len(annual_metrics_rows)} | failures={len(grid_failures)}",
    )

    return {
        "anchor_location": {
            "lat": float(station_coord[0]),
            "lon": float(station_coord[1]),
        },
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "station_source": station_source,
        "selection_mode": selection_mode,
        "selection_strategy": resolved_strategy,
        "auto_select": auto_select if selection_mode == "auto" else None,
        "target_elevation_m": resolved_target_elevation_m,
        "selected_stations_by_variable": selected_station_map,
        "grid_sources": normalized_grid_sources,
        "candidate_review_artifacts": candidate_review_artifacts,
        "grid_source_metadata": grid_source_metadata,
        "precip_source": normalize_climate_dataset_name(precip_source),
        "temp_source": normalize_climate_dataset_name(temp_source),
        "wet_day_threshold_mm": float(wet_day_threshold_mm),
        "min_overlap_days": int(min_overlap_days),
        "station_summary": station_summary,
        "grid_fetch_summary": grid_fetch_summary,
        "grid_failures": grid_failures,
        "warnings": warnings,
        "metrics": metrics_rows,
        "monthly_metrics": monthly_metrics_rows,
        "seasonal_metrics": seasonal_metrics_rows,
        "annual_metrics": annual_metrics_rows,
        "xclim_available": XCLIM_AVAILABLE,
        "xclim_precip_indices": xclim_precip_rows,
        "pooled_reference_method": "date_mean_across_selected_stations",
        "pooled_daily_metrics": pooled_daily_metrics,
        "pooled_monthly_metrics": pooled_monthly_metrics,
        "pooled_seasonal_metrics": pooled_seasonal_metrics,
        "pooled_annual_metrics": pooled_annual_metrics,
        "overall_metrics": overall_metrics,
        "use_case_rankings": use_case_rankings,
    }


def _json_default(value):
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    if isinstance(value, np.floating):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare observed station data against historical gridded climate datasets."
    )
    parser.add_argument(
        "--station-source",
        choices=["auto", "ghcn_daily", "gsod", "custom_csv"],
        default="ghcn_daily",
        help="Observed station backend: ghcn_daily, gsod, custom_csv, or auto (rank across NOAA backends). custom_csv requires --custom-station-file.",
    )
    parser.add_argument("--station-lat", type=float, required=True)
    parser.add_argument("--station-lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--grid-source", action="append", dest="grid_sources", default=[])
    parser.add_argument("--precip-source", default=DEFAULT_AUTO_PRECIP_SOURCE)
    parser.add_argument("--temp-source", default=DEFAULT_AUTO_TEMP_SOURCE)
    parser.add_argument("--station-id", default=None)
    parser.add_argument("--custom-station-file", default=None,
                        help="Path to custom station CSV/JSON. Use with --station-source custom_csv.")
    parser.add_argument("--custom-station-name", default=None,
                        help="Optional station label for custom station file.")
    parser.add_argument("--custom-temp-unit", choices=["c", "f", "k"], default="c",
                        help="Temperature unit in custom station file (default: c).")
    parser.add_argument("--custom-precip-unit", choices=["mm", "inch", "tenth_mm"], default="mm",
                        help="Precipitation unit in custom station file (default: mm).")
    parser.add_argument("--selection-mode", choices=["auto", "specified"], default="auto")
    parser.add_argument(
        "--selection-strategy",
        choices=sorted(SUPPORTED_SELECTION_STRATEGIES),
        default=DEFAULT_SELECTION_STRATEGY,
    )
    parser.add_argument("--auto-select", default="auto-1")
    parser.add_argument("--variables", default="precipitation,max_temperature,min_temperature")
    parser.add_argument("--wet-day-threshold-mm", type=float, default=DEFAULT_WET_DAY_THRESHOLD_MM)
    parser.add_argument("--min-overlap-days", type=int, default=DEFAULT_MIN_OVERLAP_DAYS)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--max-distance-km", type=float, default=50.0)
    parser.add_argument("--target-elevation-m", type=float, default=None)
    parser.add_argument("--max-elevation-diff-m", type=float, default=500.0)
    parser.add_argument("--no-auto-anchor-elevation", action="store_true")
    parser.add_argument("--disable-completeness-guard", action="store_true")
    parser.add_argument("--min-completeness-ratio", type=float, default=0.7)
    parser.add_argument("--max-auto-stations", type=int, default=10)
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--score-limit", type=int, default=25)
    parser.add_argument("--candidate-report-prefix", default=None)
    parser.add_argument("--open-report", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    try:
        if args.station_source == "custom_csv" and not args.custom_station_file:
            raise ValueError(
                "station_source='custom_csv' requires --custom-station-file. "
                + custom_station_format_help()
            )
        result = compare_station_to_grids(
            station_source=args.station_source,
            station_coord=(args.station_lat, args.station_lon),
            date_from=date.fromisoformat(args.start),
            date_to=date.fromisoformat(args.end),
            grid_sources=args.grid_sources,
            variables=parse_variables(args.variables),
            station_id=args.station_id,
            selection_mode=args.selection_mode,
            selection_strategy=args.selection_strategy,
            auto_select=args.auto_select,
            max_distance_km=args.max_distance_km,
            target_elevation_m=args.target_elevation_m,
            max_elevation_diff_m=args.max_elevation_diff_m,
            min_completeness_ratio=args.min_completeness_ratio,
            candidate_limit=args.candidate_limit,
            score_limit=args.score_limit,
            auto_anchor_elevation=not args.no_auto_anchor_elevation,
            disable_completeness_guard=args.disable_completeness_guard,
            max_auto_stations=args.max_auto_stations,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            precip_source=args.precip_source,
            temp_source=args.temp_source,
            wet_day_threshold_mm=args.wet_day_threshold_mm,
            min_overlap_days=args.min_overlap_days,
            verbose=not args.quiet,
            custom_station_file=args.custom_station_file,
            custom_station_name=args.custom_station_name,
            custom_temp_unit=args.custom_temp_unit,
            custom_precip_unit=args.custom_precip_unit,
            candidate_report_prefix=args.candidate_report_prefix,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, default=_json_default),
            encoding="utf-8",
        )

    if args.format == "json":
        print(json.dumps(result, indent=2, default=_json_default))
    else:
        print(render_compare_report(result))
        if args.output:
            print(f"\nSaved JSON report: {args.output}")
    if args.open_report and result.get("candidate_review_artifacts", {}).get("html"):
        html_path = result["candidate_review_artifacts"]["html"]
        opened = _open_report_html(html_path)
        if not args.quiet:
            print(f"{'Opened' if opened else 'Could not open'} report HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
