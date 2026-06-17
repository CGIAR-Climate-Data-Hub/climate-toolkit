"""NOAA GSOD station fetch helpers."""

from __future__ import annotations

import json
from datetime import datetime, date
from io import StringIO
from pathlib import Path
from time import sleep
from time import perf_counter
from typing import Iterable

import pandas as pd
import requests

from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable
from climate_tookit.weather_station.ghcn_daily import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MAX_DISTANCE_KM,
    DEFAULT_MAX_ELEVATION_DIFF_M,
    DEFAULT_MIN_COMPLETENESS_RATIO,
    DEFAULT_SCORE_LIMIT,
    _haversine_km,
    annotate_completeness_threshold,
    build_completeness_threshold_sequence,
    load_ghcn_stations,
)


GSOD_TEMPLATE = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/{year}/{station}.csv"
DEFAULT_GSOD_CACHE_ROOT = Path("outputs/cache/weather_stations")
DEFAULT_GSOD_TIMEOUT_SECONDS = 30
DEFAULT_GSOD_MAX_RETRIES = 2
GSOD_COVERAGE_CACHE_SCHEMA_VERSION = "v1"

SUPPORTED_VARIABLES = {
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
    ClimateVariable.mean_temperature,
    ClimateVariable.wind_speed,
}

SUPPORTED_GSOD_WMO_VARIABLES = {
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
    ClimateVariable.mean_temperature,
    ClimateVariable.wind_speed,
}

GSOD_COLUMN_MAP = {
    ClimateVariable.precipitation: "PRCP",
    ClimateVariable.max_temperature: "MAX",
    ClimateVariable.min_temperature: "MIN",
    ClimateVariable.mean_temperature: "TEMP",
    ClimateVariable.wind_speed: "WDSP",
}

GSOD_MISSING_VALUES = {
    "TEMP": 9999.9,
    "DEWP": 9999.9,
    "SLP": 9999.9,
    "STP": 999.9,
    "VISIB": 999.9,
    "WDSP": 999.9,
    "MXSPD": 999.9,
    "GUST": 999.9,
    "MAX": 9999.9,
    "MIN": 9999.9,
    "PRCP": 99.99,
    "SNDP": 999.9,
}


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _gsod_cache_root(cache_dir: str | Path | None = None) -> Path:
    return Path(cache_dir or DEFAULT_GSOD_CACHE_ROOT) / "gsod"


def _cache_hit(cache_path: Path, refresh_cache: bool) -> bool:
    return cache_path.exists() and not refresh_cache


def _normalize_station_id(station_id: str) -> str:
    token = str(station_id).strip()
    if len(token) == 5 and token.isdigit():
        return f"{token}099999"
    if len(token) == 11 and token.isdigit():
        return token
    raise ValueError(
        f"Unsupported GSOD station_id '{station_id}'. Use 5-digit WMO-like ID or 11-digit GSOD ID."
    )


def _download_text(
    *,
    station_id: str,
    year: int,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    timeout_seconds: int = DEFAULT_GSOD_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_GSOD_MAX_RETRIES,
) -> str | None:
    cache_path = _gsod_cache_root(cache_dir) / "stations" / station_id / f"{year}.csv"
    if cache_path.exists() and not refresh_cache:
        return cache_path.read_text(encoding="utf-8")

    url = GSOD_TEMPLATE.format(year=year, station=station_id)
    last_error = None
    for attempt in range(max(int(max_retries), 0) + 1):
        try:
            response = requests.get(url, timeout=timeout_seconds)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(response.text, encoding="utf-8")
            return response.text
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt >= max(int(max_retries), 0):
                break
            sleep(0.5 * (attempt + 1))
    raise RuntimeError(
        "GSOD download failed after retries for "
        f"station_id={station_id} year={year}. "
        f"Last error: {last_error}"
    )


def _unsupported_station_variables(variables: Iterable[ClimateVariable]) -> list[str]:
    unsupported = [
        variable.name
        for variable in (variables or [])
        if variable not in SUPPORTED_VARIABLES
    ]
    return sorted(set(unsupported))


def _requested_columns(variables: Iterable[ClimateVariable]) -> list[str]:
    columns = []
    for variable in (variables or []):
        col = GSOD_COLUMN_MAP.get(variable)
        if col and col not in columns:
            columns.append(col)
    return columns


def _coverage_variable_fragment(variables: Iterable[ClimateVariable]) -> str:
    tokens = sorted(variable.name for variable in (variables or []))
    return "-".join(tokens) if tokens else "no_variables"


def _coverage_cache_paths(
    *,
    station_id: str,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    base = (
        _gsod_cache_root(cache_dir)
        / "coverage"
        / GSOD_COVERAGE_CACHE_SCHEMA_VERSION
        / station_id
    )
    filename = (
        f"{date_from.isoformat()}_{date_to.isoformat()}_"
        f"{_coverage_variable_fragment(variables)}.json"
    )
    data_path = base / filename
    manifest_path = base / f"{filename}.manifest.json"
    return data_path, manifest_path


def _load_cached_coverage_summary(
    *,
    station_id: str,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> dict | None:
    data_path, manifest_path = _coverage_cache_paths(
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
    )
    if refresh_cache or not data_path.exists() or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("cache_schema_version") != GSOD_COVERAGE_CACHE_SCHEMA_VERSION:
        return None
    if manifest.get("station_id") != station_id:
        return None
    if manifest.get("start_date") != date_from.isoformat():
        return None
    if manifest.get("end_date") != date_to.isoformat():
        return None
    if manifest.get("requested_variables") != sorted(variable.name for variable in (variables or [])):
        return None
    return payload


def _save_cached_coverage_summary(
    *,
    station_id: str,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None,
    payload: dict,
) -> None:
    data_path, manifest_path = _coverage_cache_paths(
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
    )
    data_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "cache_schema_version": GSOD_COVERAGE_CACHE_SCHEMA_VERSION,
        "station_id": station_id,
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
        "requested_variables": sorted(variable.name for variable in (variables or [])),
    }
    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _requested_station_fields(variables: Iterable[ClimateVariable]) -> list[str]:
    fields = []
    for variable in (variables or []):
        if variable == ClimateVariable.precipitation:
            fields.append("precipitation")
        elif variable == ClimateVariable.max_temperature:
            fields.append("max_temperature")
        elif variable == ClimateVariable.min_temperature:
            fields.append("min_temperature")
        elif variable == ClimateVariable.mean_temperature:
            fields.append("mean_temperature")
        elif variable == ClimateVariable.wind_speed:
            fields.append("wind_speed")
    return fields


def _days_inclusive(date_from: date, date_to: date) -> int:
    return (pd.Timestamp(date_to) - pd.Timestamp(date_from)).days + 1


def _normalize_wmo_token(token: str | None) -> str | None:
    if token is None:
        return None
    raw = str(token).strip()
    if not raw or raw.lower() == "none":
        return None
    if len(raw) == 5 and raw.isdigit():
        return raw
    if len(raw) == 11 and raw.isdigit():
        return raw[:5]
    return None


def _candidate_station_base_table(
    *,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    station_id: str | None = None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = DEFAULT_MAX_ELEVATION_DIFF_M,
) -> pd.DataFrame:
    unsupported = [
        variable.name
        for variable in (variables or [])
        if variable not in SUPPORTED_GSOD_WMO_VARIABLES
    ]
    if unsupported:
        raise ValueError(
            "GSOD station backend does not support variables: "
            f"{', '.join(sorted(set(unsupported)))}. Supported variables: "
            "precipitation, max_temperature, min_temperature, mean_temperature, wind_speed."
        )

    stations = load_ghcn_stations(cache_dir=cache_dir, refresh_cache=refresh_cache).copy()
    stations["wmo_id"] = stations["wmo_id"].apply(_normalize_wmo_token)
    stations = stations[stations["wmo_id"].notna()].copy()
    if stations.empty:
        raise ValueError("No WMO-linked station metadata available for GSOD candidate search.")

    stations["station_id"] = stations["wmo_id"].apply(_normalize_station_id)
    lat, lon = location_coord
    stations["distance_km"] = stations.apply(
        lambda row: _haversine_km(lat, lon, float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    if target_elevation_m is not None:
        stations["elevation_diff_m"] = (stations["elevation_m"] - float(target_elevation_m)).abs()
    else:
        stations["elevation_diff_m"] = pd.NA

    if station_id:
        station_token = _normalize_station_id(station_id)
        stations = stations[stations["station_id"] == station_token].copy()
        if stations.empty:
            raise ValueError(f"Requested station_id '{station_id}' not found in GSOD candidate set.")
    else:
        stations = stations[stations["distance_km"] <= float(max_distance_km)].copy()
        if target_elevation_m is not None:
            stations = stations[stations["elevation_diff_m"] <= float(max_elevation_diff_m)].copy()
        if stations.empty:
            raise ValueError(
                "No GSOD station passed auto-select bounds for requested variables. "
                f"Bounds used: max_distance_km={max_distance_km}, "
                f"max_elevation_diff_m={max_elevation_diff_m if target_elevation_m is not None else 'not_applied'}."
            )

    return stations.sort_values(["distance_km", "station_id"]).reset_index(drop=True)


def evaluate_gsod_station_candidate(
    *,
    candidate: dict,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    verbose: bool = False,
    candidate_rank: int | None = None,
    candidate_total: int | None = None,
) -> dict:
    station_code = str(candidate["station_id"])
    cached_summary = _load_cached_coverage_summary(
        station_id=station_code,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
    )
    if cached_summary is not None:
        if verbose:
            rank_label = (
                f" [{candidate_rank}/{candidate_total}]"
                if candidate_rank is not None and candidate_total is not None
                else ""
            )
            print(
                f"[{_ts()}] GSOD candidate{rank_label} | station_id={station_code} | "
                "coverage_cache=hit"
            )
        return {
            **candidate,
            **cached_summary,
            "station_cache_hit": bool(cached_summary.get("station_cache_hit", False)),
            "coverage_cache_hit": True,
        }

    requested_columns = _requested_columns(variables)
    frames: list[pd.DataFrame] = []
    cache_hits: list[bool] = []
    year_summaries: list[str] = []
    if verbose:
        rank_label = (
            f" [{candidate_rank}/{candidate_total}]"
            if candidate_rank is not None and candidate_total is not None
            else ""
        )
        print(
            f"[{_ts()}] GSOD candidate{rank_label} | station_id={station_code} | "
            f"years={date_from.year}..{date_to.year} | coverage_cache=miss"
        )
    for year in range(date_from.year, date_to.year + 1):
        cache_path = _gsod_cache_root(cache_dir) / "stations" / station_code / f"{year}.csv"
        file_cache_hit = _cache_hit(cache_path, refresh_cache)
        cache_hits.append(file_cache_hit)
        if verbose:
            print(
                f"[{_ts()}] GSOD year fetch | station_id={station_code} | year={year} | "
                f"file_cache={'hit' if file_cache_hit else 'miss'}"
            )
        text = _download_text(
            station_id=station_code,
            year=year,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        if text is None:
            year_summaries.append(f"{year}:404")
            continue
        year_frame = pd.read_csv(StringIO(text))
        year_frame["DATE"] = pd.to_datetime(year_frame["DATE"])
        year_frame = year_frame[
            (year_frame["DATE"].dt.date >= date_from)
            & (year_frame["DATE"].dt.date <= date_to)
        ].copy()
        if year_frame.empty:
            year_summaries.append(f"{year}:0")
            continue
        keep = [column for column in ["DATE", *requested_columns] if column in year_frame.columns]
        year_frame = _clean_missing_values(year_frame[keep], requested_columns)
        year_summaries.append(f"{year}:{len(year_frame)}")
        frames.append(year_frame)

    if frames:
        frame = pd.concat(frames, ignore_index=True).sort_values("DATE").reset_index(drop=True)
    else:
        frame = pd.DataFrame(columns=["DATE", *requested_columns])

    expected_days = _days_inclusive(date_from, date_to)
    requested_fields = _requested_station_fields(variables)
    field_column_map = {
        "precipitation": "PRCP",
        "max_temperature": "MAX",
        "min_temperature": "MIN",
        "mean_temperature": "TEMP",
        "wind_speed": "WDSP",
    }
    field_counts = {
        field: int(frame[field_column_map[field]].notna().sum())
        if field_column_map[field] in frame.columns
        else 0
        for field in requested_fields
    }
    field_ratios = {
        field: (count / expected_days if expected_days else 0.0)
        for field, count in field_counts.items()
    }
    min_ratio = min(field_ratios.values()) if field_ratios else 0.0
    mean_ratio = sum(field_ratios.values()) / len(field_ratios) if field_ratios else 0.0
    ratio_columns = {
        f"completeness_{field}": round(ratio, 4)
        for field, ratio in field_ratios.items()
    }
    payload = {
        **candidate,
        "expected_days": expected_days,
        "available_rows": int(len(frame)),
        "requested_fields": ",".join(requested_fields),
        "min_completeness_ratio": round(min_ratio, 4),
        "mean_completeness_ratio": round(mean_ratio, 4),
        "field_counts": field_counts,
        "field_ratios": field_ratios,
        **ratio_columns,
        "station_cache_hit": all(cache_hits) if cache_hits else False,
        "coverage_cache_hit": False,
    }
    _save_cached_coverage_summary(
        station_id=station_code,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
        payload={
            key: value
            for key, value in payload.items()
            if key not in candidate
        },
    )
    if verbose:
        print(
            f"[{_ts()}] GSOD candidate complete | station_id={station_code} | "
            f"rows={payload['available_rows']} | "
            f"mean_ratio={payload['mean_completeness_ratio']:.4f} | "
            f"years={', '.join(year_summaries) if year_summaries else 'none'}"
        )
    return payload


def list_gsod_station_candidates(
    *,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    station_id: str | None = None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = DEFAULT_MAX_ELEVATION_DIFF_M,
    min_completeness_ratio: float = DEFAULT_MIN_COMPLETENESS_RATIO,
    candidate_limit: int | None = DEFAULT_CANDIDATE_LIMIT,
    score_limit: int = DEFAULT_SCORE_LIMIT,
    enforce_threshold: bool = False,
    verbose: bool = False,
) -> pd.DataFrame:
    base = _candidate_station_base_table(
        location_coord=location_coord,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        station_id=station_id,
        max_distance_km=max_distance_km,
        target_elevation_m=target_elevation_m,
        max_elevation_diff_m=max_elevation_diff_m,
    )
    score_subset = base.head(max(int(score_limit), 1)).copy()
    scored = [
        evaluate_gsod_station_candidate(
            candidate=row._asdict() if hasattr(row, "_asdict") else row.to_dict(),
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            verbose=verbose,
            candidate_rank=index + 1,
            candidate_total=len(score_subset),
        )
        for index, (_, row) in enumerate(score_subset.iterrows())
    ]
    frame = pd.DataFrame(scored)
    if frame.empty:
        return frame
    frame = annotate_completeness_threshold(
        frame,
        threshold=float(min_completeness_ratio),
    )
    if enforce_threshold:
        frame = frame[frame["all_fields_meet_threshold"]].copy()
    if frame.empty:
        raise ValueError(
            "No GSOD station passed per-variable completeness threshold. "
            f"Threshold used: min_completeness_ratio={min_completeness_ratio:.2f}."
        )
    frame = frame.sort_values(
        [
            "all_fields_meet_threshold",
            "n_fields_passing_threshold",
            "mean_completeness_ratio",
            "min_completeness_ratio",
            "distance_km",
            "station_id",
        ],
        ascending=[False, False, False, False, True, True],
    ).reset_index(drop=True)
    if candidate_limit is None:
        return frame.copy()
    return frame.head(max(int(candidate_limit), 1)).copy()


def select_gsod_station_candidates(
    *,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    station_id: str | None = None,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = DEFAULT_MAX_ELEVATION_DIFF_M,
    min_completeness_ratio: float = DEFAULT_MIN_COMPLETENESS_RATIO,
    candidate_limit: int | None = DEFAULT_CANDIDATE_LIMIT,
    score_limit: int = DEFAULT_SCORE_LIMIT,
    relax_thresholds: bool = True,
    allow_partial_fallback: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    ranked = list_gsod_station_candidates(
        location_coord=location_coord,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        station_id=station_id,
        max_distance_km=max_distance_km,
        target_elevation_m=target_elevation_m,
        max_elevation_diff_m=max_elevation_diff_m,
        min_completeness_ratio=min_completeness_ratio,
        candidate_limit=None,
        score_limit=score_limit,
        enforce_threshold=False,
        verbose=verbose,
    )
    threshold_sequence = build_completeness_threshold_sequence(min_completeness_ratio)
    if not relax_thresholds:
        threshold_sequence = threshold_sequence[:1]

    for index, threshold in enumerate(threshold_sequence):
        annotated = annotate_completeness_threshold(ranked, threshold=threshold)
        eligible = annotated[annotated["all_fields_meet_threshold"]].copy()
        if eligible.empty:
            continue
        eligible["selection_status"] = "strict" if index == 0 else "relaxed"
        if candidate_limit is None:
            return eligible.reset_index(drop=True)
        return eligible.head(max(int(candidate_limit), 1)).reset_index(drop=True)

    if allow_partial_fallback:
        annotated = annotate_completeness_threshold(ranked, threshold=float(min_completeness_ratio))
        eligible = annotated[annotated["n_fields_passing_threshold"] > 0].copy()
        if not eligible.empty:
            eligible["selection_status"] = "partial_fields"
            if candidate_limit is None:
                return eligible.reset_index(drop=True)
            return eligible.head(max(int(candidate_limit), 1)).reset_index(drop=True)

    raise ValueError(
        "No GSOD station passed per-variable completeness threshold, even after relaxation. "
        f"Threshold sequence used: {', '.join(f'{value:.2f}' for value in threshold_sequence)}."
    )


def _clean_missing_values(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    cleaned = frame.copy()
    for column in columns:
        if column not in cleaned.columns:
            continue
        values = pd.to_numeric(cleaned[column], errors="coerce")
        missing = GSOD_MISSING_VALUES.get(column)
        if missing is not None:
            values = values.where(values != missing)
        cleaned[column] = values
    return cleaned


def fetch_gsod_records(
    *,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    station_id: str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    unsupported = _unsupported_station_variables(variables)
    if unsupported:
        raise ValueError(
            "GSOD station backend does not support variables: "
            f"{', '.join(unsupported)}. Supported variables: "
            "precipitation, max_temperature, min_temperature, mean_temperature, wind_speed."
        )
    if not station_id:
        raise ValueError(
            "GSOD fetch currently requires explicit station_id. "
            "Auto station discovery/candidate ranking for GSOD not wired yet."
        )

    started = perf_counter()
    gsod_station_id = _normalize_station_id(station_id)
    if verbose:
        print(
            f"[{_ts()}] GSOD fetch start | station_id={gsod_station_id} | "
            f"years={date_from.year}..{date_to.year} | cache_root={_gsod_cache_root(cache_dir)}"
        )

    frames: list[pd.DataFrame] = []
    requested_columns = _requested_columns(variables)
    year_fetches = []
    for year in range(date_from.year, date_to.year + 1):
        fetch_started = perf_counter()
        text = _download_text(
            station_id=gsod_station_id,
            year=year,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        year_fetches.append((year, perf_counter() - fetch_started, text is not None))
        if text is None:
            continue
        year_frame = pd.read_csv(StringIO(text))
        year_frame["DATE"] = pd.to_datetime(year_frame["DATE"])
        year_frame = year_frame[
            (year_frame["DATE"].dt.date >= date_from)
            & (year_frame["DATE"].dt.date <= date_to)
        ].copy()
        if year_frame.empty:
            continue
        keep = [
            column for column in ["STATION", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION", "NAME", *requested_columns]
            if column in year_frame.columns
        ]
        year_frame = year_frame[keep]
        year_frame = _clean_missing_values(year_frame, requested_columns)
        frames.append(year_frame)

    if not frames:
        if verbose:
            print(f"[{_ts()}] GSOD fetch complete | rows=0 | total_elapsed={perf_counter() - started:.2f}s")
        return pd.DataFrame()

    frame = pd.concat(frames, ignore_index=True).sort_values("DATE").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["DATE"])
    frame["station_id"] = gsod_station_id
    frame["station_name"] = frame["NAME"] if "NAME" in frame.columns else pd.Series([pd.NA] * len(frame))
    frame["station_lat"] = frame["LATITUDE"] if "LATITUDE" in frame.columns else float(location_coord[0])
    frame["station_lon"] = frame["LONGITUDE"] if "LONGITUDE" in frame.columns else float(location_coord[1])
    frame["station_elevation_m"] = frame["ELEVATION"] if "ELEVATION" in frame.columns else pd.Series([pd.NA] * len(frame))
    frame["station_distance_km"] = pd.NA
    frame["station_source"] = "gsod"
    if verbose:
        years_found = sum(1 for _, _, found in year_fetches if found)
        print(
            f"[{_ts()}] GSOD fetch complete | rows={len(frame)} | years_found={years_found} | "
            f"total_elapsed={perf_counter() - started:.2f}s"
        )
    return frame


__all__ = [
    "DEFAULT_GSOD_CACHE_ROOT",
    "evaluate_gsod_station_candidate",
    "fetch_gsod_records",
    "list_gsod_station_candidates",
    "select_gsod_station_candidates",
]
