"""Benchmark NEX-GDDP optimization choices under real Earth Engine load.

This harness is meant to answer practical operator question:

"Which knob matters most for our workload: worker count, chunk size,
site batch size, or cache reuse?"

It does that by:

1. partitioning sites into worker shards
2. running package-native NEX batch extractor in parallel subprocesses
3. measuring cold-cache and/or warm-cache runtime
4. counting retry / quota / cache-hit signals from logs
5. ranking configurations by success, stability, and throughput

Use modest worker counts first. This script intentionally defaults to
conservative settings because Earth Engine quotas are per project.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS,
    POLICY_PROFILE_CHOICES,
    default_ensemble_models_for_location,
)


RETRY_LINE_RE = re.compile(r"Retrying in\s+\d+(?:\.\d+)?s", re.IGNORECASE)
QUOTA_RE = re.compile(
    r"(?:\b429\b|too many requests|rate limit|quota exceeded|too many concurrent aggregations)",
    re.IGNORECASE,
)
CACHE_HIT_RE = re.compile(r"\bcache hit\b", re.IGNORECASE)
FETCHED_RE = re.compile(r"\bfetched\b", re.IGNORECASE)

DEFAULT_WORKER_COUNTS = [1, 2, 4]
DEFAULT_CHUNK_DAYS = [90, 180, 365]
DEFAULT_POINT_BATCH_SIZES = [10, 25, 50]


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float


def parse_csv_list(raw: str, caster=int) -> list[int]:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(caster(token))
    if not values:
        raise ValueError(f"No values parsed from '{raw}'")
    return values


def parse_location_coord(raw: str) -> tuple[float, float]:
    lat_str, lon_str = [part.strip() for part in raw.split(",", 1)]
    return float(lat_str), float(lon_str)


def load_sites_csv(path: str | os.PathLike) -> list[Site]:
    frame = pd.read_csv(path)
    required = {"name", "lat", "lon"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Sites CSV missing required columns: {', '.join(sorted(missing))}")
    return [
        Site(name=str(row["name"]), lat=float(row["lat"]), lon=float(row["lon"]))
        for _, row in frame.iterrows()
    ]


def shard_sites(sites: list[Site], worker_count: int) -> list[list[Site]]:
    if worker_count <= 0:
        raise ValueError("worker_count must be positive")
    if not sites:
        return []
    shards: list[list[Site]] = [[] for _ in range(min(worker_count, len(sites)))]
    for index, site in enumerate(sites):
        shards[index % len(shards)].append(site)
    return [shard for shard in shards if shard]


def write_sites_csv(path: Path, sites: Iterable[Site]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "lat", "lon"])
        writer.writeheader()
        for site in sites:
            writer.writerow({"name": site.name, "lat": site.lat, "lon": site.lon})


def safe_label(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip("-")
    return normalized or "value"


def build_worker_command(
    *,
    python_executable: str,
    worker_sites_csv: Path,
    start: str,
    end: str,
    model: str,
    scenario: str,
    project_id: str,
    cache_dir: Path,
    output_dir: Path,
    chunk_days: int,
    point_batch_size: int,
    target_elements_per_batch: int,
    tile_scale: float,
    retry_attempts: int,
    refresh_cache: bool,
    quiet: bool,
) -> list[str]:
    data_output = output_dir / "data.json"
    summary_output = output_dir / "summary.csv"
    manifest_output = output_dir / "manifest.csv"
    command = [
        python_executable,
        "-m",
        "climate_tookit.fetch_data.nex_gddp_batch",
        "--sites-csv",
        str(worker_sites_csv),
        "--start",
        start,
        "--end",
        end,
        "--model",
        model,
        "--scenario",
        scenario,
        "--project-id",
        project_id,
        "--cache-dir",
        str(cache_dir),
        "--point-batch-size",
        str(point_batch_size),
        "--chunk-days",
        str(chunk_days),
        "--target-elements-per-batch",
        str(target_elements_per_batch),
        "--tile-scale",
        str(tile_scale),
        "--retry-attempts",
        str(retry_attempts),
        "--stage",
        "raw",
        "--output",
        str(data_output),
        "--summary-output",
        str(summary_output),
        "--manifest-output",
        str(manifest_output),
    ]
    if refresh_cache:
        command.append("--refresh-cache")
    if quiet:
        command.append("--quiet")
    return command


def signal_counts(log_text: str) -> dict[str, int]:
    return {
        "retry_lines": len(RETRY_LINE_RE.findall(log_text)),
        "quota_lines": len(QUOTA_RE.findall(log_text)),
        "cache_hit_lines": len(CACHE_HIT_RE.findall(log_text)),
        "fetched_lines": len(FETCHED_RE.findall(log_text)),
    }


def summarize_worker_outputs(output_dir: Path) -> dict[str, object]:
    manifest_path = output_dir / "manifest.csv"
    summary_path = output_dir / "summary.csv"
    data_path = output_dir / "data.json"

    manifest_rows = 0
    manifest_cache_hits = 0
    manifest_elapsed_seconds = 0.0
    extracted_rows = 0
    sites_covered = 0

    if manifest_path.exists():
        manifest_df = pd.read_csv(manifest_path)
        manifest_rows = len(manifest_df)
        if "cache_hit" in manifest_df.columns:
            manifest_cache_hits = int(manifest_df["cache_hit"].fillna(False).astype(bool).sum())
        if "elapsed_seconds" in manifest_df.columns:
            manifest_elapsed_seconds = float(manifest_df["elapsed_seconds"].fillna(0).sum())

    if summary_path.exists():
        summary_df = pd.read_csv(summary_path)
        sites_covered = len(summary_df)
        if "days" in summary_df.columns:
            extracted_rows = int(summary_df["days"].fillna(0).sum())

    return {
        "manifest_rows": manifest_rows,
        "manifest_cache_hits": manifest_cache_hits,
        "manifest_elapsed_seconds": round(manifest_elapsed_seconds, 3),
        "extracted_rows": extracted_rows,
        "sites_covered": sites_covered,
        "data_output_exists": data_path.exists(),
        "summary_output_exists": summary_path.exists(),
        "manifest_output_exists": manifest_path.exists(),
    }


def run_worker_group(
    *,
    python_executable: str,
    shards: list[list[Site]],
    start: str,
    end: str,
    models: list[str],
    scenario: str,
    project_id: str,
    cache_dir: Path,
    run_dir: Path,
    chunk_days: int,
    point_batch_size: int,
    target_elements_per_batch: int,
    tile_scale: float,
    retry_attempts: int,
    refresh_cache: bool,
    quiet: bool,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[int, subprocess.Popen[str], Path]] = []
    wall_start = time.perf_counter()

    for worker_index, shard in enumerate(shards, start=1):
        for model in models:
            worker_dir = run_dir / f"worker_{worker_index:02d}" / safe_label(model)
            worker_dir.mkdir(parents=True, exist_ok=True)
            worker_sites_csv = worker_dir / "sites.csv"
            write_sites_csv(worker_sites_csv, shard)
            command = build_worker_command(
                python_executable=python_executable,
                worker_sites_csv=worker_sites_csv,
                start=start,
                end=end,
                model=model,
                scenario=scenario,
                project_id=project_id,
                cache_dir=cache_dir,
                output_dir=worker_dir,
                chunk_days=chunk_days,
                point_batch_size=point_batch_size,
                target_elements_per_batch=target_elements_per_batch,
                tile_scale=tile_scale,
                retry_attempts=retry_attempts,
                refresh_cache=refresh_cache,
                quiet=quiet,
            )
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            processes.append((worker_index, process, worker_dir, model))

    worker_results = []
    for worker_index, process, worker_dir, model in processes:
        stdout, _ = process.communicate()
        log_path = worker_dir / "run.log"
        log_path.write_text(stdout or "", encoding="utf-8")
        output_summary = summarize_worker_outputs(worker_dir)
        signals = signal_counts(stdout or "")
        worker_results.append(
            {
                "worker_index": worker_index,
                "model": model,
                "returncode": process.returncode,
                "log_path": str(log_path),
                **signals,
                **output_summary,
            }
        )

    wall_seconds = time.perf_counter() - wall_start
    total_rows = sum(int(item["extracted_rows"]) for item in worker_results)
    total_retries = sum(int(item["retry_lines"]) for item in worker_results)
    total_quota = sum(int(item["quota_lines"]) for item in worker_results)
    total_cache_hits = sum(int(item["manifest_cache_hits"]) for item in worker_results)
    success = all(int(item["returncode"]) == 0 for item in worker_results)

    return {
        "success": success,
        "wall_seconds": round(wall_seconds, 3),
        "rows_per_second": round(total_rows / wall_seconds, 3) if wall_seconds > 0 else None,
        "total_rows": total_rows,
        "total_retry_lines": total_retries,
        "total_quota_lines": total_quota,
        "total_cache_hits": total_cache_hits,
        "workers": worker_results,
    }


def rank_key(result: dict[str, object]) -> tuple:
    success = 0 if result["success"] else 1
    quota = int(result["total_quota_lines"])
    retries = int(result["total_retry_lines"])
    wall = float(result["wall_seconds"])
    throughput = -(float(result["rows_per_second"]) if result["rows_per_second"] is not None else 0.0)
    return (success, quota, retries, wall, throughput)


def trial_configs(
    worker_counts: list[int],
    chunk_days_values: list[int],
    point_batch_sizes: list[int],
) -> list[dict[str, int]]:
    return [
        {
            "worker_count": worker_count,
            "chunk_days": chunk_days,
            "point_batch_size": point_batch_size,
        }
        for worker_count, chunk_days, point_batch_size in itertools.product(
            worker_counts,
            chunk_days_values,
            point_batch_sizes,
        )
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark NEX-GDDP optimization choices under live Earth Engine load."
    )
    parser.add_argument("--sites-csv", required=True, help="CSV with columns name,lat,lon")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--extra-model",
        action="append",
        default=[],
        help="Repeatable extra model name.",
    )
    parser.add_argument(
        "--all-available-models",
        action="store_true",
        help="Use all AVAILABLE_MODELS from nex_gddp source policy.",
    )
    parser.add_argument(
        "--policy-location",
        default=None,
        help="Optional lat,lon used to resolve default ensemble models for one location.",
    )
    parser.add_argument(
        "--policy-profile",
        choices=POLICY_PROFILE_CHOICES,
        default="default",
        help="Optional ensemble policy profile when using --policy-location.",
    )
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--worker-counts",
        default="1,2,4",
        help="Comma-separated worker counts to test.",
    )
    parser.add_argument(
        "--chunk-days-values",
        default="90,180,365",
        help="Comma-separated chunk-day values to test.",
    )
    parser.add_argument(
        "--point-batch-sizes",
        default="10,25,50",
        help="Comma-separated point-batch-size values to test.",
    )
    parser.add_argument(
        "--measure-mode",
        choices=("cold", "warm", "both"),
        default="both",
        help="Cold uses fresh cache. Warm primes cache, then measures second pass.",
    )
    parser.add_argument("--target-elements-per-batch", type=int, default=4500)
    parser.add_argument("--tile-scale", type=float, default=1.0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable to use for worker subprocesses.",
    )
    parser.add_argument(
        "--output-prefix",
        default="analysis/nex_parallel_optimization",
        help="Prefix for benchmark outputs.",
    )
    parser.add_argument(
        "--keep-run-dirs",
        action="store_true",
        help="Retain detailed worker directories and logs.",
    )
    parser.add_argument(
        "--quiet-workers",
        action="store_true",
        help="Pass --quiet to worker jobs. Usually leave off so retry/cache signals remain visible.",
    )
    return parser.parse_args()


def resolve_models(args: argparse.Namespace) -> list[str]:
    if args.all_available_models:
        return list(AVAILABLE_MODELS)
    if args.policy_location:
        coord = parse_location_coord(args.policy_location)
        policy_profile = None if args.policy_profile == "default" else args.policy_profile
        return default_ensemble_models_for_location(coord, policy_profile=policy_profile)
    if args.model:
        return [args.model, *args.extra_model]
    raise ValueError(
        "Provide --model, or use --all-available-models, or use --policy-location."
    )


def main() -> int:
    args = parse_args()
    sites = load_sites_csv(args.sites_csv)
    worker_counts = parse_csv_list(args.worker_counts)
    chunk_days_values = parse_csv_list(args.chunk_days_values)
    point_batch_sizes = parse_csv_list(args.point_batch_sizes)
    configs = trial_configs(worker_counts, chunk_days_values, point_batch_sizes)

    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    summary_json = prefix.with_suffix(".json")
    ranking_csv = prefix.with_suffix(".csv")
    runs_root = prefix.parent / f"{prefix.name}_runs"

    models = resolve_models(args)

    print("NEX optimization benchmark")
    print(f"Sites:          {len(sites)}")
    print(f"Period:         {args.start} .. {args.end}")
    print(f"Models:         {', '.join(models)}")
    print(f"Scenario:       {args.scenario}")
    print(f"Worker counts:  {worker_counts}")
    print(f"Chunk days:     {chunk_days_values}")
    print(f"Point batches:  {point_batch_sizes}")
    print(f"Measure mode:   {args.measure_mode}")
    print()

    results = []
    for trial_index, config in enumerate(configs, start=1):
        worker_count = int(config["worker_count"])
        chunk_days = int(config["chunk_days"])
        point_batch_size = int(config["point_batch_size"])
        trial_name = (
            f"w{worker_count}_c{chunk_days}_b{point_batch_size}"
        )
        shards = shard_sites(sites, worker_count)
        trial_dir = runs_root / trial_name
        if trial_dir.exists():
            shutil.rmtree(trial_dir)
        cache_dir = trial_dir / "cache"

        print(
            f"[{trial_index}/{len(configs)}] {trial_name} | "
            f"workers={worker_count} chunks={chunk_days} batch={point_batch_size}"
        )

        trial_result: dict[str, object] = {
            "trial_name": trial_name,
            **config,
            "site_count": len(sites),
            "shard_count": len(shards),
            "measurements": {},
        }

        if args.measure_mode in {"cold", "both"}:
            cold_dir = trial_dir / "cold"
            cold = run_worker_group(
                python_executable=args.python_executable,
                shards=shards,
                start=args.start,
                end=args.end,
                models=models,
                scenario=args.scenario,
                project_id=args.project_id,
                cache_dir=cache_dir,
                run_dir=cold_dir,
                chunk_days=chunk_days,
                point_batch_size=point_batch_size,
                target_elements_per_batch=args.target_elements_per_batch,
                tile_scale=args.tile_scale,
                retry_attempts=args.retry_attempts,
                refresh_cache=True,
                quiet=args.quiet_workers,
            )
            trial_result["measurements"]["cold"] = cold

        if args.measure_mode in {"warm", "both"}:
            warm_prime_dir = trial_dir / "warm_prime"
            warm_measured_dir = trial_dir / "warm_measured"
            _ = run_worker_group(
                python_executable=args.python_executable,
                shards=shards,
                start=args.start,
                end=args.end,
                models=models,
                scenario=args.scenario,
                project_id=args.project_id,
                cache_dir=cache_dir,
                run_dir=warm_prime_dir,
                chunk_days=chunk_days,
                point_batch_size=point_batch_size,
                target_elements_per_batch=args.target_elements_per_batch,
                tile_scale=args.tile_scale,
                retry_attempts=args.retry_attempts,
                refresh_cache=True,
                quiet=args.quiet_workers,
            )
            warm = run_worker_group(
                python_executable=args.python_executable,
                shards=shards,
                start=args.start,
                end=args.end,
                models=models,
                scenario=args.scenario,
                project_id=args.project_id,
                cache_dir=cache_dir,
                run_dir=warm_measured_dir,
                chunk_days=chunk_days,
                point_batch_size=point_batch_size,
                target_elements_per_batch=args.target_elements_per_batch,
                tile_scale=args.tile_scale,
                retry_attempts=args.retry_attempts,
                refresh_cache=False,
                quiet=args.quiet_workers,
            )
            trial_result["measurements"]["warm"] = warm

        decision_basis = (
            trial_result["measurements"].get("warm")
            or trial_result["measurements"].get("cold")
        )
        trial_result["decision_basis"] = decision_basis
        results.append(trial_result)

        basis = decision_basis or {}
        print(
            f"  success={basis.get('success')} | wall={basis.get('wall_seconds')}s | "
            f"rows/s={basis.get('rows_per_second')} | retries={basis.get('total_retry_lines')} | "
            f"quota={basis.get('total_quota_lines')}"
        )

        if not args.keep_run_dirs:
            warm_prime_dir = trial_dir / "warm_prime"
            if warm_prime_dir.exists():
                shutil.rmtree(warm_prime_dir)

    ranked = sorted(results, key=lambda item: rank_key(item["decision_basis"]))
    ranking_rows = []
    for rank, item in enumerate(ranked, start=1):
        basis = item["decision_basis"]
        ranking_rows.append(
            {
                "rank": rank,
                "trial_name": item["trial_name"],
                "worker_count": item["worker_count"],
                "chunk_days": item["chunk_days"],
                "point_batch_size": item["point_batch_size"],
                "site_count": item["site_count"],
                "shard_count": item["shard_count"],
                "success": basis["success"],
                "wall_seconds": basis["wall_seconds"],
                "rows_per_second": basis["rows_per_second"],
                "total_rows": basis["total_rows"],
                "total_retry_lines": basis["total_retry_lines"],
                "total_quota_lines": basis["total_quota_lines"],
                "total_cache_hits": basis["total_cache_hits"],
            }
        )

    ranking_df = pd.DataFrame(ranking_rows)
    ranking_df.to_csv(ranking_csv, index=False)
    summary_json.write_text(json.dumps({"results": results, "ranking": ranking_rows}, indent=2), encoding="utf-8")

    print()
    print(f"Saved ranking CSV:  {ranking_csv}")
    print(f"Saved summary JSON: {summary_json}")
    print()
    if ranking_rows:
        best = ranking_rows[0]
        print(
            "Best current config | "
            f"workers={best['worker_count']} chunk_days={best['chunk_days']} "
            f"point_batch_size={best['point_batch_size']} | "
            f"wall={best['wall_seconds']}s retries={best['total_retry_lines']} quota={best['total_quota_lines']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
