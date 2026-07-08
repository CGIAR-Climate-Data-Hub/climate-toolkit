"""User-facing runtime notes for cache-backed climate fetches."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .source_data.sources.utils.models import normalize_climate_dataset_name

HISTORICAL_GEE_CACHE_SOURCES = {
    "agera_5",
    "chirps_v2",
    "chirps_v3_daily_rnl",
    "era_5",
    "imerg",
    "terraclimate",
}


def _uses_historical_gee_cache_path(
    source: str | None,
    *,
    precip_source: str | None = None,
    temp_source: str | None = None,
) -> bool:
    source_name = normalize_climate_dataset_name(source)
    precip_name = normalize_climate_dataset_name(precip_source)
    temp_name = normalize_climate_dataset_name(temp_source)

    if source_name in {"nasa_power", "nex_gddp"}:
        return False

    if source_name == "auto":
        return True

    if source_name == "paired":
        return any(
            part in HISTORICAL_GEE_CACHE_SOURCES
            for part in (precip_name, temp_name)
        )

    return source_name in HISTORICAL_GEE_CACHE_SOURCES


def build_historical_cache_note(
    source: str | None,
    *,
    precip_source: str | None = None,
    temp_source: str | None = None,
    refresh_cache: bool = False,
    cache_dir: str | None = None,
) -> Optional[str]:
    """Return a brief note for GEE/Xee historical requests, else None."""
    if not _uses_historical_gee_cache_path(
        source,
        precip_source=precip_source,
        temp_source=temp_source,
    ):
        return None

    if refresh_cache:
        lead = (
            "Historical GEE/Xee fetch note: --refresh-cache forces a cold fetch "
            "and bypasses saved cache files, so this run may take tens of "
            "seconds to minutes."
        )
    else:
        lead = (
            "Historical GEE/Xee fetch note: first run may take tens of seconds "
            "to minutes; repeat runs should be much faster when the same cache "
            "is reused."
        )

    if cache_dir:
        return f"{lead} Cache root: {Path(cache_dir)}."

    return (
        f"{lead} Prefer a stable project-local cache under outputs/cache/... "
        "so repeat runs can reuse saved files."
    )
