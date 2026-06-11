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

from climate_tookit.calculate_hazards.hazards import (
    build_actual_vs_ltm_comparisons,
    compute_ltm_baseline,
    evaluate_hazard_metrics,
    resolve_thresholds,
)


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

    def test_build_actual_vs_ltm_comparisons_matches_season_slot_and_computes_deltas(self):
        thresholds = resolve_thresholds("Maize")
        assessments = [
            {
                "season_info": {"year": 2018, "season_number": 1, "total_seasons_per_year": 2},
                "season_statistics": {
                    "total_precipitation_mm": 600.0,
                    "mean_temperature_c": 25.0,
                    "min_tmin_c": 12.0,
                    "max_tmax_c": 34.0,
                    "NDD": 18,
                    "NTx35": 5,
                    "NTx40": 0,
                    "NDWS": 12,
                    "NDWL0": 1,
                    "dry_spell_statistics": {
                        "number_of_dry_spells": 2,
                        "max_dry_spell_length_days": 9,
                        "mean_dry_spell_length_days": 8.5,
                    },
                },
                "hazard_evaluation": evaluate_hazard_metrics(
                    {
                        "total_precipitation_mm": 600.0,
                        "mean_temperature_c": 25.0,
                        "NDD": 18,
                        "NTx35": 5,
                        "NTx40": 0,
                        "NDWS": 12,
                        "NDWL0": 1,
                    },
                    thresholds,
                ),
            },
            {
                "season_info": {"year": 2019, "season_number": 1, "total_seasons_per_year": 2},
                "season_statistics": {
                    "total_precipitation_mm": 500.0,
                    "mean_temperature_c": 24.0,
                    "min_tmin_c": 11.0,
                    "max_tmax_c": 33.0,
                    "NDD": 20,
                    "NTx35": 7,
                    "NTx40": 1,
                    "NDWS": 15,
                    "NDWL0": 2,
                    "dry_spell_statistics": {
                        "number_of_dry_spells": 3,
                        "max_dry_spell_length_days": 10,
                        "mean_dry_spell_length_days": 9.0,
                    },
                },
                "hazard_evaluation": evaluate_hazard_metrics(
                    {
                        "total_precipitation_mm": 500.0,
                        "mean_temperature_c": 24.0,
                        "NDD": 20,
                        "NTx35": 7,
                        "NTx40": 1,
                        "NDWS": 15,
                        "NDWL0": 2,
                    },
                    thresholds,
                ),
            },
            {
                "season_info": {"year": 2018, "season_number": 2, "total_seasons_per_year": 2},
                "season_statistics": {
                    "total_precipitation_mm": 900.0,
                    "mean_temperature_c": 21.0,
                },
                "hazard_evaluation": evaluate_hazard_metrics(
                    {"total_precipitation_mm": 900.0, "mean_temperature_c": 21.0},
                    thresholds,
                ),
            },
        ]
        baseline_ltm = compute_ltm_baseline(assessments, "Maize", thresholds)
        comparisons = build_actual_vs_ltm_comparisons(assessments, baseline_ltm)

        self.assertEqual(3, len(comparisons))
        season1_2018 = comparisons[0]
        self.assertEqual(2018, season1_2018["year"])
        self.assertEqual(1, season1_2018["season_number"])
        self.assertEqual(50.0, season1_2018["metrics"]["total_mm"]["delta"])
        self.assertEqual(9.09, season1_2018["metrics"]["total_mm"]["pct"])
        self.assertEqual(-1.0, season1_2018["metrics"]["NDD"]["delta"])
        self.assertEqual(-5.26, season1_2018["metrics"]["NDD"]["pct"])
        self.assertIn("precipitation", season1_2018["hazard_status_comparison"])

        season2 = comparisons[2]
        self.assertEqual(2, season2["season_number"])
        self.assertEqual(900.0, season2["metrics"]["total_mm"]["baseline_ltm"])


if __name__ == "__main__":
    unittest.main()
