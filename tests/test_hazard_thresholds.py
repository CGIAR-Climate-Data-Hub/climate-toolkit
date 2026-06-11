import sys
import types
import unittest


def _install_test_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

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

from climate_tookit.calculate_hazards.hazards import evaluate_hazard_metrics, resolve_thresholds


class HazardThresholdTests(unittest.TestCase):
    def test_resolve_thresholds_includes_atlas_index_defaults(self):
        thresholds = resolve_thresholds("Maize")
        self.assertIn("Total Precip", thresholds)
        self.assertIn("TAVG", thresholds)
        self.assertIn("NDD", thresholds)
        self.assertIn("NTx35", thresholds)
        self.assertIn("NTx40", thresholds)
        self.assertIn("NDWS", thresholds)
        self.assertIn("NDWL0", thresholds)

    def test_resolve_thresholds_merges_user_override_without_dropping_defaults(self):
        thresholds = resolve_thresholds(
            "Maize",
            custom_thresholds={
                "NDD": {
                    "no_stress": (None, 5),
                    "moderate_stress": (5, 10),
                    "severe_stress": (10, 15),
                    "extreme_stress": (15, None),
                }
            },
        )
        self.assertIn("Total Precip", thresholds)
        self.assertEqual((None, 5), thresholds["NDD"]["no_stress"])

    def test_evaluate_hazard_metrics_covers_atlas_index_statuses(self):
        thresholds = resolve_thresholds("Maize")
        result = evaluate_hazard_metrics(
            {
                "total_precipitation_mm": 600.0,
                "mean_temperature_c": 25.0,
                "NDD": 16,
                "NTx35": 22,
                "NTx40": 11,
                "NDWS": 26,
                "NDWL0": 6,
            },
            thresholds,
        )
        self.assertEqual("no_stress", result["precipitation"]["status"])
        self.assertEqual("no_stress", result["temperature"]["status"])
        self.assertEqual("moderate_stress", result["NDD"]["status"])
        self.assertEqual("severe_stress", result["NTx35"]["status"])
        self.assertEqual("extreme_stress", result["NTx40"]["status"])
        self.assertEqual("extreme_stress", result["NDWS"]["status"])
        self.assertEqual("severe_stress", result["NDWL0"]["status"])


if __name__ == "__main__":
    unittest.main()
