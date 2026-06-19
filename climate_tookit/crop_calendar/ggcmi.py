"""GGCMI Phase 3 crop-calendar point extraction helpers."""

from __future__ import annotations

import json
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any

import pandas as pd

from climate_tookit._resources import (
    load_json_resource,
    package_resource_exists,
    packaged_resource_path,
)
from .registry import get_crop_support, normalize_crop_name


GGCMI_DATA_PACKAGE = "climate_tookit.data.ggcmi_phase3"
PARQUET_RESOURCE = "crop_calendar.parquet"
MANIFEST_RESOURCE = "crop_calendar_manifest.json"

DATA_SOURCE_USED_LABELS = {
    1: "MIRCA",
    2: "SAGE",
    3: "Iizumi et al. 2019",
    4: "RiceAtlas",
    5: "Dimou et al. 2018",
    6: "ChinCropPhen",
    7: "IndiaAgStat",
    8: "Brazil CONAB",
    9: "Australia ABARES",
}
CALENDAR_SYSTEM_CHOICES = ("rf", "ir", "both")


class GGCMICalendarAssetMissingError(FileNotFoundError):
    """Raised when packaged GGCMI asset has not been built yet."""


def asset_paths() -> dict[str, Path]:
    parquet = Path(str(files(GGCMI_DATA_PACKAGE).joinpath(PARQUET_RESOURCE)))
    manifest = Path(str(files(GGCMI_DATA_PACKAGE).joinpath(MANIFEST_RESOURCE)))
    return {"data_dir": parquet.parent, "parquet": parquet, "manifest": manifest}


def asset_available() -> bool:
    return package_resource_exists(GGCMI_DATA_PACKAGE, PARQUET_RESOURCE) and package_resource_exists(
        GGCMI_DATA_PACKAGE, MANIFEST_RESOURCE
    )


def _require_asset() -> None:
    if not asset_available():
        raise GGCMICalendarAssetMissingError(
            f"GGCMI calendar asset not found in package {GGCMI_DATA_PACKAGE}:{PARQUET_RESOURCE}. "
            "Build it first with analysis/build_ggcmi_phase3_asset.py."
        )


def load_calendar_manifest() -> dict[str, Any]:
    _require_asset()
    return load_json_resource(GGCMI_DATA_PACKAGE, MANIFEST_RESOURCE)


def load_calendar_table(
    *,
    crop_name: str | None = None,
    crop_code: str | None = None,
    system: str | None = None,
    path: Path | None = None,
) -> pd.DataFrame:
    filters = []
    if crop_name is not None:
        crop = get_crop_support(normalize_crop_name(crop_name, require_calendar=True))
        filters.append(("crop_name", "==", crop.canonical_name))
    if crop_code is not None:
        filters.append(("crop_code", "==", crop_code))
    if system is not None:
        normalized_system = str(system).lower()
        if normalized_system not in {"rf", "ir"}:
            raise ValueError("system must be 'rf' or 'ir'")
        filters.append(("system", "==", normalized_system))
    if path is not None:
        if filters:
            return pd.read_parquet(path, filters=filters)
        return pd.read_parquet(path)

    _require_asset()
    with packaged_resource_path(GGCMI_DATA_PACKAGE, PARQUET_RESOURCE) as parquet_path:
        if filters:
            return pd.read_parquet(parquet_path, filters=filters)
        return pd.read_parquet(parquet_path)


def _month_day_from_doy(day_of_year: int, *, base_year: int = 2001) -> str:
    resolved = date(base_year, 1, 1) + timedelta(days=int(day_of_year) - 1)
    return resolved.strftime("%m-%d")


def build_fixed_season_tokens(calendar_rows: pd.DataFrame) -> list[str]:
    tokens = []
    if calendar_rows.empty:
        return tokens
    for row in calendar_rows.sort_values(["system", "season_id"]).itertuples(index=False):
        if pd.isna(row.planting_day) or pd.isna(row.maturity_day):
            continue
        tokens.append(
            f"{_month_day_from_doy(int(row.planting_day))}:{_month_day_from_doy(int(row.maturity_day))}"
        )
    return tokens


def resolve_calendar_preset(
    lat: float,
    lon: float,
    crop_name: str,
    *,
    system: str = "rf",
    path: Path | None = None,
) -> dict[str, Any]:
    requested_system = str(system).lower()
    if requested_system not in CALENDAR_SYSTEM_CHOICES:
        raise ValueError(
            f"calendar system must be one of {', '.join(CALENDAR_SYSTEM_CHOICES)}"
        )

    rows = extract_point_calendar(
        lat,
        lon,
        crop_name,
        system=None if requested_system == "both" else requested_system,
        path=path,
    )
    if rows.empty:
        raise ValueError(f"No GGCMI calendar rows found for crop '{crop_name}'.")

    tokens = []
    for token in rows["fixed_season_token"].tolist():
        if token and token not in tokens:
            tokens.append(token)
    if not tokens:
        raise ValueError(f"GGCMI calendar for crop '{crop_name}' did not yield usable season windows.")
    if len(tokens) > 2:
        raise ValueError(
            f"GGCMI calendar for crop '{crop_name}' and system='{requested_system}' "
            f"yields {len(tokens)} distinct windows ({', '.join(tokens)}). "
            "Current fixed-season workflow supports at most 2 windows; choose rf or ir explicitly."
        )

    first = rows.iloc[0]
    return {
        "calendar_source": "ggcmi_phase3",
        "crop_name": normalize_crop_name(crop_name, require_calendar=True),
        "calendar_system": requested_system,
        "fixed_season": ",".join(tokens),
        "fixed_season_tokens": tokens,
        "matched_lat": float(first["matched_lat"]),
        "matched_lon": float(first["matched_lon"]),
        "distance_deg": float(first["distance_deg"]),
        "systems_included": sorted(rows["system"].dropna().unique().tolist()),
        "calendar_rows": rows.where(pd.notnull(rows), None).to_dict(orient="records"),
    }


def extract_point_calendar(
    lat: float,
    lon: float,
    crop_name: str,
    *,
    system: str | None = None,
    path: Path | None = None,
) -> pd.DataFrame:
    normalized_crop = normalize_crop_name(crop_name, require_calendar=True)
    table = load_calendar_table(crop_name=normalized_crop, system=system, path=path)
    if table.empty:
        return table.copy()

    working = table.copy()
    working["distance_sq"] = (working["lat"] - float(lat)) ** 2 + (working["lon"] - float(lon)) ** 2
    nearest_distance = working["distance_sq"].min()
    nearest = working.loc[working["distance_sq"] == nearest_distance].copy()
    nearest["query_lat"] = float(lat)
    nearest["query_lon"] = float(lon)
    nearest["matched_lat"] = nearest["lat"]
    nearest["matched_lon"] = nearest["lon"]
    nearest["distance_deg"] = nearest["distance_sq"] ** 0.5
    nearest["fixed_season_token"] = nearest.apply(
        lambda row: (
            None
            if pd.isna(row["planting_day"]) or pd.isna(row["maturity_day"])
            else f"{_month_day_from_doy(int(row['planting_day']))}:{_month_day_from_doy(int(row['maturity_day']))}"
        ),
        axis=1,
    )
    return nearest.sort_values(["system", "season_id"]).reset_index(drop=True)
