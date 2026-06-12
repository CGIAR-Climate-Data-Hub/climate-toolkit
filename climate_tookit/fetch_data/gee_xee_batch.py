"""Package-native many-site GEE extraction using Xee.

This module provides shared Xee-backed batch fetching for historical and
non-NEX Earth Engine sources so projection and historical pipelines can use
same Python stack and common multi-site contract.
"""

from __future__ import annotations

import argparse
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
    site_date_integrity_summary,
)
from .preprocess_data.preprocess_data import preprocess_transformed_data
from .source_data.sources.utils.models import ClimateDataset
from .source_data.sources.utils.settings import Settings, set_logging
from .source_data.sources.xee_common import (
    DEFAULT_EE_OPT_URL,
    format_ee_setup_error,
    import_xee_stack,
    initialize_earth_engine,
    is_chunk_overflow_error,
    is_retryable_ee_error,
    open_point_dataset,
    point_dataset_to_frame,
    progress_bar,
)
from .transform_data.transform_data import default_variables, load_variable_mappings

set_logging()
logger = logging.getLogger(__name__)

VALID_STAGES = ("raw", "transformed", "preprocessed")
DEFAULT_BATCH_CACHE_DIR = "outputs/cache/gee_xee_batch"
DEFAULT_CHUNK_DAYS = 365
DEFAULT_RETRY_ATTEMPTS = 4
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
CACHE_SCHEMA_VERSION = "v1"

SUPPORTED_GEE_XEE_BATCH_SOURCES = {
    ClimateDataset.agera_5,
    ClimateDataset.era_5,
    ClimateDataset.terraclimate,
    ClimateDataset.imerg,
    ClimateDataset.chirps,
    ClimateDataset.chirts,
    ClimateDataset.cmip_6,
}

DAILY_AGG_REDUCER = {
    "NASA/GPM_L3/IMERG_V07": "sum",
    "NASA/GPM_L3/IMERG_V06": "sum",
    "ECMWF/ERA5_LAND/HOURLY": "mean",
}


def _log_progress(message: str, verbose: bool) -> None:
    if verbose:
        logger.info(message)


def _coerce_source(source: str | ClimateDataset) -> ClimateDataset:
    if isinstance(source, ClimateDataset):
        dataset = source
    else:
        try:
            dataset = ClimateDataset[source]
        except KeyError as exc:
            valid = ", ".join(item.name for item in SUPPORTED_GEE_XEE_BATCH_SOURCES)
            raise ValueError(
                f"Unsupported source '{source}'. Valid Xee batch sources: {valid}"
            ) from exc

    if dataset not in SUPPORTED_GEE_XEE_BATCH_SOURCES:
        valid = ", ".join(item.name for item in SUPPORTED_GEE_XEE_BATCH_SOURCES)
        raise ValueError(
            f"Source '{dataset.name}' is not currently supported by gee_xee_batch. "
            f"Valid sources: {valid}"
        )
    return dataset


def _requested_band_names(data_settings, variables) -> list[str]:
    active_variables = variables or default_variables()
    bands = []
    for variable in active_variables:
        variable_name = getattr(variable, "name", str(variable).split(".")[-1])
        band_name = data_settings.variable.get_band(variable_name)
        if band_name:
            bands.append(band_name)

    ordered = []
    for band in bands:
        if band not in ordered:
            ordered.append(band)

    if not ordered:
        raise ValueError("No source-compatible variables were requested.")
    return ordered


def _scale_band_columns(frame: pd.DataFrame, data_settings, variables) -> pd.DataFrame:
    scaled = frame.copy()
    for variable in variables:
        variable_name = getattr(variable, "name", str(variable).split(".")[-1])
        band_name = data_settings.variable.get_band(variable_name)
        variable_meta = getattr(data_settings.variable, variable_name, None)
        if band_name in scaled.columns and variable_meta is not None:
            scale = getattr(variable_meta, "scale", 1.0)
            scaled[band_name] = scaled[band_name] * scale
    return scaled


def _daily_aggregated_collection(ee_module, image_name, start, end, point, bands):
    reducer_name = DAILY_AGG_REDUCER.get(image_name, "mean")
    n_days = end.difference(start, "day").floor()
    days_seq = ee_module.List.sequence(0, n_days.subtract(1))
    raw = (
        ee_module.ImageCollection(image_name)
        .filterDate(start, end)
        .filterBounds(point)
    )
    if bands:
        raw = raw.select(bands)

    def daily_image(day_offset):
        day_offset = ee_module.Number(day_offset)
        day_start = start.advance(day_offset, "day")
        day_end = day_start.advance(1, "day")
        day_slice = raw.filterDate(day_start, day_end)
        aggregate = day_slice.sum() if reducer_name == "sum" else day_slice.mean()
        return aggregate.set("system:time_start", day_start.millis())

    return ee_module.ImageCollection.fromImages(days_seq.map(daily_image))


def _collection_and_expected_dates(
    *,
    ee_module,
    data_settings,
    site: Site,
    start_date: date,
    end_date: date,
    bands: list[str],
):
    point = ee_module.Geometry.Point([site.lon, site.lat])
    image_name = data_settings.gee_image
    cadence = data_settings.cadence

    if cadence == "monthly":
        chunk_start = date(start_date.year, start_date.month, 1)
        chunk_end = date(end_date.year, end_date.month, 1)
        ee_start = ee_module.Date(chunk_start.isoformat())
        ee_end = ee_module.Date((chunk_end + timedelta(days=32)).replace(day=1).isoformat())
        collection = (
            ee_module.ImageCollection(image_name)
            .filterDate(ee_start, ee_end)
            .filterBounds(point)
            .select(bands)
        )
        expected_dates = pd.date_range(chunk_start, chunk_end, freq="MS")
        return collection, expected_dates, chunk_start, chunk_end, "MS"

    chunk_start = start_date
    chunk_end = end_date
    ee_start = ee_module.Date(chunk_start.isoformat())
    ee_end = ee_module.Date((chunk_end + timedelta(days=1)).isoformat())

    if image_name in DAILY_AGG_REDUCER:
        collection = _daily_aggregated_collection(
            ee_module,
            image_name,
            ee_start,
            ee_end,
            point,
            bands,
        )
    else:
        collection = (
            ee_module.ImageCollection(image_name)
            .filterDate(ee_start, ee_end)
            .filterBounds(point)
            .select(bands)
        )
    expected_dates = pd.date_range(chunk_start, chunk_end, freq="D")
    return collection, expected_dates, chunk_start, chunk_end, "D"


def _cache_paths(
    *,
    cache_dir: str | Path | None,
    source: ClimateDataset,
    site: Site,
    start: date,
    end: date,
    bands: list[str],
) -> tuple[Path, Path]:
    band_fragment = "-".join(bands)
    site_fragment = safe_site_fragment(site.name)
    base = (
        Path(cache_dir or DEFAULT_BATCH_CACHE_DIR)
        / CACHE_SCHEMA_VERSION
        / source.name
        / site_fragment
    )
    filename = (
        f"{start.isoformat()}_{end.isoformat()}_"
        f"{band_fragment}.json"
    )
    data_path = base / filename
    manifest_path = base / f"{filename}.manifest.json"
    return data_path, manifest_path


def _read_cached_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_json(path)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    return frame


def _write_cached_frame(
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
    *,
    start: date,
    end: date,
    site: Site,
    expected_dates: pd.DatetimeIndex,
) -> dict[str, object]:
    return site_date_integrity_summary(
        frame,
        start=start,
        end=end,
        sites=[site],
        expected_dates=expected_dates,
    )


def _build_manifest(
    *,
    frame: pd.DataFrame,
    source: ClimateDataset,
    site: Site,
    bands: list[str],
    start: date,
    end: date,
    expected_dates: pd.DatetimeIndex,
) -> dict[str, object]:
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "dataset": "gee_xee_batch",
        "source": source.name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "site_count": 1,
        "sites": [site.__dict__],
        "bands": bands,
        "integrity": _integrity_summary(
            frame,
            start=start,
            end=end,
            site=site,
            expected_dates=expected_dates,
        ),
    }


def _load_valid_cached_chunk(
    data_path: Path,
    manifest_path: Path,
    *,
    start: date,
    end: date,
    site: Site,
    expected_dates: pd.DatetimeIndex,
    refresh_cache: bool,
    verbose: bool,
) -> tuple[pd.DataFrame | None, dict[str, object] | None]:
    if refresh_cache or not data_path.exists() or not manifest_path.exists():
        return None, None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _log_progress(
            f"Cache manifest unreadable for {site.name} {start}..{end}; refetching.",
            verbose,
        )
        return None, None

    if not manifest.get("integrity", {}).get("complete", False):
        _log_progress(
            f"Cache manifest incomplete for {site.name} {start}..{end}; refetching.",
            verbose,
        )
        return None, None

    frame = _read_cached_frame(data_path)
    integrity = _integrity_summary(
        frame,
        start=start,
        end=end,
        site=site,
        expected_dates=expected_dates,
    )
    if not integrity.get("complete", False):
        _log_progress(
            f"Cached data incomplete for {site.name} {start}..{end}; refetching.",
            verbose,
        )
        return None, None
    return frame, manifest


def _fetch_site_chunk(
    *,
    ee_module,
    xr_module,
    source: ClimateDataset,
    data_settings,
    site: Site,
    variables,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    bands = _requested_band_names(data_settings, variables)
    collection, expected_dates, normalized_start, normalized_end, freq = (
        _collection_and_expected_dates(
            ee_module=ee_module,
            data_settings=data_settings,
            site=site,
            start_date=start_date,
            end_date=end_date,
            bands=bands,
        )
    )
    dataset = open_point_dataset(
        xr_module,
        collection,
        lon=site.lon,
        lat=site.lat,
        pixel_size_meters=data_settings.resolution,
    )
    frame = point_dataset_to_frame(
        dataset,
        start_date=normalized_start,
        end_date=normalized_end,
        band_names=bands,
        time_coord="time",
        output_date_column="date",
        freq=freq,
    )
    frame = _scale_band_columns(frame, data_settings, variables)
    frame.insert(0, "lon", site.lon)
    frame.insert(0, "lat", site.lat)
    frame.insert(0, "site", site.name)
    return frame, expected_dates


def _fetch_with_retries(
    *,
    ee_module,
    xr_module,
    source: ClimateDataset,
    data_settings,
    site: Site,
    variables,
    start_date: date,
    end_date: date,
    retry_attempts: int,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    attempt = 0
    while True:
        attempt += 1
        try:
            return _fetch_site_chunk(
                ee_module=ee_module,
                xr_module=xr_module,
                source=source,
                data_settings=data_settings,
                site=site,
                variables=variables,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            if is_chunk_overflow_error(exc):
                raise
            if attempt >= retry_attempts or not is_retryable_ee_error(exc):
                raise
            time.sleep(DEFAULT_RETRY_BACKOFF_SECONDS * attempt)


def _chunk_dates(data_settings, date_from: date, date_to: date, chunk_days: int) -> list[tuple[date, date]]:
    if data_settings.cadence == "monthly":
        return [(date_from, date_to)]

    chunks: list[tuple[date, date]] = []
    cursor = date_from
    while cursor <= date_to:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), date_to)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _transform_batch_frame(raw_df: pd.DataFrame, source: ClimateDataset) -> pd.DataFrame:
    mappings = load_variable_mappings().get(source.name, {})
    if not mappings:
        raise ValueError(f"No variable mappings found for source '{source.name}'")
    return raw_df.rename(columns=mappings)


def _summary_frame(frame: pd.DataFrame, source: ClimateDataset) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=["source", "site", "lat", "lon", "row_count", "start_date", "end_date"]
        )
    summary = (
        frame.groupby(["site", "lat", "lon"], as_index=False)
        .agg(
            row_count=("date", "count"),
            start_date=("date", "min"),
            end_date=("date", "max"),
        )
    )
    summary.insert(0, "source", source.name)
    return summary


def run_gee_xee_batch_extraction(
    *,
    source: str | ClimateDataset,
    sites: list[Site],
    variables=None,
    date_from: date,
    date_to: date,
    settings: Settings | None = None,
    cache_dir: str | Path | None = DEFAULT_BATCH_CACHE_DIR,
    refresh_cache: bool = False,
    verbose: bool = True,
    ee_project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dataset = _coerce_source(source)
    settings = settings or Settings.load()
    data_settings = getattr(settings, dataset.name)
    active_variables = variables or default_variables()
    if not sites:
        raise ValueError("At least one site is required.")

    chunks = _chunk_dates(data_settings, date_from, date_to, chunk_days)
    total = len(sites) * len(chunks)
    completed = 0
    bands = _requested_band_names(data_settings, active_variables)
    frames: list[pd.DataFrame] = []
    manifest_rows: list[dict[str, object]] = []

    _log_progress(
        f"Starting GEE Xee batch fetch for {dataset.name} "
        f"{date_from}..{date_to} across {len(sites)} site(s) and {len(chunks)} chunk(s).",
        verbose,
    )

    ee_module = None
    xr_module = None
    for site in sites:
        for chunk_start, chunk_end in chunks:
            completed += 1
            _log_progress(
                f"{progress_bar(completed - 1, total)} batch {completed}/{total}: "
                f"{site.name} {chunk_start}..{chunk_end}",
                verbose,
            )

            normalized_start = (
                date(chunk_start.year, chunk_start.month, 1)
                if data_settings.cadence == "monthly"
                else chunk_start
            )
            normalized_end = (
                date(chunk_end.year, chunk_end.month, 1)
                if data_settings.cadence == "monthly"
                else chunk_end
            )
            expected_dates = (
                pd.date_range(normalized_start, normalized_end, freq="MS")
                if data_settings.cadence == "monthly"
                else pd.date_range(normalized_start, normalized_end, freq="D")
            )

            data_path, manifest_path = _cache_paths(
                cache_dir=cache_dir,
                source=dataset,
                site=site,
                start=normalized_start,
                end=normalized_end,
                bands=bands,
            )
            batch_start = time.perf_counter()
            cached_frame, cached_manifest = _load_valid_cached_chunk(
                data_path,
                manifest_path,
                start=normalized_start,
                end=normalized_end,
                site=site,
                expected_dates=expected_dates,
                refresh_cache=refresh_cache,
                verbose=verbose,
            )
            if cached_frame is not None and cached_manifest is not None:
                frames.append(cached_frame)
                elapsed = time.perf_counter() - batch_start
                _log_progress(
                    f"Cache hit for {site.name} {normalized_start}..{normalized_end} "
                    f"in {elapsed:.2f}s.",
                    verbose,
                )
                manifest_rows.append(
                    {
                        "source": dataset.name,
                        "site": site.name,
                        "start_date": normalized_start.isoformat(),
                        "end_date": normalized_end.isoformat(),
                        "cache_hit": True,
                        "elapsed_seconds": round(elapsed, 4),
                        "data_path": str(data_path),
                    }
                )
                continue

            if ee_module is None or xr_module is None:
                ee_module, xr_module = import_xee_stack(required_for="gee_xee_batch")
                initialize_earth_engine(
                    ee_module,
                    project_id=ee_project_id,
                    ee_opt_url=ee_opt_url,
                )

            frame, expected_dates = _fetch_with_retries(
                ee_module=ee_module,
                xr_module=xr_module,
                source=dataset,
                data_settings=data_settings,
                site=site,
                variables=active_variables,
                start_date=chunk_start,
                end_date=chunk_end,
                retry_attempts=max(1, retry_attempts),
            )
            manifest = _build_manifest(
                frame=frame,
                source=dataset,
                site=site,
                bands=bands,
                start=normalized_start,
                end=normalized_end,
                expected_dates=expected_dates,
            )
            _write_cached_frame(data_path, manifest_path, frame, manifest)
            frames.append(frame)
            elapsed = time.perf_counter() - batch_start
            manifest_rows.append(
                {
                    "source": dataset.name,
                    "site": site.name,
                    "start_date": normalized_start.isoformat(),
                    "end_date": normalized_end.isoformat(),
                    "cache_hit": False,
                    "elapsed_seconds": round(elapsed, 4),
                    "data_path": str(data_path),
                }
            )

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not result.empty:
        result = (
            result.drop_duplicates(subset=["site", "lat", "lon", "date"], keep="last")
            .sort_values(["site", "date"])
            .reset_index(drop=True)
        )

    summary_df = _summary_frame(result, dataset)
    manifest_df = pd.DataFrame(manifest_rows)
    _log_progress(
        f"{progress_bar(total, total)} completed {total}/{total} batch(es); "
        f"{len(result)} row(s) ready.",
        verbose,
    )
    return result, summary_df, manifest_df


def fetch_gee_xee_batch_data(
    *,
    source: str | ClimateDataset,
    sites: Iterable[Site | dict | tuple] | None = None,
    sites_csv: str | os.PathLike | None = None,
    variables=None,
    date_from: date,
    date_to: date,
    settings: Settings | None = None,
    stage: str = "preprocessed",
    cache_dir: str | Path | None = DEFAULT_BATCH_CACHE_DIR,
    refresh_cache: bool = False,
    verbose: bool = True,
    ee_project_id: str | None = None,
    ee_opt_url: str = DEFAULT_EE_OPT_URL,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if stage not in VALID_STAGES:
        raise ValueError(
            f"Invalid stage '{stage}'. Must be one of: {', '.join(VALID_STAGES)}"
        )

    dataset = _coerce_source(source)
    resolved_sites = load_sites(sites=sites, sites_csv=sites_csv)
    raw_df, summary_df, manifest_df = run_gee_xee_batch_extraction(
        source=dataset,
        sites=resolved_sites,
        variables=variables,
        date_from=date_from,
        date_to=date_to,
        settings=settings,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        verbose=verbose,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        chunk_days=chunk_days,
        retry_attempts=retry_attempts,
    )

    if stage == "raw":
        return raw_df, summary_df, manifest_df

    transformed_df = _transform_batch_frame(raw_df, dataset)
    if stage == "transformed":
        return transformed_df, summary_df, manifest_df

    preprocessed_df = preprocess_transformed_data(
        transformed_df=transformed_df,
        source=dataset.name,
        group_columns=["site", "lat", "lon"],
        verbose=verbose,
    )
    return preprocessed_df, summary_df, manifest_df


def main():
    parser = argparse.ArgumentParser(
        description="Package-native many-site GEE Xee extraction."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help='Repeatable site spec: "name,lat,lon"',
    )
    parser.add_argument("--sites-csv", default=None)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--cache-dir", default=DEFAULT_BATCH_CACHE_DIR)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument(
        "--stage",
        choices=VALID_STAGES,
        default="preprocessed",
    )
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument(
        "--format",
        choices=["csv", "json", "print"],
        default="print",
    )
    args = parser.parse_args()

    try:
        sites = [parse_site_spec(raw) for raw in args.site]
        data_df, summary_df, manifest_df = fetch_gee_xee_batch_data(
            source=args.source,
            sites=sites,
            sites_csv=args.sites_csv,
            date_from=date.fromisoformat(args.start),
            date_to=date.fromisoformat(args.end),
            stage=args.stage,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            verbose=not args.quiet,
        )
    except (ValueError, ImportError) as exc:
        print(f"Error: {format_ee_setup_error(exc)}")
        return 1

    if args.format == "print" or not args.output:
        print(data_df)
        print(summary_df)
        print(manifest_df)
        return 0

    if args.format == "csv":
        data_df.to_csv(args.output, index=False)
    else:
        data_df.to_json(args.output, orient="records", date_format="iso", indent=2)
    print(f"Saved data to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
