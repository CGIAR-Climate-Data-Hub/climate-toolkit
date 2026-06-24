"""Benchmark NASA POWER point API against public Zarr stores.

Purpose:

- compare current toolkit `nasa_power` backend (one HTTP point request per site)
  against public NASA POWER MERRA2 Zarr stores
- test workload shapes that matter to toolkit: long daily series across many sites
- capture variable-coverage gaps before any backend change

This is analysis harness for issue #54, not production package backend.

Prerequisites for this harness:

- `zarr`
- `s3fs`

These are not currently part of the stable toolkit runtime contract.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import s3fs
import xarray as xr

from climate_tookit.fetch_data.source_data.sources.nasa_power import DownloadData
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


TEMPORAL_STORE = "nasa-power/merra2/temporal/power_merra2_daily_temporal_lst.zarr"
SPATIAL_STORE = "nasa-power/merra2/spatial/power_merra2_daily_spatial_lst.zarr"

TOOLKIT_TO_ZARR = {
    "precipitation": "PRECTOTCORR",
    "mean_temperature": "T2M",
    "max_temperature": "T2M_MAX",
    "min_temperature": "T2M_MIN",
    "humidity": "RH2M",
    "wind_speed": "WS2M",
    "solar_radiation": "ALLSKY_SFC_SW_DWN",
}

DEFAULT_VARIABLES = [
    "precipitation",
    "max_temperature",
    "min_temperature",
    "humidity",
    "wind_speed",
    "solar_radiation",
]

PERIOD_PRESETS = {
    "short10": ("2020-01-01", "2020-01-10"),
    "one_year": ("2020-01-01", "2020-12-31"),
    "ten_year": ("2011-01-01", "2020-12-31"),
}

BACKEND_CHOICES = ("api_point", "zarr_temporal", "zarr_spatial")


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float


def parse_csv_list(raw: str, caster=int) -> list:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(caster(token))
    if not values:
        raise ValueError(f"No values parsed from '{raw}'")
    return values


def load_sites_csv(path: str | Path) -> list[Site]:
    frame = pd.read_csv(path)
    required = {"name", "lat", "lon"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Sites CSV missing required columns: {', '.join(sorted(missing))}")
    return [
        Site(name=str(row["name"]), lat=float(row["lat"]), lon=float(row["lon"]))
        for _, row in frame.iterrows()
    ]


def climate_variables(names: Sequence[str]) -> list[ClimateVariable]:
    resolved: list[ClimateVariable] = []
    for name in names:
        try:
            resolved.append(ClimateVariable[name])
        except KeyError as exc:
            raise ValueError(f"Unsupported toolkit variable '{name}'") from exc
    return resolved


def expected_days(start: str, end: str) -> int:
    return len(pd.date_range(start, end, freq="D"))


def safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def summarize_frame(frame: pd.DataFrame, requested_vars: Sequence[str]) -> dict[str, object]:
    if frame.empty:
        return {
            "rows": 0,
            "columns": [],
            "available_variables": [],
            "missing_variables": list(requested_vars),
        }
    columns = list(frame.columns)
    available = [name for name in requested_vars if name in columns]
    missing = [name for name in requested_vars if name not in columns]
    return {
        "rows": int(len(frame)),
        "columns": columns,
        "available_variables": available,
        "missing_variables": missing,
    }


def benchmark_api(
    *,
    sites: Sequence[Site],
    start: str,
    end: str,
    variable_names: Sequence[str],
) -> dict[str, object]:
    temp_root = Path(tempfile.mkdtemp(prefix="nasa_power_api_bench_"))
    settings = Settings.load()
    variables = climate_variables(variable_names)
    per_site_rows: list[dict[str, object]] = []
    started = time.perf_counter()
    try:
        for site in sites:
            site_start = time.perf_counter()
            downloader = DownloadData(
                location_coord=(site.lat, site.lon),
                date_from_utc=date.fromisoformat(start),
                date_to_utc=date.fromisoformat(end),
                variables=variables,
                settings=settings,
                source=ClimateDataset.nasa_power,
                verbose=False,
                cache_dir=temp_root,
                refresh_cache=True,
            )
            frame = downloader.download_variables()
            per_site_rows.append(
                {
                    "site": site.name,
                    "lat": site.lat,
                    "lon": site.lon,
                    "elapsed_seconds": round(time.perf_counter() - site_start, 3),
                    **summarize_frame(frame, variable_names),
                }
            )
        total_seconds = time.perf_counter() - started
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    return {
        "backend": "api_point",
        "sites": len(sites),
        "start": start,
        "end": end,
        "expected_days": expected_days(start, end),
        "variables_requested": list(variable_names),
        "total_seconds": round(total_seconds, 3),
        "seconds_per_site": round(total_seconds / max(len(sites), 1), 3),
        "site_results": per_site_rows,
    }


def _store_name(kind: str) -> str:
    if kind == "temporal":
        return TEMPORAL_STORE
    if kind == "spatial":
        return SPATIAL_STORE
    raise ValueError(f"Unknown store kind '{kind}'")


def _open_zarr_dataset(kind: str):
    fs = s3fs.S3FileSystem(anon=True)
    store = s3fs.S3Map(root=_store_name(kind), s3=fs, check=False)
    open_started = time.perf_counter()
    ds = xr.open_zarr(store, consolidated=True)
    open_seconds = time.perf_counter() - open_started
    return fs, ds, open_seconds


def _close_zarr_fs(fs: s3fs.S3FileSystem) -> None:
    try:
        s3_client = getattr(fs, "_s3", None)
        loop = getattr(fs, "loop", None)
        if s3_client is not None and loop is not None:
            fs.close_session(loop, s3_client)
    except Exception:
        pass


def _extract_zarr_dataset(
    *,
    ds: xr.Dataset,
    zarr_vars: Sequence[str],
    sites: Sequence[Site],
    start: str,
    end: str,
) -> tuple[xr.Dataset, list[dict[str, object]]]:
    lat_indexer = xr.DataArray([site.lat for site in sites], dims="site")
    lon_indexer = xr.DataArray([site.lon for site in sites], dims="site")
    subset = (
        ds[list(zarr_vars)]
        .sel(lat=lat_indexer, lon=lon_indexer, method="nearest")
        .sel(time=slice(start, end))
        .load()
    )
    site_meta = []
    for idx, site in enumerate(sites):
        site_slice = subset.isel(site=idx)
        site_meta.append(
            {
                "site": site.name,
                "requested_lat": site.lat,
                "requested_lon": site.lon,
                "resolved_lat": float(site_slice["lat"].values),
                "resolved_lon": float(site_slice["lon"].values),
            }
        )
    return subset, site_meta


def benchmark_zarr(
    *,
    kind: str,
    sites: Sequence[Site],
    start: str,
    end: str,
    variable_names: Sequence[str],
) -> dict[str, object]:
    fs, ds, open_seconds = _open_zarr_dataset(kind)
    requested = list(variable_names)
    available_zarr = set(ds.data_vars)
    variable_results: list[dict[str, object]] = []
    rows_total = 0
    extract_started = time.perf_counter()
    try:
        supported_pairs = [
            (toolkit_var, TOOLKIT_TO_ZARR[toolkit_var])
            for toolkit_var in requested
            if TOOLKIT_TO_ZARR[toolkit_var] in available_zarr
        ]
        supported_zarr_vars = [zarr_var for _, zarr_var in supported_pairs]
        resolved_sites = []
        loaded_subset = None
        if supported_zarr_vars:
            loaded_subset, resolved_sites = _extract_zarr_dataset(
                ds=ds,
                zarr_vars=supported_zarr_vars,
                sites=sites,
                start=start,
                end=end,
            )
        for toolkit_var in requested:
            zarr_var = TOOLKIT_TO_ZARR[toolkit_var]
            if zarr_var not in available_zarr:
                variable_results.append(
                    {
                        "toolkit_variable": toolkit_var,
                        "zarr_variable": zarr_var,
                        "supported": False,
                        "rows": 0,
                        "resolved_sites": [],
                    }
                )
                continue

            assert loaded_subset is not None
            frame = (
                loaded_subset[zarr_var]
                .to_series()
                .rename("value")
                .reset_index()
            )
            frame["site"] = frame["site"].map(lambda idx: sites[int(idx)].name)
            rows_total += len(frame)
            variable_results.append(
                {
                    "toolkit_variable": toolkit_var,
                    "zarr_variable": zarr_var,
                    "supported": True,
                    "rows": int(len(frame)),
                    "resolved_sites": resolved_sites,
                }
            )
        extract_seconds = time.perf_counter() - extract_started
    finally:
        _close_zarr_fs(fs)

    supported = [row["toolkit_variable"] for row in variable_results if row["supported"]]
    missing = [row["toolkit_variable"] for row in variable_results if not row["supported"]]
    total_seconds = open_seconds + extract_seconds

    return {
        "backend": f"zarr_{kind}",
        "sites": len(sites),
        "start": start,
        "end": end,
        "expected_days": expected_days(start, end),
        "variables_requested": requested,
        "variables_supported": supported,
        "variables_missing": missing,
        "open_seconds": round(open_seconds, 3),
        "extract_seconds": round(extract_seconds, 3),
        "total_seconds": round(total_seconds, 3),
        "seconds_per_site": round(total_seconds / max(len(sites), 1), 3),
        "rows_total": rows_total,
        "variable_results": variable_results,
        "chunk_signature": {
            var: list(ds[var].encoding.get("preferred_chunks", {}).values()) if ds[var].encoding.get("preferred_chunks") else None
            for var in sorted(set(TOOLKIT_TO_ZARR.values()).intersection(set(ds.data_vars)))
        },
    }


def compare_api_vs_zarr_sample(
    *,
    site: Site,
    start: str,
    end: str,
    variable_names: Sequence[str],
) -> dict[str, object]:
    api_result = benchmark_api(sites=[site], start=start, end=end, variable_names=variable_names)
    variables = climate_variables(variable_names)
    temp_root = Path(tempfile.mkdtemp(prefix="nasa_power_api_compare_"))
    settings = Settings.load()
    try:
        downloader = DownloadData(
            location_coord=(site.lat, site.lon),
            date_from_utc=date.fromisoformat(start),
            date_to_utc=date.fromisoformat(end),
            variables=variables,
            settings=settings,
            source=ClimateDataset.nasa_power,
            verbose=False,
            cache_dir=temp_root,
            refresh_cache=True,
        )
        api_frame = downloader.download_variables().copy()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    comparisons: list[dict[str, object]] = []
    for kind in ("temporal", "spatial"):
        fs, ds, _open_seconds = _open_zarr_dataset(kind)
        try:
            for toolkit_var in variable_names:
                zarr_var = TOOLKIT_TO_ZARR[toolkit_var]
                if zarr_var not in ds.data_vars or toolkit_var not in api_frame.columns:
                    comparisons.append(
                        {
                            "backend": f"zarr_{kind}",
                            "variable": toolkit_var,
                            "comparable": False,
                            "reason": "missing_in_backend_or_api_frame",
                        }
                    )
                    continue
                arr = (
                    ds[zarr_var]
                    .sel(lat=site.lat, lon=site.lon, method="nearest")
                    .sel(time=slice(start, end))
                    .load()
                )
                zarr_frame = (
                    arr.to_series()
                    .rename("zarr_value")
                    .reset_index()
                    .rename(columns={"time": "date"})
                )
                merged = api_frame.merge(zarr_frame[["date", "zarr_value"]], on="date", how="inner")
                merged["api_value"] = merged[toolkit_var]
                merged["abs_diff"] = (merged["api_value"] - merged["zarr_value"]).abs()
                comparisons.append(
                    {
                        "backend": f"zarr_{kind}",
                        "variable": toolkit_var,
                        "comparable": True,
                        "rows": int(len(merged)),
                        "max_abs_diff": None if merged.empty else float(merged["abs_diff"].max()),
                        "mean_abs_diff": None if merged.empty else float(merged["abs_diff"].mean()),
                        "resolved_lat": float(arr["lat"].values),
                        "resolved_lon": float(arr["lon"].values),
                    }
                )
        finally:
            _close_zarr_fs(fs)

    return {
        "site": site.name,
        "start": start,
        "end": end,
        "api_baseline_total_seconds": api_result["total_seconds"],
        "comparisons": comparisons,
    }


def benchmark_matrix(
    *,
    all_sites: Sequence[Site],
    site_counts: Sequence[int],
    period_names: Sequence[str],
    variable_names: Sequence[str],
    backends: Sequence[str],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    total_jobs = len(site_counts) * len(period_names) * len(backends)
    job_index = 0
    for site_count in site_counts:
        sites = list(all_sites[:site_count])
        if len(sites) < site_count:
            raise ValueError(f"Requested {site_count} sites but only {len(all_sites)} available")
        for period_name in period_names:
            start, end = PERIOD_PRESETS[period_name]
            batch_results = []
            for backend in backends:
                job_index += 1
                print(
                    f"[{job_index}/{total_jobs}] backend={backend} "
                    f"sites={site_count} period={period_name} {start}..{end}",
                    flush=True,
                )
                if backend == "api_point":
                    result = benchmark_api(
                        sites=sites,
                        start=start,
                        end=end,
                        variable_names=variable_names,
                    )
                elif backend == "zarr_temporal":
                    result = benchmark_zarr(
                        kind="temporal",
                        sites=sites,
                        start=start,
                        end=end,
                        variable_names=variable_names,
                    )
                elif backend == "zarr_spatial":
                    result = benchmark_zarr(
                        kind="spatial",
                        sites=sites,
                        start=start,
                        end=end,
                        variable_names=variable_names,
                    )
                else:
                    raise ValueError(f"Unknown backend '{backend}'")
                batch_results.append(result)

            for result in batch_results:
                result["site_count"] = site_count
                result["period_name"] = period_name
            results.extend(batch_results)
    return results


def flatten_summary_rows(results: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for result in results:
        rows.append(
            {
                "backend": result["backend"],
                "period_name": result["period_name"],
                "site_count": result["site_count"],
                "start": result["start"],
                "end": result["end"],
                "expected_days": result["expected_days"],
                "variables_requested": ",".join(result["variables_requested"]),
                "variables_supported": ",".join(result.get("variables_supported", result["variables_requested"])),
                "variables_missing": ",".join(result.get("variables_missing", [])),
                "open_seconds": result.get("open_seconds"),
                "extract_seconds": result.get("extract_seconds"),
                "total_seconds": result["total_seconds"],
                "seconds_per_site": result["seconds_per_site"],
                "rows_total": result.get("rows_total"),
            }
        )
    return rows


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark NASA POWER point API vs temporal/spatial Zarr stores."
    )
    parser.add_argument(
        "--sites-csv",
        default="analysis/sites_benchmark.csv",
        help="CSV with name,lat,lon columns.",
    )
    parser.add_argument(
        "--site-counts",
        default="1,5,10",
        help="Comma-separated subset sizes from sites CSV.",
    )
    parser.add_argument(
        "--periods",
        default="short10,one_year,ten_year",
        help=f"Comma-separated period presets: {', '.join(PERIOD_PRESETS)}",
    )
    parser.add_argument(
        "--variables",
        default=",".join(DEFAULT_VARIABLES),
        help="Comma-separated toolkit variable names.",
    )
    parser.add_argument(
        "--backends",
        default=",".join(BACKEND_CHOICES),
        help=f"Comma-separated backends: {', '.join(BACKEND_CHOICES)}",
    )
    parser.add_argument(
        "--summary-output",
        default="analysis/nasa_power_zarr_benchmark_summary.csv",
        help="CSV output path for flattened summary rows.",
    )
    parser.add_argument(
        "--json-output",
        default="analysis/nasa_power_zarr_benchmark_results.json",
        help="JSON output path for full benchmark payload.",
    )
    parser.add_argument(
        "--sample-compare-output",
        default="analysis/nasa_power_zarr_sample_compare.json",
        help="JSON output path for one-site API-vs-Zarr value comparison.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    all_sites = load_sites_csv(args.sites_csv)
    site_counts = parse_csv_list(args.site_counts, int)
    period_names = parse_csv_list(args.periods, str)
    invalid_periods = [name for name in period_names if name not in PERIOD_PRESETS]
    if invalid_periods:
        raise ValueError(f"Unknown period preset(s): {', '.join(invalid_periods)}")
    variable_names = parse_csv_list(args.variables, str)
    unknown_vars = [name for name in variable_names if name not in TOOLKIT_TO_ZARR]
    if unknown_vars:
        raise ValueError(f"Unknown toolkit variable(s): {', '.join(unknown_vars)}")
    backends = parse_csv_list(args.backends, str)
    invalid_backends = [name for name in backends if name not in BACKEND_CHOICES]
    if invalid_backends:
        raise ValueError(f"Unknown backend(s): {', '.join(invalid_backends)}")

    results = benchmark_matrix(
        all_sites=all_sites,
        site_counts=site_counts,
        period_names=period_names,
        variable_names=variable_names,
        backends=backends,
    )

    summary_rows = flatten_summary_rows(results)
    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

    sample_compare = compare_api_vs_zarr_sample(
        site=all_sites[0],
        start=PERIOD_PRESETS["short10"][0],
        end=PERIOD_PRESETS["short10"][1],
        variable_names=[name for name in variable_names if name != "solar_radiation"],
    )

    json_payload = {
        "site_counts": site_counts,
        "periods": {name: {"start": PERIOD_PRESETS[name][0], "end": PERIOD_PRESETS[name][1]} for name in period_names},
        "variables": variable_names,
        "backends": list(backends),
        "results": results,
        "sample_compare": sample_compare,
    }
    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    sample_compare_path = Path(args.sample_compare_output)
    sample_compare_path.parent.mkdir(parents=True, exist_ok=True)
    sample_compare_path.write_text(json.dumps(sample_compare, indent=2), encoding="utf-8")

    print(f"Saved summary CSV: {summary_path}")
    print(f"Saved full JSON: {json_path}")
    print(f"Saved sample compare JSON: {sample_compare_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
