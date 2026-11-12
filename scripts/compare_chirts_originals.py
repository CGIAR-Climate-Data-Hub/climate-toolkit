"""Compare live anonymous CHIRTS-ERA5 toolkit reads with locally downloaded CHC daily TIFFs."""

import argparse
from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from climate_toolkit import fetch_climate_data


SITES = [("Nairobi", -1.286, 36.817), ("Ouagadougou", 12.37, -1.53), ("Cusco", -13.52, -71.97)]
ARCHIVE = "https://data.chc.ucsb.edu/experimental/CHIRTS-ERA5"


def compare_day(day, directory, cache):
    import rasterio

    frame = fetch_climate_data(
        sites=SITES,
        source="chirts_era5",
        backend="huggingface",
        allow_gee=False,
        stage="raw",
        date_from=day,
        date_to=day,
        cache_dir=cache,
        verbose=False,
    )
    if frame.attrs["quality_control"]["flagged_rows"]:
        raise ValueError(f"Toolkit QC flagged temperatures for {day}")
    (info,) = frame.attrs["data_provenance"]
    cells = {c["site"]: (c["lon"], c["lat"]) for c in info["selected_cells"]}
    if len(frame) != len(SITES) or not frame["date"].eq(str(day)).all():
        raise ValueError(f"Unexpected rows for {day}")
    values = frame.set_index("site", verify_integrity=True)
    originals = []
    samples = []
    for variable in ("Tmin", "Tmax"):
        name = f"CHIRTS-ERA5.daily_{variable}.{day:%Y.%m.%d}.tif"
        path = directory / name
        with path.open("rb") as f:
            sha256 = hashlib.file_digest(f, "sha256").hexdigest()
        originals.append(
            dict(
                variable=variable,
                sha256=sha256,
                url=f"{ARCHIVE}/{variable.lower()}/tifs/daily/{day.year}/{name}",
            )
        )
        with rasterio.open(path) as tif:
            if tif.crs.to_epsg() != 4326 or tif.count != 1:
                raise ValueError(f"Unexpected raster schema: {name}")
            for site, lat, lon in SITES:
                row, col = tif.index(lon, lat)
                centre = tif.xy(row, col)
                if not np.allclose(centre, cells[site], rtol=0, atol=1e-4):
                    raise ValueError(f"Different grid cells: {name}, {site}")
                sample = next(tif.sample([(lon, lat)], masked=True))[0]
                if np.ma.is_masked(sample):
                    raise ValueError(f"Missing original: {name}, {site}")
                original = float(sample)
                mirror = float(values.at[site, variable])
                if not np.isfinite([original, mirror]).all():
                    raise ValueError(f"Non-finite temperature: {name}, {site}")
                samples.append(
                    dict(
                        site=site,
                        variable=variable,
                        chc_cell_lon_lat=centre,
                        mirror_cell_lon_lat=cells[site],
                        original_c=original,
                        toolkit_c=mirror,
                        abs_difference_c=abs(original - mirror),
                    )
                )
    return dict(
        date=day.isoformat(), mirror_revision=info["revision"], originals=originals, samples=samples
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory containing CHC daily GeoTIFFs")
    parser.add_argument("dates", nargs="+", type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as cache:
        days = [compare_day(day, args.directory, cache) for day in args.dates]
    maximum = max(s["abs_difference_c"] for day in days for s in day["samples"])
    report = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        toolkit_version=version("climate-toolkit"),
        sites=SITES,
        tolerance_c=0.05,
        max_abs_difference_c=maximum,
        days=days,
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    if maximum > 0.05 + 1e-12:
        raise SystemExit(f"Maximum difference exceeds packing tolerance: {maximum} C")


if __name__ == "__main__":
    main()
