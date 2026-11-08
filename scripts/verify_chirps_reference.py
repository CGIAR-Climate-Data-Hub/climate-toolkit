"""Opt-in CHIRPS v3 final/RNL mirror validation against native Earth Engine pixels.

Run with Python 3.12+, climate-toolkit[cloud], and an authenticated GCP_PROJECT_ID.
Use --grid-only for the separate anonymous land, ocean and boundary checks.
Direct toolkit calls explicitly disable Earth Engine. Only the reference uses it.
"""

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from climate_toolkit import fetch_climate_data


COLLECTION = "UCSB-CHC/CHIRPS/V3/DAILY_RNL"
SITES = [("Nairobi", -1.286, 36.817), ("Ouagadougou", 12.37, -1.53), ("Cusco", -13.52, -71.97)]
WINDOWS = [("2019-12-01", "2020-02-29"), ("2025-12-01", "2026-02-28")]
PROVIDERS = ("dynamical", "huggingface")
OUTPUT = Path(__file__).resolve().parents[1] / "outputs/validation/issue-177"


def reference(days):
    images = (
        ee.ImageCollection(COLLECTION)
        .filterDate(days[0].date().isoformat(), (days[-1].date() + timedelta(days=1)).isoformat())
        .select("precipitation")
        .sort("system:time_start")
    )
    grid = images.first().projection()
    # Name bands by the producer timestamp. Sampling a stack avoids one RPC per day.
    bands = images.map(
        lambda im: im.unmask(-9999).set("system:index", im.date().format("yyyyMMdd"))
    ).toBands()
    points = ee.FeatureCollection(
        [ee.Feature(ee.Geometry.Point([lon, lat]), {"site": site}) for site, lat, lon in SITES]
    )
    rows, cells = [], {}
    for f in bands.sampleRegions(collection=points, projection=grid, geometries=True).getInfo()[
        "features"
    ]:
        site = f["properties"]["site"]
        cells[site] = f["geometry"]["coordinates"]
        for day in days:
            value = f["properties"][day.strftime("%Y%m%d_precipitation")]
            rows.append((site, day, value if value != -9999 else np.nan))
    return pd.DataFrame(rows, columns=["site", "date", "reference"]), cells, grid.getInfo()


def validate_grid():
    """Check matching direct-provider cells and ocean masks without EE access."""
    from climate_toolkit.fetch_data.direct_cloud import DataQualityError

    # (requested site, lat, lon), expected centre (lat, lon), expected ocean mask.
    cases = [
        (("Mombasa", -4.047, 39.668), (-4.025, 39.675), False),
        (("offshore", -4.047, 39.905), (-4.025, 39.925), True),
        (("grid-boundary", -4.05, 39.70), (-4.075, 39.675), False),
        (("west", 0, -180), (-0.025, -179.975), True),
        (("east", 0, 180), (-0.025, 179.975), True),
        (("north", 60, -150.02), (59.975, -150.025), False),
        (("south", -60, -150.02), (-59.975, -150.025), True),
    ]
    report = {}
    day = date(2020, 2, 29)
    for provider in PROVIDERS:
        kwargs = dict(
            source="chirps_v3_daily_rnl",
            sites=[site for site, _, _ in cases],
            backend=provider,
            allow_gee=False,
            date_from=day,
            date_to=day,
            cache_dir=str(OUTPUT / "grid-cache"),
            verbose=False,
        )
        raw = fetch_climate_data(stage="raw", **kwargs)
        (record,) = raw.attrs["data_provenance"]
        cells = {c["site"]: (c["lat"], c["lon"]) for c in record["selected_cells"]}
        values = raw.set_index("site", verify_integrity=True).precipitation
        for (site, _, _), centre, masked in cases:
            if not np.allclose(cells[site], centre, rtol=0, atol=1e-5):
                raise ValueError(f"Unexpected cell: {provider}, {site}, {cells[site]}")
            if pd.isna(values[site]) != masked:
                raise ValueError(f"Unexpected land mask: {provider}, {site}")
        try:
            fetch_climate_data(stage="preprocessed", **kwargs)
        except DataQualityError:
            pass
        else:
            raise ValueError(f"{provider} accepted ocean nodata for analysis")
        for latitude, longitude in [(60.01, 0), (-60.01, 0), (0, 180.01), (0, -180.01)]:
            try:
                fetch_climate_data(
                    **{**kwargs, "sites": [("outside", latitude, longitude)]}, stage="raw"
                )
            except ValueError as exc:
                if "outside" not in str(exc).lower():
                    raise
            else:
                raise ValueError(f"{provider} accepted coordinates outside the CHIRPS domain")
        report[provider] = dict(
            revision=record["revision"],
            cells=cells,
            values_mm={name: None if pd.isna(v) else v for name, v in values.items()},
            qc=raw.attrs["quality_control"],
        )
    (OUTPUT / "grid.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grid-only",
        action="store_true",
        help="Check direct access and grid edges without Earth Engine",
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.grid_only:
        validate_grid()
        return
    ee.Initialize(project=os.environ["GCP_PROJECT_ID"])
    parts = []
    windows = []
    for start, end in WINDOWS:
        days = pd.date_range(start, end)
        df, cells, grid = reference(days)
        expected = pd.MultiIndex.from_product([[s[0] for s in SITES], days], names=["site", "date"])
        df = df.set_index(["site", "date"], verify_integrity=True).sort_index()
        if not df.index.equals(expected.sort_values()):
            raise ValueError(f"Reference does not cover the expected site-days for {start}")
        info = dict(start=start, end=end, reference_cells=cells, grid=grid, providers={})
        for provider in PROVIDERS:
            print(f"{start}..{end}: {provider}", flush=True)
            data = fetch_climate_data(
                source="chirps_v3_daily_rnl",
                backend=provider,
                allow_gee=False,
                sites=SITES,
                date_from=days[0].date(),
                date_to=days[-1].date(),
                stage="preprocessed",
                cache_dir=str(OUTPUT / "cache"),
                verbose=False,
            )
            records = data.attrs["data_provenance"]
            for record in records:
                if record["backend"] != provider:
                    raise ValueError(f"Unexpected provider: {record['backend']}")
                for cell in record["selected_cells"]:
                    if not np.allclose(
                        cells[cell["site"]], [cell["lon"], cell["lat"]], rtol=0, atol=1e-5
                    ):
                        raise ValueError(f"Different pixels: {provider}, {cell}")
            info["providers"][provider] = [
                {
                    "revision": p["revision"],
                    "window": p["window"],
                    "selected_cells": p["selected_cells"],
                }
                for p in records
            ]
            series = data.set_index(
                ["site", "date"], verify_integrity=True
            ).precipitation.sort_index()
            if not series.index.equals(df.index):
                raise ValueError(f"Unexpected site-days for {provider}, {start}")
            df[provider] = series
        parts.append(df.reset_index().assign(season=start))
        windows.append(info)
    daily = pd.concat(parts, ignore_index=True)
    summary = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        toolkit=version("climate-toolkit"),
        reference=COLLECTION,
        windows=windows,
        site_days=len(daily),
        providers={},
    )
    for provider in PROVIDERS:
        error = (daily[provider] - daily.reference).abs()
        tolerance = (0.05 if provider == "huggingface" else daily.reference.abs() / 256) + 1e-5
        summary["providers"][provider] = dict(
            max_abs_mm=error.max(),
            mean_abs_mm=error.mean(),
            out_of_tolerance=int((error > tolerance).sum()),
            wet_gt_1mm_disagreements=int(((daily[provider] > 1) != (daily.reference > 1)).sum()),
            wet_ge_1mm_disagreements=int(((daily[provider] >= 1) != (daily.reference >= 1)).sum()),
        )
    measures = ["reference", *PROVIDERS]
    summary["missing_days"] = daily[measures].isna().sum().to_dict()
    daily["month"] = daily.date.dt.strftime("%Y-%m")
    for period in ("month", "season"):
        totals = daily.groupby(["site", period])[measures].sum(min_count=1)
        totals.to_csv(OUTPUT / f"{period}-totals.csv")
        for provider in PROVIDERS:
            summary["providers"][provider][f"max_abs_{period}_total_difference_mm"] = (
                (totals[provider] - totals.reference).abs().max()
            )
    path = OUTPUT / "daily.csv"
    daily.to_csv(path, index=False)
    summary["daily_csv_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary["providers"], indent=2))
    if any(summary["missing_days"].values()) or any(
        r["out_of_tolerance"] for r in summary["providers"].values()
    ):
        raise SystemExit(
            "Sample contains missing or out-of-tolerance observations; inspect daily.csv"
        )


if __name__ == "__main__":
    main()
