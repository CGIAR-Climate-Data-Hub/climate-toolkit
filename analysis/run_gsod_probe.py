#!/usr/bin/env python3
"""Quick NOAA GSOD coverage probe for candidate stations."""

from __future__ import annotations

import argparse
from io import StringIO

import pandas as pd
import requests


GSOD_TEMPLATE = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/{year}/{station}.csv"

MISSING_BY_COLUMN = {
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


def _normalize_station_id(station: str) -> str:
    token = station.strip()
    if len(token) == 5 and token.isdigit():
        return f"{token}099999"
    if len(token) == 11 and token.isdigit():
        return token
    raise ValueError(
        f"Unsupported station token '{station}'. Use 5-digit WMO-like ID or 11-digit GSOD ID."
    )


def _fetch_year(station_id: str, year: int) -> pd.DataFrame:
    url = GSOD_TEMPLATE.format(year=year, station=station_id)
    response = requests.get(url, timeout=120)
    if response.status_code == 404:
        return pd.DataFrame()
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


def _valid_count(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    values = pd.to_numeric(frame[column], errors="coerce")
    missing = MISSING_BY_COLUMN.get(column)
    if missing is not None:
        values = values.where(values != missing)
    return int(values.notna().sum())


def probe_station(
    *,
    site_name: str,
    station_token: str,
    start_year: int,
    end_year: int,
) -> dict:
    station_id = _normalize_station_id(station_token)
    frames = []
    for year in range(start_year, end_year + 1):
        year_df = _fetch_year(station_id, year)
        if not year_df.empty:
            year_df["YEAR_FETCHED"] = year
            frames.append(year_df)

    if not frames:
        return {
            "site": site_name,
            "station_id": station_id,
            "rows": 0,
            "years_found": 0,
            "precipitation_days": 0,
            "precipitation_pct": 0.0,
            "max_temperature_days": 0,
            "max_temperature_pct": 0.0,
            "min_temperature_days": 0,
            "min_temperature_pct": 0.0,
            "mean_temperature_days": 0,
            "mean_temperature_pct": 0.0,
            "wind_speed_days": 0,
            "wind_speed_pct": 0.0,
        }

    frame = pd.concat(frames, ignore_index=True)
    expected_days = pd.date_range(
        f"{start_year}-01-01",
        f"{end_year}-12-31",
        freq="D",
    ).size

    precip_days = _valid_count(frame, "PRCP")
    tmax_days = _valid_count(frame, "MAX")
    tmin_days = _valid_count(frame, "MIN")
    tavg_days = _valid_count(frame, "TEMP")
    wind_days = _valid_count(frame, "WDSP")

    first = frame.iloc[0]
    return {
        "site": site_name,
        "station_id": station_id,
        "station_name": first.get("NAME"),
        "rows": int(len(frame)),
        "years_found": int(frame["YEAR_FETCHED"].nunique()),
        "precipitation_days": precip_days,
        "precipitation_pct": round((precip_days / expected_days) * 100.0, 1),
        "max_temperature_days": tmax_days,
        "max_temperature_pct": round((tmax_days / expected_days) * 100.0, 1),
        "min_temperature_days": tmin_days,
        "min_temperature_pct": round((tmin_days / expected_days) * 100.0, 1),
        "mean_temperature_days": tavg_days,
        "mean_temperature_pct": round((tavg_days / expected_days) * 100.0, 1),
        "wind_speed_days": wind_days,
        "wind_speed_pct": round((wind_days / expected_days) * 100.0, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe NOAA GSOD daily station coverage.")
    parser.add_argument("--station", action="append", required=True, help="Site name,station_token")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    rows = []
    for token in args.station:
        site_name, station_token = [part.strip() for part in token.split(",", 1)]
        rows.append(
            probe_station(
                site_name=site_name,
                station_token=station_token,
                start_year=args.start_year,
                end_year=args.end_year,
            )
        )

    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False))
    if args.output:
        frame.to_csv(args.output, index=False)
        print(f"Saved CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
