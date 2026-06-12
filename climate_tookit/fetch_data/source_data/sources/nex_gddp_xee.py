"""
Proof-of-concept Xee-backed NEX-GDDP downloader.

This module provides Xee-backed implementation used by package `nex_gddp`
adapter.

Historical notes from initial PoC:

1. ``xee`` to the runtime dependencies.
2. Earth Engine authentication in the execution environment.
3. End-to-end validation against the existing fetch/transform/preprocess flow.

Upstream references used for this PoC:
- Xee README / quickstart:
  https://github.com/google/Xee
- Xee open_dataset reference:
  https://github.com/google/Xee/blob/main/docs/open_dataset.md
- Earth Engine NEX-GDDP-CMIP6 catalog:
  https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6

Important dataset notes reflected below:
- ``pr`` is exposed by Earth Engine as precipitation rate in ``kg m-2 s-1``.
  This PoC converts it to ``mm/day`` via ``* 86400``.
- ``tasmin`` / ``tasmax`` are exposed in Kelvin. This PoC converts them to
  Celsius via ``- 273.15``.
- The Earth Engine catalog documents ``historical`` as pre-2015 and SSP
  scenarios as post-2014. This PoC enforces that split early.
- Current package implementation targets Earth Engine dataset version ``1.1``.
  Version ``1.2`` should be treated as future follow-up work, not active
  runtime expectation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from ...multi_site import (
    CACHE_COORD_DECIMALS,
    normalize_cache_coord,
    safe_coord_fragment,
)
from .xee_common import (
    DEFAULT_EE_OPT_URL,
    import_xee_stack,
    infer_ee_project_id,
    initialize_earth_engine,
    is_chunk_overflow_error,
    is_retryable_ee_error,
    manual_point_grid,
    open_point_dataset,
    point_dataset_to_frame,
    progress_bar,
)
from .utils import models
from .utils.settings import Settings, set_logging

set_logging()
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ACCESS-CM2"
DEFAULT_SCENARIO = "ssp245"
DEFAULT_DATASET_VERSION = "1.1"
DEFAULT_CACHE_DIR = "outputs/cache/nex_gddp_xee"
DEFAULT_CHUNK_DAYS = 365
DEFAULT_RETRY_ATTEMPTS = 4
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
MIN_CHUNK_DAYS = 1
CACHE_SCHEMA_VERSION = "v1"
AFRICA_CMIP6_GUIDANCE_URL = (
    "https://cgiar-climate-data-hub.github.io/wikis/aaa-atlas/"
    "african-cmip6-ensembling/"
)
SECONDS_PER_DAY = 86_400.0
RAINCELL_WARN_THRESHOLD_MM_DAY = 500.0
ARID_RAINBOMB_DRY_DAY_THRESHOLD_MM = 1.0
ARID_RAINBOMB_DRY_DAY_FRACTION = 0.8
ARID_RAINBOMB_WET_DAY_MEDIAN_MAX_MM = 2.0
ARID_RAINBOMB_SPIKE_MIN_MM_DAY = 50.0
ARID_RAINBOMB_RATIO_MIN = 40.0

SCENARIO_MAPPING = {
    "historical": "historical",
    "ssp126": "ssp126",
    "ssp1-2.6": "ssp126",
    "SSP1-2.6": "ssp126",
    "ssp245": "ssp245",
    "ssp2-4.5": "ssp245",
    "SSP2-4.5": "ssp245",
    "ssp370": "ssp370",
    "ssp3-7.0": "ssp370",
    "SSP3-7.0": "ssp370",
    "ssp585": "ssp585",
    "ssp5-8.5": "ssp585",
    "SSP5-8.5": "ssp585",
}


def _canonical_variable_name(variable) -> str:
    if hasattr(variable, "name"):
        return variable.name
    return str(variable).split(".")[-1]


def _normalize_scenario(scenario: str | None) -> str:
    if scenario is None:
        return DEFAULT_SCENARIO
    try:
        return SCENARIO_MAPPING[scenario]
    except KeyError as exc:
        valid = ", ".join(sorted(SCENARIO_MAPPING))
        raise ValueError(f"Unsupported NEX-GDDP scenario '{scenario}'. Valid keys: {valid}") from exc


def _validate_period_against_scenario(
    scenario: str,
    date_from_utc: date,
    date_to_utc: date,
) -> None:
    if date_from_utc > date_to_utc:
        raise ValueError("date_from_utc must be on or before date_to_utc")

    historical_cutoff = date(2014, 12, 31)
    future_start = date(2015, 1, 1)

    if scenario == "historical" and date_to_utc > historical_cutoff:
        raise ValueError(
            "NEX-GDDP 'historical' should only be used through 2014-12-31."
        )
    if scenario != "historical" and date_from_utc < future_start:
        raise ValueError(
            f"NEX-GDDP '{scenario}' should only be used from 2015-01-01 onward."
        )


def _manual_point_grid(lon: float, lat: float, pixel_size_meters: float) -> dict:
    return manual_point_grid(lon=lon, lat=lat, pixel_size_meters=pixel_size_meters)


def _is_africa_coordinate(lat: float, lon: float) -> bool:
    return -35.0 <= lat <= 38.0 and -20.0 <= lon <= 55.0


def _is_horn_of_africa_coordinate(lat: float, lon: float) -> bool:
    return -5.0 <= lat <= 18.0 and 28.0 <= lon <= 52.0


def _import_xee_stack():
    return import_xee_stack(required_for="nex_gddp_xee")


def _infer_ee_project_id(explicit_project_id: str | None) -> str:
    return infer_ee_project_id(explicit_project_id)


def _version_sort_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in str(version).split("."))


def _safe_coord_fragment(value: float) -> str:
    return safe_coord_fragment(value)


def _normalize_cache_coord(value: float) -> float:
    return normalize_cache_coord(value)


def _progress_bar(current: int, total: int, width: int = 20) -> str:
    return progress_bar(current, total, width=width)


def _coerce_version_filter_value(version: str) -> float | str:
    try:
        return float(version)
    except (TypeError, ValueError):
        return version


def _resolve_dataset_version(collection, preferred_version: str = DEFAULT_DATASET_VERSION) -> str | None:
    histogram = collection.aggregate_histogram("version").getInfo() or {}
    available = sorted(
        {
            str(key)
            for key, count in histogram.items()
            if key not in (None, "null") and count
        },
        key=_version_sort_key,
    )
    if preferred_version in available:
        return preferred_version
    if available:
        return available[-1]
    return None


def _is_retryable_ee_error(err: Exception) -> bool:
    return is_retryable_ee_error(err)


def _is_chunk_overflow_error(err: Exception) -> bool:
    return is_chunk_overflow_error(err)


def _warn_on_suspicious_precipitation(
    frame: pd.DataFrame,
    *,
    model: str,
    scenario: str,
    threshold_mm_day: float = RAINCELL_WARN_THRESHOLD_MM_DAY,
) -> None:
    if "pr" not in frame.columns or frame.empty:
        return

    precip = pd.to_numeric(frame["pr"], errors="coerce")
    max_idx = precip.idxmax()
    max_precip = float(precip.loc[max_idx]) if len(precip.dropna()) else float("nan")
    max_date = pd.to_datetime(frame.loc[max_idx, "date"], errors="coerce").strftime("%Y-%m-%d")

    wet_days = precip[precip > 0]
    if len(wet_days) < 3:
        return

    median_wet = float(wet_days.median())
    dry_fraction = float((precip.fillna(0) <= ARID_RAINBOMB_DRY_DAY_THRESHOLD_MM).mean())
    is_arid_signature = (
        dry_fraction >= ARID_RAINBOMB_DRY_DAY_FRACTION
        and median_wet <= ARID_RAINBOMB_WET_DAY_MEDIAN_MAX_MM
    )
    if not is_arid_signature:
        return

    ratio = (max_precip / median_wet) if median_wet > 0 else float("inf")
    if max_precip >= threshold_mm_day or (
        max_precip >= ARID_RAINBOMB_SPIKE_MIN_MM_DAY
        and ratio >= ARID_RAINBOMB_RATIO_MIN
    ):
        extreme = frame.loc[precip > threshold_mm_day, ["date", "pr"]].copy()
        if not extreme.empty:
            extreme["date"] = pd.to_datetime(extreme["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            preview = ", ".join(
                f"{row.date}={float(row.pr):.2f} mm/day"
                for row in extreme.head(3).itertuples(index=False)
            )
            if len(extreme) > 3:
                preview = f"{preview}, ..."
        else:
            preview = f"{max_date}={max_precip:.2f} mm/day"

        logger.warning(
            "Potential NEX-GDDP arid-zone rainbomb detected for model=%s scenario=%s: "
            "max daily precipitation %.2f mm/day on %s versus wet-day median %.2f mm/day "
            "(ratio %.1fx, dry-day fraction %.0f%%). Sample: %s. This can indicate unstable "
            "downscaling/bias-correction in very arid regimes.",
            model,
            scenario,
            max_precip,
            max_date,
            median_wet,
            ratio,
            dry_fraction * 100.0,
            preview,
        )


def _maybe_log_africa_guidance(
    *,
    lat: float,
    lon: float,
    scenario: str,
    date_from_utc: date,
    date_to_utc: date,
) -> None:
    if not _is_africa_coordinate(lat, lon):
        return

    logger.warning(
        "Africa coordinate detected for NEX-GDDP (%s, %s). For African climate-rationale work, "
        "note CGIAR African CMIP6 ensembling guidance: %s . It uses region-tuned African "
        "sub-ensembles, excludes CanESM5 from default central-estimate ensemble, and assumes "
        "r1i1p1f1 across its 18-model NEX workflow.",
        lat,
        lon,
        AFRICA_CMIP6_GUIDANCE_URL,
    )

    if scenario == "historical":
        return

    if not _is_horn_of_africa_coordinate(lat, lon):
        return

    months = {date_from_utc.month, date_to_utc.month}
    if months & {3, 4, 5}:
        logger.warning(
            "Horn/East Africa coordinate detected for future NEX-GDDP (%s, %s). "
            "For MAM rainfall, East African Paradox caveat applies: observed drying versus CMIP6 "
            "wetting is unresolved structural bias. See %s .",
            lat,
            lon,
            AFRICA_CMIP6_GUIDANCE_URL,
        )


class DownloadData(models.DataDownloadBase):
    """
    Xee-based NEX-GDDP downloader prototype.

    The public contract mirrors the existing source adapters:
    ``download_variables()`` returns a pandas DataFrame with raw NEX band names
    (``date``, ``pr``, ``tasmax``, ``tasmin``). Unit normalization happens here
    so downstream alpha testing can inspect physically meaningful values.
    """

    def __init__(
        self,
        variables: List[models.ClimateVariable],
        location_coord: Tuple[float, float],
        date_from_utc: date,
        date_to_utc: date,
        settings: Settings,
        source: models.ClimateDataset,
        model: str | None = None,
        scenario: str | None = None,
        ee_project_id: str | None = None,
        ee_opt_url: str = DEFAULT_EE_OPT_URL,
        cache_dir: str | None = None,
        refresh_cache: bool = False,
        verbose: bool = True,
        chunk_days: int | None = None,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    ):
        super().__init__(
            location_coord=location_coord,
            date_from_utc=date_from_utc,
            date_to_utc=date_to_utc,
            variables=variables,
        )
        self.date_from_utc = date_from_utc
        self.date_to_utc = date_to_utc
        self.location_coord = location_coord
        self.variables = variables
        self.settings = settings
        self.source = source
        self.model = model or DEFAULT_MODEL
        self.scenario = _normalize_scenario(scenario)
        self.ee_project_id = ee_project_id
        self.ee_opt_url = ee_opt_url
        self.cache_dir = Path(
            cache_dir
            or os.getenv("CLIMATE_TOOKIT_NEX_GDDP_CACHE_DIR")
            or DEFAULT_CACHE_DIR
        )
        self.refresh_cache = refresh_cache
        self.verbose = verbose
        self.chunk_days = chunk_days or int(
            os.getenv("CLIMATE_TOOKIT_NEX_GDDP_CHUNK_DAYS", str(DEFAULT_CHUNK_DAYS))
        )
        self.retry_attempts = max(1, retry_attempts)

        _validate_period_against_scenario(
            scenario=self.scenario,
            date_from_utc=self.date_from_utc,
            date_to_utc=self.date_to_utc,
        )

    def _log_progress(self, message: str) -> None:
        if self.verbose:
            logger.info(message)

    def _ensure_ee_initialized(self, ee_module) -> None:
        initialize_earth_engine(
            ee_module,
            project_id=self.ee_project_id,
            ee_opt_url=self.ee_opt_url,
        )

    def _requested_band_names(self) -> list[str]:
        bands = []
        for variable in self.variables:
            variable_name = _canonical_variable_name(variable)
            band_name = self.settings.nex_gddp.variable.get_band(variable_name)
            if band_name:
                bands.append(band_name)

        ordered = []
        for band in bands:
            if band not in ordered:
                ordered.append(band)

        if not ordered:
            raise ValueError("No NEX-GDDP-compatible variables were requested.")
        return ordered

    def _build_collection(self, ee_module, start_date: date, end_date: date):
        lat, lon = self.location_coord
        start = start_date.strftime("%Y-%m-%d")
        end = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        point = ee_module.Geometry.Point([lon, lat])

        collection = (
            ee_module.ImageCollection(self.settings.nex_gddp.gee_image)
            .filterDate(start, end)
            .filterBounds(point)
            .filter(ee_module.Filter.eq("model", self.model))
            .filter(ee_module.Filter.eq("scenario", self.scenario))
        )
        selected_version = _resolve_dataset_version(collection)
        if selected_version:
            collection = collection.filter(
                ee_module.Filter.eq(
                    "version",
                    _coerce_version_filter_value(selected_version),
                )
            )
        collection = collection.select(self._requested_band_names())

        return collection, selected_version

    def _open_dataset(self, xr_module, collection):
        lat, lon = self.location_coord
        return open_point_dataset(
            xr_module,
            collection,
            lon=lon,
            lat=lat,
            pixel_size_meters=self.settings.nex_gddp.resolution,
        )

    def _dataset_to_frame(
        self,
        dataset,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        return point_dataset_to_frame(
            dataset,
            start_date=start_date,
            end_date=end_date,
            band_names=self._requested_band_names(),
            time_coord="time",
            output_date_column="date",
            freq="D",
        )

    def _chunk_dates(self, start_date: date, end_date: date) -> list[tuple[date, date]]:
        chunks = []
        cursor = start_date
        while cursor <= end_date:
            chunk_end = min(cursor + timedelta(days=self.chunk_days - 1), end_date)
            chunks.append((cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        return chunks

    def _cache_base_dir(self) -> Path:
        lat, lon = self.location_coord
        return (
            self.cache_dir
            / CACHE_SCHEMA_VERSION
            / self.scenario
            / self.model
            / f"lat_{_safe_coord_fragment(lat)}_lon_{_safe_coord_fragment(lon)}"
        )

    def _cache_paths(self, start_date: date, end_date: date) -> tuple[Path, Path]:
        bands = "-".join(self._requested_band_names())
        filename = f"{start_date.isoformat()}_{end_date.isoformat()}_{bands}.json"
        data_path = self._cache_base_dir() / filename
        manifest_path = self._cache_base_dir() / f"{filename}.manifest.json"
        return data_path, manifest_path

    def _integrity_summary(
        self,
        frame: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> dict[str, object]:
        expected_dates = pd.date_range(start_date, end_date, freq="D")
        if "date" not in frame.columns:
            return {
                "complete": False,
                "row_count": len(frame),
                "expected_rows": len(expected_dates),
                "missing_dates": [d.strftime("%Y-%m-%d") for d in expected_dates],
                "duplicate_dates": [],
            }

        dates = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None)
        seen = set(dates.dropna())
        missing = [d.strftime("%Y-%m-%d") for d in expected_dates if d not in seen]
        duplicates = [
            d.strftime("%Y-%m-%d")
            for d in dates[dates.duplicated(keep=False)].dropna().sort_values().unique()
        ]
        return {
            "complete": not missing and not duplicates and len(frame) == len(expected_dates),
            "row_count": len(frame),
            "expected_rows": len(expected_dates),
            "missing_dates": missing,
            "duplicate_dates": duplicates,
        }

    def _build_manifest(
        self,
        frame: pd.DataFrame,
        start_date: date,
        end_date: date,
        selected_version: str | None,
    ) -> dict[str, object]:
        integrity = self._integrity_summary(frame, start_date, end_date)
        return {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "dataset": "nex_gddp_xee",
            "model": self.model,
            "scenario": self.scenario,
            "selected_version": selected_version,
            "lat": self.location_coord[0],
            "lon": self.location_coord[1],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "bands": self._requested_band_names(),
            "integrity": integrity,
        }

    def _write_chunk_cache(
        self,
        frame: pd.DataFrame,
        manifest: dict[str, object],
        data_path: Path,
        manifest_path: Path,
    ) -> None:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        temp_data = data_path.with_suffix(data_path.suffix + ".part")
        temp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".part")

        with temp_data.open("w", encoding="utf-8") as handle:
            handle.write(frame.to_json(orient="records", date_format="iso", indent=2))
        with temp_manifest.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

        os.replace(temp_data, data_path)
        os.replace(temp_manifest, manifest_path)

    def _read_chunk_cache(self, data_path: Path) -> pd.DataFrame:
        frame = pd.read_json(data_path)
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
        return frame

    def _slice_frame_to_dates(
        self,
        frame: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        if frame.empty or "date" not in frame.columns:
            return frame.copy()
        out = frame.copy()
        out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
        mask = (
            (out["date"] >= pd.Timestamp(start_date))
            & (out["date"] <= pd.Timestamp(end_date))
        )
        return out.loc[mask].sort_values("date").reset_index(drop=True)

    def _load_valid_cached_chunk(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
        data_path, manifest_path = self._cache_paths(start_date, end_date)
        partial_paths = [data_path.with_suffix(data_path.suffix + ".part"), manifest_path.with_suffix(manifest_path.suffix + ".part")]
        if any(path.exists() for path in partial_paths):
            self._log_progress(
                f"Ignoring stale partial cache for {start_date}..{end_date}."
            )

        if self.refresh_cache or not data_path.exists() or not manifest_path.exists():
            return None, None

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._log_progress(f"Cache manifest unreadable for {start_date}..{end_date}; refetching.")
            return None, None

        if not manifest.get("integrity", {}).get("complete", False):
            self._log_progress(f"Cache manifest marked incomplete for {start_date}..{end_date}; refetching.")
            return None, None

        frame = self._read_chunk_cache(data_path)
        integrity = self._integrity_summary(frame, start_date, end_date)
        if not integrity["complete"]:
            self._log_progress(f"Cache integrity failed for {start_date}..{end_date}; refetching.")
            return None, None
        return frame, manifest

    def _load_valid_covering_cached_chunk(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
        if self.refresh_cache:
            return None, None

        base_dir = self._cache_base_dir()
        if not base_dir.exists():
            return None, None

        candidates: list[tuple[date, date, Path]] = []
        for manifest_path in base_dir.glob("*.manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not manifest.get("integrity", {}).get("complete", False):
                continue
            try:
                cached_start = date.fromisoformat(manifest["start_date"])
                cached_end = date.fromisoformat(manifest["end_date"])
            except (KeyError, ValueError):
                continue
            if cached_start <= start_date and cached_end >= end_date:
                candidates.append((cached_start, cached_end, manifest_path))

        if not candidates:
            return None, None

        candidates.sort(key=lambda item: ((item[1] - item[0]).days, item[0], item[1]))
        cached_start, cached_end, _ = candidates[0]
        frame, manifest = self._load_valid_cached_chunk(cached_start, cached_end)
        if frame is None or manifest is None:
            return None, None

        sliced = self._slice_frame_to_dates(frame, start_date, end_date)
        integrity = self._integrity_summary(sliced, start_date, end_date)
        if not integrity["complete"]:
            return None, None
        return sliced, {
            "selected_version": manifest.get("selected_version"),
            "derived_from_covering_cache": True,
            "integrity": integrity,
            "covering_start_date": cached_start.isoformat(),
            "covering_end_date": cached_end.isoformat(),
        }

    def _load_valid_cached_annual_cover(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
        if self.refresh_cache:
            return None, None

        annual_frames = []
        annual_manifests = []
        for year in range(start_date.year, end_date.year + 1):
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            frame, manifest = self._load_valid_cached_chunk(year_start, year_end)
            if frame is None or manifest is None:
                return None, None
            annual_frames.append(frame)
            annual_manifests.append(manifest)

        combined = pd.concat(annual_frames, ignore_index=True)
        combined = (
            combined.drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .reset_index(drop=True)
        )
        sliced = self._slice_frame_to_dates(combined, start_date, end_date)
        integrity = self._integrity_summary(sliced, start_date, end_date)
        if not integrity["complete"]:
            return None, None

        versions = sorted(
            {
                manifest.get("selected_version")
                for manifest in annual_manifests
                if manifest.get("selected_version")
            },
            key=_version_sort_key,
        )
        return sliced, {
            "selected_version": ",".join(versions) if versions else None,
            "derived_from_annual_cache": True,
            "integrity": integrity,
            "source_years": [year for year in range(start_date.year, end_date.year + 1)],
        }

    def _normalize_units(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "pr" in frame.columns:
            frame["pr"] = frame["pr"] * SECONDS_PER_DAY
        for column in ("tasmin", "tasmax"):
            if column in frame.columns:
                frame[column] = frame[column] - 273.15
        return frame

    def _fetch_single_chunk(
        self,
        ee_module,
        xr_module,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, str | None]:
        collection, selected_version = self._build_collection(ee_module, start_date, end_date)
        dataset = self._open_dataset(xr_module, collection)
        frame = self._dataset_to_frame(dataset, start_date, end_date)
        frame = self._normalize_units(frame)
        return frame, selected_version

    def _fetch_chunk_with_resilience(
        self,
        ee_module,
        xr_module,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, str | None]:
        span_days = (end_date - start_date).days + 1
        last_error = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return self._fetch_single_chunk(ee_module, xr_module, start_date, end_date)
            except Exception as err:  # pragma: no cover - exercised via helper tests
                last_error = err
                if _is_chunk_overflow_error(err) and span_days > MIN_CHUNK_DAYS:
                    midpoint = start_date + timedelta(days=(span_days // 2) - 1)
                    self._log_progress(
                        f"Chunk {start_date}..{end_date} overflowed; splitting at {midpoint}."
                    )
                    left_frame, left_version = self._fetch_chunk_with_resilience(
                        ee_module,
                        xr_module,
                        start_date,
                        midpoint,
                    )
                    right_frame, right_version = self._fetch_chunk_with_resilience(
                        ee_module,
                        xr_module,
                        midpoint + timedelta(days=1),
                        end_date,
                    )
                    version = left_version or right_version
                    return pd.concat([left_frame, right_frame], ignore_index=True), version

                if _is_retryable_ee_error(err) and attempt < self.retry_attempts:
                    delay = DEFAULT_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    self._log_progress(
                        f"Transient NEX-GDDP fetch error on {start_date}..{end_date} "
                        f"(attempt {attempt}/{self.retry_attempts}): {err}. "
                        f"Retrying in {delay:.1f}s."
                    )
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    def _fetch_or_load_chunk(
        self,
        ee_module,
        xr_module,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        cached_frame, cached_manifest = self._load_valid_cached_chunk(start_date, end_date)
        if cached_frame is not None and cached_manifest is not None:
            self._log_progress(f"Cache hit for {start_date}..{end_date}.")
            return cached_frame, cached_manifest

        covering_frame, covering_manifest = self._load_valid_covering_cached_chunk(start_date, end_date)
        if covering_frame is not None and covering_manifest is not None:
            self._log_progress(
                f"Cache slice hit for {start_date}..{end_date} from covering cache "
                f"{covering_manifest['covering_start_date']}..{covering_manifest['covering_end_date']}."
            )
            return covering_frame, covering_manifest

        annual_frame, annual_manifest = self._load_valid_cached_annual_cover(start_date, end_date)
        if annual_frame is not None and annual_manifest is not None:
            self._log_progress(
                f"Cache slice hit for {start_date}..{end_date} from annual cache years "
                f"{annual_manifest['source_years']}."
            )
            return annual_frame, annual_manifest

        started = time.perf_counter()
        frame, selected_version = self._fetch_chunk_with_resilience(
            ee_module,
            xr_module,
            start_date,
            end_date,
        )
        manifest = self._build_manifest(frame, start_date, end_date, selected_version)
        data_path, manifest_path = self._cache_paths(start_date, end_date)
        self._write_chunk_cache(frame, manifest, data_path, manifest_path)
        elapsed = time.perf_counter() - started
        self._log_progress(
            f"Fetched {start_date}..{end_date} in {elapsed:.2f}s and saved cache to {data_path}."
        )
        return frame, manifest

    def download_variables(self) -> pd.DataFrame:
        chunks = self._chunk_dates(self.date_from_utc, self.date_to_utc)
        total = len(chunks)
        frames = []
        selected_versions = []
        pending_fetch_chunks: list[tuple[int, date, date]] = []

        self._log_progress(
            f"Starting NEX-GDDP Xee fetch for {self.model}/{self.scenario} "
            f"{self.date_from_utc}..{self.date_to_utc} in {total} chunk(s)."
        )
        self._log_progress(
            f"Cache root: {self._cache_base_dir()} "
            f"(refresh_cache={self.refresh_cache})"
        )

        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            self._log_progress(
                f"{_progress_bar(index - 1, total)} chunk {index}/{total}: "
                f"{chunk_start}..{chunk_end}"
            )
            cached_frame, cached_manifest = self._load_valid_cached_chunk(
                chunk_start,
                chunk_end,
            )
            if cached_frame is not None and cached_manifest is not None:
                self._log_progress(f"Cache hit for {chunk_start}..{chunk_end}.")
                version = cached_manifest.get("selected_version")
                if version:
                    selected_versions.append(version)
                frames.append(cached_frame)
                continue
            covering_frame, covering_manifest = self._load_valid_covering_cached_chunk(
                chunk_start,
                chunk_end,
            )
            if covering_frame is not None and covering_manifest is not None:
                self._log_progress(
                    f"Cache slice hit for {chunk_start}..{chunk_end} from covering cache "
                    f"{covering_manifest['covering_start_date']}..{covering_manifest['covering_end_date']}."
                )
                version = covering_manifest.get("selected_version")
                if version:
                    selected_versions.append(version)
                frames.append(covering_frame)
                continue
            annual_frame, annual_manifest = self._load_valid_cached_annual_cover(
                chunk_start,
                chunk_end,
            )
            if annual_frame is not None and annual_manifest is not None:
                self._log_progress(
                    f"Cache slice hit for {chunk_start}..{chunk_end} from annual cache years "
                    f"{annual_manifest['source_years']}."
                )
                version = annual_manifest.get("selected_version")
                if version:
                    selected_versions.append(version)
                frames.append(annual_frame)
                continue
            pending_fetch_chunks.append((index, chunk_start, chunk_end))

        ee_module = None
        xr_module = None
        if pending_fetch_chunks:
            ee_module, xr_module = _import_xee_stack()
            self._ensure_ee_initialized(ee_module)

        for index, chunk_start, chunk_end in pending_fetch_chunks:
            frame, manifest = self._fetch_or_load_chunk(
                ee_module,
                xr_module,
                chunk_start,
                chunk_end,
            )
            version = manifest.get("selected_version")
            if version:
                selected_versions.append(version)
            frames.append(frame)

        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not frame.empty:
            frame = (
                frame.drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .reset_index(drop=True)
            )

        integrity = self._integrity_summary(frame, self.date_from_utc, self.date_to_utc)
        if not integrity["complete"]:
            raise ValueError(
                "Combined NEX-GDDP cache/fetch output failed integrity check: "
                f"missing_dates={integrity['missing_dates']} "
                f"duplicate_dates={integrity['duplicate_dates']}"
            )

        _warn_on_suspicious_precipitation(
            frame,
            model=self.model,
            scenario=self.scenario,
        )

        self._log_progress(
            f"{_progress_bar(total, total)} completed {total}/{total} chunk(s); "
            f"{len(frame)} daily row(s) ready."
        )
        return frame

    def download_precipitation(self):
        raise NotImplementedError("Use download_variables()")

    def download_temperature(self):
        raise NotImplementedError("Use download_variables()")

    def download_rainfall(self):
        raise NotImplementedError("Use download_variables()")

    def download_windspeed(self):
        raise NotImplementedError("Use download_variables()")

    def download_solar_radiation(self):
        raise NotImplementedError("Use download_variables()")

    def download_humidity(self):
        raise NotImplementedError("Use download_variables()")

    def download_soil_moisture(self):
        raise NotImplementedError("Use download_variables()")
