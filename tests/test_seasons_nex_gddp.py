from datetime import date
import sys
import types
import unittest

import pandas as pd


def _install_test_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    ee = types.ModuleType("ee")
    ee.Authenticate = lambda *args, **kwargs: None
    ee.Initialize = lambda *args, **kwargs: None
    sys.modules.setdefault("ee", ee)

    cdsapi = types.ModuleType("cdsapi")
    cdsapi_api = types.ModuleType("cdsapi.api")

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

    cdsapi_api.Client = _Client
    cdsapi.api = cdsapi_api
    sys.modules.setdefault("cdsapi", cdsapi)
    sys.modules.setdefault("cdsapi.api", cdsapi_api)

    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    ticker = types.ModuleType("matplotlib.ticker")

    class _MaxNLocator:
        def __init__(self, *args, **kwargs):
            pass

    ticker.MaxNLocator = _MaxNLocator
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)
    sys.modules.setdefault("matplotlib.ticker", ticker)


_install_test_stubs()

import climate_tookit.season_analysis.seasons as seasons
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


class SeasonsNexGddpTests(unittest.TestCase):
    def test_get_climate_data_passes_model_and_scenario_for_nex(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2041-01-01", "2041-01-02"]),
                    "max_temperature": [30.0, 31.0],
                    "min_temperature": [20.0, 21.0],
                    "precipitation": [1.0, 2.0],
                }
            )

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            frame = seasons.get_climate_data(
                -1.286,
                36.817,
                "2041-01-01",
                "2041-01-02",
                force_source="nex_gddp",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            seasons.preprocess_data = orig

        self.assertEqual("ACCESS-CM2", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])
        self.assertEqual(
            ["precipitation", "max_temperature", "min_temperature"],
            [variable.name for variable in calls[0]["variables"]],
        )
        self.assertIn("tmax", frame.columns)
        self.assertIn("tmin", frame.columns)
        self.assertIn("precip", frame.columns)

    def test_get_climate_data_requests_minimal_variables_for_historical_source(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                    "max_temperature": [25.0, 26.0],
                    "min_temperature": [15.0, 16.0],
                    "precipitation": [3.0, 1.0],
                }
            )

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-01-01",
                "2020-01-02",
                force_source="era_5",
            )
        finally:
            seasons.preprocess_data = orig

        self.assertEqual(
            ["precipitation", "max_temperature", "min_temperature"],
            [variable.name for variable in calls[0]["variables"]],
        )

    def test_fetch_and_analyze_years_forwards_nex_model_and_scenario(self):
        calls = []

        def fake_fetch_full_year_plus_cessation(
            lat,
            lon,
            year,
            source="auto",
            extra_months=6,
            model=None,
            scenario=None,
        ):
            calls.append(
                {
                    "year": year,
                    "source": source,
                    "model": model,
                    "scenario": scenario,
                }
            )
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2041-01-01", "2041-01-02"]),
                    "precip": [0.0, 0.0],
                    "tmax": [30.0, 30.0],
                    "tmin": [20.0, 20.0],
                    "ET0_mm_day": [5.0, 5.0],
                }
            )

        orig_fetch = seasons.fetch_full_year_plus_cessation
        orig_detect = seasons.detect_onset_cessation
        orig_reassign = seasons.reassign_spillover_seasons
        orig_dedup = seasons.remove_duplicate_seasons
        seasons.fetch_full_year_plus_cessation = fake_fetch_full_year_plus_cessation
        seasons.detect_onset_cessation = lambda df: []
        seasons.reassign_spillover_seasons = lambda results_dict, **kwargs: results_dict
        seasons.remove_duplicate_seasons = lambda results_dict: results_dict
        try:
            seasons.fetch_and_analyze_years(
                -1.286,
                36.817,
                2041,
                2041,
                source="nex_gddp",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            seasons.fetch_full_year_plus_cessation = orig_fetch
            seasons.detect_onset_cessation = orig_detect
            seasons.reassign_spillover_seasons = orig_reassign
            seasons.remove_duplicate_seasons = orig_dedup

        self.assertEqual(
            [
                {
                    "year": 2041,
                    "source": "nex_gddp",
                    "model": "ACCESS-CM2",
                    "scenario": "ssp245",
                }
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
