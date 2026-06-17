"""Station-data download entrypoint using toolkit pipeline."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from time import perf_counter

import pandas as pd

from climate_tookit.fetch_data.fetch_data import fetch_data, parse_variables, save_output
from climate_tookit.weather_station.dem import fetch_anchor_elevation
from climate_tookit.weather_station.ghcn_daily import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_MAX_DISTANCE_KM,
    DEFAULT_MAX_ELEVATION_DIFF_M,
    DEFAULT_MIN_COMPLETENESS_RATIO,
    DEFAULT_SCORE_LIMIT,
    list_ghcn_station_candidates,
    select_ghcn_station_candidates,
)
from climate_tookit.weather_station.gsod import (
    list_gsod_station_candidates,
    select_gsod_station_candidates,
)
from climate_tookit.weather_station.custom_station import (
    custom_station_format_help,
    load_custom_station_data,
    summarize_custom_station_candidate,
)
from climate_tookit.weather_station.station_selector import (
    SUPPORTED_STATION_SOURCES,
    list_station_candidates,
    select_station_candidates,
    summarize_station_search_scope,
)

DEFAULT_MAX_AUTO_STATIONS = 10


def _open_report_html(path: str | Path) -> bool:
    target = Path(path)
    opener = shutil.which("open") or shutil.which("xdg-open")
    if opener is None:
        return False
    try:
        subprocess.run([opener, str(target)], check=False)
    except Exception:
        return False
    return True


def _selection_warnings(frame: pd.DataFrame) -> list[str]:
    warnings = frame.attrs.get("selection_warnings", [])
    if not warnings:
        return []
    return [str(item) for item in warnings]


def parse_auto_select_scope(value: str, *, max_auto_stations: int = DEFAULT_MAX_AUTO_STATIONS) -> int:
    token = str(value).strip().lower()
    if token == "auto-all":
        return int(max_auto_stations)
    match = re.fullmatch(r"auto-(\d+)", token)
    if not match:
        raise ValueError("auto_select must be 'auto-all' or match 'auto-<n>' such as auto-1, auto-2, auto-3.")
    count = int(match.group(1))
    if count < 1:
        raise ValueError("auto_select count must be >= 1.")
    return min(count, int(max_auto_stations))


def _format_optional_number(value, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def _joined_fields(value) -> str:
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "none"
        return ", ".join(str(item) for item in value)
    if value is None:
        return "n/a"
    if pd.isna(value):
        return "n/a"
    return str(value)


def _format_field_coverage(row) -> str:
    counts = row.get("field_counts")
    expected_days = row.get("expected_days")
    if not isinstance(counts, dict) or expected_days in (None, 0) or pd.isna(expected_days):
        return "n/a"
    parts = []
    for field, count in counts.items():
        pct = (float(count) / float(expected_days)) * 100.0 if expected_days else 0.0
        parts.append(f"{field}={int(count)}/{int(expected_days)} ({pct:.0f}%)")
    return ", ".join(parts) if parts else "n/a"


def _render_list_candidate_summary(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No candidate stations."
    lines = [f"Candidate stations: {len(frame)}"]
    for rank, (_, row) in enumerate(frame.iterrows(), start=1):
        if str(row.get("station_source", "")).strip().lower() == "custom_csv":
            header = (
                f"{rank}. custom_csv | {row.get('station_id', 'unknown')} | "
                f"{row.get('station_name', 'unknown')} | "
                f"source file={row.get('custom_station_file', 'n/a')}"
            )
        else:
            header = (
                f"{rank}. {row.get('station_source', 'unknown')} | "
                f"{row.get('station_id', 'unknown')} | {row.get('station_name', 'unknown')} | "
                f"distance={_format_optional_number(row.get('distance_km'))} km | "
                f"elevation={_format_optional_number(row.get('elevation_m'), 1)} m | "
                f"elev_diff={_format_optional_number(row.get('elevation_diff_m'), 1)} m"
            )
        lines.extend(
            [
                header,
                (
                    f"   coverage={_format_field_coverage(row)} | "
                    f"status={row.get('threshold_status', 'n/a')}"
                ),
                (
                    f"   requested={_joined_fields(row.get('requested_fields'))} | "
                    f"pass={_joined_fields(row.get('fields_passing_threshold'))} | "
                    f"fail={_joined_fields(row.get('fields_failing_threshold'))}"
                ),
            ]
        )
    return "\n".join(lines)


def _render_download_summary(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No station observations returned."
    lines = [f"Returned stations: {frame['station_id'].nunique()} | rows={len(frame)}"]
    group_columns = ["station_id"]
    if "selection_rank" in frame.columns:
        group_columns.append("selection_rank")
    grouped = frame.groupby(group_columns, dropna=False, sort=False)
    variable_columns = [
        column for column in (
            "precipitation",
            "max_temperature",
            "min_temperature",
            "mean_temperature",
            "wind_speed",
            "humidity",
        )
        if column in frame.columns
    ]
    for _, station_frame in grouped:
        first = station_frame.iloc[0]
        row_count = len(station_frame)
        date_min = pd.to_datetime(station_frame["date"]).min()
        date_max = pd.to_datetime(station_frame["date"]).max()
        availability = []
        for column in variable_columns:
            availability.append(f"{column}={int(station_frame[column].notna().sum())}/{row_count}")
        lines.extend(
            [
                (
                    f"{int(first['selection_rank'])}. " if "selection_rank" in station_frame.columns else ""
                )
                + (
                    (
                        f"{first.get('station_id', 'unknown')} | {first.get('station_name', 'unknown')} | "
                        f"rows={row_count} | dates={date_min.date()}..{date_max.date()} | "
                        f"source file={first.get('custom_station_file', 'uploaded dataset')}"
                    )
                    if str(first.get("station_source", "")).strip().lower() == "custom_csv"
                    else
                    (
                        f"{first.get('station_id', 'unknown')} | {first.get('station_name', 'unknown')} | "
                        f"rows={row_count} | dates={date_min.date()}..{date_max.date()} | "
                        f"distance={_format_optional_number(first.get('distance_km', first.get('station_distance_km')))} km | "
                        f"elevation={_format_optional_number(first.get('station_elevation_m'), 1)} m | "
                        f"elev_diff={_format_optional_number(first.get('elevation_diff_m'), 1)} m"
                    )
                ),
                (
                    f"   selection={first.get('selection_status', 'n/a')} | "
                    f"threshold={_joined_fields(first.get('selection_threshold_used'))} | "
                    f"vars={', '.join(availability) if availability else 'n/a'}"
                ),
                (
                    f"   requested={_joined_fields(first.get('requested_fields'))} | "
                    f"pass={_joined_fields(first.get('fields_passing_threshold'))} | "
                    f"fail={_joined_fields(first.get('fields_failing_threshold'))}"
                ),
            ]
        )
    return "\n".join(lines)


def render_station_output_summary(frame: pd.DataFrame, *, selection_mode: str) -> str:
    if selection_mode == "list":
        return _render_list_candidate_summary(frame)
    return _render_download_summary(frame)


def download_station_data(
    *,
    station_source: str,
    station_coord: tuple[float, float],
    date_from: date,
    date_to: date,
    variables=None,
    station_id: str | None = None,
    stage: str = "preprocessed",
    verbose: bool = True,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
    selection_mode: str = "auto",
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    target_elevation_m: float | None = None,
    max_elevation_diff_m: float = DEFAULT_MAX_ELEVATION_DIFF_M,
    min_completeness_ratio: float = DEFAULT_MIN_COMPLETENESS_RATIO,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    score_limit: int = DEFAULT_SCORE_LIMIT,
    auto_select: str = "auto-1",
    auto_anchor_elevation: bool = True,
    disable_completeness_guard: bool = False,
    max_auto_stations: int = DEFAULT_MAX_AUTO_STATIONS,
    custom_station_file: str | None = None,
    custom_station_name: str | None = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
):
    station_source = str(station_source).strip().lower()
    if station_source not in SUPPORTED_STATION_SOURCES:
        raise ValueError(
            f"Unsupported station_source '{station_source}'. Currently supported: "
            f"{', '.join(sorted(SUPPORTED_STATION_SOURCES))}"
        )
    if station_source == "gsod":
        if selection_mode != "specified":
            raise ValueError(
                "GSOD currently supports selection_mode='specified' only. "
                "Pass --station-id with a 5-digit WMO-like ID or 11-digit GSOD ID."
            )
        if not station_id:
            raise ValueError("GSOD requires --station-id.")
        return fetch_data(
            source=station_source,
            location_coord=station_coord,
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            stage=stage,
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
        )
    if station_source == "custom_csv":
        if not custom_station_file:
            raise ValueError(
                "station_source='custom_csv' requires --custom-station-file. "
                + custom_station_format_help()
            )
        if selection_mode == "list":
            return summarize_custom_station_candidate(
                custom_station_file=custom_station_file,
                date_from=date_from,
                date_to=date_to,
                variables=variables,
                station_coord=station_coord,
                station_id=station_id,
                station_name=custom_station_name,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                custom_temp_unit=custom_temp_unit,
                custom_precip_unit=custom_precip_unit,
            )
        frame = load_custom_station_data(
            custom_station_file=custom_station_file,
            date_from=date_from,
            date_to=date_to,
            variables=variables,
            stage=stage,
            station_coord=station_coord,
            station_id=station_id,
            station_name=custom_station_name,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            custom_temp_unit=custom_temp_unit,
            custom_precip_unit=custom_precip_unit,
        )
        resolved_requested_fields = [
            item.name if hasattr(item, "name") else str(item)
            for item in (variables or [])
        ]
        frame = frame.copy()
        frame["selection_status"] = "custom_file"
        frame["selection_threshold_used"] = pd.NA
        frame["threshold_status"] = "custom_file"
        frame["requested_fields"] = pd.Series([resolved_requested_fields] * len(frame), index=frame.index, dtype=object)
        frame["fields_passing_threshold"] = pd.Series([resolved_requested_fields] * len(frame), index=frame.index, dtype=object)
        frame["fields_failing_threshold"] = pd.Series([[]] * len(frame), index=frame.index, dtype=object)
        frame["all_fields_meet_threshold"] = True
        frame["custom_station_file"] = str(Path(custom_station_file).expanduser())
        return frame
    resolved_target_elevation_m = target_elevation_m
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
            if verbose:
                print(
                    "Anchor elevation unavailable; continuing without elevation guard. "
                    f"Reason: {exc}"
                )
    if selection_mode == "list":
        if verbose:
            print(
                "Listing station candidates "
                f"(source={station_source}; max_distance_km={max_distance_km:.1f}; "
                f"target_elevation_m={_format_optional_number(resolved_target_elevation_m, 1)}; "
                f"score_limit={score_limit}; candidate_limit={candidate_limit})"
            )
        if station_source == "ghcn_daily":
            candidates = list_ghcn_station_candidates(
                location_coord=station_coord,
                date_from=date_from,
                date_to=date_to,
                variables=variables,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
                max_distance_km=max_distance_km,
                target_elevation_m=resolved_target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=candidate_limit,
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
                variables=variables,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
                max_distance_km=max_distance_km,
                target_elevation_m=resolved_target_elevation_m,
                max_elevation_diff_m=max_elevation_diff_m,
                min_completeness_ratio=min_completeness_ratio,
                candidate_limit=candidate_limit,
                score_limit=score_limit,
                enforce_threshold=False,
                verbose=verbose,
            )
        if verbose:
            print(f"Candidate listing complete: {len(candidates)} station(s) scored.")
            for warning in _selection_warnings(candidates):
                print(f"Warning: {warning}")
        return candidates
    if selection_mode == "specified" and not station_id:
        raise ValueError("selection_mode='specified' requires --station-id")
    if selection_mode == "auto":
        resolved_limit = parse_auto_select_scope(
            auto_select,
            max_auto_stations=max_auto_stations,
        )
        if verbose:
            print(
                "Selecting station candidates "
                f"({auto_select}; max_distance_km={max_distance_km:.1f}; "
                f"target_elevation_m={_format_optional_number(resolved_target_elevation_m, 1)}; "
                f"completeness_guard={'off' if disable_completeness_guard else 'on'})"
            )
        if disable_completeness_guard:
            if station_source == "ghcn_daily":
                candidates = list_ghcn_station_candidates(
                    location_coord=station_coord,
                    date_from=date_from,
                    date_to=date_to,
                    variables=variables,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                    station_id=None,
                    max_distance_km=max_distance_km,
                    target_elevation_m=resolved_target_elevation_m,
                    max_elevation_diff_m=max_elevation_diff_m,
                    min_completeness_ratio=min_completeness_ratio,
                    candidate_limit=resolved_limit,
                    score_limit=score_limit,
                    enforce_threshold=False,
                    verbose=verbose,
                ).copy()
            else:
                candidates = list_station_candidates(
                    station_source=station_source,
                    location_coord=station_coord,
                    date_from=date_from,
                    date_to=date_to,
                    variables=variables,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                    station_id=None,
                    max_distance_km=max_distance_km,
                    target_elevation_m=resolved_target_elevation_m,
                    max_elevation_diff_m=max_elevation_diff_m,
                    min_completeness_ratio=min_completeness_ratio,
                    candidate_limit=resolved_limit,
                    score_limit=score_limit,
                    enforce_threshold=False,
                    verbose=verbose,
                ).copy()
            candidates["selection_status"] = "guard_disabled"
            candidates["selection_threshold_used"] = pd.NA
            candidates["threshold_status"] = "guard_disabled"
            candidates["fields_passing_threshold"] = pd.Series(
                [pd.NA] * len(candidates),
                index=candidates.index,
                dtype=object,
            )
            candidates["fields_failing_threshold"] = pd.Series(
                [pd.NA] * len(candidates),
                index=candidates.index,
                dtype=object,
            )
            candidates["n_fields_passing_threshold"] = pd.Series(
                [pd.NA] * len(candidates),
                index=candidates.index,
                dtype=object,
            )
            candidates["all_fields_meet_threshold"] = pd.Series(
                [pd.NA] * len(candidates),
                index=candidates.index,
                dtype=object,
            )
        else:
            if station_source == "ghcn_daily":
                candidates = select_ghcn_station_candidates(
                    location_coord=station_coord,
                    date_from=date_from,
                    date_to=date_to,
                    variables=variables,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                    station_id=None,
                    max_distance_km=max_distance_km,
                    target_elevation_m=resolved_target_elevation_m,
                    max_elevation_diff_m=max_elevation_diff_m,
                    min_completeness_ratio=min_completeness_ratio,
                    candidate_limit=resolved_limit,
                    score_limit=score_limit,
                    verbose=verbose,
                )
            else:
                candidates = select_station_candidates(
                    station_source=station_source,
                    location_coord=station_coord,
                    date_from=date_from,
                    date_to=date_to,
                    variables=variables,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                    station_id=None,
                    max_distance_km=max_distance_km,
                    target_elevation_m=resolved_target_elevation_m,
                    max_elevation_diff_m=max_elevation_diff_m,
                    min_completeness_ratio=min_completeness_ratio,
                    candidate_limit=resolved_limit,
                    score_limit=score_limit,
                    verbose=verbose,
                )
        if verbose:
            print(
                f"Candidate selection complete: {len(candidates)} station(s) ready for fetch."
            )
            for warning in _selection_warnings(candidates):
                print(f"Warning: {warning}")
        if verbose and len(candidates) < resolved_limit:
            print(
                f"Requested {resolved_limit} station(s) via {auto_select}, "
                f"but only {len(candidates)} candidate(s) available for this window."
            )
        frames = []
        for rank, (_, candidate_row) in enumerate(candidates.iterrows(), start=1):
            if verbose:
                print(
                    f"Fetching station {rank}/{len(candidates)}: "
                    f"{candidate_row.get('station_source', station_source)} | "
                    f"{candidate_row['station_id']} | "
                    f"{candidate_row.get('station_name', 'unknown')} | "
                    f"distance={_format_optional_number(candidate_row.get('distance_km'))} km"
                )
            fetch_source = str(candidate_row.get("station_source", station_source)).strip().lower()
            station_frame = fetch_data(
                source=fetch_source,
                location_coord=station_coord,
                variables=variables,
                date_from=date_from,
                date_to=date_to,
                stage=stage,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=str(candidate_row["station_id"]),
            )
            if station_frame.empty:
                continue
            station_frame = station_frame.copy()
            station_frame["selection_rank"] = rank
            station_frame["selection_mode"] = auto_select
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
                    station_frame[column] = pd.Series(
                        [candidate_row[column]] * len(station_frame),
                        index=station_frame.index,
                        dtype=object,
                )
            frames.append(station_frame)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
    return fetch_data(
        source=station_source,
        location_coord=station_coord,
        variables=variables,
        date_from=date_from,
        date_to=date_to,
        stage=stage,
        verbose=verbose,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        station_id=station_id,
    )


def _render_candidate_map_html(
    *,
    candidates,
    anchor_lat: float,
    anchor_lon: float,
    title: str,
    period_start: str | None = None,
    period_end: str | None = None,
    scope_summary: dict | None = None,
) -> str:
    if candidates.empty:
        return "<html><body><p>No candidate stations.</p></body></html>"

    stations = []
    rows = []
    for idx, row in candidates.reset_index(drop=True).iterrows():
        rank = idx + 1
        station_id = str(row.get("station_id", "unknown"))
        station_name = str(row.get("station_name", "unknown"))
        station_source = str(row.get("station_source", "unknown"))
        distance_km = float(row["distance_km"]) if not pd.isna(row.get("distance_km")) else None
        min_complete = (
            float(row["min_completeness_ratio"])
            if not pd.isna(row.get("min_completeness_ratio"))
            else None
        )
        mean_complete = (
            float(row["mean_completeness_ratio"])
            if not pd.isna(row.get("mean_completeness_ratio"))
            else None
        )
        field_counts = row.get("field_counts") if isinstance(row.get("field_counts"), dict) else {}
        expected_days = (
            int(row.get("expected_days"))
            if row.get("expected_days") is not None and not pd.isna(row.get("expected_days"))
            else None
        )
        variable_completeness_parts = []
        for field_name, count in field_counts.items():
            if expected_days and expected_days > 0:
                pct = (float(count) / float(expected_days)) * 100.0
                variable_completeness_parts.append(f"{field_name}: {int(count)}/{expected_days} ({pct:.0f}%)")
            else:
                variable_completeness_parts.append(f"{field_name}: {int(count)}")
        variable_completeness_text = " | ".join(variable_completeness_parts) if variable_completeness_parts else "n/a"
        stations.append(
            {
                "rank": rank,
                "station_id": station_id,
                "station_name": station_name,
                "station_source": station_source,
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "distance_km": distance_km,
                "min_completeness_ratio": min_complete,
                "mean_completeness_ratio": mean_complete,
                "requested_fields": str(row.get("requested_fields", "")),
                "variable_completeness": variable_completeness_text,
            }
        )
        rows.append(
            "<tr>"
            f"<td><span class=\"rank-pill\">{rank}</span></td>"
            f"<td>{html.escape(station_source)}</td>"
            f"<td>{html.escape(station_id)}</td>"
            f"<td>{html.escape(station_name)}</td>"
            f"<td>{html.escape(f'{period_start} to {period_end}' if period_start and period_end else 'n/a')}</td>"
            f"<td>{'n/a' if distance_km is None else f'{distance_km:.2f}'}</td>"
            f"<td>{'n/a' if min_complete is None else f'{min_complete:.2f}'}</td>"
            f"<td>{'n/a' if mean_complete is None else f'{mean_complete:.2f}'}</td>"
            f"<td class=\"variable-completeness\">{html.escape(variable_completeness_text)}</td>"
            f"<td class=\"requested-fields\">{html.escape(str(row.get('requested_fields')))}</td>"
            "</tr>"
        )
    stations_json = json.dumps(stations)
    scope_summary = scope_summary or {}
    scope_label = html.escape(str(scope_summary.get("scope_label", "NOAA station discovery")))
    search_radius_km = scope_summary.get("search_radius_km")
    ghcn_local = scope_summary.get("ghcn_local_station_records")
    gsod_local = scope_summary.get("gsod_local_station_records")
    unique_local = scope_summary.get("unique_noaa_physical_stations")
    shown_local = scope_summary.get("displayed_station_count")
    shown_ghcn = scope_summary.get("displayed_ghcn_candidates")
    shown_gsod = scope_summary.get("displayed_gsod_candidates")
    deduped_backend_records = scope_summary.get("deduped_backend_records")
    scope_note = html.escape(str(scope_summary.get("scope_note", "")))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <style>
    :root {{
      --ink: #14213d;
      --muted: #5b6470;
      --line: #d7dee7;
      --bg: #eef3f7;
      --card: rgba(255,255,255,0.92);
      --focus: #111827;
      --rank1: #d97706;
      --rankN: #2563eb;
      --site: #0f172a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fef3c7 0, transparent 28%),
        radial-gradient(circle at top right, #dbeafe 0, transparent 32%),
        linear-gradient(180deg, #f8fafc 0%, #edf2f7 100%);
    }}
    .page {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 28px 40px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr 0.8fr;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid rgba(215, 222, 231, 0.9);
      border-radius: 18px;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
      backdrop-filter: blur(8px);
    }}
    .hero-main {{
      padding: 24px 24px 18px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 2.4rem;
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
      max-width: 64ch;
    }}
    .hero-side {{
      padding: 20px 22px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      justify-content: center;
    }}
    .meta-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 3px;
    }}
    .meta-value {{
      font-size: 1.15rem;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 18px;
      align-items: start;
    }}
    .scope-strip {{
      margin: 0 0 18px;
      padding: 14px 16px;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .scope-item {{
      background: rgba(255,255,255,0.78);
      border: 1px solid rgba(215, 222, 231, 0.9);
      border-radius: 14px;
      padding: 12px 14px;
    }}
    .scope-value {{
      font-size: 1.3rem;
      font-weight: 800;
      line-height: 1.1;
      margin-top: 4px;
    }}
    .scope-note-card {{
      margin: 0 0 18px;
      padding: 14px 16px;
      color: var(--muted);
      font-size: 0.96rem;
      line-height: 1.5;
    }}
    .map-card {{ overflow: hidden; }}
    .map-head {{
      padding: 16px 18px 10px;
      border-bottom: 1px solid rgba(215, 222, 231, 0.7);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .map-title {{
      font-size: 1.05rem;
      font-weight: 700;
    }}
    .map-note {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    #map {{
      width: 100%;
      height: 620px;
      background: #dbe7f0;
    }}
    .legend {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .legend-dot {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      display: inline-block;
    }}
    .legend-site {{ background: var(--site); }}
    .legend-rank1 {{ background: var(--rank1); }}
    .legend-rankN {{ background: var(--rankN); }}
    .legend-line {{
      width: 18px;
      height: 0;
      border-top: 2px dashed #6b7280;
      display: inline-block;
    }}
    .table-card {{
      padding: 16px 18px 18px;
      min-width: 0;
    }}
    .table-title {{
      margin: 0 0 12px;
      font-size: 1.05rem;
      font-weight: 700;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    table {{
      border-collapse: separate;
      border-spacing: 0;
      width: 100%;
      min-width: 980px;
      font-size: 0.94rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .rank-pill {{
      display: inline-flex;
      min-width: 30px;
      height: 30px;
      border-radius: 999px;
      align-items: center;
      justify-content: center;
      background: #e8eef6;
      color: var(--ink);
      font-weight: 700;
    }}
    .requested-fields {{
      min-width: 220px;
      max-width: 320px;
      white-space: normal;
      overflow-wrap: anywhere;
      color: var(--muted);
    }}
    .variable-completeness {{
      min-width: 240px;
      max-width: 360px;
      white-space: normal;
      overflow-wrap: anywhere;
      color: var(--muted);
    }}
    .leaflet-popup-content {{
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    .popup-title {{
      font-weight: 800;
      margin-bottom: 6px;
    }}
    .popup-meta {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .distance-label {{
      background: rgba(255,255,255,0.92);
      border: 1px solid rgba(215, 222, 231, 0.95);
      border-radius: 999px;
      padding: 2px 7px;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.10);
      color: var(--ink);
      font-size: 0.76rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    @media (max-width: 980px) {{
      .hero, .grid {{ grid-template-columns: 1fr; }}
      .scope-strip {{ grid-template-columns: 1fr 1fr; }}
      #map {{ height: 480px; }}
    }}
    @media (max-width: 640px) {{
      .scope-strip {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="card hero-main">
        <h1>{html.escape(title)}</h1>
        <p class="subtitle">
          Nearby weather stations ranked against focal coordinates you supplied. Report only covers stations discoverable through current toolkit NOAA backends. Map uses live web tiles, so internet connection needed for background basemap.
        </p>
      </div>
      <div class="card hero-side">
        <div>
          <div class="meta-label">Focal Location</div>
          <div class="meta-value">{anchor_lat:.4f}, {anchor_lon:.4f}</div>
        </div>
        <div>
          <div class="meta-label">Candidate Stations</div>
          <div class="meta-value">{len(stations)}</div>
        </div>
        <div>
          <div class="meta-label">Assessment Period</div>
          <div class="meta-value">{html.escape(f'{period_start} to {period_end}' if period_start and period_end else 'n/a')}</div>
        </div>
        <div>
          <div class="meta-label">Top Candidate</div>
          <div class="meta-value">{html.escape(stations[0]["station_name"])}</div>
        </div>
      </div>
    </section>

    <section class="card scope-strip">
      <div class="scope-item">
        <div class="meta-label">Discovery Scope</div>
        <div class="scope-value">{scope_label}</div>
      </div>
      <div class="scope-item">
        <div class="meta-label">Search Radius</div>
        <div class="scope-value">{'n/a' if search_radius_km is None else f'{float(search_radius_km):.0f} km'}</div>
      </div>
      <div class="scope-item">
        <div class="meta-label">GHCN Records In Bounds</div>
        <div class="scope-value">{'n/a' if ghcn_local is None else int(ghcn_local)}</div>
      </div>
      <div class="scope-item">
        <div class="meta-label">GSOD Records In Bounds</div>
        <div class="scope-value">{'n/a' if gsod_local is None else int(gsod_local)}</div>
      </div>
      <div class="scope-item">
        <div class="meta-label">Unique Physical Stations</div>
        <div class="scope-value">{'n/a' if unique_local is None else int(unique_local)}</div>
      </div>
    </section>

    <section class="card scope-note-card">
      <strong>Displayed in this report:</strong>
      {'n/a' if shown_local is None else int(shown_local)} station(s)
      {' ' if shown_ghcn is None and shown_gsod is None else f'| shown by source: GHCN={int(shown_ghcn or 0)}, GSOD={int(shown_gsod or 0)} '}
      {' ' if deduped_backend_records is None else f'| backend duplicates merged={int(deduped_backend_records)} '}
      <br>
      {scope_note}
    </section>

    <section class="grid">
      <div class="card map-card">
        <div class="map-head">
          <div>
            <div class="map-title">Map review</div>
            <div class="map-note">Focal location and candidate stations in geographic context. Marker size scales with station completeness. Raw NOAA scope and duplicate merging shown above.</div>
          </div>
          <div class="legend">
            <span class="legend-item"><span class="legend-dot legend-site"></span>Focal location</span>
            <span class="legend-item"><span class="legend-dot legend-rank1"></span>Top-ranked station</span>
            <span class="legend-item"><span class="legend-dot legend-rankN"></span>Other candidates</span>
            <span class="legend-item"><span class="legend-line"></span>Distance line</span>
          </div>
        </div>
        <div id="map"></div>
      </div>

      <div class="card table-card">
        <h2 class="table-title">Candidate summary</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rank</th><th>Source</th><th>Station ID</th><th>Name</th><th>Assessment period</th><th>Distance (km)</th>
                <th>Min completeness</th><th>Mean completeness</th><th>Variable completeness</th><th>Requested fields</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script>
    const focalLocation = [{anchor_lat}, {anchor_lon}];
    const stations = {stations_json};

    const map = L.map('map', {{
      zoomControl: true,
      scrollWheelZoom: true
    }});

    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19
    }}).addTo(map);

    const focalIcon = L.divIcon({{
      className: 'custom-div-icon',
      html: '<div style="width:18px;height:18px;border-radius:999px;background:#0f172a;border:3px solid white;box-shadow:0 0 0 2px rgba(15,23,42,0.25);"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    }});

    const focalMarker = L.marker(focalLocation, {{ icon: focalIcon }})
      .addTo(map)
      .bindPopup('<div class="popup-title">Focal location</div><div class="popup-meta">Input coordinates provided for station search.</div>');

    const bounds = [focalLocation];
    stations.forEach((station, idx) => {{
      const isTop = idx === 0;
      const color = isTop ? '#d97706' : '#2563eb';
      const completeness = station.mean_completeness_ratio ?? station.min_completeness_ratio ?? 0.3;
      const radius = Math.max(6, Math.min(16, 6 + (completeness * 10) + (isTop ? 1.5 : 0)));

      const distanceLine = L.polyline([focalLocation, [station.lat, station.lon]], {{
        color: '#6b7280',
        weight: isTop ? 2.8 : 2.0,
        opacity: isTop ? 0.85 : 0.60,
        dashArray: isTop ? '6 6' : '4 6'
      }}).addTo(map);

      const midpoint = [
        (focalLocation[0] + station.lat) / 2,
        (focalLocation[1] + station.lon) / 2
      ];
      const distanceLabel = station.distance_km === null
        ? 'distance n/a'
        : station.distance_km.toFixed(1) + ' km';
      L.marker(midpoint, {{
        interactive: false,
        keyboard: false,
        icon: L.divIcon({{
          className: 'distance-label-marker',
          html: '<div class="distance-label">' + distanceLabel + '</div>',
          iconSize: [68, 18],
          iconAnchor: [34, 9]
        }})
      }}).addTo(map);

      const marker = L.circleMarker([station.lat, station.lon], {{
        radius: radius,
        color: 'white',
        weight: 2,
        fillColor: color,
        fillOpacity: 0.95
      }}).addTo(map);
      marker.bindPopup(
        '<div class="popup-title">#' + station.rank + ' ' + station.station_name + '</div>' +
        '<div class="popup-meta">' +
        station.station_id + ' | ' + station.station_source + '<br>' +
        'Distance: ' + (station.distance_km === null ? 'n/a' : station.distance_km.toFixed(2) + ' km') + '<br>' +
        'Min completeness: ' + (station.min_completeness_ratio === null ? 'n/a' : station.min_completeness_ratio.toFixed(2)) + '<br>' +
        'Mean completeness: ' + (station.mean_completeness_ratio === null ? 'n/a' : station.mean_completeness_ratio.toFixed(2)) + '<br>' +
        'By variable: ' + station.variable_completeness + '<br>' +
        'Marker radius: ' + radius.toFixed(1) +
        '</div>'
      );
      bounds.push([station.lat, station.lon]);
    }});

    if (bounds.length === 1) {{
      map.setView(focalLocation, 11);
    }} else {{
      map.fitBounds(bounds, {{ padding: [40, 40] }});
    }}
  </script>
</body>
</html>"""


def save_candidate_review_artifacts(
    *,
    candidates,
    report_prefix: str | Path,
    anchor_lat: float,
    anchor_lon: float,
    station_source: str = "ghcn_daily",
    period_start: str | None = None,
    period_end: str | None = None,
    scope_summary: dict | None = None,
):
    prefix = Path(report_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    html_path = prefix.with_suffix(".html")
    candidates.to_csv(csv_path, index=False)
    candidates.to_json(json_path, orient="records", indent=2)
    html_path.write_text(
        _render_candidate_map_html(
            candidates=candidates,
            anchor_lat=anchor_lat,
            anchor_lon=anchor_lon,
            title=(
                "Observed station candidate review"
                if str(station_source).strip().lower() == "auto"
                else f"{str(station_source).strip()} candidate station review"
            ),
            period_start=period_start,
            period_end=period_end,
            scope_summary=scope_summary,
        ),
        encoding="utf-8",
    )
    return csv_path, json_path, html_path


def main():
    parser = argparse.ArgumentParser(
        description="Download observed weather-station data through toolkit pipeline."
    )
    parser.add_argument(
        "--station-source",
        choices=sorted(SUPPORTED_STATION_SOURCES),
        default="ghcn_daily",
        help="Observed station backend: ghcn_daily, gsod, custom_csv, or auto (rank across NOAA backends). custom_csv requires --custom-station-file.",
    )
    parser.add_argument("--station-lat", type=float, required=True)
    parser.add_argument("--station-lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--station-id", default=None)
    parser.add_argument("--custom-station-file", default=None,
                        help="Path to custom station CSV/JSON. Use with --station-source custom_csv.")
    parser.add_argument("--custom-station-name", default=None,
                        help="Optional station label for custom station file.")
    parser.add_argument("--custom-temp-unit", choices=["c", "f", "k"], default="c",
                        help="Temperature unit in custom station file (default: c).")
    parser.add_argument("--custom-precip-unit", choices=["mm", "inch", "tenth_mm"], default="mm",
                        help="Precipitation unit in custom station file (default: mm).")
    parser.add_argument("--selection-mode", choices=["auto", "specified", "list"], default="auto")
    parser.add_argument("--auto-select", default="auto-1")
    parser.add_argument("--variables", default=None)
    parser.add_argument("--stage", choices=["raw", "transformed", "preprocessed"], default="preprocessed")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--max-distance-km", type=float, default=DEFAULT_MAX_DISTANCE_KM)
    parser.add_argument("--target-elevation-m", type=float, default=None)
    parser.add_argument("--max-elevation-diff-m", type=float, default=DEFAULT_MAX_ELEVATION_DIFF_M)
    parser.add_argument("--no-auto-anchor-elevation", action="store_true")
    parser.add_argument("--disable-completeness-guard", action="store_true")
    parser.add_argument("--min-completeness-ratio", type=float, default=DEFAULT_MIN_COMPLETENESS_RATIO)
    parser.add_argument("--max-auto-stations", type=int, default=DEFAULT_MAX_AUTO_STATIONS)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--score-limit", type=int, default=DEFAULT_SCORE_LIMIT)
    parser.add_argument("--report-prefix", default=None,
                        help="Prefix for candidate-review CSV/JSON/HTML outputs. Most useful with --selection-mode list.")
    parser.add_argument("--open-report", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--format", choices=["csv", "json", "print"], default="print")
    args = parser.parse_args()

    try:
        started = perf_counter()
        variables = parse_variables(args.variables)
        frame = download_station_data(
            station_source=args.station_source,
            station_coord=(args.station_lat, args.station_lon),
            date_from=date.fromisoformat(args.start),
            date_to=date.fromisoformat(args.end),
            variables=variables,
            station_id=args.station_id,
            stage=args.stage,
            verbose=not args.quiet,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            selection_mode=args.selection_mode,
            max_distance_km=args.max_distance_km,
            target_elevation_m=args.target_elevation_m,
            max_elevation_diff_m=args.max_elevation_diff_m,
            min_completeness_ratio=args.min_completeness_ratio,
            candidate_limit=args.candidate_limit,
            score_limit=args.score_limit,
            auto_select=args.auto_select,
            auto_anchor_elevation=not args.no_auto_anchor_elevation,
            disable_completeness_guard=args.disable_completeness_guard,
            max_auto_stations=args.max_auto_stations,
            custom_station_file=args.custom_station_file,
            custom_station_name=args.custom_station_name,
            custom_temp_unit=args.custom_temp_unit,
            custom_precip_unit=args.custom_precip_unit,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    if args.selection_mode == "list" and args.report_prefix:
        scope_summary = summarize_station_search_scope(
            station_source=args.station_source,
            location_coord=(args.station_lat, args.station_lon),
            max_distance_km=args.max_distance_km,
            target_elevation_m=args.target_elevation_m,
            max_elevation_diff_m=args.max_elevation_diff_m,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            displayed_candidates=frame,
        )
        csv_path, json_path, html_path = save_candidate_review_artifacts(
            candidates=frame,
            report_prefix=args.report_prefix,
            anchor_lat=args.station_lat,
            anchor_lon=args.station_lon,
            station_source=args.station_source,
            period_start=args.start,
            period_end=args.end,
            scope_summary=scope_summary,
        )
        if not args.quiet:
            print(f"Saved candidate review CSV: {csv_path}")
            print(f"Saved candidate review JSON: {json_path}")
            print(f"Saved candidate review HTML: {html_path}")
        if args.open_report:
            opened = _open_report_html(html_path)
            if not args.quiet:
                print(
                    f"{'Opened' if opened else 'Could not open'} report HTML: {html_path}"
                )

    if args.format == "print" or not args.output:
        print(render_station_output_summary(frame, selection_mode=args.selection_mode))
    else:
        save_output(frame, args.output, args.format)
        print(f"Saved to {Path(args.output)}")
    if not args.quiet:
        detail = f"{args.selection_mode}"
        if args.selection_mode == "auto":
            detail = f"{detail}:{args.auto_select}"
        print(f"Selection mode: {detail} | elapsed={perf_counter() - started:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
