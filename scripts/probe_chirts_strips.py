"""Opt-in scientific and transport check for CHC daily CHIRTS-ERA5 GeoTIFFs.

Requires climate-toolkit[cloud], tifffile and imagecodecs. Each original read
has its own ETag, time limit and byte budget. Outputs stay in the local project.
"""

import argparse
from datetime import date, datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
from time import monotonic

import numpy as np
from tifffile import TiffFile

from climate_toolkit import fetch_climate_data
from compare_chirts_originals import ARCHIVE, SITES
from probe_chc_backup import RangeReader


POINTS = [*SITES, ("Pacific", 0.025, -150.025)]
OUT = Path(__file__).resolve().parents[1] / "outputs/validation/issue-179"
TOLERANCE = 0.05


def sample_strips(remote, points):
    """Read a compressed scanline once for all sites sharing that row."""
    with TiffFile(remote, name="original.tif") as tif:
        page = tif.pages[0]
        geo = tif.geotiff_metadata or {}
        if (
            len(tif.pages) != 1
            or page.shape != (2600, 7200)
            or page.dtype != np.float32
            or page.is_tiled
            or page.rowsperstrip != 1
            or geo.get("GeographicTypeGeoKey") != 4326
            or geo.get("GTRasterTypeGeoKey") != 1
        ):
            raise ValueError("Unexpected CHC scanline or geographic grid schema")
        scale = geo["ModelPixelScale"]
        origin = geo["ModelTiepoint"]
        if not np.allclose(scale, [0.05, 0.05, 0], rtol=0, atol=1e-8) or origin != [
            0,
            0,
            0,
            -180,
            70,
            0,
        ]:
            raise ValueError("Unexpected CHC grid transform")
        dx, dy = scale[:2]
        west, north = origin[3:5]
        rows = {}
        samples = {}
        for site, lat, lon in points:
            row = int(np.floor((north - lat) / dy))
            col = int(np.floor((lon - west) / dx))
            if not (0 <= row < page.imagelength and 0 <= col < page.imagewidth):
                raise ValueError(f"Point outside original grid: {site}")
            if row not in rows:
                start, size = page.dataoffsets[row], page.databytecounts[row]
                chunk = remote.fetch(start, start + size - 1)
                decoded, _, _ = page.decode(chunk, row)
                rows[row] = decoded.reshape(page.imagewidth)
            value = float(rows[row][col])
            samples[site] = dict(
                lon=west + (col + 0.5) * dx,
                lat=north - (row + 0.5) * dy,
                original_c=None if value == -9999 else value,
            )
        return samples


def compare_file(day, variable, grid, cells, min_request_interval):
    url = f"{ARCHIVE}/{variable.lower()}/tifs/daily/{day.year}/CHIRTS-ERA5.daily_{variable}.{day:%Y.%m.%d}.tif"
    start = monotonic()
    with RangeReader(url, 1024**2, 45, min_request_interval) as reader:
        result = dict(variable=variable, url=url)
        try:
            samples = sample_strips(reader, POINTS)
            for site, sample in samples.items():
                if not np.allclose([sample["lat"], sample["lon"]], cells[site], rtol=0, atol=1e-5):
                    raise ValueError(f"Grid centres disagree at {site}")
                original = sample["original_c"]
                mirror = float(grid.at[site, variable])
                if site == "Pacific":
                    if original is not None or not np.isnan(mirror):
                        raise ValueError("Expected masked Pacific ocean cell in both products")
                    sample["mirror_c"] = None
                else:
                    if original is None or not np.isfinite([mirror, original]).all():
                        raise ValueError(f"Missing land temperature at {site}")
                    sample["mirror_c"] = mirror
                    sample["abs_difference_c"] = abs(mirror - original)
            result["samples"] = samples
            largest = max(s.get("abs_difference_c", 0) for s in samples.values())
            result["passed"] = largest <= TOLERANCE + 1e-12
            if not result["passed"]:
                result["error"] = f"Maximum difference {largest:.6f} °C exceeds {TOLERANCE} °C"
        except (OSError, ValueError, RuntimeError) as exc:
            result.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            # TIFF parsers can wrap a failed metadata read in a format error.
            if reader.last_status is not None and reader.last_status >= 400:
                result["http_status"] = reader.last_status
                result["retry_after"] = reader.retry_after
        return dict(
            **result,
            etag=reader.etag,
            file_bytes=reader.size,
            requests=reader.requests,
            response_body_bytes=reader.bytes,
            seconds=round(monotonic() - start, 3),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+", type=date.fromisoformat)
    parser.add_argument(
        "--variables", nargs="+", choices=["Tmin", "Tmax"], default=["Tmax", "Tmin"]
    )
    parser.add_argument("--min-request-interval", type=float, default=3.0)
    parser.add_argument("--output", type=Path, default=OUT / "daily-strips.json")
    args = parser.parse_args()
    if not 0 <= args.min_request_interval < 45:
        parser.error("Request interval must be between zero and the 45-second file budget")
    OUT.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        toolkit_version=version("climate-toolkit"),
        points=POINTS,
        tolerance_c=TOLERANCE,
        min_request_interval=args.min_request_interval,
        cases=[],
    )
    for day in args.dates:
        frame = fetch_climate_data(
            "chirts_era5",
            backend="huggingface",
            allow_gee=False,
            sites=POINTS,
            date_from=day,
            date_to=day,
            stage="raw",
            cache_dir=str(OUT / "mirror-cache"),
            verbose=False,
        )
        (info,) = frame.attrs["data_provenance"]
        if info["backend"] != "huggingface" or not frame.date.eq(str(day)).all():
            raise ValueError(f"Unexpected mirror source or dates for {day}")
        cells = {c["site"]: [c["lat"], c["lon"]] for c in info["selected_cells"]}
        grid = frame.set_index("site", verify_integrity=True)
        case = dict(date=str(day), revision=info["revision"], mirror_cells=cells, files=[])
        report["cases"].append(case)
        for variable in args.variables:
            file = compare_file(day, variable, grid, cells, args.min_request_interval)
            case["files"].append(file)
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
            print(day, variable, file["passed"], file.get("error", ""), flush=True)
            if file.get("http_status") == 429:
                raise SystemExit(f"CHC rate limited requests. Retry-After: {file['retry_after']}")
    if not all(f["passed"] for c in report["cases"] for f in c["files"]):
        raise SystemExit("One or more original comparisons failed")


if __name__ == "__main__":
    main()
