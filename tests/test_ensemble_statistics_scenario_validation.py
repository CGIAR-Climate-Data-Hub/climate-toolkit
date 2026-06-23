import sys
import types
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


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

import climate_tookit.climate_statistics.ensemble_statistics as es
import climate_tookit.climate_statistics.statistics as stats


class EnsembleStatisticsScenarioValidationTests(unittest.TestCase):
    def test_single_year_statistics_rejects_nex_ltm_run(self):
        result = stats.analyze_climate_statistics(
            location_coord=(-1.286, 36.817),
            start_year=2050,
            end_year=2050,
            source="nex_gddp",
            model="MRI-ESM2-0",
            scenario="ssp245",
        )
        self.assertIn("error", result)
        self.assertIn("multi-year period", result["error"])

    def test_header_does_not_label_pre2015_ssp_run_as_baseline(self):
        result = {
            "period": {"start_year": 1991, "end_year": 2020},
            "scenario": "ssp245",
        }
        header = es._ltm_header_ensemble(result)
        self.assertNotIn("BASELINE", header)

    def test_header_labels_true_historical_window_as_baseline(self):
        result = {
            "period": {"start_year": 1991, "end_year": 2014},
            "scenario": "historical",
        }
        header = es._ltm_header_ensemble(result)
        self.assertIn("BASELINE", header)

    def test_rejects_ssp_window_before_2015(self):
        result = es.analyze_ensemble_nex_gddp(
            location_coord=(-1.286, 36.817),
            start_year=1991,
            end_year=2020,
            scenario="ssp245",
            verbose=False,
        )
        self.assertIn("error", result)
        self.assertIn("2015-01-01", result["error"])

    def test_rejects_single_year_ensemble_nex_ltm_run(self):
        result = es.analyze_ensemble_nex_gddp(
            location_coord=(-1.286, 36.817),
            start_year=2050,
            end_year=2050,
            scenario="ssp245",
            verbose=False,
        )
        self.assertIn("error", result)
        self.assertIn("multi-year period", result["error"])

    def test_cli_all_error_payload_saves_error_report_not_success_banner(self):
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "ensemble_stats_errors.json"
            argv = [
                "ensemble_statistics.py",
                "--location=-1.286,36.817",
                "--start-year=2050",
                "--end-year=2050",
                "--fixed-season=03-01:05-31",
                "--models=MRI-ESM2-0",
                "--scenarios=ssp245,ssp585",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), mock.patch("sys.stdout", stdout):
                with self.assertRaises(SystemExit) as ctx:
                    es.main()

            self.assertEqual(1, ctx.exception.code)
            rendered = stdout.getvalue()
            self.assertIn("Saved error report to:", rendered)
            self.assertNotIn("✓ SAVED", rendered)
            self.assertTrue(output_path.exists())

    def test_cli_json_output_creates_missing_directory(self):
        argv = [
            "ensemble_statistics.py",
            "--location=-1.286,36.817",
            "--start-year=2040",
            "--end-year=2060",
            "--models=MRI-ESM2-0",
            "--scenarios=ssp245",
            "--format=json",
        ]

        payload = {
            "period": {"start_year": 2040, "end_year": 2060},
            "scenario": "ssp245",
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "ensemble_stats.json"
            stdout = StringIO()
            with mock.patch("sys.argv", argv + [f"--output={output_path}"]), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(es, "analyze_ensemble_nex_gddp", return_value=payload):
                es.main()

            self.assertTrue(output_path.exists())
            self.assertIn("Saved to", stdout.getvalue())

    def test_cli_passes_project_id_to_ensemble_analysis(self):
        argv = [
            "ensemble_statistics.py",
            "--location=-1.286,36.817",
            "--start-year=2040",
            "--end-year=2060",
            "--scenarios=ssp245",
            "--project-id=demo-project",
            "--no-save",
        ]

        seen = {}

        def _fake_analyze(**kwargs):
            seen.update(kwargs)
            return {
                "period": {"start_year": 2040, "end_year": 2060},
                "scenario": "ssp245",
                "location": {"lat": -1.286, "lon": 36.817},
                "source": "nex_gddp",
                "mode": "auto",
                "ensemble": True,
                "n_models_ok": 1,
                "models_failed": [],
                "ltm_season_summary": {"mode": "auto", "windows": []},
                "annual_summary": {},
            }

        with mock.patch("sys.argv", argv), \
             mock.patch.object(es, "analyze_ensemble_nex_gddp", side_effect=_fake_analyze):
            es.main()

        self.assertEqual("demo-project", seen["ee_project_id"])

    def test_propagates_per_model_season_slot_warning(self):
        fake_result = {
            "season_statistics": [
                {"year": 2050, "season_number": 1, "precipitation": {"total_mm": 400}}
            ],
            "ltm_season_summary": {"mode": "auto", "windows": []},
            "annual_summary": {"2050": {"annual_rain_mm": 800.0, "is_humid": False}},
            "season_slot_warning": (
                "Auto-detected season counts differ across years, "
                "so LTM season windows by season_number would blend incomparable seasons."
            ),
        }

        with mock.patch.object(es, "default_ensemble_models_for_location", return_value=["MRI-ESM2-0"]), \
             mock.patch.object(es, "analyze_climate_statistics", return_value=fake_result):
            result = es.analyze_ensemble_nex_gddp(
                location_coord=(-1.286, 36.817),
                start_year=2040,
                end_year=2060,
                scenario="ssp245",
                verbose=False,
            )

        self.assertIn("season_slot_warning", result)
        self.assertIn("unstable season-slot counts", result["season_slot_warning"])
        self.assertEqual([], result["ltm_season_summary"]["windows"])
        self.assertIn("Use --fixed-season", result["ltm_season_summary"]["warning"])

    def test_serial_worker_metadata_recorded(self):
        fake_result = {
            "season_statistics": [
                {"year": 2050, "season_number": 1, "precipitation": {"total_mm": 400}}
            ],
            "ltm_season_summary": {"mode": "fixed", "windows": [{"season_number": 1}]},
            "annual_summary": {"2050": {"annual_rain_mm": 800.0, "is_humid": False}},
            "_elapsed_seconds": 0.25,
        }

        with mock.patch.object(
            es,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MRI-ESM2-0", "ACCESS-CM2"], "policy_id": "unit-test"},
        ), mock.patch.object(es, "analyze_climate_statistics", return_value=fake_result):
            result = es.analyze_ensemble_nex_gddp(
                location_coord=(-1.286, 36.817),
                start_year=2040,
                end_year=2060,
                scenario="ssp245",
                verbose=False,
                model_workers=1,
            )

        timing = result["metadata"]["timing"]
        self.assertEqual(1, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])

    def test_parallel_worker_path_uses_executor(self):
        tasks_seen = []

        def fake_task_runner(task):
            tasks_seen.append(task)
            return {
                "model": task["model"],
                "elapsed_seconds": 0.5,
                "result": {
                    "_elapsed_seconds": 0.5,
                    "season_statistics": [
                        {"year": 2050, "season_number": 1, "precipitation": {"total_mm": 400}}
                    ],
                    "ltm_season_summary": {"mode": "fixed", "windows": [{"season_number": 1}]},
                    "annual_summary": {"2050": {"annual_rain_mm": 800.0, "is_humid": False}},
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
            es,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MRI-ESM2-0", "ACCESS-CM2"], "policy_id": "unit-test"},
        ), mock.patch.object(es, "_run_ensemble_model_task", side_effect=fake_task_runner), \
             mock.patch.object(es, "ProcessPoolExecutor", _FakeExecutor), \
             mock.patch.object(es, "as_completed", lambda futures: list(futures)):
            result = es.analyze_ensemble_nex_gddp(
                location_coord=(-1.286, 36.817),
                start_year=2040,
                end_year=2060,
                scenario="ssp245",
                verbose=False,
                model_workers=8,
            )

        timing = result["metadata"]["timing"]
        self.assertEqual(8, timing["model_workers_requested"])
        self.assertEqual(2, timing["model_workers_used"])
        self.assertEqual(2, len(tasks_seen))
        self.assertTrue(all(task["suppress_child_stdout"] for task in tasks_seen))

    def test_parallel_workers_fall_back_to_serial_when_blocked(self):
        def fake_task_runner(task):
            return {
                "model": task["model"],
                "elapsed_seconds": 0.5,
                "result": {
                    "_elapsed_seconds": 0.5,
                    "season_statistics": [
                        {"year": 2050, "season_number": 1, "precipitation": {"total_mm": 400}}
                    ],
                    "ltm_season_summary": {"mode": "fixed", "windows": [{"season_number": 1}]},
                    "annual_summary": {"2050": {"annual_rain_mm": 800.0, "is_humid": False}},
                },
            }

        class _BrokenExecutor:
            def __init__(self, max_workers):
                raise PermissionError("blocked semaphore")

        with mock.patch.object(
            es,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MRI-ESM2-0", "ACCESS-CM2"], "policy_id": "unit-test"},
        ), mock.patch.object(es, "_run_ensemble_model_task", side_effect=fake_task_runner), \
             mock.patch.object(es, "ProcessPoolExecutor", _BrokenExecutor):
            result = es.analyze_ensemble_nex_gddp(
                location_coord=(-1.286, 36.817),
                start_year=2040,
                end_year=2060,
                scenario="ssp245",
                verbose=False,
                model_workers=4,
            )

        timing = result["metadata"]["timing"]
        self.assertEqual(4, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])

    def test_child_error_payload_is_preserved_in_failed_models(self):
        fake_result = {
            "error": "Climate data fetch failed: oauth2.googleapis.com DNS failure",
        }

        with mock.patch.object(
            es,
            "resolve_ensemble_policy_for_location",
            return_value={"models": ["MRI-ESM2-0"], "policy_id": "unit-test"},
        ), mock.patch.object(es, "analyze_climate_statistics", return_value=fake_result):
            result = es.analyze_ensemble_nex_gddp(
                location_coord=(-1.286, 36.817),
                start_year=2040,
                end_year=2060,
                scenario="ssp585",
                fixed_season="03-01:05-31",
                verbose=False,
                model_workers=1,
            )

        self.assertIn("All models failed.", result["error"])
        self.assertIn("Common cause:", result["error"])
        self.assertEqual(
            "Climate data fetch failed: oauth2.googleapis.com DNS failure",
            result["failed_models"][0]["error"],
        )


if __name__ == "__main__":
    unittest.main()
