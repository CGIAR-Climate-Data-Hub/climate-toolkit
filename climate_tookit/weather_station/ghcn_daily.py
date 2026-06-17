"""NOAA GHCN-Daily station discovery and record fetch helpers."""

from __future__ import annotations

import math
from datetime import datetime
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Iterable

import pandas as pd
import requests

from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


STATIONS_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
INVENTORY_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
STATION_DLY_TEMPLATE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/{station_id}.dly"

DEFAULT_GHCN_CACHE_ROOT = Path("outputs/cache/weather_stations")
DEFAULT_MAX_DISTANCE_KM = 50.0
DEFAULT_MAX_ELEVATION_DIFF_M = 500.0
DEFAULT_MIN_COMPLETENESS_RATIO = 0.7
DEFAULT_CANDIDATE_LIMIT = 10
DEFAULT_SCORE_LIMIT = 25
DEFAULT_RELAXED_COMPLETENESS_THRESHOLDS = (0.5, 0.3, 0.1)

SUPPORTED_ELEMENTS = {
    "PRCP",
    "TMAX",
    "TMIN",
    "TAVG",
    "AWND",
    "RHAV",
}

CORE_VARIABLES = {
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
    ClimateVariable.mean_temperature,
}

OPTIONAL_VARIABLE_ELEMENTS = {
    ClimateVariable.wind_speed: {"AWND"},
    ClimateVariable.humidity: {"RHAV"},
}

SUPPORTED_VARIABLES = (
    CORE_VARIABLES
    | set(OPTIONAL_VARIABLE_ELEMENTS.keys())
)


def _ghcn_cache_root(cache_dir: str | Path | None = None) -> Path:
    return Path(cache_dir or DEFAULT_GHCN_CACHE_ROOT) / "ghcn_daily"


def _download_text(
    *,
    url: str,
    cache_path: Path,
    refresh_cache: bool = False,
    timeout_seconds: int = 120,
) -> str:
    if cache_path.exists() and not refresh_cache:
        return cache_path.read_text(encoding="utf-8")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def _cache_hit(cache_path: Path, refresh_cache: bool) -> bool:
    return cache_path.exists() and not refresh_cache


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _days_inclusive(date_from: date, date_to: date) -> int:
    return (pd.Timestamp(date_to) - pd.Timestamp(date_from)).days + 1


def _parse_station_line(line: str) -> dict | None:
    if not line.strip():
        return None
    station_id = line[0:11].strip()
    if not station_id:
        return None
    return {
        "station_id": station_id,
        "lat": float(line[12:20]),
        "lon": float(line[21:30]),
        "elevation_m": float(line[31:37]),
        "state": line[38:40].strip() or None,
        "station_name": line[41:71].strip(),
        "gsn_flag": line[72:75].strip() or None,
        "hcn_crn_flag": line[76:79].strip() or None,
        "wmo_id": line[80:85].strip() or None,
    }


def _parse_inventory_line(line: str) -> dict | None:
    parts = line.split()
    if len(parts) != 6:
        return None
    station_id, lat, lon, element, start_year, end_year = parts
    return {
        "station_id": station_id,
        "lat": float(lat),
        "lon": float(lon),
        "element": element,
        "start_year": int(start_year),
        "end_year": int(end_year),
    }


def load_ghcn_stations(
    *,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    cache_path = _ghcn_cache_root(cache_dir) / "index" / "ghcnd-stations.txt"
    text = _download_text(
        url=STATIONS_URL,
        cache_path=cache_path,
        refresh_cache=refresh_cache,
    )
    records = [
        parsed
        for parsed in (_parse_station_line(line) for line in text.splitlines())
        if parsed is not None
    ]
    return pd.DataFrame(records)


def load_ghcn_inventory(
    *,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    cache_path = _ghcn_cache_root(cache_dir) / "index" / "ghcnd-inventory.txt"
    text = _download_text(
        url=INVENTORY_URL,
        cache_path=cache_path,
        refresh_cache=refresh_cache,
    )
    records = [
        parsed
        for parsed in (_parse_inventory_line(line) for line in text.splitlines())
        if parsed is not None and parsed["element"] in SUPPORTED_ELEMENTS
    ]
    return pd.DataFrame(records)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _selection_requirements(
    variables: Iterable[ClimateVariable],
) -> tuple[set[str], set[str]]:
    requested = list(variables or [])
    core_requested = [variable for variable in requested if variable in CORE_VARIABLES]
    optional_requested = [variable for variable in requested if variable in OPTIONAL_VARIABLE_ELEMENTS]

    required_elements: set[str] = set()
    preferred_elements: set[str] = set()

    if core_requested:
        for variable in core_requested:
            if variable == ClimateVariable.precipitation:
                required_elements.add("PRCP")
            elif variable == ClimateVariable.max_temperature:
                required_elements.add("TMAX")
            elif variable == ClimateVariable.min_temperature:
                required_elements.add("TMIN")
            elif variable == ClimateVariable.mean_temperature:
                required_elements.update({"TMAX", "TMIN"})
        for variable in optional_requested:
            preferred_elements.update(OPTIONAL_VARIABLE_ELEMENTS[variable])
    else:
        for variable in optional_requested:
            required_elements.update(OPTIONAL_VARIABLE_ELEMENTS[variable])

    return required_elements, preferred_elements


def _unsupported_station_variables(variables: Iterable[ClimateVariable]) -> list[str]:
    unsupported = [
        variable.name
        for variable in (variables or [])
        if variable not in SUPPORTED_VARIABLES
    ]
    return sorted(set(unsupported))


def _station_supports_variable(
    available_elements: set[str],
    variable: ClimateVariable,
) -> bool:
    if variable == ClimateVariable.precipitation:
        return "PRCP" in available_elements
    if variable == ClimateVariable.max_temperature:
        return "TMAX" in available_elements
    if variable == ClimateVariable.min_temperature:
        return "TMIN" in available_elements
    if variable == ClimateVariable.mean_temperature:
        return "TAVG" in available_elements or {"TMAX", "TMIN"}.issubset(available_elements)
    if variable == ClimateVariable.wind_speed:
        return "AWND" in available_elements
    if variable == ClimateVariable.humidity:
        return "RHAV" in available_elements
    return False


def _requested_station_fields(
    variables: Iterable[ClimateVariable],
) -> list[str]:
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
        elif variable == ClimateVariable.humidity:
            fields.append("humidity")
    return fields


def _element_columns_to_standard(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    mapped = frame.copy()
    if "PRCP" in mapped.columns:
        mapped["precipitation"] = mapped["PRCP"] / 10.0
    if "TMAX" in mapped.columns:
        mapped["max_temperature"] = mapped["TMAX"] / 10.0
    if "TMIN" in mapped.columns:
        mapped["min_temperature"] = mapped["TMIN"] / 10.0
    if "TAVG" in mapped.columns:
        mapped["mean_temperature"] = mapped["TAVG"] / 10.0
    elif {"max_temperature", "min_temperature"}.issubset(mapped.columns):
        mapped["mean_temperature"] = (
            mapped["max_temperature"] + mapped["min_temperature"]
        ) / 2.0
    if "AWND" in mapped.columns:
        mapped["wind_speed"] = mapped["AWND"] / 10.0
    if "RHAV" in mapped.columns:
        mapped["humidity"] = mapped["RHAV"]
    return mapped


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
    unsupported = _unsupported_station_variables(variables)
    if unsupported:
        raise ValueError(
            "GHCN-Daily station backend does not support variables: "
            f"{', '.join(unsupported)}. Supported variables: "
            "precipitation, max_temperature, min_temperature, mean_temperature, "
            "wind_speed, humidity."
        )

    stations = load_ghcn_stations(cache_dir=cache_dir, refresh_cache=refresh_cache)
    inventory = load_ghcn_inventory(cache_dir=cache_dir, refresh_cache=refresh_cache)
    request_start_year = int(date_from.year)
    request_end_year = int(date_to.year)
    eligible_inventory = inventory[
        (inventory["start_year"] <= request_start_year)
        & (inventory["end_year"] >= request_end_year)
    ].copy()

    station_elements = (
        eligible_inventory.groupby("station_id")["element"]
        .apply(lambda series: set(series.astype(str)))
        .to_dict()
    )

    candidates = stations.copy()
    if station_id:
        candidates = candidates[candidates["station_id"] == station_id].copy()
        if candidates.empty:
            raise ValueError(f"Requested station_id '{station_id}' not found in GHCN station index.")

    supported_station_ids = {
        station_code
        for station_code, available in station_elements.items()
        if all(_station_supports_variable(available, variable) for variable in (variables or []))
    }
    if variables:
        candidates = candidates[candidates["station_id"].isin(supported_station_ids)].copy()
    if candidates.empty:
        raise ValueError(
            "No GHCN station found with full year-span coverage for requested variables "
            f"{[variable.name for variable in variables or []]} in {request_start_year}-{request_end_year}."
        )

    lat, lon = location_coord
    candidates["distance_km"] = candidates.apply(
        lambda row: _haversine_km(lat, lon, float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    if target_elevation_m is not None:
        candidates["elevation_diff_m"] = (candidates["elevation_m"] - float(target_elevation_m)).abs()
    else:
        candidates["elevation_diff_m"] = pd.NA

    if station_id is None:
        candidates = candidates[candidates["distance_km"] <= float(max_distance_km)].copy()
        if target_elevation_m is not None:
            candidates = candidates[candidates["elevation_diff_m"] <= float(max_elevation_diff_m)].copy()
        if candidates.empty:
            raise ValueError(
                "No GHCN station passed auto-select bounds for requested variables. "
                f"Bounds used: max_distance_km={max_distance_km}, "
                f"max_elevation_diff_m={max_elevation_diff_m if target_elevation_m is not None else 'not_applied'}."
            )

    candidates["available_elements"] = candidates["station_id"].map(
        lambda station_code: sorted(station_elements.get(station_code, set()))
    )
    return candidates.sort_values(["distance_km", "station_id"]).reset_index(drop=True)


def _candidate_requested_elements(
    available_elements: set[str],
    variables: Iterable[ClimateVariable],
) -> set[str]:
    requested_elements: set[str] = set()
    for variable in (variables or []):
        if variable == ClimateVariable.precipitation:
            requested_elements.add("PRCP")
        elif variable == ClimateVariable.max_temperature:
            requested_elements.add("TMAX")
        elif variable == ClimateVariable.min_temperature:
            requested_elements.add("TMIN")
        elif variable == ClimateVariable.mean_temperature:
            if "TAVG" in available_elements:
                requested_elements.add("TAVG")
            else:
                requested_elements.update({"TMAX", "TMIN"})
        elif variable == ClimateVariable.wind_speed:
            requested_elements.add("AWND")
        elif variable == ClimateVariable.humidity:
            requested_elements.add("RHAV")
    return requested_elements


def resolve_ghcn_station_metadata(
    *,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    station_id: str,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> dict:
    candidates = _candidate_station_base_table(
        location_coord=location_coord,
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        station_id=station_id,
    )
    if candidates.empty:
        raise ValueError(f"Requested station_id '{station_id}' not found in GHCN candidate set.")
    return candidates.iloc[0].to_dict()


def evaluate_ghcn_station_candidate(
    *,
    candidate: dict,
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
) -> dict:
    available_elements = set(candidate.get("available_elements") or [])
    requested_elements = _candidate_requested_elements(available_elements, variables)
    station_code = candidate["station_id"]
    cache_path = _ghcn_cache_root(cache_dir) / "stations" / f"{station_code}.dly"
    text = _download_text(
        url=STATION_DLY_TEMPLATE.format(station_id=station_code),
        cache_path=cache_path,
        refresh_cache=refresh_cache,
    )
    raw_frame = _parse_dly_text(
        text,
        requested_elements=requested_elements,
        date_from=date_from,
        date_to=date_to,
    )
    mapped_frame = _element_columns_to_standard(raw_frame)
    expected_days = _days_inclusive(date_from, date_to)
    requested_fields = _requested_station_fields(variables)
    field_counts = {
        field: int(mapped_frame[field].notna().sum()) if field in mapped_frame.columns else 0
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
    return {
        **candidate,
        "expected_days": expected_days,
        "available_rows": int(len(mapped_frame)),
        "requested_fields": ",".join(requested_fields),
        "min_completeness_ratio": round(min_ratio, 4),
        "mean_completeness_ratio": round(mean_ratio, 4),
        "field_counts": field_counts,
        "field_ratios": field_ratios,
        **ratio_columns,
        "station_cache_hit": _cache_hit(cache_path, refresh_cache),
    }


def build_completeness_threshold_sequence(
    min_completeness_ratio: float,
) -> list[float]:
    thresholds = [float(min_completeness_ratio), *DEFAULT_RELAXED_COMPLETENESS_THRESHOLDS]
    ordered: list[float] = []
    for threshold in thresholds:
        bounded = min(max(float(threshold), 0.0), 1.0)
        if bounded not in ordered:
            ordered.append(bounded)
    return ordered


def annotate_completeness_threshold(
    frame: pd.DataFrame,
    *,
    threshold: float,
) -> pd.DataFrame:
    annotated = frame.copy()
    active_threshold = float(threshold)
    annotated["fields_passing_threshold"] = annotated["field_ratios"].apply(
        lambda ratios: sorted([field for field, ratio in ratios.items() if float(ratio) >= active_threshold])
    )
    annotated["fields_failing_threshold"] = annotated["field_ratios"].apply(
        lambda ratios: sorted([field for field, ratio in ratios.items() if float(ratio) < active_threshold])
    )
    annotated["n_fields_passing_threshold"] = annotated["fields_passing_threshold"].apply(len)
    annotated["all_fields_meet_threshold"] = annotated["fields_failing_threshold"].apply(
        lambda fields: len(fields) == 0
    )
    annotated["selection_threshold_used"] = active_threshold
    annotated["threshold_status"] = annotated.apply(
        lambda row: (
            "strict_all_fields"
            if row["all_fields_meet_threshold"]
            else ("partial_fields" if row["n_fields_passing_threshold"] > 0 else "below_threshold")
        ),
        axis=1,
    )
    return annotated


def list_ghcn_station_candidates(
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
        evaluate_ghcn_station_candidate(
            candidate=row._asdict() if hasattr(row, "_asdict") else row.to_dict(),
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )
        for _, row in score_subset.iterrows()
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
            "No GHCN station passed per-variable completeness threshold. "
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


def select_ghcn_station_candidates(
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
) -> pd.DataFrame:
    ranked = list_ghcn_station_candidates(
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
        "No GHCN station passed per-variable completeness threshold, even after relaxation. "
        f"Threshold sequence used: {', '.join(f'{value:.2f}' for value in threshold_sequence)}."
    )


def select_ghcn_station(
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
    candidate_limit: int = 1,
    score_limit: int = DEFAULT_SCORE_LIMIT,
    relax_thresholds: bool = True,
    allow_partial_fallback: bool = True,
) -> dict:
    candidates = select_ghcn_station_candidates(
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
        candidate_limit=candidate_limit,
        score_limit=score_limit,
        relax_thresholds=relax_thresholds,
        allow_partial_fallback=allow_partial_fallback,
    )
    return candidates.iloc[0].to_dict()


def _parse_dly_text(
    text: str,
    *,
    requested_elements: set[str],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    records_by_date: dict[pd.Timestamp, dict] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        station_id = line[0:11]
        year = int(line[11:15])
        month = int(line[15:17])
        element = line[17:21]
        if element not in requested_elements:
            continue

        for day in range(1, 32):
            base = 21 + (day - 1) * 8
            raw_value = int(line[base:base + 5])
            qflag = line[base + 6:base + 7]
            if raw_value == -9999 or qflag.strip():
                continue
            try:
                current_date = pd.Timestamp(year=year, month=month, day=day)
            except ValueError:
                continue
            if current_date.date() < date_from or current_date.date() > date_to:
                continue
            row = records_by_date.setdefault(current_date, {"date": current_date, "station_id": station_id.strip()})
            row[element] = raw_value

    frame = pd.DataFrame(sorted(records_by_date.values(), key=lambda item: item["date"]))
    return frame.reset_index(drop=True) if not frame.empty else frame


def fetch_ghcn_daily_records(
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
    started = perf_counter()
    cache_root = _ghcn_cache_root(cache_dir)
    stations_cache = cache_root / "index" / "ghcnd-stations.txt"
    inventory_cache = cache_root / "index" / "ghcnd-inventory.txt"
    if verbose:
        print(
            f"[{_ts()}] GHCN-Daily fetch start | cache_root={cache_root} | "
            f"stations_cache={'hit' if _cache_hit(stations_cache, refresh_cache) else 'miss'} | "
            f"inventory_cache={'hit' if _cache_hit(inventory_cache, refresh_cache) else 'miss'}"
        )

    select_started = perf_counter()
    if station_id:
        selected_station = resolve_ghcn_station_metadata(
            location_coord=location_coord,
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
        )
    else:
        selected_station = select_ghcn_station(
            location_coord=location_coord,
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
        )
    select_elapsed = perf_counter() - select_started
    if verbose:
        print(
            f"[{_ts()}] Station selected | id={selected_station['station_id']} | "
            f"name={selected_station['station_name']} | distance_km={selected_station['distance_km']:.2f} | "
            f"elevation_m={selected_station['elevation_m']:.1f} | select_elapsed={select_elapsed:.2f}s"
        )

    available_elements = set(selected_station.get("available_elements") or [])
    requested_elements = _candidate_requested_elements(available_elements, variables)

    if not requested_elements:
        requested_elements = {"PRCP", "TMAX", "TMIN"}

    station_code = selected_station["station_id"]
    cache_path = _ghcn_cache_root(cache_dir) / "stations" / f"{station_code}.dly"
    station_cache_status = "hit" if _cache_hit(cache_path, refresh_cache) else "miss"
    station_fetch_started = perf_counter()
    text = _download_text(
        url=STATION_DLY_TEMPLATE.format(station_id=station_code),
        cache_path=cache_path,
        refresh_cache=refresh_cache,
    )
    station_fetch_elapsed = perf_counter() - station_fetch_started
    if verbose:
        print(
            f"[{_ts()}] Station file ready | id={station_code} | cache={station_cache_status} | "
            f"path={cache_path} | fetch_elapsed={station_fetch_elapsed:.2f}s"
        )

    parse_started = perf_counter()
    frame = _parse_dly_text(
        text,
        requested_elements=requested_elements,
        date_from=date_from,
        date_to=date_to,
    )
    parse_elapsed = perf_counter() - parse_started
    if frame.empty:
        if verbose:
            total_elapsed = perf_counter() - started
            print(
                f"[{_ts()}] GHCN-Daily fetch complete | rows=0 | parse_elapsed={parse_elapsed:.2f}s | "
                f"total_elapsed={total_elapsed:.2f}s"
            )
        return frame

    if "TAVG" not in frame.columns and {"TMAX", "TMIN"}.issubset(frame.columns):
        frame["TAVG"] = (frame["TMAX"] + frame["TMIN"]) / 2.0

    frame["station_name"] = selected_station["station_name"]
    frame["station_lat"] = float(selected_station["lat"])
    frame["station_lon"] = float(selected_station["lon"])
    frame["station_elevation_m"] = float(selected_station["elevation_m"])
    frame["station_distance_km"] = float(selected_station["distance_km"])
    frame["station_source"] = "ghcn_daily"
    if verbose:
        total_elapsed = perf_counter() - started
        print(
            f"[{_ts()}] GHCN-Daily fetch complete | rows={len(frame)} | "
            f"parse_elapsed={parse_elapsed:.2f}s | total_elapsed={total_elapsed:.2f}s"
        )
    return frame


__all__ = [
    "DEFAULT_GHCN_CACHE_ROOT",
    "fetch_ghcn_daily_records",
    "load_ghcn_inventory",
    "load_ghcn_stations",
    "annotate_completeness_threshold",
    "build_completeness_threshold_sequence",
    "list_ghcn_station_candidates",
    "select_ghcn_station",
    "select_ghcn_station_candidates",
    "_parse_dly_text",
    "_parse_inventory_line",
    "_parse_station_line",
]
