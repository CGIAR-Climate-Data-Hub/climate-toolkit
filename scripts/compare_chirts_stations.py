"""Opt-in comparison of published CHIRTS-ERA5 with NOAA GHCN-Daily stations.

Run with Python 3.12+ and the installed climate-toolkit cloud extra. Downloads
are anonymous. Local input snapshots, matched dates and results live under
outputs/validation/issue-178. Delete a station snapshot to fetch a new revision.
"""

from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
import requests

from climate_toolkit import fetch_climate_data
from climate_toolkit.weather_station.compare import _compute_variable_metrics
from climate_toolkit.weather_station.ghcn_daily import (
    STATIONS_URL,
    STATION_DLY_TEMPLATE,
    _parse_dly_text,
    _parse_station_line,
)

ROOT = Path(__file__).resolve().parents[1] / "outputs/validation/issue-178"
STATIONS = ("KE000063740", "UVM00065503", "PEM00084686")
WINDOWS = [(date(1994, 1, 1), date(1995, 12, 31)), (date(2023, 1, 1), date(2024, 12, 31))]
ELEMENTS = {"TMAX": "Tmax", "TMIN": "Tmin"}


def snapshot(url):
    path = ROOT / "stations" / url.rsplit("/", 1)[1]
    if not path.exists():
        response = requests.get(url, timeout=(10, 60))
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(response.content)
        Path(tmp.name).replace(path)
    data = path.read_bytes()
    return data.decode("ascii"), {"url": url, "sha256": hashlib.sha256(data).hexdigest()}


def station_frame(text, station_id, start, end):
    frame = _parse_dly_text(text, requested_elements=set(ELEMENTS), date_from=start, date_to=end)
    if frame.empty:
        return pd.DataFrame(
            index=pd.DatetimeIndex([], name="date"), columns=list(ELEMENTS.values()), dtype=float
        )
    if not frame.station_id.eq(station_id).all():
        raise ValueError(f"Station ID mismatch for {station_id}")
    # The toolkit parser already excludes -9999 and nonblank NOAA quality flags.
    return (
        frame.set_index("date", verify_integrity=True)
        .reindex(columns=list(ELEMENTS))
        .rename(columns=ELEMENTS)
        / 10
    )


def compare(station, dates, grid, observations):
    model = grid.set_index("date", verify_integrity=True).sort_index()
    if not model.index.as_unit("ns").equals(dates.as_unit("ns")):
        raise ValueError(f"Incomplete CHIRTS dates at {station}")
    data = model[["Tmax", "Tmin"]].join(observations, lsuffix="_grid", rsuffix="_station")
    obs_cols = ["Tmax_station", "Tmin_station"]
    observed = data[obs_cols]
    inverted = observed.Tmax_station.lt(observed.Tmin_station)
    outside = (observed < -90) | (observed > 60)
    data[obs_cols] = observed.mask(outside)
    data.loc[inverted, obs_cols] = np.nan
    data = data.reset_index()
    stats = {}
    for variable in ELEMENTS.values():
        pairs = data[[variable + "_grid", variable + "_station"]].dropna()
        metrics = _compute_variable_metrics(data, variable=variable)
        record = dict(
            days=len(dates), paired_days=len(pairs), missing_station_days=len(dates) - len(pairs)
        )
        if metrics:
            record.update(
                {
                    key: metrics[key]
                    for key in ("station_mean", "grid_mean", "bias", "mae", "rmse", "correlation")
                }
            )
            if variable == "Tmax":
                grid_hot = pairs.Tmax_grid.ge(35)
                station_hot = pairs.Tmax_station.ge(35)
                record["days_ge_35c"] = dict(
                    station=int(station_hot.sum()),
                    grid=int(grid_hot.sum()),
                    hits=int((grid_hot & station_hot).sum()),
                    misses=int((~grid_hot & station_hot).sum()),
                    false_alarms=int((grid_hot & ~station_hot).sum()),
                )
        stats[variable] = record
    return data, dict(
        station_inverted_days=int(inverted.sum()),
        station_outside_range_values=int(outside.sum().sum()),
        variables=stats,
    )


def main():
    index, index_info = snapshot(STATIONS_URL)
    stations = {
        line[:11]: _parse_station_line(line) for line in index.splitlines() if line[:11] in STATIONS
    }
    if set(stations) != set(STATIONS):
        raise ValueError("Missing station metadata")
    sites = [(s, stations[s]["lat"], stations[s]["lon"]) for s in STATIONS]
    observations = {}
    report = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        toolkit=version("climate-toolkit"),
        station_index=index_info,
        stations={},
        windows=[],
    )
    for s in STATIONS:
        observations[s], source = snapshot(STATION_DLY_TEMPLATE.format(station_id=s))
        report["stations"][s] = {**stations[s], **source}
    daily = []
    for start, end in WINDOWS:
        dates = pd.date_range(start, end, name="date")
        grid = fetch_climate_data(
            "chirts_era5",
            backend="huggingface",
            allow_gee=False,
            sites=sites,
            date_from=start,
            date_to=end,
            stage="raw",
            workers=2,
            cache_dir=str(ROOT / "station-grid-cache"),
            verbose=False,
        )
        if grid.attrs["quality_control"]["flagged_rows"] or set(grid.site) != set(STATIONS):
            raise ValueError("Incomplete or QC-flagged station grid sample")
        provenance = grid.attrs["data_provenance"]
        if not provenance or any(r["backend"] != "huggingface" for r in provenance):
            raise ValueError("Unexpected grid provenance")
        info = dict(
            start=str(start),
            end=str(end),
            stations={},
            provenance=[
                {k: r[k] for k in ("backend", "revision", "window", "selected_cells", "coverage")}
                for r in provenance
            ],
        )
        for s in STATIONS:
            frame, stats = compare(
                s, dates, grid.loc[grid.site == s], station_frame(observations[s], s, start, end)
            )
            daily.append(frame.assign(station=s))
            info["stations"][s] = stats
        report["windows"].append(info)
        print(start, end, "complete", flush=True)
    out = ROOT / "station-pairs.csv"
    pd.concat(daily, ignore_index=True).to_csv(out, index=False)
    report["daily_csv_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    (ROOT / "station-summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
