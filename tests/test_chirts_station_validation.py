from pathlib import Path

import numpy as np
import pandas as pd


def test_station_pairs_use_each_variables_observed_dates(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from compare_chirts_stations import compare

    dates = pd.date_range("2020-02-27", periods=5, name="date")
    grid = pd.DataFrame({"date": dates, "Tmax": [35, 34, 36, 40, 30], "Tmin": [15] * 5})
    obs = pd.DataFrame(
        {"Tmax": [35, 35, 34, np.nan, 10], "Tmin": [np.nan, 13, 15, 14, 11]}, index=dates
    )
    _, result = compare("test", dates, grid, obs)
    assert result["station_inverted_days"] == 1
    highs = result["variables"]["Tmax"]
    assert (highs["paired_days"], highs["missing_station_days"]) == (3, 2)
    assert highs["days_ge_35c"] == dict(station=2, grid=2, hits=1, misses=1, false_alarms=1)
    assert highs["bias"] == 0.3333
    lows = result["variables"]["Tmin"]
    assert (lows["paired_days"], lows["bias"]) == (3, 1)
