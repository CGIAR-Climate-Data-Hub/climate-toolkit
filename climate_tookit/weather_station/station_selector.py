"""Cross-backend station candidate selection."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

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
    list_ghcn_station_candidates,
    load_ghcn_stations,
    select_ghcn_station_candidates,
)
from climate_tookit.weather_station.gsod import (
    list_gsod_station_candidates,
    load_gsod_stations,
    select_gsod_station_candidates,
)
from climate_tookit.weather_station.custom_station import (
    custom_station_format_help,
    summarize_custom_station_candidate,
)


SUPPORTED_STATION_SOURCES = {"auto", "ghcn_daily", "gsod", "custom_csv"}


def _attach_selection_warnings(
    frame: pd.DataFrame,
    warnings: list[str] | None,
) -> pd.DataFrame:
    attached = frame.copy()
    if warnings:
        attached.attrs["selection_warnings"] = list(warnings)
    return attached


def _selection_warnings_from_frame(frame: pd.DataFrame) -> list[str]:
    warnings = frame.attrs.get("selection_warnings", [])
    if not warnings:
        return []
    return [str(item) for item in warnings]


def _normalize_station_source(station_source: str) -> str:
    token = str(station_source or "auto").strip().lower()
    if token not in SUPPORTED_STATION_SOURCES:
        raise ValueError(
            f"Unsupported station_source '{station_source}'. Currently supported: "
            f"{', '.join(sorted(SUPPORTED_STATION_SOURCES))}"
        )
    return token


def _dispatch_list(
    *,
    station_source: str,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir=None,
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
    custom_station_file: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    station_name: str | None = None,
) -> pd.DataFrame:
    if station_source == "custom_csv":
        if not custom_station_file:
            raise ValueError(
                "station_source='custom_csv' requires --custom-station-file. "
                + custom_station_format_help()
            )
        return summarize_custom_station_candidate(
            custom_station_file=custom_station_file,
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            station_coord=location_coord,
            station_id=station_id,
            station_name=station_name,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
    if station_source == "ghcn_daily":
        return list_ghcn_station_candidates(
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
            enforce_threshold=enforce_threshold,
        )
    return list_gsod_station_candidates(
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
        enforce_threshold=enforce_threshold,
        verbose=verbose,
    )


def _dispatch_select(
    *,
    station_source: str,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir=None,
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
    custom_station_file: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    station_name: str | None = None,
) -> pd.DataFrame:
    if station_source == "custom_csv":
        frame = _dispatch_list(
            station_source=station_source,
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
            candidate_limit=1,
            score_limit=score_limit,
            enforce_threshold=False,
            verbose=verbose,
            custom_station_file=custom_station_file,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
            station_name=station_name,
        ).copy()
        frame["selection_status"] = "custom_file"
        return frame
    if station_source == "ghcn_daily":
        return select_ghcn_station_candidates(
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
    return select_gsod_station_candidates(
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
        verbose=verbose,
    )


def _physical_station_key(row: pd.Series) -> str:
    lat = row.get("lat")
    lon = row.get("lon")
    name = str(row.get("station_name") or "").strip().lower()
    lat_key = "na" if lat is None or pd.isna(lat) else f"{float(lat):.3f}"
    lon_key = "na" if lon is None or pd.isna(lon) else f"{float(lon):.3f}"
    if name and lat_key != "na" and lon_key != "na":
        return f"meta:{name}:{lat_key}:{lon_key}"
    wmo_id = row.get("wmo_id")
    if wmo_id is not None and not pd.isna(wmo_id) and str(wmo_id).strip():
        return f"wmo:{str(wmo_id).strip()}"
    return f"meta:{name}:{lat_key}:{lon_key}"


def summarize_station_search_scope(
    *,
    station_source: str,
    location_coord: tuple[float, float],
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = DEFAULT_MAX_ELEVATION_DIFF_M,
    cache_dir=None,
    refresh_cache: bool = False,
    displayed_candidates: pd.DataFrame | None = None,
) -> dict:
    source_name = _normalize_station_source(station_source)
    if source_name == "custom_csv":
        shown = 0 if displayed_candidates is None else int(len(displayed_candidates))
        return {
            "scope_label": "custom station file",
            "search_radius_km": float(max_distance_km),
            "ghcn_local_station_records": 0,
            "gsod_local_station_records": 0,
            "unique_noaa_physical_stations": 0,
            "displayed_station_count": shown,
            "deduped_backend_records": 0,
            "scope_note": "Custom station workflow does not use NOAA station discovery indices.",
        }

    lat, lon = location_coord
    stations = load_ghcn_stations(cache_dir=cache_dir, refresh_cache=refresh_cache).copy()
    stations["distance_km"] = stations.apply(
        lambda row: _haversine_km(lat, lon, float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    if target_elevation_m is not None:
        stations["elevation_diff_m"] = (stations["elevation_m"] - float(target_elevation_m)).abs()
    else:
        stations["elevation_diff_m"] = pd.NA

    within_bounds = stations[stations["distance_km"] <= float(max_distance_km)].copy()
    if target_elevation_m is not None:
        within_bounds = within_bounds[
            within_bounds["elevation_diff_m"] <= float(max_elevation_diff_m)
        ].copy()

    ghcn_local = within_bounds.copy()
    gsod_local = pd.DataFrame()
    if source_name in {"auto", "gsod"}:
        gsod_stations = load_gsod_stations(
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        ).copy()
        if not gsod_stations.empty:
            gsod_stations["distance_km"] = gsod_stations.apply(
                lambda row: _haversine_km(lat, lon, float(row["lat"]), float(row["lon"])),
                axis=1,
            )
            if target_elevation_m is not None:
                gsod_stations["elevation_diff_m"] = (
                    gsod_stations["elevation_m"] - float(target_elevation_m)
                ).abs()
            else:
                gsod_stations["elevation_diff_m"] = pd.NA
            gsod_local = gsod_stations[
                gsod_stations["distance_km"] <= float(max_distance_km)
            ].copy()
            if target_elevation_m is not None:
                gsod_local = gsod_local[
                    gsod_local["elevation_diff_m"] <= float(max_elevation_diff_m)
                ].copy()

    union_frames: list[pd.DataFrame] = []
    if source_name in {"auto", "ghcn_daily"} and not ghcn_local.empty:
        tagged = ghcn_local.copy()
        tagged["station_source"] = "ghcn_daily"
        union_frames.append(tagged)
    if source_name in {"auto", "gsod"} and not gsod_local.empty:
        tagged = gsod_local.copy()
        tagged["station_source"] = "gsod"
        union_frames.append(tagged)

    unique_count = 0
    deduped_backend_records = 0
    if union_frames:
        union = pd.concat(union_frames, ignore_index=True)
        total_backend_records = int(len(union))
        union["physical_station_key"] = union.apply(_physical_station_key, axis=1)
        unique_count = int(union["physical_station_key"].nunique())
        deduped_backend_records = max(total_backend_records - unique_count, 0)

    shown = unique_count if displayed_candidates is None else int(len(displayed_candidates))
    displayed_ghcn_candidates = 0
    displayed_gsod_candidates = 0
    if displayed_candidates is not None and not displayed_candidates.empty and "station_source" in displayed_candidates.columns:
        source_counts = displayed_candidates["station_source"].astype(str).value_counts()
        displayed_ghcn_candidates = int(source_counts.get("ghcn_daily", 0))
        displayed_gsod_candidates = int(source_counts.get("gsod", 0))
    scope_label = {
        "auto": "NOAA GHCN + GSOD",
        "ghcn_daily": "NOAA GHCN-Daily",
        "gsod": "NOAA GSOD",
    }.get(source_name, source_name)

    if source_name == "auto":
        scope_note = (
            "Map shows NOAA-backed discovery only. GSOD local discovery now uses NOAA ISD history "
            "metadata; duplicate physical stations across GHCN and GSOD are merged in report."
        )
    elif source_name == "gsod":
        scope_note = (
            "Map shows NOAA GSOD discovery from NOAA ISD history metadata. Local or national stations "
            "absent from NOAA indices will not appear here."
        )
    else:
        scope_note = (
            "Map shows NOAA-backed discovery only. Local or national stations absent from NOAA indices "
            "will not appear here."
        )

    return {
        "scope_label": scope_label,
        "search_radius_km": float(max_distance_km),
        "elevation_guard_m": (
            None if target_elevation_m is None else float(max_elevation_diff_m)
        ),
        "ghcn_local_station_records": int(len(ghcn_local)),
        "gsod_local_station_records": int(len(gsod_local)),
        "unique_noaa_physical_stations": unique_count,
        "displayed_station_count": shown,
        "displayed_ghcn_candidates": displayed_ghcn_candidates,
        "displayed_gsod_candidates": displayed_gsod_candidates,
        "deduped_backend_records": deduped_backend_records,
        "scope_note": scope_note,
    }


def _combine_auto_candidates(
    *,
    frames: list[pd.DataFrame],
    candidate_limit: int | None,
) -> pd.DataFrame:
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty:
        return combined
    combined["physical_station_key"] = combined.apply(_physical_station_key, axis=1)
    combined["station_backend_priority"] = combined["station_source"].map(
        {"ghcn_daily": 0, "gsod": 1}
    ).fillna(9)
    combined = combined.sort_values(
        [
            "all_fields_meet_threshold",
            "n_fields_passing_threshold",
            "mean_completeness_ratio",
            "min_completeness_ratio",
            "distance_km",
            "station_backend_priority",
            "station_id",
        ],
        ascending=[False, False, False, False, True, True, True],
    ).reset_index(drop=True)
    combined = combined.drop_duplicates(subset=["physical_station_key"], keep="first").reset_index(drop=True)
    if candidate_limit is None:
        return combined
    return combined.head(max(int(candidate_limit), 1)).copy()


def list_station_candidates(
    *,
    station_source: str,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir=None,
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
    custom_station_file: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    station_name: str | None = None,
) -> pd.DataFrame:
    source_name = _normalize_station_source(station_source)
    if source_name in {"ghcn_daily", "gsod", "custom_csv"}:
        frame = _dispatch_list(
            station_source=source_name,
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
            enforce_threshold=enforce_threshold,
            verbose=verbose,
            custom_station_file=custom_station_file,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
            station_name=station_name,
        ).copy()
        frame["station_source"] = source_name
        return _attach_selection_warnings(frame, _selection_warnings_from_frame(frame))

    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    warnings: list[str] = []
    for backend in ("ghcn_daily", "gsod"):
        try:
            frame = _dispatch_list(
                station_source=backend,
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
                enforce_threshold=enforce_threshold,
                verbose=verbose,
            ).copy()
        except Exception as exc:
            errors.append(f"{backend}: {exc}")
            continue
        if frame.empty:
            continue
        frame["station_source"] = backend
        warnings.extend(_selection_warnings_from_frame(frame))
        frames.append(frame)
    if not frames:
        detail = " | ".join(errors) if errors else "no backends returned candidates"
        raise ValueError(f"No station candidates found across station backends. {detail}")
    if errors:
        warnings.append(
            "Auto station selection skipped backend(s): " + " | ".join(errors)
        )
    return _attach_selection_warnings(
        _combine_auto_candidates(frames=frames, candidate_limit=candidate_limit),
        warnings,
    )


def select_station_candidates(
    *,
    station_source: str,
    location_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables: Iterable[ClimateVariable],
    cache_dir=None,
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
    custom_station_file: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    station_name: str | None = None,
) -> pd.DataFrame:
    source_name = _normalize_station_source(station_source)
    if source_name in {"ghcn_daily", "gsod", "custom_csv"}:
        frame = _dispatch_select(
            station_source=source_name,
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
            verbose=verbose,
            custom_station_file=custom_station_file,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
            station_name=station_name,
        ).copy()
        frame["station_source"] = source_name
        return _attach_selection_warnings(frame, _selection_warnings_from_frame(frame))

    ranked = list_station_candidates(
        station_source="auto",
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
        return _attach_selection_warnings(
            _combine_auto_candidates(frames=[eligible], candidate_limit=candidate_limit),
            _selection_warnings_from_frame(ranked),
        )

    if allow_partial_fallback:
        annotated = annotate_completeness_threshold(ranked, threshold=float(min_completeness_ratio))
        eligible = annotated[annotated["n_fields_passing_threshold"] > 0].copy()
        if not eligible.empty:
            eligible["selection_status"] = "partial_fields"
            return _attach_selection_warnings(
                _combine_auto_candidates(frames=[eligible], candidate_limit=candidate_limit),
                _selection_warnings_from_frame(ranked),
            )

    raise ValueError(
        "No station candidate passed per-variable completeness threshold, even after relaxation. "
        f"Threshold sequence used: {', '.join(f'{value:.2f}' for value in threshold_sequence)}."
    )


__all__ = [
    "SUPPORTED_STATION_SOURCES",
    "list_station_candidates",
    "select_station_candidates",
    "summarize_station_search_scope",
]
