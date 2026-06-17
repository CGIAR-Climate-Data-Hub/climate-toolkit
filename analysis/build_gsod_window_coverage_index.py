"""Prewarm and export GSOD station coverage summaries for a target window."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from climate_tookit.fetch_data.fetch_data import parse_variables
from climate_tookit.weather_station.gsod import list_gsod_station_candidates


def _coord_token(value: float) -> str:
    token = f"{float(value):.4f}"
    return token.replace("-", "m").replace(".", "p")


def _default_output_prefix(
    *,
    lat: float,
    lon: float,
    date_from: date,
    date_to: date,
) -> Path:
    return (
        Path("outputs/cache/weather_stations/gsod/coverage/index_runs")
        / f"lat_{_coord_token(lat)}_lon_{_coord_token(lon)}"
        / f"{date_from.isoformat()}_{date_to.isoformat()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precompute GSOD candidate coverage summaries for one site and date window."
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--variables", required=True)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--max-distance-km", type=float, default=250.0)
    parser.add_argument("--target-elevation-m", type=float, default=None)
    parser.add_argument("--max-elevation-diff-m", type=float, default=500.0)
    parser.add_argument("--min-completeness-ratio", type=float, default=0.7)
    parser.add_argument("--score-limit", type=int, default=25)
    parser.add_argument("--candidate-limit", type=int, default=25)
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    date_from = date.fromisoformat(args.start)
    date_to = date.fromisoformat(args.end)
    variables = parse_variables(args.variables)
    output_prefix = Path(args.output_prefix) if args.output_prefix else _default_output_prefix(
        lat=args.lat,
        lon=args.lon,
        date_from=date_from,
        date_to=date_to,
    )

    candidates = list_gsod_station_candidates(
        location_coord=(args.lat, args.lon),
        date_from=date_from,
        date_to=date_to,
        variables=variables,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
        max_distance_km=args.max_distance_km,
        target_elevation_m=args.target_elevation_m,
        max_elevation_diff_m=args.max_elevation_diff_m,
        min_completeness_ratio=args.min_completeness_ratio,
        candidate_limit=args.candidate_limit,
        score_limit=args.score_limit,
        enforce_threshold=False,
        verbose=not args.quiet,
    )

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    manifest_path = output_prefix.with_suffix(".manifest.json")
    candidates.to_csv(csv_path, index=False)
    candidates.to_json(json_path, orient="records", indent=2)
    manifest_path.write_text(
        json.dumps(
            {
                "lat": args.lat,
                "lon": args.lon,
                "start": date_from.isoformat(),
                "end": date_to.isoformat(),
                "variables": [variable.name for variable in variables],
                "rows": int(len(candidates)),
                "score_limit": int(args.score_limit),
                "candidate_limit": int(args.candidate_limit),
                "refresh_cache": bool(args.refresh_cache),
                "csv_path": str(csv_path),
                "json_path": str(json_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "GSOD window coverage index ready | "
        f"rows={len(candidates)} | csv={csv_path} | json={json_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
