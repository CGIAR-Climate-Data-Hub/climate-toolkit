"""Station diagnostics must use exactly the days and aggregates behind the metrics."""

import base64
import io
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from climate_toolkit.weather_station import compare


def test_paired_periods_and_report(tmp_path, monkeypatch):
    dates = pd.to_datetime(["2019-12-31", "2020-01-01", "2020-02-29", "2020-03-01"])
    stations = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "station_id": ["A"] * 4 + ["B"] * 4,
            "station_name": ["<Gauge>"] * 4 + ["Second"] * 4,
            "station_lat": [0.0] * 4 + [1.0] * 4,
            "station_lon": [0.0] * 8,
            "precipitation": [0, 2, None, 8, 4, None, 6, 8],
            "min_temperature": [10, 20, None, 30, 10, 20, 30, 40],
        }
    )

    def grid(source, **kwargs):
        if source == "paired":
            raise ValueError("temporarily <unavailable>")
        return pd.DataFrame(
            {"date": dates, "precipitation": [2, 3, 1, 10], "min_temperature": [14, 24, 34, 44]}
        )

    monkeypatch.setattr(compare, "download_station_data", lambda **kw: stations.copy())
    monkeypatch.setattr(compare, "_fetch_grid_source", grid)
    opts = dict(
        station_source="ghcn_daily",
        station_coord=(0, 0),
        date_from=date(2019, 12, 31),
        date_to=date(2020, 3, 1),
        grid_sources=["era5_land", "paired"],
        variables=["precipitation", "min_temperature"],
        auto_select="auto-2",
        disable_completeness_guard=True,
        auto_anchor_elevation=False,
        verbose=False,
    )
    baseline = compare.compare_station_to_grids(**opts)
    path = tmp_path / "nested" / "diagnostics.html"
    report = compare.compare_station_to_grids(**opts, diagnostics_html=path)
    assert Path(report.pop("diagnostics_html")) == path
    assert report == baseline
    html = path.read_text()
    assert html.count("data:image/png;base64,") == 6
    assert "Wet hits" in html and "&lt;Gauge&gt;" in html and "&lt;unavailable&gt;" in html
    encoded = re.search(r'href="data:text/csv;base64,([^"]+)"', html).group(1)
    rows = pd.read_csv(io.BytesIO(base64.b64decode(encoded)))
    season = rows[(rows.period_start == "2019-12-01") & (rows.timescale == "seasonal")]
    lookup = season.set_index(["station_id", "variable"])
    assert lookup.loc[
        ("A", "precipitation"), ["station", "grid", "paired_days", "calendar_days"]
    ].tolist() == [2, 5, 2, 91]
    assert lookup.loc[("A", "min_temperature"), "station"] == 15
    # Pooled daily observations are 2, 2, 6; the contributing stations vary by day.
    assert lookup.loc[
        ("POOLED_REF", "precipitation"), ["station", "grid", "paired_days"]
    ].tolist() == [10, 6, 3]
    assert set(rows.grid_source) == {"era5_land"}
    assert rows[
        (rows.variable == "precipitation")
        & (rows.station_id == "A")
        & (rows.timescale == "monthly")
    ].period_start.tolist() == ["2019-12-01", "2020-01-01", "2020-03-01"]

    compare.compare_station_to_grids(**{**opts, "grid_sources": ["paired"]}, diagnostics_html=path)
    empty = path.read_text()
    assert "No paired station and grid observations" in empty
    assert "&lt;unavailable&gt;" in empty
    assert "data:image" not in empty


def test_candidate_only_diagnostics_rejected_before_fetch(tmp_path):
    with pytest.raises(ValueError, match="require a comparison"):
        compare.compare_station_to_grids(
            station_source="auto",
            station_coord=(0, 0),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 2, 1),
            grid_sources=["era5_land"],
            selection_mode="list",
            diagnostics_html=tmp_path / "unused.html",
        )
