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
    annotate_completeness_threshold,
    build_completeness_threshold_sequence,
    list_ghcn_station_candidates,
    select_ghcn_station_candidates,
)
from climate_tookit.weather_station.gsod import (
    list_gsod_station_candidates,
    select_gsod_station_candidates,
)


SUPPORTED_STATION_SOURCES = {"auto", "ghcn_daily", "gsod"}


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
) -> pd.DataFrame:
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
) -> pd.DataFrame:
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
    wmo_id = row.get("wmo_id")
    if wmo_id is not None and not pd.isna(wmo_id) and str(wmo_id).strip():
        return f"wmo:{str(wmo_id).strip()}"
    lat = row.get("lat")
    lon = row.get("lon")
    name = str(row.get("station_name") or "").strip().lower()
    lat_key = "na" if lat is None or pd.isna(lat) else f"{float(lat):.3f}"
    lon_key = "na" if lon is None or pd.isna(lon) else f"{float(lon):.3f}"
    return f"meta:{name}:{lat_key}:{lon_key}"


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
) -> pd.DataFrame:
    source_name = _normalize_station_source(station_source)
    if source_name in {"ghcn_daily", "gsod"}:
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
) -> pd.DataFrame:
    source_name = _normalize_station_source(station_source)
    if source_name in {"ghcn_daily", "gsod"}:
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
]
