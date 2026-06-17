"""Custom user-supplied weather station ingestion and normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from climate_tookit.fetch_data.preprocess_data.preprocess_data import (
    clean_climate_data,
    quality_control_checks,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    canonical_climate_variable_name,
)


DEFAULT_CUSTOM_CACHE_ROOT = Path("outputs/cache/weather_stations/custom")

CUSTOM_COLUMN_ALIASES = {
    "date": "date",
    "day": "date",
    "datetime": "date",
    "time": "date",
    "station_id": "station_id",
    "id": "station_id",
    "station": "station_id",
    "station_name": "station_name",
    "name": "station_name",
    "station_lat": "station_lat",
    "latitude": "station_lat",
    "lat": "station_lat",
    "station_lon": "station_lon",
    "longitude": "station_lon",
    "lon": "station_lon",
    "station_elevation_m": "station_elevation_m",
    "elevation_m": "station_elevation_m",
    "elevation": "station_elevation_m",
    "altitude_m": "station_elevation_m",
    "precipitation": "precipitation",
    "precip": "precipitation",
    "rain": "precipitation",
    "rainfall": "precipitation",
    "prcp": "precipitation",
    "max_temperature": "max_temperature",
    "tmax": "max_temperature",
    "maximum_temperature": "max_temperature",
    "min_temperature": "min_temperature",
    "tmin": "min_temperature",
    "minimum_temperature": "min_temperature",
    "mean_temperature": "mean_temperature",
    "tmean": "mean_temperature",
    "tavg": "mean_temperature",
    "average_temperature": "mean_temperature",
    "humidity": "humidity",
    "relative_humidity": "humidity",
    "rh": "humidity",
    "wind_speed": "wind_speed",
    "windspeed": "wind_speed",
    "wind": "wind_speed",
    "solar_radiation": "solar_radiation",
    "solar": "solar_radiation",
    "radiation": "solar_radiation",
}

VARIABLE_COLUMNS = {
    "precipitation",
    "max_temperature",
    "min_temperature",
    "mean_temperature",
    "humidity",
    "wind_speed",
    "solar_radiation",
}

STATION_METADATA_COLUMNS = {
    "station_id",
    "station_name",
    "station_lat",
    "station_lon",
    "station_elevation_m",
    "station_distance_km",
    "station_source",
}


def _custom_cache_root(cache_dir: str | None) -> Path:
    if cache_dir:
        return Path(cache_dir) / "weather_stations" / "custom"
    return DEFAULT_CUSTOM_CACHE_ROOT


def _cache_key(path: Path) -> str:
    stat = path.stat()
    payload = f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _requested_variable_names(variables: Iterable[ClimateVariable | str] | None) -> list[str]:
    names: list[str] = []
    for variable in (variables or []):
        if hasattr(variable, "name"):
            names.append(str(variable.name))
        else:
            names.append(canonical_climate_variable_name(str(variable)))
    return names


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError("custom station file must be .csv or .json")


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    seen: set[str] = set()
    for column in frame.columns:
        canonical = CUSTOM_COLUMN_ALIASES.get(str(column).strip().lower())
        if canonical and canonical not in seen:
            renamed[column] = canonical
            seen.add(canonical)
        else:
            renamed[column] = str(column).strip()
    return frame.rename(columns=renamed)


def _apply_custom_unit_conversions(
    frame: pd.DataFrame,
    *,
    temp_unit: str,
    precip_unit: str,
) -> pd.DataFrame:
    converted = frame.copy()
    temp_token = str(temp_unit or "c").strip().lower()
    precip_token = str(precip_unit or "mm").strip().lower()

    temp_columns = [
        column for column in ("max_temperature", "min_temperature", "mean_temperature")
        if column in converted.columns
    ]
    if temp_token == "k":
        for column in temp_columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce") - 273.15
    elif temp_token == "f":
        for column in temp_columns:
            values = pd.to_numeric(converted[column], errors="coerce")
            converted[column] = (values - 32.0) * (5.0 / 9.0)
    else:
        for column in temp_columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce")

    if "precipitation" in converted.columns:
        values = pd.to_numeric(converted["precipitation"], errors="coerce")
        if precip_token in {"inch", "inches", "in"}:
            converted["precipitation"] = values * 25.4
        elif precip_token in {"tenth_mm", "tenths_mm"}:
            converted["precipitation"] = values / 10.0
        else:
            converted["precipitation"] = values

    for column in ("humidity", "wind_speed", "solar_radiation", "station_lat", "station_lon", "station_elevation_m"):
        if column in converted.columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce")
    return converted


def _ensure_station_metadata(
    frame: pd.DataFrame,
    *,
    station_coord: tuple[float, float] | None,
    station_id: str | None,
    station_name: str | None,
    source_path: Path,
) -> pd.DataFrame:
    ensured = frame.copy()
    if "station_id" not in ensured.columns or ensured["station_id"].isna().all():
        fallback_id = station_id or source_path.stem
        ensured["station_id"] = fallback_id
    else:
        ensured["station_id"] = ensured["station_id"].fillna(station_id or source_path.stem).astype(str)

    if "station_name" not in ensured.columns or ensured["station_name"].isna().all():
        fallback_name = station_name or source_path.stem
        ensured["station_name"] = fallback_name
    else:
        ensured["station_name"] = ensured["station_name"].fillna(station_name or source_path.stem).astype(str)

    lat, lon = station_coord if station_coord is not None else (None, None)
    if "station_lat" not in ensured.columns:
        ensured["station_lat"] = lat
    else:
        ensured["station_lat"] = ensured["station_lat"].fillna(lat)
    if "station_lon" not in ensured.columns:
        ensured["station_lon"] = lon
    else:
        ensured["station_lon"] = ensured["station_lon"].fillna(lon)

    if "station_elevation_m" not in ensured.columns:
        ensured["station_elevation_m"] = pd.NA
    ensured["station_distance_km"] = 0.0
    ensured["station_source"] = "custom_csv"
    return ensured


def _build_expected_columns(requested_variables: list[str]) -> list[str]:
    ordered = ["date", *sorted(STATION_METADATA_COLUMNS)]
    for variable in requested_variables:
        if variable in VARIABLE_COLUMNS and variable not in ordered:
            ordered.append(variable)
    return ordered


def _filter_date_window(frame: pd.DataFrame, *, date_from: date, date_to: date) -> pd.DataFrame:
    filtered = frame.copy()
    filtered["date"] = pd.to_datetime(filtered["date"], errors="coerce")
    filtered = filtered.dropna(subset=["date"])
    start_ts = pd.Timestamp(date_from)
    end_ts = pd.Timestamp(date_to)
    filtered = filtered[(filtered["date"] >= start_ts) & (filtered["date"] <= end_ts)].copy()
    return filtered.sort_values("date").reset_index(drop=True)


def load_custom_station_data(
    *,
    custom_station_file: str | Path,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable | str] | None,
    stage: str = "preprocessed",
    station_coord: tuple[float, float] | None = None,
    station_id: str | None = None,
    station_name: str | None = None,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
) -> pd.DataFrame:
    source_path = Path(custom_station_file).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Custom station file not found: {source_path}")

    requested_variables = _requested_variable_names(variables)
    if not requested_variables:
        requested_variables = ["precipitation", "max_temperature", "min_temperature"]

    cache_root = _custom_cache_root(cache_dir) / _cache_key(source_path)
    cache_root.mkdir(parents=True, exist_ok=True)
    stage_token = str(stage).strip().lower()
    cache_path = cache_root / f"{stage_token}_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    manifest_path = cache_root / f"{stage_token}_{date_from.isoformat()}_{date_to.isoformat()}.json"

    if cache_path.exists() and manifest_path.exists() and not refresh_cache:
        cached = pd.read_csv(cache_path, parse_dates=["date"])
        cached.attrs["cache_hit"] = True
        cached.attrs["cache_path"] = str(cache_path)
        return cached

    raw = _read_table(source_path)
    normalized = _normalize_columns(raw)
    if "date" not in normalized.columns:
        raise ValueError("Custom station file must include a date column.")

    normalized = _ensure_station_metadata(
        normalized,
        station_coord=station_coord,
        station_id=station_id,
        station_name=station_name,
        source_path=source_path,
    )
    normalized = _filter_date_window(
        normalized,
        date_from=date_from,
        date_to=date_to,
    )
    if normalized.empty:
        raise ValueError(
            f"Custom station file has no rows in requested window {date_from.isoformat()}..{date_to.isoformat()}."
        )

    available_variables = [column for column in requested_variables if column in normalized.columns]
    if not available_variables:
        raise ValueError(
            "Custom station file does not contain any requested variables. "
            f"Requested: {requested_variables}. Available columns: {list(normalized.columns)}"
        )

    keep_columns = [
        column
        for column in _build_expected_columns(requested_variables)
        if column in normalized.columns
    ]
    normalized = normalized[keep_columns].copy()

    if stage_token == "raw":
        result = normalized
    else:
        converted = _apply_custom_unit_conversions(
            normalized,
            temp_unit=custom_temp_unit,
            precip_unit=custom_precip_unit,
        )
        if (
            "mean_temperature" not in converted.columns
            and "max_temperature" in converted.columns
            and "min_temperature" in converted.columns
        ):
            converted["mean_temperature"] = (
                converted["max_temperature"] + converted["min_temperature"]
            ) / 2.0
        if stage_token == "transformed":
            result = converted
        elif stage_token == "preprocessed":
            result = clean_climate_data(
                converted,
                group_columns=["station_id"],
            )
            result = quality_control_checks(
                result,
                group_columns=["station_id"],
                verbose=False,
            )
            roundable = [
                column
                for column in result.select_dtypes(include=["number"]).columns
                if column not in {"station_lat", "station_lon"}
            ]
            result[roundable] = result[roundable].round(2)
        else:
            raise ValueError("stage must be raw, transformed, or preprocessed")

    result.to_csv(cache_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "source_file": str(source_path),
                "stage": stage_token,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "requested_variables": requested_variables,
                "available_variables": available_variables,
                "custom_temp_unit": custom_temp_unit,
                "custom_precip_unit": custom_precip_unit,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result.attrs["cache_hit"] = False
    result.attrs["cache_path"] = str(cache_path)
    return result


def summarize_custom_station_candidate(
    *,
    custom_station_file: str | Path,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable | str] | None,
    station_coord: tuple[float, float] | None = None,
    station_id: str | None = None,
    station_name: str | None = None,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
) -> pd.DataFrame:
    frame = load_custom_station_data(
        custom_station_file=custom_station_file,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        stage="preprocessed",
        station_coord=station_coord,
        station_id=station_id,
        station_name=station_name,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        custom_temp_unit=custom_temp_unit,
        custom_precip_unit=custom_precip_unit,
    )
    requested_variables = _requested_variable_names(variables)
    first = frame.iloc[0]
    expected_days = int((pd.Timestamp(date_to) - pd.Timestamp(date_from)).days) + 1
    field_counts = {
        variable: int(frame[variable].notna().sum())
        for variable in requested_variables
        if variable in frame.columns
    }
    ratios = {
        variable: (count / expected_days if expected_days > 0 else 0.0)
        for variable, count in field_counts.items()
    }
    min_ratio = min(ratios.values()) if ratios else 0.0
    mean_ratio = sum(ratios.values()) / len(ratios) if ratios else 0.0
    row = {
        "station_source": "custom_csv",
        "station_id": first.get("station_id"),
        "station_name": first.get("station_name"),
        "lat": first.get("station_lat"),
        "lon": first.get("station_lon"),
        "elevation_m": first.get("station_elevation_m"),
        "distance_km": 0.0,
        "elevation_diff_m": 0.0 if station_coord is not None else pd.NA,
        "requested_fields": requested_variables,
        "field_counts": field_counts,
        "expected_days": expected_days,
        "min_completeness_ratio": round(float(min_ratio), 4),
        "mean_completeness_ratio": round(float(mean_ratio), 4),
        "fields_passing_threshold": requested_variables,
        "fields_failing_threshold": [],
        "n_fields_passing_threshold": len(requested_variables),
        "all_fields_meet_threshold": True,
        "selection_threshold_used": 0.0,
        "threshold_status": "custom_file",
        "selection_status": "custom_file",
    }
    return pd.DataFrame([row])
