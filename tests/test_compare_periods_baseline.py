from datetime import date
import sys
import types
import unittest


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

import climate_tookit.compare_periods.ensemble_periods as ep
import climate_tookit.compare_periods.periods as cp


class ComparePeriodsBaselineScenarioTests(unittest.TestCase):
    def test_compare_one_model_uses_historical_for_baseline_and_ssp_for_future(self):
        calls = []

        def fake_analyze_climate_statistics(
            *,
            location_coord,
            start_year,
            end_year,
            source,
            fixed_season=None,
            model=None,
            scenario=None,
            **kwargs,
        ):
            calls.append((start_year, end_year, source, model, scenario))
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season=None,
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(
            [
                (1991, 2020, "nex_gddp", "ACCESS-CM2", "historical"),
                (2040, 2060, "nex_gddp", "ACCESS-CM2", "ssp245"),
            ],
            calls,
        )

    def test_ensemble_compare_does_not_raise_name_error_for_location_filtering(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2"]
        ep._compare_one_model = lambda **kwargs: {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
        }
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertNotIn("error", result)
        self.assertEqual(result["n_models_ok"], 1)

    def test_ensemble_compare_rejects_single_year_baseline_period(self):
        result = ep.ensemble_compare(
            location=(-1.286, 36.817),
            baseline_start=1991,
            baseline_end=1991,
            future_start=2050,
            future_end=2051,
            scenario="ssp245",
            verbose=False,
        )

        self.assertIn("error", result)
        self.assertIn("Single-year NEX-GDDP baseline/future comparisons are not allowed", result["error"])

    def test_ensemble_compare_rejects_single_year_future_period(self):
        result = ep.ensemble_compare(
            location=(-1.286, 36.817),
            baseline_start=1991,
            baseline_end=1992,
            future_start=2050,
            future_end=2050,
            scenario="ssp245",
            verbose=False,
        )

        self.assertIn("error", result)
        self.assertIn("Single-year NEX-GDDP baseline/future comparisons are not allowed", result["error"])

    def test_compare_one_model_rejects_single_year_periods_before_fetch(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {}

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1991,
                future_start=2050,
                future_end=2050,
                fixed_season=None,
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertIn("error", result)
        self.assertEqual([], calls)

    def test_diff_block_uses_baseline_magnitude_for_negative_values(self):
        result = cp._diff_block(
            {"water_balance": {"total_balance": -722.10}},
            {"water_balance": {"total_balance": -705.00}},
            "future_avg",
            "baseline_avg",
        )

        self.assertEqual(-17.1, result["water_balance"]["total_balance"]["diff"])
        self.assertEqual(-2.43, result["water_balance"]["total_balance"]["pct"])

    def test_diff_value_2level_uses_baseline_magnitude_for_negative_values(self):
        result = ep._diff_value_2level(
            {"water_balance": {"total_balance": -722.10}},
            {"water_balance": {"total_balance": -705.00}},
            "future_ltm",
            "baseline_ltm",
        )

        self.assertEqual(-17.1, result["water_balance"]["total_balance"]["diff"])
        self.assertEqual(-2.43, result["water_balance"]["total_balance"]["pct"])


if __name__ == "__main__":
    unittest.main()
