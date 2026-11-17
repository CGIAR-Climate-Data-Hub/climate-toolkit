"""Benchmark anonymous CHC cold reads against the #178 1/30-year point workloads.

Run with the probe_chirts_strips dependencies plus h5py. Each case uses a fresh
process and no persisted source data. Only complete cases qualify for warm replay.
"""

import argparse
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

import h5py
import numpy as np

from benchmark_direct_cloud import sites_for
from compare_chirts_originals import ARCHIVE
from probe_chc_backup import RangeReader
from probe_chirts_strips import sample_strips

OUT = Path(__file__).resolve().parents[1] / "outputs/validation/issue-179-long"


def annual(remote, year, sites):
    """Share each compressed spatial chunk among all points that fall inside it."""
    with h5py.File(remote) as nc:
        a = nc["temp"]
        n = (date(year + 1, 1, 1) - date(year, 1, 1)).days
        expected = (date(year, 1, 1) - date(1980, 1, 1)).days + np.arange(n)
        if nc["time"].attrs["units"] != b"days since 1980-1-1 0:0:0" or not np.array_equal(
            nc["time"][:], expected
        ):
            raise ValueError("Incomplete or unexpected daily time coordinate")
        lat, lon = nc["latitude"][:], nc["longitude"][:]
        groups = {}
        step, dy, dx = a.chunks
        for idx, (_, y, x) in enumerate(sites):
            i, j = int(np.argmin(abs(lat - y))), int(np.argmin(abs(lon - x)))
            groups.setdefault((i // dy, j // dx), []).append((idx, i, j))
        out = np.empty((n, len(sites)), dtype=float)
        for points in groups.values():
            indices, iy, ix = np.array(points).T
            y0, x0 = min(iy), min(ix)
            for start in range(0, n, step):
                slab = a[start : start + step, y0 : max(iy) + 1, x0 : max(ix) + 1]
                out[start : start + step, indices] = slab[:, iy - y0, ix - x0]
        return out


def run_case(route, count, layout, years, seconds):
    sites = sites_for(count, layout)
    start = time.monotonic()
    first = date(1991 if years == 30 else 2020, 1, 1)
    last = date(2020, 12, 31)
    case = dict(
        route=route,
        sites=count,
        layout=layout,
        years=years,
        deadline_s=seconds,
        requests=0,
        response_body_bytes=0,
        completed_files=0,
        completed_days=0,
        requested_days=(last - first).days + 1,
        warm_s=None,
    )
    series = []
    try:
        day = first
        while day <= last:
            parts = []
            for var in ("Tmax", "Tmin"):
                if route == "annual":
                    path = f"netcdf/daily/CHIRTS-ERA5.daily_{var}.{day.year}.nc"
                else:
                    path = f"tifs/daily/{day.year}/CHIRTS-ERA5.daily_{var}.{day:%Y.%m.%d}.tif"
                url = f"{ARCHIVE}/{var.lower()}/{path}"
                left = seconds - (time.monotonic() - start)
                if left <= 0:
                    raise TimeoutError("Whole-case deadline reached")
                with RangeReader(url, 512 * 1024**2, left) as remote:
                    try:
                        if route == "annual":
                            arr = annual(remote, day.year, sites)
                        else:
                            samples = sample_strips(remote, sites)
                            arr = np.array(
                                [[samples[name]["original_c"] for name, _, _ in sites]], dtype=float
                            )
                        if not np.isfinite(arr).all() or arr.min() < -90 or arr.max() > 60:
                            raise ValueError("Missing or invalid land temperature")
                    finally:
                        case.update(
                            last_url=url,
                            last_etag=remote.etag,
                            last_status=remote.last_status,
                            retry_after=remote.retry_after,
                        )
                        case["requests"] += remote.requests
                        case["response_body_bytes"] += remote.bytes
                    parts.append(arr)
                    case["completed_files"] += 1
            if np.any(parts[0] < parts[1]):
                raise ValueError("Tmax below Tmin")
            series.append(np.stack(parts, axis=-1))
            day += timedelta(days=len(parts[0]))
            case["completed_days"] += len(parts[0])
        case["cold_s"] = round(time.monotonic() - start, 3)
        if case["cold_s"] > seconds:
            raise TimeoutError("Whole-case deadline reached")
        data = np.concatenate(series)
        with tempfile.NamedTemporaryFile(dir=OUT, suffix=".npy") as f:
            np.save(f, data)
            f.flush()
            f.seek(0)
            warm = time.monotonic()
            np.testing.assert_array_equal(np.load(f), data)
            case["warm_s"] = round(time.monotonic() - warm, 4)
        case["status"] = "complete"
    except Exception as exc:
        case.update(status="incomplete", error=f"{type(exc).__name__}: {exc}")
    case.setdefault("cold_s", round(time.monotonic() - start, 3))
    case["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )
    return case


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", nargs=4, metavar=("ROUTE", "SITES", "LAYOUT", "YEARS"))
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--route", choices=["annual", "daily"], required=False)
    args = p.parse_args()
    if args.seconds <= 0:
        p.error("--seconds must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    if args.worker:
        route, n, layout, y = args.worker
        if route not in ("annual", "daily") or layout not in ("clustered", "dispersed"):
            p.error("Choose annual or daily and clustered or dispersed")
        if n not in ("1", "10", "100") or y not in ("1", "30"):
            p.error("Choose 1, 10 or 100 sites and 1 or 30 years")
        print(json.dumps(run_case(route, int(n), layout, int(y), args.seconds)))
        return
    results = []
    for y in (1, 30):
        for n, layout in (
            (1, "clustered"),
            (10, "clustered"),
            (10, "dispersed"),
            (100, "clustered"),
            (100, "dispersed"),
        ):
            for route in [args.route] if args.route else ["annual", "daily"]:
                result = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "--seconds",
                        str(args.seconds),
                        "--worker",
                        route,
                        str(n),
                        layout,
                        str(y),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                row = json.loads(result.stdout)
                results.append(row)
                (OUT / "matrix.json").write_text(
                    json.dumps(
                        dict(checked_utc=datetime.now(timezone.utc).isoformat(), results=results),
                        indent=2,
                    )
                    + "\n"
                )
                print(
                    route,
                    n,
                    layout,
                    y,
                    row["completed_days"],
                    row["cold_s"],
                    row.get("error", "ok"),
                    flush=True,
                )
                if row.get("last_status") == 429:
                    retry = row.get("retry_after")
                    delay = (
                        float(retry)
                        if retry and retry.isdigit()
                        else max(0, parsedate_to_datetime(retry).timestamp() - time.time())
                        if retry
                        else 30
                    )
                    time.sleep(delay)


if __name__ == "__main__":
    main()
