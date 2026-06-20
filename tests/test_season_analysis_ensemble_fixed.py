import sys
import tempfile
import types
import unittest
from pathlib import Path

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

import climate_tookit.season_analysis.ensemble as ensemble


class SeasonAnalysisEnsembleFixedTests(unittest.TestCase):
    def test_main_creates_missing_output_directory(self):
        orig_run = ensemble.run_ensemble
        orig_print = ensemble.print_summary
        orig_default_models = ensemble.default_ensemble_models_for_location
        orig_argv = sys.argv[:]
        ensemble.run_ensemble = lambda *args, **kwargs: {"ok": True}
        ensemble.print_summary = lambda results: None
        ensemble.default_ensemble_models_for_location = lambda *args, **kwargs: ["MRI-ESM2-0"]
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "nested" / "results" / "season_ensemble.json"
                sys.argv = [
                    "ensemble.py",
                    "--location=-1.286,36.817",
                    "--start-year=2040",
                    "--end-year=2060",
                    f"--output={output_path}",
                    "--quiet",
                ]
                ensemble.main()
                self.assertTrue(output_path.exists())
        finally:
            ensemble.run_ensemble = orig_run
            ensemble.print_summary = orig_print
            ensemble.default_ensemble_models_for_location = orig_default_models
            sys.argv = orig_argv

    def test_average_model_over_period_preserves_fixed_month_day_dates(self):
        model_result = {
            "model": "MRI-ESM2-0",
            "seasons_dict": {
                2050: [
                    {
                        "onset": pd.Timestamp("2050-03-01"),
                        "cessation": pd.Timestamp("2050-05-31"),
                        "regime": "fixed",
                        "length_days": 92,
                        "total_rainfall_mm": 100.0,
                        "rainy_days": 20,
                        "dry_days": 72,
                        "dry_spells": 2,
                        "eto_seasons": [
                            {
                                "onset": pd.Timestamp("2050-03-18"),
                                "cessation": pd.Timestamp("2050-04-20"),
                                "regime": "unimodal",
                                "length_days": 42,
                                "total_rainfall_mm": 70.0,
                                "rainy_days": 15,
                                "dry_days": 27,
                                "dry_spells": 1,
                            }
                        ],
                    }
                ],
                2051: [
                    {
                        "onset": pd.Timestamp("2051-03-01"),
                        "cessation": pd.Timestamp("2051-05-31"),
                        "regime": "fixed",
                        "length_days": 92,
                        "total_rainfall_mm": 120.0,
                        "rainy_days": 24,
                        "dry_days": 68,
                        "dry_spells": 3,
                        "eto_seasons": [
                            {
                                "onset": pd.Timestamp("2051-05-03"),
                                "cessation": pd.Timestamp("2051-04-20"),
                                "regime": "unimodal",
                                "length_days": 42,
                                "total_rainfall_mm": 90.0,
                                "rainy_days": 18,
                                "dry_days": 24,
                                "dry_spells": 1,
                            }
                        ],
                    }
                ],
            },
            "annual_dict": {
                2050: {"annual_rain_mm": 700.0, "low_rain_months": 6, "is_humid": False},
                2051: {"annual_rain_mm": 740.0, "low_rain_months": 5, "is_humid": False},
            },
        }

        averaged = ensemble._average_model_over_period(model_result, n_slots=1)
        season = averaged["seasons"][0]
        eto = season["eto_seasons"][0]

        self.assertEqual("2050-03-01", season["onset"])
        self.assertEqual("2050-05-31", season["cessation"])
        self.assertEqual("2050-04-10", eto["onset"])
        self.assertEqual("2050-04-20", eto["cessation"])
        self.assertEqual(110.0, season["total_rainfall_mm"])
        self.assertEqual(720.0, averaged["annual_rain_mm"])

    def test_use_nex_gddp_patch_accepts_model_and_scenario_keywords(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2050-03-01", "2050-03-02"]),
                    "max_temperature": [26.0, 27.0],
                    "min_temperature": [16.0, 17.0],
                    "precipitation": [5.0, 0.0],
                }
            )

        original = ensemble.preprocess_data
        ensemble.preprocess_data = fake_preprocess_data
        try:
            with ensemble.use_nex_gddp("MRI-ESM2-0", "ssp245") as state:
                frame = ensemble.seasons.get_climate_data(
                    -1.286,
                    36.817,
                    "2050-03-01",
                    "2050-03-02",
                    force_source="nex_gddp",
                    model=None,
                    scenario=None,
                )
        finally:
            ensemble.preprocess_data = original

        self.assertEqual(1, state["success"])
        self.assertEqual(0, state["fail"])
        self.assertEqual("MRI-ESM2-0", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])
        self.assertIn("precip", frame.columns)
        self.assertEqual([5.0, 0.0], frame["precip"].tolist())

    def test_seasons_get_climate_data_applies_custom_station_override(self):
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "precipitation": [1.0, 2.0, 3.0],
                "max_temperature": [24.0, 25.0, 26.0],
                "min_temperature": [14.0, 15.0, 16.0],
            }
        )
        original = ensemble.seasons._fetch_raw
        ensemble.seasons._fetch_raw = lambda *args, **kwargs: base_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "season_override.csv"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-03"],
                        "precipitation": [9.0, 8.0],
                    }
                ).to_csv(csv_path, index=False)
                frame = ensemble.seasons.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-03",
                    force_source="agera_5",
                    custom_station_file=str(csv_path),
                    custom_station_variables=["precipitation"],
                )
        finally:
            ensemble.seasons._fetch_raw = original

        self.assertEqual([9.0, 2.0, 8.0], frame["precip"].tolist())
        self.assertEqual([24.0, 25.0, 26.0], frame["tmax"].tolist())

    def test_seasons_get_climate_data_skips_custom_override_when_no_overlap(self):
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-03-01", periods=2, freq="D"),
                "precipitation": [1.0, 2.0],
                "max_temperature": [24.0, 25.0],
                "min_temperature": [14.0, 15.0],
            }
        )
        original = ensemble.seasons._fetch_raw
        ensemble.seasons._fetch_raw = lambda *args, **kwargs: base_frame.copy()
        try:
            frame = ensemble.seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-03-01",
                "2020-03-02",
                force_source="agera_5",
                custom_station_file=str(Path("tests/fixtures/custom_station_gsod_like.csv")),
                custom_station_variables=["precipitation"],
                custom_temp_unit="f",
                custom_precip_unit="inch",
            )
        finally:
            ensemble.seasons._fetch_raw = original

        self.assertEqual([1.0, 2.0], frame["precip"].tolist())
        self.assertTrue(frame.attrs.get("custom_station_warnings"))

    def test_seasons_get_climate_data_accepts_tamsat_in_paired_mode(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs["source"])
            if kwargs["source"] == "tamsat":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
                        "precipitation": [4.0, 0.0],
                        "soil_moisture": [30.0, 29.5],
                    }
                )
            if kwargs["source"] == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
                        "max_temperature": [24.0, 25.0],
                        "min_temperature": [14.0, 15.0],
                    }
                )
            raise AssertionError(f"unexpected source {kwargs['source']}")

        original = ensemble.seasons.preprocess_data
        ensemble.seasons.preprocess_data = fake_preprocess_data
        try:
            frame = ensemble.seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-03-01",
                "2020-03-02",
                force_source="paired",
                precip_source="tamsat",
                temp_source="agera_5",
            )
        finally:
            ensemble.seasons.preprocess_data = original

        self.assertEqual(["tamsat", "agera_5"], calls)
        self.assertEqual([4.0, 0.0], frame["precip"].tolist())
        self.assertEqual([24.0, 25.0], frame["tmax"].tolist())

    def test_seasons_get_climate_data_rejects_paired_without_sources(self):
        with self.assertRaises(RuntimeError) as ctx:
            ensemble.seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-03-01",
                "2020-03-02",
                force_source="paired",
            )

        self.assertIn("requires both precip_source and temp_source", str(ctx.exception))

    def test_seasons_get_climate_data_rejects_all_missing_precipitation(self):
        def fake_preprocess_data(**kwargs):
            if kwargs["source"] == "tamsat":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
                        "precipitation": [None, None],
                    }
                )
            if kwargs["source"] == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
                        "max_temperature": [24.0, 25.0],
                        "min_temperature": [14.0, 15.0],
                    }
                )
            raise AssertionError(f"unexpected source {kwargs['source']}")

        original = ensemble.seasons.preprocess_data
        ensemble.seasons.preprocess_data = fake_preprocess_data
        try:
            with self.assertRaises(RuntimeError) as ctx:
                ensemble.seasons.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-03-01",
                    "2020-03-02",
                    force_source="paired",
                    precip_source="tamsat",
                    temp_source="agera_5",
                )
        finally:
            ensemble.seasons.preprocess_data = original

        self.assertIn("no usable daily values", str(ctx.exception))

    def test_run_ensemble_records_worker_metadata_in_serial_mode(self):
        orig_task_runner = ensemble._run_season_model_task

        def fake_task_runner(task):
            return {
                "model": task["model"],
                "scenario": task["scenario"],
                "seasons_dict": {2050: [{"season_number": 1}], 2051: [{"season_number": 1}]},
                "annual_dict": {
                    2050: {"annual_rain_mm": 700.0, "low_rain_months": 6, "is_humid": False},
                    2051: {"annual_rain_mm": 740.0, "low_rain_months": 5, "is_humid": False},
                },
                "skip_info": {"perhumid_years": [], "no_season_years": [], "analyzed_years": [2050, 2051]},
                "elapsed_seconds": 0.5,
            }

        ensemble._run_season_model_task = fake_task_runner
        try:
            result = ensemble.run_ensemble(
                -1.286,
                36.817,
                2050,
                2051,
                scenarios=["ssp245"],
                models=["ACCESS-CM2", "MRI-ESM2-0"],
                fixed_arg="03-01:05-31",
                verbose=False,
                model_workers=1,
            )
        finally:
            ensemble._run_season_model_task = orig_task_runner

        timing = result["ssp245"]["metadata"]["timing"]
        self.assertEqual(1, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["ssp245"]["metadata"]["models_ok"])

    def test_run_ensemble_parallel_path_uses_executor(self):
        orig_task_runner = ensemble._run_season_model_task
        orig_executor = ensemble.ProcessPoolExecutor
        orig_as_completed = ensemble.as_completed
        tasks_seen = []

        def fake_task_runner(task):
            tasks_seen.append(task)
            return {
                "model": task["model"],
                "scenario": task["scenario"],
                "seasons_dict": {2050: [{"season_number": 1}]},
                "annual_dict": {
                    2050: {"annual_rain_mm": 700.0, "low_rain_months": 6, "is_humid": False},
                },
                "skip_info": {"perhumid_years": [], "no_season_years": [], "analyzed_years": [2050]},
                "elapsed_seconds": 0.5,
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

        ensemble._run_season_model_task = fake_task_runner
        ensemble.ProcessPoolExecutor = _FakeExecutor
        ensemble.as_completed = lambda futures: list(futures)
        try:
            result = ensemble.run_ensemble(
                -1.286,
                36.817,
                2050,
                2050,
                scenarios=["ssp245"],
                models=["ACCESS-CM2", "MRI-ESM2-0"],
                fixed_arg="03-01:05-31",
                verbose=False,
                model_workers=8,
            )
        finally:
            ensemble._run_season_model_task = orig_task_runner
            ensemble.ProcessPoolExecutor = orig_executor
            ensemble.as_completed = orig_as_completed

        timing = result["ssp245"]["metadata"]["timing"]
        self.assertEqual(8, timing["model_workers_requested"])
        self.assertEqual(2, timing["model_workers_used"])
        self.assertEqual(2, len(tasks_seen))

    def test_run_ensemble_parallel_falls_back_when_blocked(self):
        orig_task_runner = ensemble._run_season_model_task
        orig_executor = ensemble.ProcessPoolExecutor

        def fake_task_runner(task):
            return {
                "model": task["model"],
                "scenario": task["scenario"],
                "seasons_dict": {2050: [{"season_number": 1}]},
                "annual_dict": {
                    2050: {"annual_rain_mm": 700.0, "low_rain_months": 6, "is_humid": False},
                },
                "skip_info": {"perhumid_years": [], "no_season_years": [], "analyzed_years": [2050]},
                "elapsed_seconds": 0.5,
            }

        class _BrokenExecutor:
            def __init__(self, max_workers):
                raise PermissionError("blocked semaphore")

        ensemble._run_season_model_task = fake_task_runner
        ensemble.ProcessPoolExecutor = _BrokenExecutor
        try:
            result = ensemble.run_ensemble(
                -1.286,
                36.817,
                2050,
                2050,
                scenarios=["ssp245"],
                models=["ACCESS-CM2", "MRI-ESM2-0"],
                fixed_arg="03-01:05-31",
                verbose=False,
                model_workers=4,
            )
        finally:
            ensemble._run_season_model_task = orig_task_runner
            ensemble.ProcessPoolExecutor = orig_executor

        timing = result["ssp245"]["metadata"]["timing"]
        self.assertEqual(4, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])


if __name__ == "__main__":
    unittest.main()
