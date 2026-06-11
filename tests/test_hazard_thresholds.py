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
    calculate_hazards,
    compute_ltm_baseline,
    evaluate_hazard_metrics,
    get_climate_data_for_season,
    resolve_thresholds,
)


class HazardThresholdTests(unittest.TestCase):
    def test_get_climate_data_for_season_forwards_requested_source(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        calls = []

        def fake_get_climate_data(lat, lon, start_date, end_date, force_source=None, model=None, scenario=None):
            calls.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "force_source": force_source,
                    "model": model,
                    "scenario": scenario,
                }
            )
            return hazards.pd.DataFrame(
                {
                    "date": hazards.pd.to_datetime(["2020-03-01", "2020-03-02"]),
                    "tmax": [28.0, 29.0],
                    "tmin": [16.0, 17.0],
                    "precip": [1.0, 0.0],
                }
            )

        orig_get = hazards.get_climate_data
        orig_add = hazards.add_et0
        hazards.get_climate_data = fake_get_climate_data
        hazards.add_et0 = lambda df, lat: df.assign(ET0_mm_day=[4.0, 4.0])
        try:
            frame = get_climate_data_for_season(
                -1.286,
                36.817,
                "2020-03-01",
                "2020-03-02",
                source="era_5",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            hazards.get_climate_data = orig_get
            hazards.add_et0 = orig_add

        self.assertEqual("era_5", calls[0]["force_source"])
        self.assertEqual("ACCESS-CM2", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])
        self.assertIn("ET0_mm_day", frame.columns)

    def test_calculate_hazards_fixed_season_uses_selected_source_for_window_fetch(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        season_fetch_calls = []

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics
        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-05-31"),
                        "length_days": 92,
                    }
                ]
            },
            {},
        )

        def fake_window_fetch(lat, lon, start_date, end_date, source="auto", model=None, scenario=None):
            season_fetch_calls.append(
                {
                    "source": source,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            return hazards.pd.DataFrame(
                {
                    "date": hazards.pd.to_datetime(["2020-03-01", "2020-03-02"]),
                    "precipitation": [10.0, 0.0],
                    "max_temperature": [28.0, 29.0],
                    "min_temperature": [16.0, 17.0],
                    "ET0_mm_day": [4.0, 4.0],
                }
            )

        hazards.get_climate_data_for_season = fake_window_fetch
        hazards.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 10.0,
            "mean_temperature_c": 22.5,
        }
        hazards.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"status": "no_stress", "value_mm": stats["total_precipitation_mm"]},
            "temperature": {"status": "no_stress", "value_c": stats["mean_temperature_c"]},
        }
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                fixed_season="03-01:05-31",
                source="era_5",
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual("era_5", season_fetch_calls[0]["source"])
        self.assertEqual("era_5", result["season_info"]["source"])

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
