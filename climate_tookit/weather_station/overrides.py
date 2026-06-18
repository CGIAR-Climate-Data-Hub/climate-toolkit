"""Shared helpers for applying custom station overrides onto gridded data."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

import pandas as pd

from climate_tookit.weather_station.custom_station import load_custom_station_data


_STATION_METADATA_COLUMNS = {
    "date",
    "station_id",
    "station_name",
    "station_lat",
    "station_lon",
    "station_elevation_m",
    "station_distance_km",
    "station_source",
}


def _attach_custom_station_warning(frame: pd.DataFrame, warning: str) -> pd.DataFrame:
    attached = frame.copy()
    warnings = list(attached.attrs.get("custom_station_warnings", []))
    if warning not in warnings:
        warnings.append(warning)
    attached.attrs["custom_station_warnings"] = warnings
    return attached


def _attach_custom_station_summary(
    frame: pd.DataFrame,
    summary_rows: list[dict],
) -> pd.DataFrame:
    attached = frame.copy()
    attached.attrs["custom_station_override_summary"] = summary_rows
    return attached


def apply_custom_station_overrides(
    base_df: pd.DataFrame,
    *,
    lat: float,
    lon: float,
    date_from: date,
    date_to: date,
    custom_station_file: Optional[str],
    custom_station_variables: Optional[Iterable[str]] = None,
    custom_station_name: Optional[str] = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    rename_map: Optional[dict[str, str]] = None,
    stage: str = "preprocessed",
) -> pd.DataFrame:
    if not custom_station_file:
        return base_df

    requested = list(custom_station_variables or [
        "precipitation",
        "max_temperature",
        "min_temperature",
    ])
    try:
        station_df = load_custom_station_data(
            custom_station_file=custom_station_file,
            date_from=date_from,
            date_to=date_to,
            variables=requested,
            stage=stage,
            station_coord=(lat, lon),
            station_name=custom_station_name,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
    except ValueError as exc:
        if "no rows in requested window" in str(exc):
            warning = (
                "Custom station override skipped: uploaded station file has no rows in "
                f"requested window {date_from.isoformat()}..{date_to.isoformat()}. "
                "Using gridded data for that period."
            )
            summary_rows = [
                {
                    "variable": variable,
                    "override_days": 0,
                    "total_days": int(len(base_df)),
                    "fallback_days": int(len(base_df)),
                    "status": "skipped_no_overlap",
                }
                for variable in requested
            ]
            return _attach_custom_station_summary(
                _attach_custom_station_warning(base_df, warning),
                summary_rows,
            )
        raise
    if station_df.empty:
        warning = (
            "Custom station override skipped: uploaded station file returned no rows in "
            f"requested window {date_from.isoformat()}..{date_to.isoformat()}. "
            "Using gridded data for that period."
        )
        summary_rows = [
            {
                "variable": variable,
                "override_days": 0,
                "total_days": int(len(base_df)),
                "fallback_days": int(len(base_df)),
                "status": "skipped_empty",
            }
            for variable in requested
        ]
        return _attach_custom_station_summary(
            _attach_custom_station_warning(base_df, warning),
            summary_rows,
        )

    working = base_df.copy()
    station_working = station_df.copy()
    if rename_map:
        station_working = station_working.rename(columns=rename_map)
    working["date"] = pd.to_datetime(working["date"])
    station_working["date"] = pd.to_datetime(station_working["date"])

    override_columns = [
        column
        for column in station_working.columns
        if column in working.columns and column not in _STATION_METADATA_COLUMNS
    ]
    if not override_columns:
        raise RuntimeError(
            "Custom station file did not provide any override columns after normalization."
        )

    merged = pd.merge(
        working,
        station_working[["date"] + override_columns],
        on="date",
        how="left",
        suffixes=("", "_station_override"),
    )
    summary_rows: list[dict] = []
    for column in override_columns:
        override_col = f"{column}_station_override"
        if override_col not in merged.columns:
            continue
        override_days = int(merged[override_col].notna().sum())
        total_days = int(len(merged))
        fallback_days = int(total_days - override_days)
        summary_rows.append(
            {
                "variable": column,
                "override_days": override_days,
                "total_days": total_days,
                "fallback_days": fallback_days,
                "status": "full_override" if fallback_days == 0 else "partial_override",
            }
        )
        merged[column] = merged[override_col].combine_first(merged.get(column))
        merged = merged.drop(columns=[override_col])
    result = merged.sort_values("date").reset_index(drop=True)
    result = _attach_custom_station_summary(result, summary_rows)
    for row in summary_rows:
        if row["fallback_days"] > 0:
            result = _attach_custom_station_warning(
                result,
                "Custom station override partial coverage for "
                f"{row['variable']}: {row['override_days']}/{row['total_days']} day(s) "
                f"overridden; remaining {row['fallback_days']} day(s) use gridded data.",
            )
    return result
