"""DEM-backed anchor elevation lookup for station screening."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from climate_tookit.fetch_data.multi_site import normalize_cache_coord, safe_coord_fragment
from climate_tookit.fetch_data.source_data.sources.xee_common import (
    format_ee_setup_error,
    initialize_earth_engine,
)


DEFAULT_DEM_DATASET = "USGS/SRTMGL1_003"
DEFAULT_DEM_BAND = "elevation"
DEFAULT_DEM_SCALE_M = 30
DEM_CACHE_SCHEMA_VERSION = "v1"
DEFAULT_DEM_CACHE_ROOT = Path("outputs/cache/weather_stations/dem_anchor")


def _dem_cache_dir(
    *,
    lat: float,
    lon: float,
    cache_dir: str | Path | None = None,
) -> Path:
    root = Path(cache_dir or DEFAULT_DEM_CACHE_ROOT)
    return (
        root
        / DEM_CACHE_SCHEMA_VERSION
        / f"lat_{safe_coord_fragment(lat)}_lon_{safe_coord_fragment(lon)}"
    )


def _dem_cache_paths(
    *,
    lat: float,
    lon: float,
    cache_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    base_dir = _dem_cache_dir(lat=lat, lon=lon, cache_dir=cache_dir)
    return base_dir / "anchor_elevation.json", base_dir / "anchor_elevation.manifest.json"


def _load_cached_anchor_elevation(
    *,
    lat: float,
    lon: float,
    cache_dir: str | Path | None = None,
) -> float | None:
    data_path, manifest_path = _dem_cache_paths(lat=lat, lon=lon, cache_dir=cache_dir)
    if not data_path.exists() or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not manifest.get("complete", False):
        return None
    return float(payload["anchor_elevation_m"])


def _save_anchor_elevation(
    *,
    lat: float,
    lon: float,
    anchor_elevation_m: float,
    dataset: str,
    band: str,
    scale_m: float,
    cache_dir: str | Path | None = None,
) -> None:
    data_path, manifest_path = _dem_cache_paths(lat=lat, lon=lon, cache_dir=cache_dir)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "anchor_elevation_m": float(anchor_elevation_m),
    }
    manifest = {
        "cache_schema_version": DEM_CACHE_SCHEMA_VERSION,
        "dataset": dataset,
        "band": band,
        "scale_m": scale_m,
        "lat": normalize_cache_coord(lat),
        "lon": normalize_cache_coord(lon),
        "complete": True,
    }
    temp_data = data_path.with_suffix(".json.part")
    temp_manifest = manifest_path.with_suffix(".json.part")
    temp_data.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temp_data.replace(data_path)
    temp_manifest.replace(manifest_path)


def fetch_anchor_elevation(
    *,
    lat: float,
    lon: float,
    cache_dir: str | Path | None = None,
    refresh_cache: bool = False,
    project_id: str | None = None,
    dataset: str = DEFAULT_DEM_DATASET,
    band: str = DEFAULT_DEM_BAND,
    scale_m: float = DEFAULT_DEM_SCALE_M,
) -> float:
    if not refresh_cache:
        cached = _load_cached_anchor_elevation(lat=lat, lon=lon, cache_dir=cache_dir)
        if cached is not None:
            return cached

    try:
        ee_module = importlib.import_module("ee")
        initialize_earth_engine(ee_module, project_id=project_id)
        point = ee_module.Geometry.Point([float(lon), float(lat)])
        image = ee_module.Image(dataset).select(band)
        values = image.reduceRegion(
            reducer=ee_module.Reducer.mean(),
            geometry=point,
            scale=scale_m,
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()
    except Exception as exc:  # pragma: no cover - exact EE exceptions vary
        raise RuntimeError(format_ee_setup_error(exc)) from exc

    if not values or values.get(band) is None:
        raise RuntimeError(
            f"DEM lookup returned no elevation for lat={lat}, lon={lon} using {dataset}:{band}."
        )

    anchor_elevation_m = float(values[band])
    _save_anchor_elevation(
        lat=lat,
        lon=lon,
        anchor_elevation_m=anchor_elevation_m,
        dataset=dataset,
        band=band,
        scale_m=scale_m,
        cache_dir=cache_dir,
    )
    return anchor_elevation_m


__all__ = [
    "DEFAULT_DEM_BAND",
    "DEFAULT_DEM_CACHE_ROOT",
    "DEFAULT_DEM_DATASET",
    "DEFAULT_DEM_SCALE_M",
    "fetch_anchor_elevation",
]
