"""Reproduce the Kapiti MOD13Q1.061 pilot with requests, rasterio, numpy and matplotlib."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import partial
import csv
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import time

import numpy as np
import requests

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/modiseuwest/modis-061-cogs"
LON, LAT = 37.133, -1.614
BANDS = ("NDVI", "EVI", "VI_Quality")
SEASONS = {
    "long_rains": (65, 81, 97, 113, 129),
    "dry": (193, 209, 225, 241, 257),
    "short_rains": (289, 305, 321, 337, 353),
}
FIRST, LAST = 2001, 2025
BASELINE = range(2001, 2021)
# Fixed native-grid footprint around the published Kapiti rangeland flux site.
ROW, COL = 774, 3416


def catalogue(year):
    params = {
        "collections": "modis-13Q1-061",
        "bbox": f"{LON - 0.001},{LAT - 0.001},{LON + 0.001},{LAT + 0.001}",
        "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
        "limit": 100,
    }
    response = requests.get(STAC, params=params, timeout=60)
    response.raise_for_status()
    page = response.json()
    if any(link["rel"] == "next" for link in page["links"]):
        raise ValueError(f"Incomplete catalogue page for {year}")
    items = {}
    wanted = {day for season in SEASONS.values() for day in season}
    for item in page["features"]:
        parts = item["id"].split(".")
        if parts[0] != "MOD13Q1" or parts[2:4] != ["h21v09", "061"]:
            continue
        if int(parts[1][1:5]) != year:
            continue  # STAC interval intersection can include the previous December.
        day = int(parts[1][-3:])
        if day in wanted:
            if day in items and item["id"] <= items[day]["id"]:
                continue  # Keep newest processing timestamp for this Terra date and tile.
            items[day] = {
                "id": item["id"],
                "assets": [item["assets"]["250m_16_days_" + b]["href"] for b in BANDS],
            }
    return list(items.values())


def read_window(item, folder, token):
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import Window

    dest = folder / (item["id"] + ".npz")
    if dest.exists():
        return
    arrays = {}
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="30",
        GDAL_HTTP_CONNECTTIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="2",
        GDAL_CACHEMAX=16 * 1024**2,
    ):
        for band, href in zip(BANDS, item["assets"]):
            # Keep the signed URL in memory. Persist only unsigned catalogue links.
            with rasterio.open("/vsicurl/" + href + "?" + token) as ds:
                x, y = transform("EPSG:4326", ds.crs, [LON], [LAT])
                if ds.index(x[0], y[0]) != (ROW, COL) or ds.shape != (4800, 4800):
                    raise ValueError(f"Unexpected native grid for {item['id']}")
                arrays[band] = ds.read(1, window=Window(COL - 4, ROW - 4, 9, 9))
    with NamedTemporaryFile(dir=folder, suffix=".npz", delete=False) as tmp:
        np.savez_compressed(tmp, **arrays)
    os.replace(tmp.name, dest)


def fetch(folder, workers):
    manifest = folder / "catalogue.json"
    with ThreadPoolExecutor(max_workers=workers) as pool:
        if not manifest.exists():
            items = [
                item for group in pool.map(catalogue, range(FIRST, LAST + 1)) for item in group
            ]
            manifest.write_text(json.dumps(items, indent=1))
        items = json.loads(manifest.read_text())
        remaining = [i for i in items if not (folder / (i["id"] + ".npz")).exists()]
        print(f"{len(items)} granules catalogued, {len(remaining)} to read", flush=True)
        if remaining:
            reply = requests.get(TOKEN, timeout=30)
            reply.raise_for_status()
            download = partial(read_window, folder=folder, token=reply.json()["token"])
            for count, _ in enumerate(pool.map(download, remaining), 1):
                if count % 50 == 0:
                    print(f"Read {count}/{len(remaining)}", flush=True)


def fill_missing(folder):
    """Request only absent Terra acquisitions from the NASA ORNL subset service."""
    items = json.loads((folder / "catalogue.json").read_text())
    existing = {item["id"].split(".")[1] for item in items}
    needed = [
        f"A{year}{day:03}"
        for year in range(FIRST, LAST + 1)
        for days in SEASONS.values()
        for day in days
        if f"A{year}{day:03}" not in existing
    ]
    # Use one request at a time for this small number of missing composites.
    for stamp in needed:
        params = dict(
            latitude=LAT,
            longitude=LON,
            startDate=stamp,
            endDate=stamp,
            kmAboveBelow=1,
            kmLeftRight=1,
        )
        raw = folder / (stamp + ".json")
        if not raw.exists():
            reply = requests.get(
                "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset", params=params, timeout=90
            )
            reply.raise_for_status()
            raw.write_bytes(reply.content)
        result = json.loads(raw.read_text())
        if (result["nrows"], result["ncols"]) != (9, 9) or not np.allclose(
            [float(result[k]) for k in ("xllcorner", "yllcorner", "cellsize")],
            [4126263.09, -180460.34, 231.656358264],
            rtol=0,
            atol=0.02,
        ):
            raise ValueError(f"ORNL subset grid differs for {stamp}")
        records = {r["band"]: r for r in result["subset"]}
        arrays, versions = {}, set()
        for band in BANDS:
            record = records["250m_16_days_" + band]
            if record["tile"] != "h21v09" or record["modis_date"] != stamp:
                raise ValueError(f"ORNL date or tile differs for {stamp}")
            versions.add(record["proc_date"])
            arrays[band] = np.asarray(
                record["data"], dtype="uint16" if band == "VI_Quality" else "int16"
            ).reshape(9, 9)
        if len(versions) != 1:
            raise ValueError(f"Mixed ORNL processing dates for {stamp}")
        item_id = f"MOD13Q1.{stamp}.h21v09.061.{versions.pop()}"
        np.savez_compressed(folder / (item_id + ".npz"), **arrays)
        items.append({"id": item_id, "source": "ORNL"})
    subset_ids = {item["id"] for item in items if item.get("source") == "ORNL"}
    if subset_ids:
        query = [("short_name", "MOD13Q1"), ("version", "061"), ("page_size", len(subset_ids))]
        query += [("producer_granule_id[]", item_id) for item_id in sorted(subset_ids)]
        response = requests.get(
            "https://cmr.earthdata.nasa.gov/search/granules.json", params=query, timeout=30
        )
        response.raise_for_status()
        if {g["producer_granule_id"] for g in response.json()["feed"]["entry"]} != subset_ids:
            raise ValueError("ORNL processing identifiers do not match NASA Collection 6.1")
    (folder / "combined.json").write_text(json.dumps(items, indent=1))


def valid_pixels(ndvi, evi, quality):
    # Collection 6.1 detailed VI QA: good MODLAND, high usefulness, land,
    # low/intermediate/climatological aerosol, clear of clouds, snow and shadow.
    return (
        ((quality & 3) == 0)
        & (((quality >> 2) & 15) <= 2)
        & (((quality >> 6) & 3) != 3)
        & (((quality >> 11) & 7) == 1)
        & ((quality & ((1 << 8) | (1 << 10) | (1 << 14) | (1 << 15))) == 0)
        & (ndvi >= -2000)
        & (ndvi <= 10000)
        & (evi >= -2000)
        & (evi <= 10000)
    )


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(folder):
    observations = {}
    for item in json.loads((folder / "combined.json").read_text()):
        when = datetime.strptime(item["id"].split(".")[1], "A%Y%j").date()
        with np.load(folder / (item["id"] + ".npz")) as data:
            mask = valid_pixels(*(data[b] for b in BANDS))
            values = [
                float(data[b][mask].mean()) * 0.0001 if mask.any() else np.nan for b in BANDS[:2]
            ]
        key = when.year, when.timetuple().tm_yday
        observations[key] = (
            item["id"],
            item.get("source", "Planetary Computer"),
            int(mask.sum()),
            *values,
        )
    rows = []
    for year in range(FIRST, LAST + 1):
        for season, days in SEASONS.items():
            for day in days:
                item_id, source, count, ndvi, evi = observations.get(
                    (year, day), ("", "", 0, np.nan, np.nan)
                )
                rows.append(
                    dict(
                        year=year,
                        season=season,
                        day=day,
                        date=date(year, 1, 1) + timedelta(days=day - 1),
                        granule=item_id,
                        source=source,
                        valid_pixels=count,
                        total_pixels=81,
                        ndvi=ndvi,
                        evi=evi,
                    )
                )
    write_csv(folder / "composites.csv", rows)
    return rows


def slope_grid(matrix, years):
    """Median pairwise slope comparing only the same composite slot across years."""
    i, j = np.triu_indices(len(years), 1)
    different = years[i] != years[j]
    i, j = i[different], j[different]
    slopes = (matrix[j] - matrix[i]) / (years[j] - years[i])[:, None]
    valid = slopes[np.isfinite(slopes)]
    return float(np.median(valid)) if valid.size else np.nan


def trend(matrix):
    years = np.arange(FIRST, LAST + 1)
    year_count = int(np.isfinite(matrix).any(axis=1).sum())
    slot_years = np.isfinite(matrix).sum(axis=0)
    result = dict(
        years=year_count,
        valid_composites=int(np.isfinite(matrix).sum()),
        years_per_slot=slot_years.tolist(),
    )
    if year_count < 10 or np.min(slot_years) < 5:
        return dict(result, slope_per_decade=None)
    slope = slope_grid(matrix, years)
    # Sample whole, contiguous three-year blocks. Keep the five slots and both
    # their original dates and gaps together when weighting pairwise slopes.
    rng = np.random.default_rng(92)
    boot = []
    for _ in range(1000):
        starts = rng.integers(len(years), size=(len(years) + 2) // 3)
        indices = ((starts[:, None] + np.arange(3)) % len(years)).ravel()[: len(years)]
        boot.append(slope_grid(matrix[indices], years[indices]))
    lo, hi = np.nanquantile(boot, [0.025, 0.975])
    return dict(
        result,
        slope_per_decade=round(slope * 10, 5),
        interval_95=[round(float(lo) * 10, 5), round(float(hi) * 10, 5)],
        interior_slope=round(slope_grid(matrix[2:-2], years[2:-2]) * 10, 5),
    )


def analyze(folder, composites):
    results, summaries = [], []
    years = np.arange(FIRST, LAST + 1)
    for fraction in (0.50, 0.75, 1.0):
        for season, days in SEASONS.items():
            for index in ("ndvi", "evi"):
                matrix = np.full((len(years), len(days)), np.nan)
                for r in composites:
                    if r["season"] == season and r["valid_pixels"] >= 81 * fraction:
                        matrix[r["year"] - FIRST, days.index(r["day"])] = r[index]
                results.append(
                    dict(season=season, index=index, pixel_fraction=fraction, **trend(matrix))
                )
                for i, year in enumerate(years):
                    history = matrix[np.isin(years, BASELINE) & (years != year)]
                    counts = np.isfinite(history).sum(axis=0)
                    slots = np.flatnonzero(np.isfinite(matrix[i]) & (counts >= 5))
                    anomaly = None
                    if len(slots) >= 3:
                        typical = np.nanmedian(history[:, slots], axis=0)
                        anomaly = round(float(np.median(matrix[i, slots] - typical)), 5)
                    summaries.append(
                        dict(
                            year=year,
                            season=season,
                            index=index,
                            pixel_fraction=fraction,
                            matched_slots=len(slots),
                            reference_years_min=int(counts[slots].min()) if len(slots) else 0,
                            anomaly=anomaly,
                        )
                    )
    write_csv(folder / "seasonal_anomalies.csv", summaries)
    (folder / "trends.json").write_text(json.dumps(results, indent=2) + "\n")


def draw_example(folder, composites, year=2024):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(10, 5), sharey="row", layout="constrained")
    for ax_row, index in zip(axes, ("ndvi", "evi")):
        for ax, (season, days) in zip(ax_row, SEASONS.items()):
            target, bands = [], []
            for day in days:
                group = [r for r in composites if r["day"] == day and r["valid_pixels"] >= 41]
                ref = [r[index] for r in group if r["year"] in BASELINE and r["year"] != year]
                bands.append(np.quantile(ref, [0.1, 0.5, 0.9]) if len(ref) >= 5 else [np.nan] * 3)
                target.append(next((r[index] for r in group if r["year"] == year), np.nan))
            low, mid, high = np.transpose(bands)
            dates = [date(year, 1, 1) + timedelta(days=d - 1) for d in days]
            ax.fill_between(days, low, high, color="#cce8df", label="2001–20 central 80%")
            ax.plot(days, mid, ".-", color="#307360", label="Reference median")
            ax.plot(days, target, "o-", color="#93440f", label=f"{year} observed")
            ax.set_xticks(days[::2], [d.strftime("%d %b") for d in dates[::2]])
            ax.spines[["right", "top"]].set_visible(False)
            if ax is ax_row[0]:
                ax.set_ylabel(index.upper())
    for ax, title in zip(axes[0], ("Long rains", "Dry season", "Short rains")):
        ax.set_title(title)
    axes[1, 0].legend(loc="upper left", fontsize=7, frameon=False)
    fig.suptitle(f"Kapiti grazing site, Kenya · {year} vegetation greenness")
    fig.savefig(folder / "kapiti_seasons.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/validation/issue-92/kapiti"))
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--offline", action="store_true", help="Use an existing complete cache")
    parser.add_argument(
        "--from-composites",
        type=Path,
        help="Analyze a saved composite CSV without fetching imagery",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    if args.from_composites:
        with args.from_composites.open() as stream:
            composites = [
                dict(
                    r,
                    year=int(r["year"]),
                    day=int(r["day"]),
                    valid_pixels=int(r["valid_pixels"]),
                    ndvi=float(r["ndvi"]),
                    evi=float(r["evi"]),
                )
                for r in csv.DictReader(stream)
            ]
    else:
        if not args.offline:
            fetch(args.output, args.workers)
            fill_missing(args.output)
        composites = summarize(args.output)
    analyze(args.output, composites)
    draw_example(args.output, composites)
    print(f"Finished in {time.monotonic() - start:.1f} s")
