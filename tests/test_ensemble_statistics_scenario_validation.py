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


if __name__ == "__main__":
    unittest.main()
