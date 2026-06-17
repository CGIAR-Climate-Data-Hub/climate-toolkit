"""Station-data download entrypoint using toolkit pipeline."""

from __future__ import annotations

import argparse
import html
import re
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
from climate_tookit.weather_station.station_selector import (
    SUPPORTED_STATION_SOURCES,
    list_station_candidates,
    select_station_candidates,
)

DEFAULT_MAX_AUTO_STATIONS = 10


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
        lines.extend(
            [
                (
                    f"{rank}. {row.get('station_source', 'unknown')} | "
                    f"{row.get('station_id', 'unknown')} | {row.get('station_name', 'unknown')} | "
                    f"distance={_format_optional_number(row.get('distance_km'))} km | "
                    f"elevation={_format_optional_number(row.get('elevation_m'), 1)} m | "
                    f"elev_diff={_format_optional_number(row.get('elevation_diff_m'), 1)} m"
                ),
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
                    f"{first.get('station_id', 'unknown')} | {first.get('station_name', 'unknown')} | "
                    f"rows={row_count} | dates={date_min.date()}..{date_max.date()} | "
                    f"distance={_format_optional_number(first.get('distance_km'))} km | "
                    f"elevation={_format_optional_number(first.get('station_elevation_m'), 1)} m | "
                    f"elev_diff={_format_optional_number(first.get('elevation_diff_m'), 1)} m"
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
            )
        if verbose:
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
) -> str:
    if candidates.empty:
        return "<html><body><p>No candidate stations.</p></body></html>"

    lats = [anchor_lat, *candidates["lat"].astype(float).tolist()]
    lons = [anchor_lon, *candidates["lon"].astype(float).tolist()]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    def project(lat: float, lon: float) -> tuple[float, float]:
        width = 760.0
        height = 460.0
        x = 40.0 + ((lon - min_lon) / max(max_lon - min_lon, 1e-9)) * (width - 80.0)
        y = 40.0 + (1.0 - ((lat - min_lat) / max(max_lat - min_lat, 1e-9))) * (height - 80.0)
        return x, y

    anchor_x, anchor_y = project(anchor_lat, anchor_lon)
    markers = [
        f'<circle cx="{anchor_x:.1f}" cy="{anchor_y:.1f}" r="7" fill="#111827" />'
        f'<text x="{anchor_x + 10:.1f}" y="{anchor_y - 10:.1f}" font-size="12">Anchor</text>'
    ]
    rows = []
    for idx, row in candidates.reset_index(drop=True).iterrows():
        x, y = project(float(row["lat"]), float(row["lon"]))
        color = "#0f766e" if idx == 0 else "#2563eb"
        markers.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}" />'
            f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" font-size="11">{html.escape(str(row["station_id"]))}</text>'
        )
        rows.append(
            "<tr>"
            f"<td>{idx + 1}</td>"
            f"<td>{html.escape(str(row.get('station_source', 'unknown')))}</td>"
            f"<td>{html.escape(str(row['station_id']))}</td>"
            f"<td>{html.escape(str(row['station_name']))}</td>"
            f"<td>{float(row['distance_km']):.2f}</td>"
            f"<td>{float(row['min_completeness_ratio']):.2f}</td>"
            f"<td>{float(row['mean_completeness_ratio']):.2f}</td>"
            f"<td>{html.escape(str(row['requested_fields']))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f3f4f6; }}
    svg {{ border: 1px solid #d1d5db; background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p>Anchor: {anchor_lat:.4f}, {anchor_lon:.4f}</p>
  <svg width="760" height="460" viewBox="0 0 760 460">
    {''.join(markers)}
  </svg>
  <table>
    <thead>
      <tr>
        <th>Rank</th><th>Source</th><th>Station ID</th><th>Name</th><th>Distance (km)</th>
        <th>Min completeness</th><th>Mean completeness</th><th>Requested fields</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""


def save_candidate_review_artifacts(
    *,
    candidates,
    report_prefix: str | Path,
    anchor_lat: float,
    anchor_lon: float,
    station_source: str = "ghcn_daily",
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
        help="Observed station backend: ghcn_daily, gsod, or auto (rank across both).",
    )
    parser.add_argument("--station-lat", type=float, required=True)
    parser.add_argument("--station-lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--station-id", default=None)
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
    parser.add_argument("--report-prefix", default=None)
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
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    if args.selection_mode == "list" and args.report_prefix:
        csv_path, json_path, html_path = save_candidate_review_artifacts(
            candidates=frame,
            report_prefix=args.report_prefix,
            anchor_lat=args.station_lat,
            anchor_lon=args.station_lon,
            station_source=args.station_source,
        )
        if not args.quiet:
            print(f"Saved candidate review CSV: {csv_path}")
            print(f"Saved candidate review JSON: {json_path}")
            print(f"Saved candidate review HTML: {html_path}")

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
