import sys
import types
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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

import climate_tookit.climatology.long_term_climatology as ltc


class ClimatologyOutputTests(unittest.TestCase):
    def test_calculate_annual_statistics_uses_leap_year_day_count(self):
        dates = pd.date_range("2020-01-01", "2020-12-31", freq="D")
        df = pd.DataFrame({
            "date": dates,
            "precipitation": [1.0] * len(dates),
            "max_temperature": [30.0] * len(dates),
            "min_temperature": [20.0] * len(dates),
        })

        with mock.patch.object(ltc, "PREPROCESS_AVAILABLE", True), \
             mock.patch.object(ltc, "preprocess_data", return_value=df):
            stats = ltc.calculate_annual_statistics(
                lat=-1.286,
                lon=36.817,
                year=2020,
                source="agera5",
                variables=[],
                verbose=False,
            )

        self.assertIsNotNone(stats)
        self.assertEqual(366, stats["observed_days"])
        self.assertEqual(366, stats["expected_days"])
        self.assertEqual(100.0, stats["data_completeness"])

    def test_calculate_annual_statistics_uses_unique_dates_for_completeness_threshold(self):
        base_dates = pd.date_range("2019-01-01", periods=299, freq="D")
        duped_dates = list(base_dates) + [base_dates[-1]]
        df = pd.DataFrame({
            "date": duped_dates,
            "precipitation": [1.0] * len(duped_dates),
            "max_temperature": [30.0] * len(duped_dates),
            "min_temperature": [20.0] * len(duped_dates),
        })

        with mock.patch.object(ltc, "PREPROCESS_AVAILABLE", True), \
             mock.patch.object(ltc, "preprocess_data", return_value=df):
            stats = ltc.calculate_annual_statistics(
                lat=-1.286,
                lon=36.817,
                year=2019,
                source="agera5",
                variables=[],
                verbose=False,
            )

        self.assertIsNone(stats)

    def test_ensemble_completeness_uses_conservative_minimum_not_rounded_mean(self):
        payload_a = {
            "period": {"years_with_data": 30},
            "climatology": {
                "precipitation": {"mean_annual_total_mm": 1000.0, "years_used": 30},
            },
            "monthly_climatology": None,
            "trends": None,
            "annual_time_series": None,
        }
        payload_b = {
            "period": {"years_with_data": 29},
            "climatology": {
                "precipitation": {"mean_annual_total_mm": 900.0, "years_used": 29},
            },
            "monthly_climatology": None,
            "trends": None,
            "annual_time_series": None,
        }

        orig_calc = ltc.calculate_climatology
        ltc.calculate_climatology = mock.Mock(side_effect=[payload_a, payload_b])
        try:
            result = ltc.calculate_climatology_ensemble(
                location_coord=(-1.286, 36.817),
                start_year=1991,
                end_year=2020,
                scenario="ssp245",
                models=["MODEL_A", "MODEL_B"],
                verbose=False,
            )
        finally:
            ltc.calculate_climatology = orig_calc

        self.assertEqual(29, result["period"]["years_with_data"])
        self.assertEqual(96.7, result["metadata"]["data_completeness_pct"])
        self.assertEqual(29, result["metadata"]["years_with_data_min"])
        self.assertEqual(29.5, result["metadata"]["years_with_data_mean"])
        self.assertEqual(30, result["metadata"]["years_with_data_max"])

    def test_main_single_source_json_creates_missing_output_directory(self):
        payload = {
            "source": "era_5",
            "period": {"start_year": 1991, "end_year": 2020},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "climatology.json"
            argv = [
                "long_term_climatology.py",
                "--location=-1.286,36.817",
                "--start-year=1991",
                "--end-year=2020",
                "--source=era_5",
                "--format=json",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(ltc, "calculate_climatology", return_value=payload):
                ltc.main()

            self.assertTrue(output_path.exists())
            self.assertIn("Climatology saved", stdout.getvalue())

    def test_main_nex_text_mode_output_creates_missing_directory(self):
        payload = {
            "scenario": "ssp245",
            "n_models_ok": 1,
            "models_failed": [],
            "climatology": {},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "climatology_ensemble.json"
            argv = [
                "long_term_climatology.py",
                "--location=-1.286,36.817",
                "--start-year=2040",
                "--end-year=2060",
                "--source=nex_gddp",
                "--scenarios=ssp245",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(ltc, "calculate_climatology_ensemble", return_value=payload), \
                 mock.patch.object(ltc, "print_ensemble_climatology_report", return_value=None):
                ltc.main()

            self.assertTrue(output_path.exists())
            self.assertIn("JSON data saved", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
