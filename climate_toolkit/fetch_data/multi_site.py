"""Shared multi-site fetch contract helpers.

These utilities define common site identity, coordinate normalization, and
site/date integrity rules that batch downloaders should share across
historical and projection pipelines.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


CACHE_COORD_DECIMALS = 4


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float


def normalize_cache_coord(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    normalized = round(float(value), CACHE_COORD_DECIMALS)
    return 0.0 if normalized == -0.0 else normalized


def safe_coord_fragment(value: float | int | str) -> str:
    return (
        f"{normalize_cache_coord(value):.{CACHE_COORD_DECIMALS}f}"
        .replace("-", "m")
        .replace(".", "p")
    )


def safe_site_fragment(name: str, max_length: int = 24) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(name).strip())
    collapsed = "-".join(part for part in cleaned.split("-") if part)
    return (collapsed or "site")[:max_length]


def normalize_site(site) -> Site:
    if isinstance(site, Site):
        return site
    if isinstance(site, dict):
        return Site(
            name=str(site["name"]),
            lat=float(site["lat"]),
            lon=float(site["lon"]),
        )
    if isinstance(site, (tuple, list)) and len(site) == 3:
        name, lat, lon = site
        return Site(name=str(name), lat=float(lat), lon=float(lon))
    raise ValueError(
        "Each site must be a Site, dict(name/lat/lon), or tuple(name, lat, lon)."
    )


def parse_site_spec(raw: str) -> Site:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Invalid site spec '{raw}'. Expected format: name,lat,lon")
    return Site(name=parts[0], lat=float(parts[1]), lon=float(parts[2]))


def load_sites(
    sites: Iterable[Site | dict | tuple] | None = None,
    sites_csv: str | os.PathLike | None = None,
) -> list[Site]:
    resolved: list[Site] = []

    for site in sites or []:
        resolved.append(normalize_site(site))

    if sites_csv:
        frame = pd.read_csv(sites_csv)
        required = {"name", "lat", "lon"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                f"Sites CSV missing required columns: {', '.join(sorted(missing))}"
            )
        for row in frame.itertuples(index=False):
            resolved.append(Site(name=str(row.name), lat=float(row.lat), lon=float(row.lon)))

    if not resolved:
        raise ValueError("Provide at least one site or a sites_csv file.")

    deduped: list[Site] = []
    seen: set[tuple[str, float, float]] = set()
    for site in resolved:
        key = (
            site.name,
            normalize_cache_coord(site.lat),
            normalize_cache_coord(site.lon),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(site)
    return deduped


def site_batch_digest(site_batch: list[Site]) -> str:
    payload = "|".join(
        f"{site.name}:{normalize_cache_coord(site.lat):.{CACHE_COORD_DECIMALS}f}:"
        f"{normalize_cache_coord(site.lon):.{CACHE_COORD_DECIMALS}f}"
        for site in site_batch
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def site_date_integrity_summary(
    frame: pd.DataFrame,
    start: date,
    end: date,
    sites: list[Site],
    *,
    freq: str = "D",
    expected_dates: pd.DatetimeIndex | None = None,
) -> dict[str, object]:
    if expected_dates is None:
        expected_dates = pd.date_range(start, end, freq=freq)
    expected_rows = len(expected_dates) * len(sites)

    required_columns = {"site", "lat", "lon", "date"}
    if not required_columns.issubset(frame.columns):
        return {
            "complete": False,
            "row_count": len(frame),
            "expected_rows": expected_rows,
            "missing_site_dates": [
                {
                    "site": site.name,
                    "lat": site.lat,
                    "lon": site.lon,
                    "date": day.strftime("%Y-%m-%d"),
                }
                for site in sites
                for day in expected_dates
            ],
            "duplicate_site_dates": [],
        }

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce").dt.tz_localize(None)

    duplicate_rows = working.loc[
        working.duplicated(subset=["site", "lat", "lon", "date"], keep=False),
        ["site", "lat", "lon", "date"],
    ].drop_duplicates()
    duplicate_site_dates = [
        {
            "site": row.site,
            "lat": float(row.lat),
            "lon": float(row.lon),
            "date": row.date.strftime("%Y-%m-%d"),
        }
        for row in duplicate_rows.itertuples(index=False)
        if pd.notna(row.date)
    ]

    expected_index = pd.MultiIndex.from_tuples(
        [
            (site.name, site.lat, site.lon, day)
            for site in sites
            for day in expected_dates
        ],
        names=["site", "lat", "lon", "date"],
    )
    actual_index = pd.MultiIndex.from_frame(
        working[["site", "lat", "lon", "date"]].dropna()
    )
    missing_index = expected_index.difference(actual_index)
    missing_site_dates = [
        {
            "site": item[0],
            "lat": float(item[1]),
            "lon": float(item[2]),
            "date": item[3].strftime("%Y-%m-%d"),
        }
        for item in missing_index.tolist()
    ]

    return {
        "complete": not missing_site_dates and not duplicate_site_dates and len(frame) == expected_rows,
        "row_count": len(frame),
        "expected_rows": expected_rows,
        "missing_site_dates": missing_site_dates,
        "duplicate_site_dates": duplicate_site_dates,
    }


__all__ = [
    "CACHE_COORD_DECIMALS",
    "Site",
    "load_sites",
    "normalize_cache_coord",
    "normalize_site",
    "parse_site_spec",
    "safe_coord_fragment",
    "safe_site_fragment",
    "site_batch_digest",
    "site_date_integrity_summary",
]
