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


if __name__ == "__main__":
    unittest.main()
