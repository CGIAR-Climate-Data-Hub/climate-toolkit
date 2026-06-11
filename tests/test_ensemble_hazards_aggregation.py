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

import climate_tookit.calculate_hazards.ensemble_hazards as eh


class EnsembleHazardsAggregationTests(unittest.TestCase):
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

        def fake_evaluate(crop, lat, lon, window, model, scenario, soilcp, soilsat):
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
        self.assertTrue(result["overall_ensemble"]["mixed_scenarios"])
        self.assertEqual(
            ["ssp245", "ssp585"],
            result["overall_ensemble"]["scenarios"],
        )
        self.assertIn("warning", result["overall_ensemble"])

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
