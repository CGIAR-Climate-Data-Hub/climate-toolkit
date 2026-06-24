"""Shared Xee + Earth Engine helpers for point-based extraction.

This module is intended to support both projection and historical
Earth Engine-backed downloaders that use Xee/xarray rather than raw
`reduceRegion()` loops.
"""

from __future__ import annotations

import importlib
import os
from datetime import date

import pandas as pd


DEFAULT_EE_OPT_URL = "https://earthengine-highvolume.googleapis.com"
METERS_PER_DEGREE = 111_320.0
MISSING_EE_PROJECT_ID_PREFIX = "Earth Engine project ID is required."
EARTH_ENGINE_SETUP_URL = (
    "https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit#earth-engine-setup"
)


def import_xee_stack(required_for: str = "xee_common"):
    missing = []
    modules = {}
    for module_name in ("ee", "xarray", "xee"):
        try:
            modules[module_name] = importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)

    if missing:
        missing_list = ", ".join(missing)
        raise ImportError(
            f"{required_for} requires optional dependencies that are not installed: "
            f"{missing_list}. Install at least 'earthengine-api', 'xarray', and 'xee'."
        )

    return modules["ee"], modules["xarray"]


def infer_ee_project_id(explicit_project_id: str | None) -> str:
    project_id = (
        explicit_project_id
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("EE_PROJECT_ID")
    )
    if not project_id:
        raise ValueError(
            "Earth Engine project ID is required. Pass ee_project_id or set one of "
            "GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or EE_PROJECT_ID."
        )
    return project_id


def format_ee_setup_error(exc: Exception) -> str:
    message = str(exc)
    if message.startswith(MISSING_EE_PROJECT_ID_PREFIX):
        return (
            "Earth Engine project ID missing. Set GCP_PROJECT_ID "
            "(or GOOGLE_CLOUD_PROJECT / EE_PROJECT_ID) and retry. "
            "Example: export GCP_PROJECT_ID=your-ee-project-id. "
            f"Setup guide: {EARTH_ENGINE_SETUP_URL}"
        )
    lowered = message.lower()
    if (
        "oauth2.googleapis.com" in lowered
        or "failed to resolve" in lowered
        or "max retries exceeded" in lowered
        or "transporterror" in lowered
    ):
        return (
            "Earth Engine auth refresh failed. Check internet/DNS access, then "
            "refresh auth if needed with: "
            ".venv/bin/python -c \"import ee; ee.Authenticate(); ee.Initialize(project='YOUR_PROJECT_ID')\". "
            f"Setup guide: {EARTH_ENGINE_SETUP_URL}"
        )
    return message


def initialize_earth_engine(
    ee_module,
    *,
    project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
) -> str:
    resolved_project_id = infer_ee_project_id(project_id)
    ee_module.Initialize(project=resolved_project_id, opt_url=ee_opt_url)
    return resolved_project_id


def progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[" + ("-" * width) + "]"
    filled = min(width, round(width * current / total))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def is_retryable_ee_error(err: Exception) -> bool:
    msg = str(err).lower()
    retry_markers = (
        "429",
        "too many requests",
        "rate limit",
        "quota exceeded",
        "temporarily unavailable",
        "internal error",
        "connection reset",
        "deadline exceeded",
        "timed out",
        "timeout",
    )
    return any(marker in msg for marker in retry_markers)


def is_chunk_overflow_error(err: Exception) -> bool:
    msg = str(err).lower()
    overflow_markers = (
        "5000 elements",
        "user memory limit exceeded",
        "computation timed out",
        "too many concurrent aggregations",
    )
    return any(marker in msg for marker in overflow_markers)


def manual_point_grid(lon: float, lat: float, pixel_size_meters: float) -> dict:
    pixel_size_degrees = pixel_size_meters / METERS_PER_DEGREE
    half = pixel_size_degrees / 2.0
    return {
        "crs": "EPSG:4326",
        "crs_transform": (
            pixel_size_degrees,
            0.0,
            lon - half,
            0.0,
            -pixel_size_degrees,
            lat + half,
        ),
        "shape_2d": (1, 1),
    }


def open_point_dataset(
    xr_module,
    collection,
    *,
    lon: float,
    lat: float,
    pixel_size_meters: float,
    fast_time_slicing: bool = False,
):
    grid = manual_point_grid(
        lon=lon,
        lat=lat,
        pixel_size_meters=pixel_size_meters,
    )
    return xr_module.open_dataset(
        collection,
        engine="ee",
        fast_time_slicing=fast_time_slicing,
        **grid,
    )


def point_dataset_to_frame(
    dataset,
    *,
    start_date: date,
    end_date: date,
    band_names: list[str],
    time_coord: str = "time",
    output_date_column: str = "date",
    freq: str = "D",
) -> pd.DataFrame:
    active_band_names = [band for band in band_names if band in dataset.data_vars]
    if not active_band_names:
        return pd.DataFrame({output_date_column: pd.date_range(start_date, end_date, freq=freq)})

    spatial_indexers = {dim: 0 for dim in dataset.dims if dim != time_coord}
    point_ds = dataset[active_band_names].isel(spatial_indexers, drop=True)
    frame = point_ds.to_dataframe().reset_index()

    if time_coord not in frame.columns:
        raise ValueError(f"Expected Xee output to contain a '{time_coord}' coordinate.")

    frame = frame.rename(columns={time_coord: output_date_column})
    frame[output_date_column] = pd.to_datetime(
        frame[output_date_column], utc=False
    ).dt.tz_localize(None)
    frame = frame[[output_date_column, *active_band_names]].sort_values(
        output_date_column
    ).reset_index(drop=True)

    full_range = pd.date_range(start_date, end_date, freq=freq)
    frame = (
        frame.set_index(output_date_column)
        .reindex(full_range)
        .rename_axis(output_date_column)
        .reset_index()
    )
    return frame


__all__ = [
    "DEFAULT_EE_OPT_URL",
    "METERS_PER_DEGREE",
    "format_ee_setup_error",
    "import_xee_stack",
    "infer_ee_project_id",
    "initialize_earth_engine",
    "is_chunk_overflow_error",
    "is_retryable_ee_error",
    "manual_point_grid",
    "open_point_dataset",
    "point_dataset_to_frame",
    "progress_bar",
]
