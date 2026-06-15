"""Package-native many-site NEX-GDDP batch extraction.

This module promotes the proven direct Earth Engine batch path into the
package so NEX-GDDP is no longer confined to analysis-only scripts.
It keeps raw/source semantics aligned with the existing pipeline and can
optionally return transformed or preprocessed data through the same
harmonization layer used elsewhere in the toolkit.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from .multi_site import (
    Site,
    load_sites,
    parse_site_spec,
    safe_site_fragment,
    site_batch_digest,
    site_date_integrity_summary,
)
from .preprocess_data.preprocess_data import preprocess_transformed_data
from .source_data.sources.nex_gddp import AVAILABLE_MODELS
from .source_data.sources.nex_gddp_xee import (
    DEFAULT_DATASET_VERSION,
    DEFAULT_RETRY_ATTEMPTS,
    SECONDS_PER_DAY,
    _canonical_variable_name,
    _coerce_version_filter_value,
    _is_chunk_overflow_error,
    _is_retryable_ee_error,
    _normalize_scenario,
    _progress_bar,
    _resolve_dataset_version,
    _validate_period_against_scenario,
)
from .source_data.sources.xee_common import (
    DEFAULT_EE_OPT_URL,
    format_ee_setup_error,
    infer_ee_project_id,
    initialize_earth_engine as initialize_earth_engine_session,
)
from .source_data.sources.utils.models import ClimateVariable, parse_variable_token
from .source_data.sources.utils.settings import Settings, set_logging
from .transform_data.transform_data import default_variables, load_variable_mappings

set_logging()
logger = logging.getLogger(__name__)

VALID_STAGES = ("raw", "transformed", "preprocessed")
DEFAULT_BATCH_CACHE_DIR = "outputs/cache/nex_gddp_batch"
DEFAULT_POINT_BATCH_SIZE = 25
DEFAULT_TARGET_ELEMENTS_PER_BATCH = 4500
DEFAULT_TILE_SCALE = 1.0
DEFAULT_CHUNK_DAYS = 365
CACHE_SCHEMA_VERSION = "v1"
MIN_CHUNK_DAYS = 1
MIN_SITE_BATCH_SIZE = 1


def _log_progress(message: str, verbose: bool) -> None:
    if verbose:
        logger.info(message)


def _import_ee():
    try:
        return importlib.import_module("ee")
    except ImportError as exc:
        raise ImportError(
            "nex_gddp_batch requires the optional dependency 'earthengine-api'."
        ) from exc


def _requested_band_names(settings: Settings, variables) -> list[str]:
    active_variables = variables or default_variables()
    bands = []
    for variable in active_variables:
        variable_name = _canonical_variable_name(variable)
        band_name = settings.nex_gddp.variable.get_band(variable_name)
        if band_name:
            bands.append(band_name)

    ordered = []
    for band in bands:
        if band not in ordered:
            ordered.append(band)

    if not ordered:
        raise ValueError("No NEX-GDDP-compatible variables were requested.")
    return ordered


def chunk_dates(date_from: date, date_to: date, chunk_days: int) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cursor = date_from
    while cursor <= date_to:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), date_to)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def chunk_sites(sites: list[Site], batch_size: int) -> list[list[Site]]:
    return [sites[i : i + batch_size] for i in range(0, len(sites), batch_size)]


def infer_chunk_days(
    *,
    explicit_chunk_days: int | None,
    point_batch_size: int,
    target_elements_per_batch: int,
) -> int:
    if explicit_chunk_days is not None:
        return explicit_chunk_days
    if point_batch_size <= 0:
        raise ValueError("point_batch_size must be positive")
    if target_elements_per_batch <= 0:
        raise ValueError("target_elements_per_batch must be positive")
    return max(1, target_elements_per_batch // point_batch_size)


def initialize_earth_engine(
    project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
):
    ee_module = _import_ee()
    resolved_project_id = infer_ee_project_id(project_id)
    initialize_earth_engine_session(
        ee_module,
        project_id=resolved_project_id,
        ee_opt_url=ee_opt_url,
    )
    return ee_module, resolved_project_id


def build_points(ee_module, site_batch: list[Site]):
    features = []
    for site in site_batch:
        feature = ee_module.Feature(
            ee_module.Geometry.Point([site.lon, site.lat]),
            {
                "site": site.name,
                "lat": site.lat,
                "lon": site.lon,
            },
        )
        features.append(feature)
    return ee_module.FeatureCollection(features)


def _site_batch_digest(site_batch: list[Site]) -> str:
    return site_batch_digest(site_batch)


def cache_paths_for_batch(
    *,
    cache_dir: str | Path | None,
    site_batch: list[Site],
    start: date,
    end: date,
    model: str,
    scenario: str,
    bands: list[str],
) -> tuple[Path, Path]:
    digest = _site_batch_digest(site_batch)
    band_fragment = "-".join(bands)
    base = Path(cache_dir or DEFAULT_BATCH_CACHE_DIR) / CACHE_SCHEMA_VERSION / scenario / model
    if len(site_batch) == 1:
        site_fragment = safe_site_fragment(site_batch[0].name)
    else:
        site_fragment = (
            f"{safe_site_fragment(site_batch[0].name)}_to_"
            f"{safe_site_fragment(site_batch[-1].name)}"
        )
    filename = (
        f"{start.isoformat()}_{end.isoformat()}_"
        f"{site_fragment}_sites{len(site_batch)}_{digest}_{band_fragment}.json"
    )
    return base / filename, base / f"{filename}.manifest.json"


def read_cached_batch(path: Path) -> pd.DataFrame:
    frame = pd.read_json(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    return frame


def write_cached_batch(
    data_path: Path,
    manifest_path: Path,
    frame: pd.DataFrame,
    manifest: dict[str, object],
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


def _integrity_summary(
    frame: pd.DataFrame,
    start: date,
    end: date,
    sites: list[Site],
) -> dict[str, object]:
    return site_date_integrity_summary(frame, start, end, sites)


def _build_manifest(
    *,
    frame: pd.DataFrame,
    start: date,
    end: date,
    sites: list[Site],
    model: str,
    scenario: str,
    bands: list[str],
    selected_version: str | None,
) -> dict[str, object]:
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "dataset": "nex_gddp_batch",
        "model": model,
        "scenario": scenario,
        "selected_version": selected_version,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "site_count": len(sites),
        "sites": [site.__dict__ for site in sites],
        "bands": bands,
        "integrity": _integrity_summary(frame, start, end, sites),
    }


def _load_valid_cached_batch(
    data_path: Path,
    manifest_path: Path,
    *,
    start: date,
    end: date,
    sites: list[Site],
    refresh_cache: bool,
    verbose: bool,
) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
    partial_paths = [
        data_path.with_suffix(data_path.suffix + ".part"),
        manifest_path.with_suffix(manifest_path.suffix + ".part"),
    ]
    if any(path.exists() for path in partial_paths):
        _log_progress(f"Ignoring stale partial cache for {start}..{end}.", verbose)

    if refresh_cache or not data_path.exists() or not manifest_path.exists():
        return None, None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _log_progress(f"Batch manifest unreadable for {start}..{end}; refetching.", verbose)
        return None, None

    if not manifest.get("integrity", {}).get("complete", False):
        _log_progress(f"Batch manifest incomplete for {start}..{end}; refetching.", verbose)
        return None, None

    frame = read_cached_batch(data_path)
    integrity = _integrity_summary(frame, start, end, sites)
    if not integrity["complete"]:
        _log_progress(f"Batch cache integrity failed for {start}..{end}; refetching.", verbose)
        return None, None
    return frame, manifest


def _full_site_date_frame(
    frame: pd.DataFrame,
    *,
    sites: list[Site],
    start: date,
    end: date,
    model: str,
    scenario: str,
) -> pd.DataFrame:
    full_dates = pd.date_range(start, end, freq="D")
    site_index = pd.DataFrame(
        [{"site": site.name, "lat": site.lat, "lon": site.lon} for site in sites]
    )
    full_index = (
        site_index.assign(_k=1)
        .merge(pd.DataFrame({"date": full_dates, "_k": 1}), on="_k")
        .drop(columns="_k")
    )

    keep_cols = [
        column
        for column in [
            "site",
            "lat",
            "lon",
            "date",
            "pr",
            "tasmax",
            "tasmin",
            "model",
            "scenario",
        ]
        if column in frame.columns
    ]
    merged = full_index.merge(
        frame[keep_cols],
        on=["site", "lat", "lon", "date"],
        how="left",
    )
    merged["model"] = model
    merged["scenario"] = scenario
    return merged.sort_values(["site", "date"]).reset_index(drop=True)


def fetch_batch(
    *,
    ee_module,
    settings: Settings,
    site_batch: list[Site],
    start: date,
    end: date,
    model: str,
    scenario: str,
    tile_scale: float,
    bands: list[str],
) -> tuple[pd.DataFrame, str | None]:
    points = build_points(ee_module, site_batch)
    collection = (
        ee_module.ImageCollection(settings.nex_gddp.gee_image)
        .filterDate(start.strftime("%Y-%m-%d"), (end + timedelta(days=1)).strftime("%Y-%m-%d"))
        .filter(ee_module.Filter.eq("model", model))
        .filter(ee_module.Filter.eq("scenario", scenario))
    )
    selected_version = _resolve_dataset_version(collection)
    if selected_version:
        collection = collection.filter(
            ee_module.Filter.eq("version", _coerce_version_filter_value(selected_version))
        )
    collection = collection.select(bands)

    def image_to_features(image):
        reduced = image.reduceRegions(
            collection=points,
            reducer=ee_module.Reducer.first(),
            scale=settings.nex_gddp.resolution,
            tileScale=tile_scale,
        )
        return reduced.map(
            lambda feature: feature.set(
                {
                    "date": image.date().format("YYYY-MM-dd"),
                    "model": model,
                    "scenario": scenario,
                }
            )
        )

    flattened = ee_module.FeatureCollection(collection.map(image_to_features).flatten())
    result = flattened.getInfo() or {}
    features = result.get("features", [])
    records = [feature["properties"] for feature in features]
    frame = pd.DataFrame(records)

    if frame.empty:
        return _full_site_date_frame(
            frame,
            sites=site_batch,
            start=start,
            end=end,
            model=model,
            scenario=scenario,
        ), selected_version

    frame["date"] = pd.to_datetime(frame["date"])
    for column in ("pr", "tasmax", "tasmin"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "pr" in frame.columns:
        frame["pr"] = frame["pr"] * SECONDS_PER_DAY
    if "tasmax" in frame.columns:
        frame["tasmax"] = frame["tasmax"] - 273.15
    if "tasmin" in frame.columns:
        frame["tasmin"] = frame["tasmin"] - 273.15

    return (
        _full_site_date_frame(
            frame,
            sites=site_batch,
            start=start,
            end=end,
            model=model,
            scenario=scenario,
        ),
        selected_version,
    )


def _fetch_batch_with_resilience(
    *,
    ee_module,
    settings: Settings,
    site_batch: list[Site],
    start: date,
    end: date,
    model: str,
    scenario: str,
    tile_scale: float,
    bands: list[str],
    retry_attempts: int,
    verbose: bool,
) -> tuple[pd.DataFrame, list[str]]:
    span_days = (end - start).days + 1
    last_error = None

    for attempt in range(1, retry_attempts + 1):
        try:
            frame, selected_version = fetch_batch(
                ee_module=ee_module,
                settings=settings,
                site_batch=site_batch,
                start=start,
                end=end,
                model=model,
                scenario=scenario,
                tile_scale=tile_scale,
                bands=bands,
            )
            versions = [selected_version] if selected_version else []
            return frame, versions
        except Exception as err:  # pragma: no cover - EE failure path
            last_error = err
            if _is_chunk_overflow_error(err) and span_days > MIN_CHUNK_DAYS:
                midpoint = start + timedelta(days=(span_days // 2) - 1)
                _log_progress(
                    f"Batch {start}..{end} overflowed; splitting at {midpoint}.",
                    verbose,
                )
                left_frame, left_versions = _fetch_batch_with_resilience(
                    ee_module=ee_module,
                    settings=settings,
                    site_batch=site_batch,
                    start=start,
                    end=midpoint,
                    model=model,
                    scenario=scenario,
                    tile_scale=tile_scale,
                    bands=bands,
                    retry_attempts=retry_attempts,
                    verbose=verbose,
                )
                right_frame, right_versions = _fetch_batch_with_resilience(
                    ee_module=ee_module,
                    settings=settings,
                    site_batch=site_batch,
                    start=midpoint + timedelta(days=1),
                    end=end,
                    model=model,
                    scenario=scenario,
                    tile_scale=tile_scale,
                    bands=bands,
                    retry_attempts=retry_attempts,
                    verbose=verbose,
                )
                combined = pd.concat([left_frame, right_frame], ignore_index=True)
                return combined, [*left_versions, *right_versions]

            if _is_retryable_ee_error(err) and attempt < retry_attempts:
                delay = 2.0 * (2 ** (attempt - 1))
                _log_progress(
                    f"Transient batch fetch error on {start}..{end} "
                    f"(attempt {attempt}/{retry_attempts}): {err}. "
                    f"Retrying in {delay:.1f}s.",
                    verbose,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(
                f"NEX-GDDP batch fetch failed for model={model} scenario={scenario} "
                f"start={start} end={end} sites={len(site_batch)}"
            ) from err

    raise last_error


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    summary = (
        frame.groupby(["site", "lat", "lon", "model", "scenario"], as_index=False)
        .agg(
            days=("date", "count"),
            precip_mean_mm_day=("pr", "mean"),
            precip_total_mm=("pr", "sum"),
            tasmax_mean_c=("tasmax", "mean"),
            tasmin_mean_c=("tasmin", "mean"),
        )
    )
    for column in ["precip_mean_mm_day", "precip_total_mm", "tasmax_mean_c", "tasmin_mean_c"]:
        summary[column] = summary[column].round(3)
    return summary


def save_frame(frame: pd.DataFrame, path: str | os.PathLike) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        target.write_text(
            frame.to_json(orient="records", date_format="iso", indent=2),
            encoding="utf-8",
        )
    else:
        frame.to_csv(target, index=False)


def _transform_batch_frame(raw_df: pd.DataFrame) -> pd.DataFrame:
    mappings = load_variable_mappings().get("nex_gddp", {})
    if not mappings:
        raise ValueError("No variable mappings found for source 'nex_gddp'")
    return raw_df.rename(columns=mappings)


def run_batch_extraction(
    *,
    sites: list[Site],
    date_from: date,
    date_to: date,
    settings: Settings | None = None,
    variables=None,
    model: str = "MRI-ESM2-0",
    scenario: str = "ssp245",
    ee_project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
    point_batch_size: int = DEFAULT_POINT_BATCH_SIZE,
    chunk_days: int | None = None,
    target_elements_per_batch: int = DEFAULT_TARGET_ELEMENTS_PER_BATCH,
    tile_scale: float = DEFAULT_TILE_SCALE,
    cache_dir: str | os.PathLike | None = None,
    refresh_cache: bool = False,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    verbose: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not sites:
        raise ValueError("At least one site is required.")
    if model not in AVAILABLE_MODELS:
        raise ValueError(f"Invalid model '{model}'. Valid models: {', '.join(AVAILABLE_MODELS)}")

    settings = settings or Settings.load()
    scenario = _normalize_scenario(scenario)
    _validate_period_against_scenario(scenario, date_from, date_to)

    if point_batch_size < MIN_SITE_BATCH_SIZE:
        raise ValueError("point_batch_size must be positive")

    bands = _requested_band_names(settings, variables)
    site_batches = chunk_sites(sites, point_batch_size)
    largest_site_batch = max(len(batch) for batch in site_batches)
    effective_chunk_days = infer_chunk_days(
        explicit_chunk_days=chunk_days,
        point_batch_size=largest_site_batch,
        target_elements_per_batch=target_elements_per_batch,
    )
    date_chunks = chunk_dates(date_from, date_to, effective_chunk_days)
    cache_root = Path(cache_dir or DEFAULT_BATCH_CACHE_DIR)

    ee_module = None
    frames: list[pd.DataFrame] = []
    batch_stats: list[dict[str, object]] = []
    selected_versions: list[str] = []
    total_batches = len(date_chunks) * len(site_batches)
    completed_batches = 0

    _log_progress(
        f"Starting NEX-GDDP batch fetch for {model}/{scenario} "
        f"{date_from}..{date_to} across {len(sites)} site(s), "
        f"{len(date_chunks)} date chunk(s), {len(site_batches)} site batch(es).",
        verbose,
    )
    _log_progress(
        f"Cache root: {cache_root} (refresh_cache={refresh_cache})",
        verbose,
    )

    for date_start, date_end in date_chunks:
        for site_batch in site_batches:
            completed_batches += 1
            batch_label = (
                f"{date_start}:{date_end} | "
                f"{site_batch[0].name}..{site_batch[-1].name} ({len(site_batch)} sites)"
            )
            _log_progress(
                f"{_progress_bar(completed_batches - 1, total_batches)} "
                f"batch {completed_batches}/{total_batches}: {batch_label}",
                verbose,
            )

            data_path, manifest_path = cache_paths_for_batch(
                cache_dir=cache_root,
                site_batch=site_batch,
                start=date_start,
                end=date_end,
                model=model,
                scenario=scenario,
                bands=bands,
            )
            batch_start = time.perf_counter()

            cached_frame, cached_manifest = _load_valid_cached_batch(
                data_path,
                manifest_path,
                start=date_start,
                end=date_end,
                sites=site_batch,
                refresh_cache=refresh_cache,
                verbose=verbose,
            )
            if cached_frame is not None and cached_manifest is not None:
                frames.append(cached_frame)
                version = cached_manifest.get("selected_version")
                if version:
                    selected_versions.append(version)
                elapsed = time.perf_counter() - batch_start
                batch_stats.append(
                    {
                        "date_start": date_start,
                        "date_end": date_end,
                        "site_count": len(site_batch),
                        "rows": len(cached_frame),
                        "seconds": round(elapsed, 2),
                        "label": batch_label,
                        "cache_hit": True,
                        "cache_path": str(data_path),
                    }
                )
                _log_progress(
                    f"Cache hit for {batch_label} in {elapsed:.2f}s.",
                    verbose,
                )
                continue

            if ee_module is None:
                ee_module, resolved_project_id = initialize_earth_engine(
                    project_id=ee_project_id,
                    ee_opt_url=ee_opt_url,
                )
                _log_progress(f"Earth Engine initialized for project {resolved_project_id}.", verbose)

            frame, versions = _fetch_batch_with_resilience(
                ee_module=ee_module,
                settings=settings,
                site_batch=site_batch,
                start=date_start,
                end=date_end,
                model=model,
                scenario=scenario,
                tile_scale=tile_scale,
                bands=bands,
                retry_attempts=max(1, retry_attempts),
                verbose=verbose,
            )
            version = versions[-1] if versions else None
            manifest = _build_manifest(
                frame=frame,
                start=date_start,
                end=date_end,
                sites=site_batch,
                model=model,
                scenario=scenario,
                bands=bands,
                selected_version=version,
            )
            write_cached_batch(data_path, manifest_path, frame, manifest)

            frames.append(frame)
            selected_versions.extend(versions)
            elapsed = time.perf_counter() - batch_start
            batch_stats.append(
                {
                    "date_start": date_start,
                    "date_end": date_end,
                    "site_count": len(site_batch),
                    "rows": len(frame),
                    "seconds": round(elapsed, 2),
                    "label": batch_label,
                    "cache_hit": False,
                    "cache_path": str(data_path),
                }
            )
            _log_progress(
                f"Fetched {batch_label} in {elapsed:.2f}s and saved cache to {data_path}.",
                verbose,
            )

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not result.empty:
        result = (
            result.drop_duplicates(subset=["site", "lat", "lon", "date"], keep="last")
            .sort_values(["site", "date", "model", "scenario"])
            .reset_index(drop=True)
        )

    integrity = _integrity_summary(result, date_from, date_to, sites)
    if not integrity["complete"]:
        raise ValueError(
            "Combined NEX-GDDP batch output failed integrity check: "
            f"missing_site_dates={len(integrity['missing_site_dates'])} "
            f"duplicate_site_dates={len(integrity['duplicate_site_dates'])}"
        )

    unique_versions = sorted({version for version in selected_versions if version})
    if unique_versions and DEFAULT_DATASET_VERSION not in unique_versions:
        logger.warning(
            "Preferred NEX-GDDP version %s unavailable; using %s for model=%s scenario=%s start=%s end=%s",
            DEFAULT_DATASET_VERSION,
            ",".join(unique_versions),
            model,
            scenario,
            date_from,
            date_to,
        )

    summary = summarize(result)
    manifest_df = pd.DataFrame(batch_stats)
    _log_progress(
        f"{_progress_bar(total_batches, total_batches)} completed {total_batches}/{total_batches} "
        f"batch(es); {len(result)} row(s) ready.",
        verbose,
    )
    return result, summary, manifest_df


def fetch_nex_gddp_batch_data(
    *,
    sites: Iterable[Site | dict | tuple] | None = None,
    sites_csv: str | os.PathLike | None = None,
    variables=None,
    date_from: date | None = None,
    date_to: date | None = None,
    settings: Settings | None = None,
    model: str = "MRI-ESM2-0",
    scenario: str = "ssp245",
    stage: str = "preprocessed",
    verbose: bool = True,
    cache_dir: str | os.PathLike | None = None,
    refresh_cache: bool = False,
    ee_project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
    point_batch_size: int = DEFAULT_POINT_BATCH_SIZE,
    chunk_days: int | None = None,
    target_elements_per_batch: int = DEFAULT_TARGET_ELEMENTS_PER_BATCH,
    tile_scale: float = DEFAULT_TILE_SCALE,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if stage not in VALID_STAGES:
        raise ValueError(
            f"Invalid stage '{stage}'. Must be one of: {', '.join(VALID_STAGES)}"
        )
    if date_from is None or date_to is None:
        raise ValueError("date_from and date_to are required.")

    resolved_sites = load_sites(sites=sites, sites_csv=sites_csv)
    raw_df, summary_df, manifest_df = run_batch_extraction(
        sites=resolved_sites,
        date_from=date_from,
        date_to=date_to,
        settings=settings,
        variables=variables,
        model=model,
        scenario=scenario,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        point_batch_size=point_batch_size,
        chunk_days=chunk_days,
        target_elements_per_batch=target_elements_per_batch,
        tile_scale=tile_scale,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        retry_attempts=retry_attempts,
        verbose=verbose,
    )

    if stage == "raw":
        return raw_df, summary_df, manifest_df

    transformed_df = _transform_batch_frame(raw_df)
    if stage == "transformed":
        return transformed_df, summary_df, manifest_df

    preprocessed_df = preprocess_transformed_data(
        transformed_df=transformed_df,
        source="nex_gddp",
        group_columns=["site", "lat", "lon", "model", "scenario"],
        verbose=verbose,
    )
    return preprocessed_df, summary_df, manifest_df


def _parse_variables(raw: str | None):
    if not raw:
        return None
    resolved = []
    for token in raw.split(","):
        variable = parse_variable_token(token)
        if not isinstance(variable, ClimateVariable):
            raise ValueError(f"Unknown climate variable '{token.strip()}'")
        resolved.append(variable)
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package-native many-site NEX-GDDP extraction."
    )
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help='Repeatable site spec: "name,lat,lon"',
    )
    parser.add_argument("--sites-csv", default=None)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--model", default="MRI-ESM2-0")
    parser.add_argument("--scenario", default="ssp245")
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--cache-dir", default=DEFAULT_BATCH_CACHE_DIR)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--point-batch-size", type=int, default=DEFAULT_POINT_BATCH_SIZE)
    parser.add_argument("--chunk-days", type=int, default=None)
    parser.add_argument(
        "--target-elements-per-batch",
        type=int,
        default=DEFAULT_TARGET_ELEMENTS_PER_BATCH,
    )
    parser.add_argument("--tile-scale", type=float, default=DEFAULT_TILE_SCALE)
    parser.add_argument("--retry-attempts", type=int, default=DEFAULT_RETRY_ATTEMPTS)
    parser.add_argument("--variables", default=None)
    parser.add_argument("--stage", choices=VALID_STAGES, default="preprocessed")
    parser.add_argument("--output", default=None)
    parser.add_argument("--summary-output", default=None)
    parser.add_argument("--manifest-output", default=None)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        variables = _parse_variables(args.variables)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        sites = [parse_site_spec(raw) for raw in args.site]
        data_df, summary_df, manifest_df = fetch_nex_gddp_batch_data(
            sites=sites,
            sites_csv=args.sites_csv,
            variables=variables,
            date_from=args.start,
            date_to=args.end,
            model=args.model,
            scenario=args.scenario,
            stage=args.stage,
            verbose=not args.quiet,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            ee_project_id=args.project_id,
            point_batch_size=args.point_batch_size,
            chunk_days=args.chunk_days,
            target_elements_per_batch=args.target_elements_per_batch,
            tile_scale=args.tile_scale,
            retry_attempts=args.retry_attempts,
        )
    except Exception as exc:
        print(f"Error: {format_ee_setup_error(exc)}")
        return 1

    if args.output:
        save_frame(data_df, args.output)
        print(f"Saved data output to {args.output}")
    else:
        print(data_df)

    if args.summary_output:
        save_frame(summary_df, args.summary_output)
        print(f"Saved summary output to {args.summary_output}")

    if args.manifest_output:
        save_frame(manifest_df, args.manifest_output)
        print(f"Saved manifest output to {args.manifest_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
