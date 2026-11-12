"""Compare the same CHIRTS-ERA5 cells across the three October 2026 mirror snapshots."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import requests
import xarray as xr

from compare_chirts_originals import SITES

REPO = "aaguilar90/chirts-era5-daily"
BASE = f"https://huggingface.co/datasets/{REPO}"
REVISIONS = (
    "a4be603034d0a32d4a827295bbad8c617626b5ab",
    "c44a0b58772e32f7cbb2b5a740d5e6586ceeb054",
    "35669afbbd1c6ab84dcc496f2f95b7cbbf75867f",
)
POINTS = [*SITES, ("Pacific", 0.025, -150.025)]
MANIFEST = "chirts_daily_era5.zarr.chirts-state.json"
START, END = "2026-09-28", "2026-10-21"


def snapshot(revision):
    record = requests.get(f"{BASE}/raw/{revision}/{MANIFEST}", timeout=30)
    record.raise_for_status()
    days = record.json()["days"]
    store = f"{BASE}/resolve/{revision}/chirts-era5-daily.zarr"
    with xr.open_zarr(store, consolidated=True, chunks={}) as ds:
        grid = (
            ds[["Tmin", "Tmax"]]
            .sel(time=slice(START, END))
            .sel(
                lat=xr.DataArray([p[1] for p in POINTS], dims="site"),
                lon=xr.DataArray([p[2] for p in POINTS], dims="site"),
                method="nearest",
            )
            .load()
        )
    cells = list(zip(grid.lat.values.tolist(), grid.lon.values.tolist()))
    rows = {}
    for time in grid.time.values:
        day = str(time)[:10]
        for variable in ("Tmin", "Tmax"):
            # Missing manifest entries mean unknown provenance even when the array contains data.
            entry = days[variable.lower()].get(day)
            raw = grid[variable].sel(time=time).values
            if not np.isfinite(raw[:-1]).all() or not np.isnan(raw[-1]):
                raise ValueError(f"Unexpected land/ocean mask for {day} {variable}")
            values = [round(float(v), 1) for v in raw[:-1]] + [None]
            rows[(day, variable)] = dict(values_c=values, manifest=entry)
    return cells, rows


def audit():
    snapshots = [snapshot(sha) for sha in REVISIONS]
    cells = snapshots[0][0]
    if any(current_cells != cells for current_cells, _ in snapshots[1:]):
        raise ValueError("Selected cells differ across mirror revisions")
    changes = []
    for i in range(1, len(snapshots)):
        old, new = snapshots[i - 1][1], snapshots[i][1]
        overlap = sorted(old.keys() & new.keys())
        changed = [
            dict(day=day, variable=var, earlier=old[(day, var)], later=new[(day, var)])
            for day, var in overlap
            if old[(day, var)]["values_c"] != new[(day, var)]["values_c"]
        ]
        changes.append(
            dict(
                earlier=REVISIONS[i - 1],
                later=REVISIONS[i],
                compared_date_variable_pairs=len(overlap),
                changed=changed,
            )
        )

    target = snapshots[-1][1][(END, "Tmin")]
    producer = requests.head(target["manifest"]["source"], timeout=20, allow_redirects=True)
    producer.raise_for_status()
    return dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        sites=[p[0] for p in POINTS],
        cells_lat_lon=cells,
        window=[START, END],
        transitions=changes,
        endpoints=[max(day for day, _ in rows) for _, rows in snapshots],
        target=dict(
            day=END,
            variable="Tmin",
            mirror=target,
            original_headers={
                k: producer.headers.get(k) for k in ("Last-Modified", "ETag", "Content-Length")
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/validation/issue-179-revisions/revision-history.json"),
    )
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
