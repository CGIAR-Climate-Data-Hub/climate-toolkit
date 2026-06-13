import sys
import tempfile
import types
import unittest
import json
import pandas as pd


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
    DEFAULT_SOILCP,
    DEFAULT_SOILSAT,
    build_actual_vs_ltm_comparisons,
    calc_water_balance,
    calculate_hazards,
    calculate_season_statistics,
    compute_ltm_baseline,
    _derive_soil_storage_params_from_row,
    evaluate_hazard_metrics,
    get_climate_data_for_season,
    load_crop_water_balance_params,
    resolve_crop_water_balance_params,
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

    def test_calculate_hazards_fixed_season_reuses_prefetched_window_df(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        prefetched = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2020-01-01", "2020-03-01", "2020-03-02", "2020-05-31"]),
                "precip": [12.0, 10.0, 0.0, 0.0],
                "tmax": [27.0, 28.0, 29.0, 29.0],
                "tmin": [15.0, 16.0, 17.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0, 4.0],
            }
        )

        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-05-31"),
                        "length_days": 92,
                        "window_df": prefetched,
                    }
                ]
            },
            {},
        )
        hazards.get_climate_data_for_season = lambda *args, **kwargs: self.fail(
            "fixed-season path should reuse prefetched window_df"
        )
        hazards.calculate_season_statistics = lambda df, **kwargs: {
            "row_count": len(df),
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

        self.assertEqual(4, result["season_statistics"]["row_count"])

    def test_calculate_hazards_fixed_season_reuses_prefetched_source_df_for_spinup(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        source_df = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(
                    ["2020-01-01", "2020-02-01", "2020-03-01", "2020-03-02", "2020-05-31"]
                ),
                "precip": [12.0, 8.0, 10.0, 0.0, 0.0],
                "tmax": [27.0, 27.5, 28.0, 29.0, 29.0],
                "tmin": [15.0, 15.5, 16.0, 17.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0, 4.0, 4.0],
            }
        )
        short_window_df = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2020-03-01", "2020-03-02", "2020-05-31"]),
                "precip": [10.0, 0.0, 0.0],
                "tmax": [28.0, 29.0, 29.0],
                "tmin": [16.0, 17.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0],
            }
        )

        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-05-31"),
                        "length_days": 92,
                        "window_df": short_window_df,
                        "source_df": source_df,
                    }
                ]
            },
            {},
        )
        hazards.get_climate_data_for_season = lambda *args, **kwargs: self.fail(
            "fixed-season path should reuse prefetched source_df before refetching"
        )
        hazards.calculate_season_statistics = lambda df, **kwargs: {
            "row_count": len(df),
            "first_date": str(hazards.pd.to_datetime(df["date"]).min().date()),
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
                source="auto",
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual(5, result["season_statistics"]["row_count"])
        self.assertEqual("2020-01-01", result["season_statistics"]["first_date"])

    def test_calculate_hazards_auto_detect_honors_requested_source(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        detect_calls = []
        season_fetch_calls = []

        orig_detect = hazards.fetch_and_analyze_years
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        hazards.fetch_and_analyze_years = lambda lat, lon, start_year, end_year, extra_months=6, source="auto", model=None, scenario=None: (
            detect_calls.append(
                {
                    "start_year": start_year,
                    "end_year": end_year,
                    "source": source,
                }
            ) or {
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
                source="agera_5",
            )
        finally:
            hazards.fetch_and_analyze_years = orig_detect
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual("agera_5", detect_calls[0]["source"])
        self.assertEqual("agera_5", season_fetch_calls[0]["source"])
        self.assertEqual("agera_5", result["season_info"]["source"])

    def test_calculate_hazards_rejects_post_2016_chirps_chirts_window(self):
        result = calculate_hazards(
            crop_name="maize",
            location_coord=(-1.286, 36.817),
            date_from="2018-01-01",
            date_to="2019-12-31",
            source="chirps+chirts",
        )

        self.assertIn("error", result)
        self.assertIn("currently ends in 2016", result["error"])

    def test_calculate_hazards_auto_detect_keeps_no_season_message_for_true_empty_detection(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_detect = hazards.fetch_and_analyze_years
        hazards.fetch_and_analyze_years = lambda *args, **kwargs: ({2020: []}, {})
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                source="auto",
            )
        finally:
            hazards.fetch_and_analyze_years = orig_detect

        self.assertEqual(
            "No growing season detected. Provide --season-start/--season-end or --fixed-season.",
            result["error"],
        )

    def test_calculate_hazards_auto_detect_surfaces_detection_fetch_error(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_detect = hazards.fetch_and_analyze_years
        hazards.fetch_and_analyze_years = lambda *args, **kwargs: (
            {2020: []},
            {2020: {"error": "HTTPSConnectionPool(...)"}},
        )
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                source="auto",
            )
        finally:
            hazards.fetch_and_analyze_years = orig_detect

        self.assertIn("Growing-season detection failed before season identification", result["error"])
        self.assertIn("HTTPSConnectionPool", result["error"])

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

    def test_resolve_crop_water_balance_params_uses_existing_crop_registry(self):
        params = resolve_crop_water_balance_params("Maize")
        loaded = load_crop_water_balance_params()
        self.assertEqual(loaded["Maize"]["kc_init"], params["kc_init"])
        self.assertEqual(loaded["Maize"]["kc_mid"], params["kc_mid"])
        self.assertEqual(loaded["Maize"]["kc_end"], params["kc_end"])
        self.assertEqual(loaded["Maize"]["root_depth_m"], params["root_depth_m"])
        self.assertEqual(loaded["Maize"]["depletion_fraction_p"], params["depletion_fraction_p"])

    def test_load_crop_water_balance_params_reads_external_json_file(self):
        payload = {
            "Maize": {
                "kc_init": 0.4,
                "kc_mid": 1.33,
                "kc_end": 0.7,
                "root_depth_m": 1.7,
                "depletion_fraction_p": 0.61,
                "source_doc": "test fixture",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(payload, handle)
            temp_path = handle.name
        try:
            loaded = load_crop_water_balance_params(temp_path)
            self.assertEqual(1.33, loaded["Maize"]["kc_mid"])
            resolved = resolve_crop_water_balance_params("Maize", params_path=temp_path)
            self.assertEqual(0.4, resolved["kc_init"])
            self.assertEqual(1.7, resolved["root_depth_m"])
            self.assertEqual(0.61, resolved["depletion_fraction_p"])
        finally:
            import os
            os.unlink(temp_path)

    def test_resolve_crop_water_balance_params_missing_crop_uses_generic_default_with_warning(self):
        params = resolve_crop_water_balance_params("Plantain")
        self.assertEqual(0.7, params["kc_init"])
        self.assertEqual(1.0, params["kc_mid"])
        self.assertEqual(0.8, params["kc_end"])
        self.assertEqual(1.0, params["root_depth_m"])
        self.assertEqual(0.5, params["depletion_fraction_p"])
        self.assertEqual("generic fallback", params["source_doc"])
        self.assertIn("using generic defaults", params["warning"])

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

    def test_derive_soil_storage_params_from_row_uses_soil_grid_values(self):
        derived = _derive_soil_storage_params_from_row(
            {
                "soil_field_capacity": 0.36,
                "soil_bulk_density": 1.3,
                "soil_clay_content": 0.32,
                "soil_sand_content": 0.28,
                "soil_organic_carbon": 0.02,
            },
            root_depth_row={"soil_root_depth": 150},
            crop_root_depth_m=1.2,
        )

        self.assertIsNotNone(derived)
        self.assertEqual("soil_grid_scaled_hwsd_root_depth", derived["source"])
        self.assertGreater(derived["soilcp"], DEFAULT_SOILCP)
        self.assertGreater(derived["soilsat"], 20.0)
        self.assertEqual(1.2, derived["root_depth_m"])
        self.assertEqual("min(crop_default,hwsd)", derived["root_depth_source"])
        self.assertIsNotNone(derived["taw_mm"])

    def test_calculate_hazards_uses_resolved_soil_parameters_for_ndws(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fetch = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics
        orig_resolve = hazards._resolve_soil_storage_params

        calc_calls = []

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
        hazards.get_climate_data_for_season = lambda *args, **kwargs: hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2020-03-01", "2020-03-02"]),
                "precipitation": [4.0, 0.0],
                "max_temperature": [28.0, 29.0],
                "min_temperature": [16.0, 17.0],
                "ET0_mm_day": [4.0, 4.0],
            }
        )

        def fake_calculate_season_statistics(df, **kwargs):
            calc_calls.append(kwargs)
            return {
                "total_precipitation_mm": 4.0,
                "mean_temperature_c": 22.5,
                "NDWS": 3,
                "NDWL0": 0,
            }

        hazards.calculate_season_statistics = fake_calculate_season_statistics
        hazards.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"status": "no_stress", "value_mm": stats["total_precipitation_mm"]},
            "temperature": {"status": "no_stress", "value_c": stats["mean_temperature_c"]},
            "NDWS": {"status": "no_stress", "value_days": stats["NDWS"]},
            "NDWL0": {"status": "no_stress", "value_days": stats["NDWL0"]},
        }
        hazards._resolve_soil_storage_params = lambda lat, lon, soilcp, soilsat, crop_root_depth_m=None: {
            "soilcp": 145.0,
            "soilsat": 62.0,
            "source": "soil_grid_scaled_hwsd_root_depth",
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
            hazards.fetch_and_analyze_years_fixed = orig_fetch
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval
            hazards._resolve_soil_storage_params = orig_resolve

        self.assertEqual(1, len(calc_calls))
        self.assertEqual(145.0, calc_calls[0]["soilcp"])
        self.assertEqual(62.0, calc_calls[0]["soilsat"])
        self.assertEqual(load_crop_water_balance_params()["Maize"]["kc_init"], calc_calls[0]["kc_init"])
        self.assertEqual(load_crop_water_balance_params()["Maize"]["kc_mid"], calc_calls[0]["kc_mid"])
        self.assertEqual(load_crop_water_balance_params()["Maize"]["kc_end"], calc_calls[0]["kc_end"])
        self.assertEqual(
            load_crop_water_balance_params()["Maize"]["depletion_fraction_p"],
            calc_calls[0]["depletion_fraction_p"],
        )
        self.assertEqual("2020-03-01", calc_calls[0]["analysis_start"])
        self.assertEqual("2020-05-31", calc_calls[0]["analysis_end"])
        self.assertEqual("soil_grid_scaled_hwsd_root_depth", result["soil_parameters"]["source"])
        self.assertEqual(145.0, result["soil_parameters"]["soilcp"])
        self.assertEqual(62.0, result["soil_parameters"]["soilsat"])
        self.assertEqual(load_crop_water_balance_params()["Maize"]["kc_mid"], result["water_balance_parameters"]["kc_mid"])

    def test_calculate_hazards_fetches_spinup_window_before_analysis_period(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        fetch_calls = []

        orig_fetch = hazards.fetch_and_analyze_years_fixed
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
            fetch_calls.append((start_date, end_date, source))
            return hazards.pd.DataFrame(
                {
                    "date": hazards.pd.to_datetime(["2020-01-01", "2020-03-01", "2020-03-02"]),
                    "precipitation": [10.0, 0.0, 0.0],
                    "max_temperature": [28.0, 29.0, 29.0],
                    "min_temperature": [16.0, 17.0, 17.0],
                    "ET0_mm_day": [4.0, 4.0, 4.0],
                }
            )

        hazards.get_climate_data_for_season = fake_window_fetch
        hazards.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 0.0,
            "mean_temperature_c": 23.0,
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
                spinup_days=60,
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fetch
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual(("2020-01-01", "2020-05-31", "era_5"), fetch_calls[0])
        self.assertEqual("2020-01-01", result["season_info"]["fetch_start_date"])
        self.assertEqual(60, result["season_info"]["spinup_days"])

    def test_calculate_season_statistics_uses_spinup_for_ndws_but_not_precip_stats(self):
        df = calculate_season_statistics(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-03-01", "2020-03-02"]),
                    "precipitation": [60.0, 60.0, 0.0, 0.0],
                    "max_temperature": [30.0, 30.0, 30.0, 30.0],
                    "min_temperature": [20.0, 20.0, 20.0, 20.0],
                    "ET0_mm_day": [4.0, 4.0, 4.0, 4.0],
                }
            ),
            soilcp=100.0,
            soilsat=50.0,
            kc=1.0,
            kc_init=1.0,
            kc_mid=1.0,
            kc_end=1.0,
            depletion_fraction_p=0.5,
            analysis_start="2020-03-01",
            analysis_end="2020-03-02",
        )

        self.assertEqual(0.0, df["total_precipitation_mm"])
        self.assertEqual(0, df["rainy_days"])
        self.assertEqual(0, df["NDWS"])

    def test_calc_water_balance_depletion_fraction_can_trigger_stress_before_soil_is_empty(self):
        wb = calc_water_balance(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-03-01"]),
                    "precipitation": [0.0],
                    "ET0_mm_day": [10.0],
                }
            ),
            soilcp=100.0,
            soilsat=50.0,
            kc=1.0,
            depletion_fraction_p=0.5,
            init_avail=40.0,
        )

        self.assertLess(wb.loc[0, "ERATIO"], 1.0)
        self.assertGreater(wb.loc[0, "AVAILABLE_SOIL_WATER_MM"], 0.0)

    def test_calc_water_balance_starts_kc_stages_at_analysis_window_not_spinup_start(self):
        wb = calc_water_balance(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(
                        ["2020-01-01", "2020-01-02", "2020-03-01", "2020-03-02", "2020-03-03", "2020-03-04"]
                    ),
                    "precipitation": [5.0, 5.0, 0.0, 0.0, 0.0, 0.0],
                    "ET0_mm_day": [4.0, 4.0, 4.0, 4.0, 4.0, 4.0],
                }
            ),
            soilcp=100.0,
            soilsat=50.0,
            kc=1.2,
            kc_init=0.3,
            kc_mid=1.2,
            kc_end=0.6,
            depletion_fraction_p=0.55,
            analysis_start="2020-03-01",
            analysis_end="2020-03-04",
        )

        self.assertEqual(0.0, wb.loc[0, "Kc"])
        self.assertEqual(0.0, wb.loc[1, "Kc"])
        self.assertEqual(0.3, wb.loc[2, "Kc"])
        self.assertEqual(1.2, wb.loc[3, "Kc"])
        self.assertEqual(1.2, wb.loc[4, "Kc"])
        self.assertEqual(0.6, wb.loc[5, "Kc"])

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
