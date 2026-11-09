"""Public hazard date bounds select onsets, including seasons crossing 31 December."""

import pandas as pd
import pytest

from climate_toolkit import evaluate_hazards
from climate_toolkit.season_analysis import seasons


@pytest.fixture
def climate(monkeypatch):
    calls = []

    def fetch(lat, lon, start, end, **kwargs):
        calls.append((start, end))
        return pd.DataFrame(
            {"date": pd.date_range(start, end), "precip": 1.0, "tmax": 36.0, "tmin": 18.0}
        )

    monkeypatch.setattr(seasons, "get_climate_data", fetch)
    return calls


def assess(start, end, definition="10-01:01-31"):
    return evaluate_hazards(
        "maize",
        (-0.3868, 37.6323),
        start,
        end,
        source="paired",
        precip_source="chirps_v3_daily_rnl",
        temp_source="era5_land",
        fixed_season=definition,
        soilcp=101,
        livestock_elevation_override_m=1100,
    )


@pytest.mark.parametrize("end", ["2010-10-01", "2010-12-31", "2011-06-30"])
def test_cross_year_single_season(climate, end):
    result = assess("2010-10-01", end)
    info = result["season_info"]
    assert (info["year"], info["cessation_date"], info["length_days"]) == (2010, "2011-01-31", 123)
    assert result["season_statistics"]["NTx35"] == 123
    assert climate == [("2010-08-02", "2011-01-31")]


def test_partial_years_keep_original_season_numbers(climate):
    result = assess("2010-09-30", "2011-03-01", "03-01:05-31,10-01:01-31")
    assert [
        (a["season_info"]["year"], a["season_info"]["season_number"]) for a in result["assessments"]
    ] == [(2010, 2), (2011, 1)]
    assert climate == [("2010-08-02", "2011-01-31"), ("2010-12-31", "2011-05-31")]


def test_season_already_in_progress_excluded(climate):
    result = assess("2010-10-02", "2011-01-31")
    assert "No fixed season starts within" in result["error"]
    assert not climate


@pytest.mark.parametrize("missing_day", ["2010-08-02", "2010-11-15", "2011-01-31"])
def test_incomplete_window_reported(monkeypatch, climate, missing_day):
    fetch = seasons.get_climate_data

    def incomplete(*args, **kwargs):
        df = fetch(*args, **kwargs)
        return df[df.date != pd.Timestamp(missing_day)]

    monkeypatch.setattr(seasons, "get_climate_data", incomplete)
    result = assess("2010-01-01", "2010-12-31")
    assert "Expected one daily record per day" in result["error"]
    assert "2010-10-01..2011-01-31" in result["error"]
