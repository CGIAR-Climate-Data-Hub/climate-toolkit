import sys
import types
import unittest
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np
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
    def test_calculate_annual_statistics_uses_precip_only_defaults_for_chirps(self):
        dates = pd.date_range("2020-01-01", "2020-12-31", freq="D")
        df = pd.DataFrame({
            "date": dates,
            "precipitation": [1.0] * len(dates),
        })
        captured = {}

        def _fake_preprocess_data(**kwargs):
            captured.update(kwargs)
            return df

        with mock.patch.object(ltc, "PREPROCESS_AVAILABLE", True), \
             mock.patch.object(ltc, "preprocess_data", side_effect=_fake_preprocess_data):
            stats = ltc.calculate_annual_statistics(
                lat=-1.286,
                lon=36.817,
                year=2020,
                source="chirps",
                variables=None,
                verbose=False,
            )

        self.assertIsNotNone(stats)
        self.assertEqual(["precipitation"], [item.name for item in captured["variables"]])

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

    def test_calculate_climatology_error_surfaces_year_failure_summary_and_notes(self):
        def _fake_annual_stats(*args, **kwargs):
            self.assertTrue(kwargs["return_error"])
            return None, (
                "Earth Engine project ID is required. Pass ee_project_id or set one of "
                "GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or EE_PROJECT_ID."
            )

        with mock.patch.object(ltc, "calculate_annual_statistics", side_effect=_fake_annual_stats):
            result = ltc.calculate_climatology(
                location_coord=(-1.286, 36.817),
                start_year=1991,
                end_year=1992,
                source="agera_5",
                verbose=False,
            )

        self.assertIn("error", result)
        self.assertIn("failure_summary", result)
        self.assertEqual(1, len(result["failure_summary"]))
        self.assertEqual(2, result["failure_summary"][0]["count"])
        notes = result.get("notes") or []
        self.assertTrue(any("Earth Engine-backed" in note for note in notes))

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

    def test_calculate_climatology_returns_plot_warning_when_matplotlib_missing(self):
        valid_stats = {
            "year": 2020,
            "observed_days": 366,
            "expected_days": 366,
            "data_completeness": 100.0,
            "precipitation": {
                "annual_total_mm": 1000.0,
                "annual_mean_daily_mm": 2.73,
                "annual_median_daily_mm": 1.0,
                "annual_max_daily_mm": 20.0,
                "annual_std_daily_mm": 3.0,
                "rainy_days": 100,
                "dry_days": 266,
                "days_with_data": 366,
            },
            "temperature": {
                "annual_mean_tmax_c": 28.0,
                "annual_mean_tmin_c": 16.0,
                "annual_mean_tavg_c": 22.0,
                "annual_max_tmax_c": 35.0,
                "annual_min_tmin_c": 10.0,
                "annual_std_tmax_c": 2.0,
                "annual_std_tmin_c": 1.5,
                "annual_diurnal_range_c": 12.0,
                "days_with_data": 366,
            },
            "_daily_df": pd.DataFrame(
                {
                    "date": pd.date_range("2020-01-01", "2020-12-31", freq="D"),
                    "precipitation": [1.0] * 366,
                    "max_temperature": [28.0] * 366,
                    "min_temperature": [16.0] * 366,
                }
            ),
            "_columns": {"precip": "precipitation", "tmax": "max_temperature", "tmin": "min_temperature"},
        }

        with TemporaryDirectory() as tmpdir, \
             mock.patch.object(ltc, "calculate_annual_statistics", return_value=(valid_stats, None)), \
             mock.patch.object(ltc, "_load_matplotlib", return_value=(None, None)):
            result = ltc.calculate_climatology(
                location_coord=(-1.286, 36.817),
                start_year=2020,
                end_year=2020,
                source="nasa_power",
                output_dir=tmpdir,
                verbose=False,
            )

        self.assertIsNone(result["plots"])
        self.assertEqual(
            [ltc._plot_runtime_warning()],
            result["plot_warnings"],
        )

    def test_main_single_source_json_sanitizes_nan_and_surfaces_plot_warning(self):
        payload = {
            "source": "era_5",
            "period": {"start_year": 1991, "end_year": 2020},
            "plot_warnings": [ltc._plot_runtime_warning()],
            "climatology": {
                "temperature": {
                    "mean_annual_tavg_c": np.float32(23.302000045776367),
                    "std_annual_tavg_c": float("nan"),
                }
            },
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

            saved = json.loads(output_path.read_text())
            self.assertEqual(23.302, saved["climatology"]["temperature"]["mean_annual_tavg_c"])
            self.assertIsNone(saved["climatology"]["temperature"]["std_annual_tavg_c"])
            self.assertEqual([ltc._plot_runtime_warning()], saved["plot_warnings"])

    def test_ensemble_worker_metadata_recorded_in_serial_mode(self):
        payload_a = {
            "period": {"years_with_data": 30},
            "climatology": {
                "precipitation": {"mean_annual_total_mm": 1000.0, "years_used": 30},
            },
            "monthly_climatology": None,
            "trends": None,
            "annual_time_series": None,
            "_elapsed_seconds": 0.25,
        }
        payload_b = {
            "period": {"years_with_data": 29},
            "climatology": {
                "precipitation": {"mean_annual_total_mm": 900.0, "years_used": 29},
            },
            "monthly_climatology": None,
            "trends": None,
            "annual_time_series": None,
            "_elapsed_seconds": 0.25,
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
                model_workers=1,
            )
        finally:
            ltc.calculate_climatology = orig_calc

        timing = result["metadata"]["timing"]
        self.assertEqual(1, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])

    def test_ensemble_parallel_path_uses_executor(self):
        tasks_seen = []

        def fake_task_runner(task):
            tasks_seen.append(task)
            return {
                "model": task["model"],
                "elapsed_seconds": 0.5,
                "result": {
                    "period": {"years_with_data": 30},
                    "climatology": {
                        "precipitation": {"mean_annual_total_mm": 1000.0, "years_used": 30},
                    },
                    "monthly_climatology": None,
                    "trends": None,
                    "annual_time_series": None,
                    "_elapsed_seconds": 0.5,
                },
            }

        class _FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class _FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, task):
                return _FakeFuture(fn(task))

        with mock.patch.object(
            ltc,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MODEL_A", "MODEL_B"], "policy_id": "unit-test"},
        ), mock.patch.object(ltc, "_run_climatology_model_task", side_effect=fake_task_runner), \
             mock.patch.object(ltc, "ProcessPoolExecutor", _FakeExecutor), \
             mock.patch.object(ltc, "as_completed", lambda futures: list(futures)):
            result = ltc.calculate_climatology_ensemble(
                location_coord=(-1.286, 36.817),
                start_year=1991,
                end_year=2020,
                scenario="ssp245",
                verbose=False,
                model_workers=8,
            )

        timing = result["metadata"]["timing"]
        self.assertEqual(8, timing["model_workers_requested"])
        self.assertEqual(2, timing["model_workers_used"])
        self.assertEqual(2, len(tasks_seen))
        self.assertTrue(all(task["suppress_child_stdout"] for task in tasks_seen))

    def test_ensemble_parallel_falls_back_to_serial_when_blocked(self):
        def fake_task_runner(task):
            return {
                "model": task["model"],
                "elapsed_seconds": 0.5,
                "result": {
                    "period": {"years_with_data": 30},
                    "climatology": {
                        "precipitation": {"mean_annual_total_mm": 1000.0, "years_used": 30},
                    },
                    "monthly_climatology": None,
                    "trends": None,
                    "annual_time_series": None,
                    "_elapsed_seconds": 0.5,
                },
            }

        class _BrokenExecutor:
            def __init__(self, max_workers):
                raise PermissionError("blocked semaphore")

        with mock.patch.object(
            ltc,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MODEL_A", "MODEL_B"], "policy_id": "unit-test"},
        ), mock.patch.object(ltc, "_run_climatology_model_task", side_effect=fake_task_runner), \
             mock.patch.object(ltc, "ProcessPoolExecutor", _BrokenExecutor):
            result = ltc.calculate_climatology_ensemble(
                location_coord=(-1.286, 36.817),
                start_year=1991,
                end_year=2020,
                scenario="ssp245",
                verbose=False,
                model_workers=4,
            )

        timing = result["metadata"]["timing"]
        self.assertEqual(4, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])


if __name__ == "__main__":
    unittest.main()
