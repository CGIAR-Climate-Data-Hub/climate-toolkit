"""Opt-in CHC annual NetCDF investigation; this is not a toolkit backend.

Run with the project environment plus h5py (investigation-only dependency):
    uv run --with h5py python scripts/probe_chc_backup.py --year 2020

Reads byte ranges, never whole global files. Reports response-body bytes rather
than wire bytes (TLS/HTTP headers excluded). Each variable has bounded elapsed
time and transfer budgets. No automatic fallback or production cache is changed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import time

import numpy as np
import requests


class RangeReader(io.RawIOBase):
    """Read-only HTTP ranges with identity checks and a small metadata cache."""

    def __init__(self, url, max_bytes, seconds):
        super().__init__()
        self.url = url
        self.max_bytes = max_bytes
        self.deadline = time.monotonic() + seconds
        self.position = 0
        self.size = None
        self.etag = None
        self.bytes = 0
        self.requests = 0
        self.cache = {}
        self.session = requests.Session()

    def fetch(self, start, end):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Probe elapsed-time budget exhausted")
        if self.bytes + end - start + 1 > self.max_bytes:
            raise ValueError("Probe response-body byte budget exhausted")
        headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
        if self.etag:
            headers["If-Match"] = self.etag
        self.requests += 1
        with self.session.get(
            self.url, headers=headers, timeout=min(20, remaining), stream=True
        ) as response:
            response.raise_for_status()
            # Validate before consuming any body: a server ignoring Range must
            # never trigger an accidental multi-gigabyte download.
            content_range = response.headers.get("Content-Range", "")
            if response.status_code != 206 or not content_range.startswith(f"bytes {start}-"):
                raise ValueError(f"Invalid range response: {response.status_code} {content_range}")
            size = int(content_range.split("/")[-1])
            expected_end = min(end, size - 1)
            if content_range != f"bytes {start}-{expected_end}/{size}":
                raise ValueError("Server returned a different byte interval")
            etag = response.headers.get("ETag")
            if not etag or etag.startswith("W/"):
                raise ValueError("Strong ETag required for this probe")
            if self.size is not None and (self.size != size or self.etag != etag):
                raise ValueError("Remote file changed during extraction")
            self.size, self.etag = size, etag
            data = bytearray()
            for part in response.iter_content(65536):
                self.bytes += len(part)
                data.extend(part)
                if len(data) > expected_end - start + 1:
                    raise ValueError("Server returned an oversized range body")
                if time.monotonic() >= self.deadline:
                    raise TimeoutError("Probe elapsed-time budget exhausted")
            if len(data) != expected_end - start + 1:
                raise ValueError("Truncated range body")
            return bytes(data)

    def read(self, n=-1):
        if n < 0:
            raise ValueError("Unbounded reads are forbidden")
        if not n or (self.size is not None and self.position >= self.size):
            return b""
        start = self.position
        end = start + n - 1
        if self.size is not None:
            end = min(end, self.size - 1)
        # Cache metadata pages; fetch compressed data chunks in one request.
        if n <= 65536:
            parts = []
            while start <= end:
                page = start // 65536
                if page not in self.cache:
                    data = self.fetch(page * 65536, page * 65536 + 65535)
                    if len(self.cache) >= 32:
                        self.cache.pop(next(iter(self.cache)))
                    self.cache[page] = data
                offset = start % 65536
                part = self.cache[page][offset : offset + end - start + 1]
                if not part:
                    break
                parts.append(part)
                start += len(part)
            result = b"".join(parts)
        else:
            result = self.fetch(start, end)
        self.position += len(result)
        return result

    def readinto(self, buffer):
        result = self.read(len(buffer))
        buffer[: len(result)] = result
        return len(result)

    def seek(self, offset, whence=0):
        if whence == 2 and self.size is None:
            self.cache[0] = self.fetch(0, 65535)
        self.position = (0 if whence == 0 else self.position if whence == 1 else self.size) + offset
        return self.position

    def tell(self):
        return self.position

    def readable(self):
        return True

    def seekable(self):
        return True

    def close(self):
        self.session.close()
        super().close()


def probe(year, variable, sites, max_bytes, seconds):
    import h5py

    url = (
        f"https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5/{variable.lower()}/"
        f"netcdf/daily/CHIRTS-ERA5.daily_{variable}.{year}.nc"
    )
    result = {"year": year, "variable": variable, "url": url, "sites": sites}
    start = time.monotonic()
    with RangeReader(url, max_bytes, seconds) as remote:
        try:
            with h5py.File(remote, "r") as dataset:
                array = dataset["temp"]
                result.update(
                    shape=list(array.shape),
                    chunks=list(array.chunks),
                    dtype=str(array.dtype),
                    source_units=str(array.attrs.get("units")),
                    time_units=str(dataset["time"].attrs.get("units")),
                    time_values=dataset["time"][:].tolist(),
                )
                latitude, longitude = dataset["latitude"][:], dataset["longitude"][:]
                values = []
                result["points"] = values
                for name, lat, lon in sites:
                    indices = []
                    for grid, value in [(latitude, lat), (longitude, lon)]:
                        delta = np.abs(grid.astype(float) - value)
                        ties = np.flatnonzero(np.isclose(delta, delta.min(), atol=1e-7, rtol=0))
                        indices.append(int(ties[np.argmin(grid[ties])]))
                    i, j = indices
                    point = array[:, i, j]
                    values.append(
                        {
                            "site": name,
                            "cell": [float(latitude[i]), float(longitude[j])],
                            "values": point.tolist(),
                            "invalid_count": int(
                                np.count_nonzero(~np.isfinite(point) | (point < -90) | (point > 60))
                            ),
                        }
                    )
                result["status"] = "ok"
        except Exception as exc:
            result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        result.update(
            seconds=round(time.monotonic() - start, 3),
            requests=remote.requests,
            response_body_bytes=remote.bytes,
            file_bytes=remote.size,
            etag=remote.etag,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--variables", nargs="+", choices=["Tmax", "Tmin"], default=["Tmax", "Tmin"]
    )
    parser.add_argument("--sites", type=int, choices=[1, 3], default=3)
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--max-mib", type=int, default=256)
    parser.add_argument("--output", default="outputs/chc_backup_probe.json")
    args = parser.parse_args()
    if args.seconds <= 0 or args.max_mib <= 0:
        parser.error("Budgets must be positive")
    sites = [("Nairobi", -1.286, 36.817), ("Ouagadougou", 12.37, -1.53), ("Cusco", -13.52, -71.97)][
        : args.sites
    ]
    report = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "cases": []}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for variable in args.variables:
        case = probe(args.year, variable, sites, args.max_mib * 1024**2, args.seconds)
        report["cases"].append(case)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps({k: v for k, v in case.items() if k not in {"points", "time_values"}}),
            flush=True,
        )


if __name__ == "__main__":
    main()
