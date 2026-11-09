"""Opt-in live benchmarks. Run with Python >=3.12 and the cloud extra.

Each case runs in a fresh process; its cold read has a wall-clock deadline.
Outputs include warm-cache latency, estimated chunk work (not network bytes),
peak RSS, revision, and failures. No credentials are required.
"""

from __future__ import annotations
import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def sites_for(count, layout):
    anchors = [(-1.286, 36.817), (12.37, -1.53), (-13.52, -71.97)]
    sites = []
    for i in range(count):
        lat, lon = anchors[0 if layout == "clustered" else i % 3]
        offset = i * 0.001 if layout == "clustered" else (i // 3) * 0.11
        sites.append((str(i), lat + offset, lon + offset))
    return sites


def worker(case, *, before_warm=None):
    import resource

    from climate_toolkit import fetch_climate_data

    source, backend, count, layout, years = case
    result = dict(source=source, backend=backend, sites=count, layout=layout, years=years)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="climate-benchmark-") as cache:
        kw = dict(
            source=source,
            backend=backend,
            allow_gee=False,
            sites=sites_for(count, layout),
            date_from=date(1991 if years == 30 else 2020, 1, 1),
            date_to=date(2020, 12, 31),
            cache_dir=cache,
            workers=2,
            verbose=False,
            stage="raw",
        )
        try:
            frame = fetch_climate_data(**kw)
            result["cold_seconds"] = round(time.monotonic() - start, 3)
            if before_warm is not None:
                before_warm()
            warm = time.monotonic()
            cached = fetch_climate_data(**kw)
            result.update(
                warm_seconds=round(time.monotonic() - warm, 3),
                rows=len(frame),
                qc=frame.attrs.get("quality_control"),
                revision=frame.attrs["data_provenance"][0]["revision"],
                estimated_source_chunk_bytes=frame.attrs["data_provenance"][0].get(
                    "estimated_source_chunk_bytes"
                ),
                cache_equal=frame.equals(cached),
                status="ok",
            )
        except Exception as exc:
            result.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                cold_seconds=round(time.monotonic() - start, 3),
            )
    result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--output", default="outputs/direct_cloud_benchmarks.json")
    parser.add_argument("--deadline", type=int, default=90)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker))
        return
    providers = [
        ("chirps_v3_daily_rnl", "dynamical"),
        ("chirps_v3_daily_rnl", "huggingface"),
        ("chirts_era5", "huggingface"),
    ]
    cases = [
        [s, b, n, layout, y]
        for s, b in providers
        for y in ([1] if args.quick else [1, 30])
        for n in [1, 10, 100]
        for layout in ["clustered", "dispersed"]
        if not (n == 1 and layout == "dispersed")
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        print("Running", case, flush=True)
        try:
            completed = subprocess.run(
                [sys.executable, __file__, "--worker", json.dumps(case)],
                capture_output=True,
                text=True,
                timeout=args.deadline,
                cwd=ROOT,
            )
            result = (
                json.loads(completed.stdout.strip().splitlines()[-1])
                if completed.returncode == 0
                else {"case": case, "status": "failed", "error": completed.stderr[-1000:]}
            )
        except subprocess.TimeoutExpired:
            result = {
                "case": case,
                "status": "deadline_exceeded",
                "deadline_seconds": args.deadline,
            }
        except Exception as exc:
            result = {"case": case, "status": "failed", "error": str(exc)}
        results.append(result)
        output.write_text(
            json.dumps(
                {
                    "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "python": sys.version,
                    "deadline_seconds": args.deadline,
                    "results": results,
                },
                indent=2,
            )
        )
        print(result, flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
