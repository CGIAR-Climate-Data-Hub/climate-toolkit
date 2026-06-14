import sys
import types
import unittest
from contextlib import redirect_stdout
from datetime import date
from io import StringIO


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

import climate_tookit.calculate_hazards.ensemble_hazards as eh


class EnsembleHazardsAggregationTests(unittest.TestCase):
    def test_calculate_ensemble_prefetches_tail_for_year_crossing_fixed_window(self):
        calls = []
        orig_preprocess = eh.preprocess_data
        orig_evaluate = eh._evaluate
        eh.preprocess_data = lambda **kwargs: calls.append(kwargs) or None
        eh._evaluate = lambda crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat: {
            "season_info": {**window, "length_days": 121},
            "season_statistics": {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 24.0,
            },
            "hazard_evaluation": {
                "precipitation": {"value_mm": 600.0, "status": "no_stress"},
                "temperature": {"value_c": 24.0, "status": "no_stress"},
            },
            "projection": {"model": model, "scenario": scenario},
        }
        try:
            eh.calculate_ensemble(
                crop="maize",
                lat=-13.5319,
                lon=-71.9675,
                start_year=2041,
                end_year=2041,
                models=["ACCESS-CM2"],
                scenarios=["ssp245"],
                fixed_season="12-01:03-31",
            )
        finally:
            eh.preprocess_data = orig_preprocess
            eh._evaluate = orig_evaluate

        self.assertEqual(1, len(calls))
        self.assertEqual(date(2042, 1, 1), calls[0]["date_from"])
        self.assertEqual(date(2042, 3, 31), calls[0]["date_to"])
        self.assertEqual("ACCESS-CM2", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])

    def test_calculate_ensemble_warns_for_year_crossing_fixed_window(self):
        orig_evaluate = eh._evaluate
        eh._evaluate = lambda crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat: {
            "season_info": {**window, "length_days": 121},
            "season_statistics": {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 24.0,
            },
            "hazard_evaluation": {
                "precipitation": {"value_mm": 600.0, "status": "no_stress"},
                "temperature": {"value_c": 24.0, "status": "no_stress"},
            },
            "projection": {"model": model, "scenario": scenario},
        }
        buf = StringIO()
        try:
            with redirect_stdout(buf):
                eh.calculate_ensemble(
                    crop="maize",
                    lat=-13.5319,
                    lon=-71.9675,
                    start_year=2041,
                    end_year=2041,
                    models=["ACCESS-CM2"],
                    scenarios=["ssp245"],
                    fixed_season="12-01:03-31",
                )
        finally:
            eh._evaluate = orig_evaluate

        self.assertIn("needs following-year tail data (2042)", buf.getvalue())

    def test_evaluate_uses_inclusive_length_days(self):
        orig_fetch = eh._fetch
        orig_calc = eh.calculate_season_statistics
        eh._fetch = lambda *args, **kwargs: None
        eh.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 600.0,
            "mean_temperature_c": 24.0,
        }
        try:
            result = eh._evaluate(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                w={
                    "start": "2041-01-01",
                    "end": "2041-12-31",
                    "season_number": 1,
                    "year": 2041,
                    "total": 1,
                },
                model="ACCESS-CM2",
                scenario="ssp245",
                thresholds=eh.resolve_thresholds("Maize"),
            )
        finally:
            eh._fetch = orig_fetch
            eh.calculate_season_statistics = orig_calc

        self.assertEqual(365, result["season_info"]["length_days"])

    def test_detect_windows_explains_empty_onset_year_range(self):
        orig = eh.fetch_and_analyze_years
        eh.fetch_and_analyze_years = lambda *args, **kwargs: ({1991: []}, {1991: {}})
        try:
            with self.assertRaisesRegex(RuntimeError, "No onset-year seasons found"):
                eh._detect_windows(-1.286, 36.817, 1991, 1991, "ACCESS-CM2", "historical")
        finally:
            eh.fetch_and_analyze_years = orig

    def test_calculate_ensemble_keeps_scenarios_separate(self):
        orig_detect = eh._detect_windows
        orig_evaluate = eh._evaluate
        eh._detect_windows = lambda *args, **kwargs: [
            {
                "start": "2050-03-01",
                "end": "2050-05-31",
                "season_number": 1,
                "year": 2050,
                "total": 1,
            }
        ]

        def fake_evaluate(crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat):
            precip = 600.0 if scenario == "ssp245" else 300.0
            status = "no_stress" if scenario == "ssp245" else "severe_stress_low"
            return {
                "season_info": {**window, "length_days": 91},
                "season_statistics": {
                    "total_precipitation_mm": precip,
                    "mean_temperature_c": 24.0,
                },
                "hazard_evaluation": {
                    "precipitation": {"value_mm": precip, "status": status},
                    "temperature": {"value_c": 24.0, "status": "no_stress"},
                },
                "projection": {"model": model, "scenario": scenario},
            }

        eh._evaluate = fake_evaluate
        try:
            result = eh.calculate_ensemble(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                start_year=2050,
                end_year=2050,
                models=["ACCESS-CM2"],
                scenarios=["ssp245", "ssp585"],
            )
        finally:
            eh._detect_windows = orig_detect
            eh._evaluate = orig_evaluate

        self.assertEqual(2, len(result["assessments"]))
        self.assertEqual(
            ["ssp245", "ssp585"],
            [block["scenario"] for block in result["assessments"]],
        )
        self.assertEqual(
            ["ssp245", "ssp585"],
            [block["scenario"] for block in result["scenario_ensembles"]],
        )
        self.assertIsNone(result["overall_ensemble"])
        self.assertIn("warning", result)
        self.assertIn("disabled", result["warning"])

    def test_calculate_ensemble_preserves_season_slots_in_scenario_summaries(self):
        orig_evaluate = eh._evaluate

        def fake_evaluate(crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat):
            precip = 600.0 if window["season_number"] == 1 else 300.0
            return {
                "season_info": {**window, "length_days": 91},
                "season_statistics": {
                    "total_precipitation_mm": precip,
                    "mean_temperature_c": 24.0,
                },
                "hazard_evaluation": {
                    "precipitation": {"value_mm": precip, "status": "no_stress"},
                    "temperature": {"value_c": 24.0, "status": "no_stress"},
                },
                "projection": {"model": model, "scenario": scenario},
            }

        eh._evaluate = fake_evaluate
        try:
            result = eh.calculate_ensemble(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                start_year=2050,
                end_year=2050,
                models=["ACCESS-CM2"],
                scenarios=["ssp245"],
                fixed_season="03-01:05-31,10-01:12-15",
            )
        finally:
            eh._evaluate = orig_evaluate

        self.assertIsNone(result["overall_ensemble"])
        self.assertIn("warning", result)
        self.assertIn("Cross-season pooled overall ensemble disabled", result["warning"])
        self.assertEqual(2, len(result["scenario_ensembles"]))
        self.assertEqual(
            [(1, 2), (2, 2)],
            [(block["season_number"], block["total_seasons_per_year"]) for block in result["scenario_ensembles"]],
        )
        self.assertEqual(
            [600.0, 300.0],
            [block["season_statistics"]["total_precipitation_mm"] for block in result["scenario_ensembles"]],
        )

    def test_calculate_ensemble_disables_scenario_rollup_when_auto_counts_vary_by_year(self):
        orig_detect = eh._detect_windows
        orig_evaluate = eh._evaluate

        def fake_detect(*args, **kwargs):
            return [
                {
                    "start": "2050-03-01",
                    "end": "2050-05-31",
                    "season_number": 1,
                    "year": 2050,
                    "total": 1,
                },
                {
                    "start": "2051-03-01",
                    "end": "2051-05-31",
                    "season_number": 1,
                    "year": 2051,
                    "total": 2,
                },
                {
                    "start": "2051-10-01",
                    "end": "2051-12-15",
                    "season_number": 2,
                    "year": 2051,
                    "total": 2,
                },
            ]

        eh._detect_windows = fake_detect
        eh._evaluate = lambda crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat: {
            "season_info": {**window, "length_days": 91},
            "season_statistics": {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 24.0,
            },
            "hazard_evaluation": {
                "precipitation": {"value_mm": 600.0, "status": "no_stress"},
                "temperature": {"value_c": 24.0, "status": "no_stress"},
            },
            "projection": {"model": model, "scenario": scenario},
        }
        try:
            result = eh.calculate_ensemble(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                start_year=2050,
                end_year=2051,
                models=["ACCESS-CM2"],
                scenarios=["ssp245"],
            )
        finally:
            eh._detect_windows = orig_detect
            eh._evaluate = orig_evaluate

        self.assertIn("season_slot_warning", result)
        self.assertIn("Auto-detected season counts differ across years within scenario", result["season_slot_warning"])
        self.assertEqual([], result["scenario_ensembles"])
        self.assertIsNone(result["overall_ensemble"])

    def test_calculate_ensemble_keeps_overall_summary_for_single_scenario(self):
        orig_detect = eh._detect_windows
        orig_evaluate = eh._evaluate
        eh._detect_windows = lambda *args, **kwargs: [
            {
                "start": "2050-03-01",
                "end": "2050-05-31",
                "season_number": 1,
                "year": 2050,
                "total": 1,
            }
        ]

        eh._evaluate = lambda crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat: {
            "season_info": {**window, "length_days": 91},
            "season_statistics": {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 24.0,
            },
            "hazard_evaluation": {
                "precipitation": {"value_mm": 600.0, "status": "no_stress"},
                "temperature": {"value_c": 24.0, "status": "no_stress"},
            },
            "projection": {"model": model, "scenario": scenario},
        }
        try:
            result = eh.calculate_ensemble(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                start_year=2050,
                end_year=2050,
                models=["ACCESS-CM2"],
                scenarios=["ssp245"],
            )
        finally:
            eh._detect_windows = orig_detect
            eh._evaluate = orig_evaluate

        self.assertIsNotNone(result["overall_ensemble"])
        self.assertEqual(["ssp245"], result["overall_ensemble"]["scenarios"])
        self.assertFalse(result["overall_ensemble"]["mixed_scenarios"])
        self.assertNotIn("warning", result)

    def test_calculate_ensemble_carries_water_balance_methodology(self):
        orig_detect = eh._detect_windows
        orig_evaluate = eh._evaluate
        eh._detect_windows = lambda *args, **kwargs: [
            {
                "start": "2050-03-01",
                "end": "2050-05-31",
                "season_number": 1,
                "year": 2050,
                "total": 1,
            }
        ]

        eh._evaluate = lambda crop, lat, lon, window, model, scenario, thresholds, soilcp, soilsat: {
            "season_info": {**window, "length_days": 91},
            "season_statistics": {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 24.0,
                "NDWS": 8,
                "NDWL0": 1,
            },
            "water_balance_methodology": {
                "threshold_source": "Atlas-inspired provisional day-count bands",
                "count_window": {
                    "requested_mode": "crop_active",
                    "applied_mode": "crop_active",
                    "counted_days": 70,
                    "counted_subseasons": 1,
                },
            },
            "hazard_evaluation": {
                "precipitation": {"value_mm": 600.0, "status": "no_stress"},
                "temperature": {"value_c": 24.0, "status": "no_stress"},
                "NDWS": {"value_days": 8, "status": "no_stress"},
                "NDWL0": {"value_days": 1, "status": "no_stress"},
            },
            "projection": {"model": model, "scenario": scenario},
        }
        try:
            result = eh.calculate_ensemble(
                crop="maize",
                lat=-1.286,
                lon=36.817,
                start_year=2050,
                end_year=2050,
                models=["ACCESS-CM2"],
                scenarios=["ssp245"],
                fixed_season="03-01:05-31",
                water_balance_window="crop_active",
            )
        finally:
            eh._detect_windows = orig_detect
            eh._evaluate = orig_evaluate

        self.assertEqual(
            "crop_active",
            result["water_balance_methodology"]["count_window"]["applied_mode"],
        )
        self.assertEqual(
            "crop_active",
            result["soil_water_balance"]["water_balance_window"],
        )
        self.assertEqual(
            "Atlas-inspired provisional day-count bands",
            result["scenario_ensembles"][0]["water_balance_methodology"]["threshold_source"],
        )

    def test_evaluate_reports_perhumid_crop_active_fallback_reason(self):
        orig_fetch = eh._fetch
        orig_calc = eh.calculate_season_statistics
        orig_eval = eh.evaluate_hazard_metrics
        orig_detect = getattr(eh, "detect_onset_cessation", None)
        orig_has_fay = eh.HAS_FAY

        dates = eh.pd.date_range("2050-03-01", periods=20, freq="D")
        eh._fetch = lambda *args, **kwargs: eh.pd.DataFrame(
            {
                "date": dates,
                "precipitation": [12.0] * len(dates),
                "max_temperature": [29.0] * len(dates),
                "min_temperature": [22.0] * len(dates),
                "ET0_mm_day": [4.0] * len(dates),
            }
        )
        eh.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 2200.0,
            "mean_temperature_c": 25.0,
            "NDWS": 7,
            "NDWL0": 81,
        }
        eh.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"value_mm": 2200.0, "status": "no_stress"},
            "temperature": {"value_c": 25.0, "status": "no_stress"},
            "NDWS": {"value_days": stats["NDWS"], "status": "no_stress"},
            "NDWL0": {"value_days": stats["NDWL0"], "status": "extreme_stress"},
        }
        eh.detect_onset_cessation = lambda df: (_ for _ in ()).throw(
            ValueError(
                "Perhumid location (annual rain=2218mm, low-rain months=0, rainy days=224). "
                "No clear onset/cessation."
            )
        )
        eh.HAS_FAY = True
        try:
            result = eh._evaluate(
                crop="maize",
                lat=4.8156,
                lon=7.0498,
                w={
                    "start": "2050-03-01",
                    "end": "2050-10-31",
                    "fixed_season": True,
                    "water_balance_window": "crop_active",
                    "season_number": 1,
                    "year": 2050,
                    "total": 1,
                },
                model="ACCESS-CM2",
                scenario="ssp245",
                thresholds=eh.resolve_thresholds("Maize"),
            )
        finally:
            eh._fetch = orig_fetch
            eh.calculate_season_statistics = orig_calc
            eh.evaluate_hazard_metrics = orig_eval
            if orig_detect is not None:
                eh.detect_onset_cessation = orig_detect
            eh.HAS_FAY = orig_has_fay

        methodology = result["water_balance_methodology"]
        self.assertEqual("full_window", methodology["count_window"]["applied_mode"])
        self.assertIn("Perhumid location", " ".join(methodology["warnings"]))

    def test_hazard_statuses_come_from_projection_distribution_not_mean_climate(self):
        bucket = [
            {
                "hazard_evaluation": {
                    "precipitation": {"value_mm": 450.0, "status": "moderate_stress_low"},
                    "temperature": {"value_c": 24.0, "status": "no_stress"},
                }
            },
            {
                "hazard_evaluation": {
                    "precipitation": {"value_mm": 550.0, "status": "no_stress"},
                    "temperature": {"value_c": 24.0, "status": "no_stress"},
                }
            },
        ]

        result = eh._aggregate_hazard_statuses(
            bucket,
            {
                "total_precipitation_mm": 500.0,
                "mean_temperature_c": 24.0,
            },
        )

        self.assertEqual("mixed", result["precipitation"]["status"])
        self.assertEqual(
            {
                "moderate_stress_low": 1,
                "no_stress": 1,
            },
            result["precipitation"]["status_counts"],
        )
        self.assertEqual(500.0, result["precipitation"]["value_mm"])
        self.assertEqual("no_stress", result["temperature"]["status"])


if __name__ == "__main__":
    unittest.main()
