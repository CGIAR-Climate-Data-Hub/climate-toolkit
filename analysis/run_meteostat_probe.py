#!/usr/bin/env python3
"""Quick Meteostat station discovery and daily coverage probe."""

from __future__ import annotations

import argparse
from datetime import datetime

import pandas as pd
from meteostat import Point, daily, stations


VARIABLE_MAP = {
    "precipitation": "prcp",
    "max_temperature": "tmax",
    "min_temperature": "tmin",
    "mean_temperature": "tavg",
    "wind_speed": "wspd",
}


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 1)


def probe_site(
    *,
    name: str,
    lat: float,
    lon: float,
    start: str,
    end: str,
    limit: int,
) -> pd.DataFrame:
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    expected_days = (end_dt.date() - start_dt.date()).days + 1

    nearby = stations.nearby(Point(lat, lon), radius=100000, limit=limit)
    if nearby is None or nearby.empty:
        print(f"{name}: no nearby Meteostat stations found")
        return pd.DataFrame()

    rows: list[dict] = []
    print(
        f"{name}: Meteostat nearby stations for {start}..{end} "
        f"(expected_days={expected_days})"
    )
    for station_id, row in nearby.iterrows():
        obs = daily(station_id, start_dt, end_dt).fetch()
        if obs is None:
            obs = pd.DataFrame()
        coverage = {
            out_name: int(obs[in_name].notna().sum()) if in_name in obs.columns else 0
            for out_name, in_name in VARIABLE_MAP.items()
        }
        rows.append(
            {
                "site": name,
                "station_id": station_id,
                "station_name": row.get("name"),
                "distance_km": round(float(row.get("distance", float("nan"))) / 1000.0, 2)
                if "distance" in row
                else None,
                "daily_rows": int(len(obs)),
                "precipitation_days": coverage["precipitation"],
                "precipitation_pct": _pct(coverage["precipitation"], expected_days),
                "max_temperature_days": coverage["max_temperature"],
                "max_temperature_pct": _pct(coverage["max_temperature"], expected_days),
                "min_temperature_days": coverage["min_temperature"],
                "min_temperature_pct": _pct(coverage["min_temperature"], expected_days),
                "mean_temperature_days": coverage["mean_temperature"],
                "mean_temperature_pct": _pct(coverage["mean_temperature"], expected_days),
                "wind_speed_days": coverage["wind_speed"],
                "wind_speed_pct": _pct(coverage["wind_speed"], expected_days),
            }
        )

    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False))
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Meteostat station coverage near site.")
    parser.add_argument("--site", action="append", required=True, help="Name,lat,lon")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    frames = []
    for site_token in args.site:
        name, lat, lon = [part.strip() for part in site_token.split(",", 2)]
        frames.append(
            probe_site(
                name=name,
                lat=float(lat),
                lon=float(lon),
                start=args.start,
                end=args.end,
                limit=args.limit,
            )
        )

    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if frames else pd.DataFrame()
    if args.output and not combined.empty:
        combined.to_csv(args.output, index=False)
        print(f"Saved CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
