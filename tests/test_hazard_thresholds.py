import sys
import tempfile
import types
import unittest
import json
import io
from pathlib import Path
from unittest import mock
import pandas as pd
from climate_tookit.climatology.xclim_reference import (
    XCLIM_AVAILABLE,
    compute_xclim_hazard_count_metrics,
)


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
    CROP_ACTIVE_WATER_BALANCE,
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
    def test_print_actual_vs_ltm_comparisons_uses_compact_headers(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        buf = io.StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = buf
            hazards._print_actual_vs_ltm_comparisons(
                [
                    {
                        "year": 2020,
                        "metrics": {
                            "total_precip": {
                                "label": "Total precipitation",
                                "actual": 800.0,
                                "baseline_ltm": 700.0,
                                "delta": 100.0,
                                "pct": 14.29,
                                "unit": "mm",
                            }
                        },
                    }
                ]
            )
        finally:
            sys.stdout = orig_stdout

        rendered = buf.getvalue()
        self.assertIn("metric", rendered)
        self.assertIn("base", rendered)
        self.assertNotIn("Metric", rendered)
        self.assertNotIn("baseline_ltm", rendered)

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_calculate_season_statistics_matches_xclim_hazard_day_counts(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=10, freq="D"),
                "precip": [0.0, 0.5, 1.0, 2.0, 0.0, 0.9, 5.0, 0.0, 0.0, 1.1],
                "tmax": [34.0, 35.0, 36.0, 40.0, 41.0, 20.0, 35.0, 39.0, 40.0, 10.0],
                "tmin": [20.0, 19.0, 18.0, 21.0, 22.0, 15.0, 19.0, 18.0, 20.0, 12.0],
            }
        )

        stats = calculate_season_statistics(frame)
        xclim_counts = compute_xclim_hazard_count_metrics(frame).iloc[0].to_dict()

        self.assertEqual(int(xclim_counts["NDD"]), stats["NDD"])
        self.assertEqual(int(xclim_counts["NTx35"]), stats["NTx35"])
        self.assertEqual(int(xclim_counts["NTx40"]), stats["NTx40"])

    def test_calculate_season_statistics_adds_thi_metrics_when_humidity_present(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=4, freq="D"),
                "precip": [1.0, 0.0, 2.0, 0.0],
                "tmax": [30.0, 32.0, 34.0, 36.0],
                "tmin": [20.0, 22.0, 23.0, 25.0],
                "humidity": [50.0, 80.0, 85.0, 90.0],
            }
        )

        stats = calculate_season_statistics(frame)

        self.assertIn("mean_thi", stats)
        self.assertIn("max_thi", stats)
        self.assertIn("thi_stress_days", stats)
        self.assertGreater(stats["thi_stress_days"], 0)

    def test_evaluate_hazard_metrics_includes_thi_band(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        hazard_eval = evaluate_hazard_metrics(
            {"mean_thi": 80.0},
            {"THI": hazards.ATLAS_HAZARD_INDEX_THRESHOLDS["THI"]},
        )

        self.assertEqual("moderate", hazard_eval["THI"]["status"])
        self.assertEqual(80.0, hazard_eval["THI"]["value_thi"])

    def test_resolve_thresholds_uses_livestock_profile_specific_thi_cutoffs(self):
        thresholds = resolve_thresholds(
            "Maize",
            livestock_type="poultry_layers",
            livestock_climate_profile="temperate",
        )

        self.assertEqual((None, 71.0), thresholds["THI"]["none"])
        self.assertEqual((76.0, 82.0), thresholds["THI"]["moderate"])

    def test_fetch_soil_grid_snapshot_uses_callable_fetch_data_function(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        hazards._fetch_soil_grid_snapshot.cache_clear()
        with mock.patch(
            "climate_tookit.fetch_data.fetch_data.fetch_data",
            return_value=hazards.pd.DataFrame(
                [{"soil_field_capacity": 0.34, "soil_wilting_point": 0.14}]
            ),
        ) as fake_fetch:
            row = hazards._fetch_soil_grid_snapshot(-1.286, 36.817)

        self.assertEqual(0.34, row["soil_field_capacity"])
        self.assertEqual("soil_grid", fake_fetch.call_args.kwargs["source"])

    def test_main_creates_missing_output_directory_for_json(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_calculate = hazards.calculate_hazards
        orig_argv = sys.argv[:]
        hazards.calculate_hazards = lambda **kwargs: {"ok": True, "crop": "maize"}
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "nested" / "results" / "hazards.json"
                sys.argv = [
                    "hazards.py",
                    "maize",
                    "--location=-1.286,36.817",
                    "--date-from=2020-01-01",
                    "--date-to=2020-12-31",
                    "--format=json",
                    f"--output={output_path}",
                ]
                hazards.main()
                self.assertTrue(output_path.exists())
        finally:
            hazards.calculate_hazards = orig_calculate
            sys.argv = orig_argv

    def test_main_json_routes_progress_text_to_stderr(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_calculate = hazards.calculate_hazards
        orig_argv = sys.argv[:]

        def fake_calculate(**kwargs):
            print("progress line from detector")
            return {"ok": True, "crop": "maize"}

        hazards.calculate_hazards = fake_calculate
        try:
            sys.argv = [
                "hazards.py",
                "maize",
                "--location=-1.286,36.817",
                "--date-from=2020-01-01",
                "--date-to=2020-12-31",
                "--format=json",
            ]
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                hazards.main()
        finally:
            hazards.calculate_hazards = orig_calculate
            sys.argv = orig_argv

        self.assertIn('"ok": true', stdout.getvalue())
        self.assertNotIn("progress line from detector", stdout.getvalue())
        self.assertIn("progress line from detector", stderr.getvalue())

    def test_calculate_hazards_disables_ltm_when_auto_detected_season_counts_vary(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_detect = hazards.fetch_and_analyze_years
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        hazards.fetch_and_analyze_years = lambda *args, **kwargs: (
            {
                2018: [
                    {
                        "onset": hazards.pd.Timestamp("2018-03-01"),
                        "cessation": hazards.pd.Timestamp("2018-05-31"),
                        "length_days": 92,
                    }
                ],
                2019: [
                    {
                        "onset": hazards.pd.Timestamp("2019-03-01"),
                        "cessation": hazards.pd.Timestamp("2019-05-31"),
                        "length_days": 92,
                    },
                    {
                        "onset": hazards.pd.Timestamp("2019-10-01"),
                        "cessation": hazards.pd.Timestamp("2019-12-15"),
                        "length_days": 76,
                    },
                ],
            },
            {},
        )
        hazards.get_climate_data_for_season = lambda *args, **kwargs: hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2019-03-01", "2019-03-02"]),
                "precipitation": [10.0, 0.0],
                "max_temperature": [28.0, 29.0],
                "min_temperature": [16.0, 17.0],
                "ET0_mm_day": [4.0, 4.0],
            }
        )
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
                date_from="2018-01-01",
                date_to="2019-12-31",
                source="auto",
            )
        finally:
            hazards.fetch_and_analyze_years = orig_detect
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertIn("warning", result)
        self.assertIn("Auto-detected season counts differ across years", result["warning"])
        self.assertIsNone(result["baseline_ltm"])
        self.assertEqual([], result["baseline_ltm_comparisons"])
        self.assertIn("water_balance_methodology", result)
        self.assertEqual(
            "rainfall_based",
            result["water_balance_methodology"]["analysis_method"],
        )

    def test_get_climate_data_for_season_forwards_requested_source(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        calls = []

        def fake_get_climate_data(
            lat,
            lon,
            start_date,
            end_date,
            force_source=None,
            precip_source=None,
            temp_source=None,
            model=None,
            scenario=None,
            ee_project_id=None,
        ):
            calls.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "force_source": force_source,
                    "precip_source": precip_source,
                    "temp_source": temp_source,
                    "model": model,
                    "scenario": scenario,
                    "ee_project_id": ee_project_id,
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
                ee_project_id="demo-project",
            )
        finally:
            hazards.get_climate_data = orig_get
            hazards.add_et0 = orig_add

        self.assertEqual("era_5", calls[0]["force_source"])
        self.assertEqual("ACCESS-CM2", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])
        self.assertEqual("demo-project", calls[0]["ee_project_id"])
        self.assertIn("ET0_mm_day", frame.columns)

    def test_calculate_hazards_fixed_season_uses_selected_source_for_window_fetch(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        season_fetch_calls = []
        fixed_call_kwargs = []

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        def fake_fixed(*args, **kwargs):
            fixed_call_kwargs.append(kwargs)
            return (
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

        hazards.fetch_and_analyze_years_fixed = fake_fixed

        def fake_window_fetch(
            lat,
            lon,
            start_date,
            end_date,
            source="auto",
            precip_source=None,
            temp_source=None,
            model=None,
            scenario=None,
            ee_project_id=None,
        ):
            season_fetch_calls.append(
                {
                    "source": source,
                    "start_date": start_date,
                    "end_date": end_date,
                    "ee_project_id": ee_project_id,
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
                ee_project_id="demo-project",
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual("era_5", season_fetch_calls[0]["source"])
        self.assertEqual("demo-project", fixed_call_kwargs[0]["ee_project_id"])
        self.assertEqual("demo-project", season_fetch_calls[0]["ee_project_id"])
        self.assertEqual("era_5", result["season_info"]["source"])
        self.assertEqual(60, fixed_call_kwargs[0]["prefetch_pad_days"])
        self.assertEqual("2020-03-01", result["season_info"]["season_identity"]["onset_date"])
        self.assertEqual(
            "regime:fixed|onset_month:03",
            result["season_info"]["season_identity"]["experimental_alignment_key"],
        )

    def test_calculate_hazards_fixed_season_forwards_paired_sources(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        season_fetch_calls = []
        fixed_call_kwargs = []

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        def fake_fixed(*args, **kwargs):
            fixed_call_kwargs.append(kwargs)
            return (
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

        hazards.fetch_and_analyze_years_fixed = fake_fixed

        def fake_window_fetch(
            lat,
            lon,
            start_date,
            end_date,
            source="auto",
            precip_source=None,
            temp_source=None,
            model=None,
            scenario=None,
            ee_project_id=None,
        ):
            season_fetch_calls.append(
                {
                    "source": source,
                    "precip_source": precip_source,
                    "temp_source": temp_source,
                    "ee_project_id": ee_project_id,
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
                source="paired",
                precip_source="tamsat",
                temp_source="agera_5",
                ee_project_id="demo-project",
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual("paired", fixed_call_kwargs[0]["source"])
        self.assertEqual("tamsat", fixed_call_kwargs[0]["precip_source"])
        self.assertEqual("agera_5", fixed_call_kwargs[0]["temp_source"])
        self.assertEqual("demo-project", fixed_call_kwargs[0]["ee_project_id"])
        self.assertEqual("paired", season_fetch_calls[0]["source"])
        self.assertEqual("tamsat", season_fetch_calls[0]["precip_source"])
        self.assertEqual("agera_5", season_fetch_calls[0]["temp_source"])
        self.assertEqual("demo-project", season_fetch_calls[0]["ee_project_id"])
        self.assertEqual("paired", result["season_info"]["source"])

    def test_calculate_hazards_fixed_season_uses_carried_fetch_error_without_refetch(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_window_fetch = hazards.get_climate_data_for_season

        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-05-31"),
                        "length_days": 92,
                        "fetch_error": "paired precip=tamsat returned no usable daily values",
                    }
                ]
            },
            {
                2020: {
                    "fetch_error": "paired precip=tamsat returned no usable daily values",
                }
            },
        )
        hazards.get_climate_data_for_season = lambda *args, **kwargs: self.fail(
            "fixed-season hazard path should not refetch when fetch_error already carried forward"
        )
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                fixed_season="03-01:05-31",
                source="paired",
                precip_source="tamsat",
                temp_source="agera_5",
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.get_climate_data_for_season = orig_window_fetch

        self.assertIn("error", result)
        self.assertIn(
            "Climate data fetch failed for fixed-season hazard window 2020-01-01..2020-05-31",
            result["error"],
        )
        self.assertIn("paired precip=tamsat returned no usable daily values", result["error"])

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
        self.assertIn("water_balance_methodology", result)
        self.assertEqual(
            "fixed_season",
            result["water_balance_methodology"]["analysis_method"],
        )
        self.assertTrue(
            any(
                "Fixed-season mode counts NDWS and NDWL0 only inside the user-defined window"
                in note
                for note in result["water_balance_methodology"]["notes"]
            )
        )

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

    def test_calculate_hazards_fixed_season_can_count_ndws_on_crop_active_subseasons(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        source_df = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(
                    ["2020-01-01", "2020-03-01", "2020-03-15", "2020-04-30", "2020-05-31"]
                ),
                "precipitation": [12.0, 4.0, 8.0, 1.0, 0.0],
                "max_temperature": [27.0, 28.0, 29.0, 30.0, 29.0],
                "min_temperature": [15.0, 16.0, 17.0, 18.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0, 4.0, 4.0],
            }
        )

        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-05-31"),
                        "length_days": 92,
                        "source_df": source_df,
                        "eto_seasons": [
                            {
                                "onset": hazards.pd.Timestamp("2020-03-15"),
                                "cessation": hazards.pd.Timestamp("2020-04-30"),
                                "length_days": 47,
                                "regime": "eto",
                            }
                        ],
                    }
                ]
            },
            {},
        )

        def fake_calc_stats(df, **kwargs):
            start = kwargs.get("analysis_start")
            end = kwargs.get("analysis_end")
            if start == "2020-03-15" and end == "2020-04-30":
                return {
                    "total_precipitation_mm": 40.0,
                    "mean_temperature_c": 22.0,
                    "rainy_days": 10,
                    "dry_days": 37,
                    "NDWS": 12,
                    "NDWL0": 1,
                }
            return {
                "total_precipitation_mm": 80.0,
                "mean_temperature_c": 22.5,
                "rainy_days": 20,
                "dry_days": 72,
                "NDWS": 60,
                "NDWL0": 6,
            }

        hazards.calculate_season_statistics = fake_calc_stats
        hazards.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"status": "no_stress", "value_mm": stats["total_precipitation_mm"]},
            "temperature": {"status": "no_stress", "value_c": stats["mean_temperature_c"]},
            "NDWS": {"status": "no_stress", "value_days": stats["NDWS"]},
            "NDWL0": {"status": "no_stress", "value_days": stats["NDWL0"]},
        }
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                fixed_season="03-01:05-31",
                source="auto",
                water_balance_window=CROP_ACTIVE_WATER_BALANCE,
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual(12, result["season_statistics"]["NDWS"])
        self.assertEqual(1, result["season_statistics"]["NDWL0"])
        methodology = result["water_balance_methodology"]
        self.assertEqual(
            CROP_ACTIVE_WATER_BALANCE,
            methodology["count_window"]["applied_mode"],
        )
        self.assertEqual(1, methodology["count_window"]["counted_subseasons"])
        self.assertEqual(
            "Atlas-inspired provisional day-count bands",
            methodology["threshold_source"],
        )

    def test_calculate_hazards_fixed_season_reports_perhumid_crop_active_fallback(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_fixed = hazards.fetch_and_analyze_years_fixed
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        source_df = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2020-01-01", "2020-03-01", "2020-06-01", "2020-10-31"]),
                "precip": [10.0, 12.0, 15.0, 11.0],
                "tmax": [28.0, 29.0, 28.0, 27.0],
                "tmin": [21.0, 22.0, 21.0, 21.0],
                "ET0_mm_day": [4.0, 4.0, 4.0, 4.0],
            }
        )

        hazards.fetch_and_analyze_years_fixed = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-01"),
                        "cessation": hazards.pd.Timestamp("2020-10-31"),
                        "length_days": 245,
                        "source_df": source_df,
                        "eto_seasons": [],
                        "eto_detection_note": (
                            "Perhumid location (annual rain=2218mm, low-rain months=0, rainy days=224). "
                            "No clear onset/cessation."
                        ),
                    }
                ]
            },
            {},
        )
        hazards.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 2200.0,
            "mean_temperature_c": 25.0,
            "NDWS": 7,
            "NDWL0": 81,
        }
        hazards.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"status": "no_stress", "value_mm": stats["total_precipitation_mm"]},
            "temperature": {"status": "no_stress", "value_c": stats["mean_temperature_c"]},
            "NDWS": {"status": "no_stress", "value_days": stats["NDWS"]},
            "NDWL0": {"status": "extreme_stress", "value_days": stats["NDWL0"]},
        }
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(4.8156, 7.0498),
                date_from="2020-01-01",
                date_to="2020-12-31",
                fixed_season="03-01:10-31",
                source="auto",
                water_balance_window=CROP_ACTIVE_WATER_BALANCE,
            )
        finally:
            hazards.fetch_and_analyze_years_fixed = orig_fixed
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        methodology = result["water_balance_methodology"]
        self.assertEqual(
            "full_window",
            methodology["count_window"]["applied_mode"],
        )
        self.assertIn(
            "Perhumid location",
            " ".join(methodology["warnings"]),
        )

    def test_calculate_hazards_auto_detect_honors_requested_source(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        detect_calls = []
        season_fetch_calls = []

        orig_detect = hazards.fetch_and_analyze_years
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        hazards.fetch_and_analyze_years = lambda lat, lon, start_year, end_year, extra_months=6, source="auto", precip_source=None, temp_source=None, model=None, scenario=None, ee_project_id=None: (
            detect_calls.append(
                {
                    "start_year": start_year,
                    "end_year": end_year,
                    "source": source,
                    "ee_project_id": ee_project_id,
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

        def fake_window_fetch(lat, lon, start_date, end_date, source="auto", precip_source=None, temp_source=None, model=None, scenario=None, ee_project_id=None):
            season_fetch_calls.append(
                {
                    "source": source,
                    "start_date": start_date,
                    "end_date": end_date,
                    "ee_project_id": ee_project_id,
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
        self.assertIsNone(detect_calls[0]["ee_project_id"])
        self.assertEqual("agera_5", season_fetch_calls[0]["source"])
        self.assertIsNone(season_fetch_calls[0]["ee_project_id"])
        self.assertEqual("agera_5", result["season_info"]["source"])

    def test_calculate_hazards_auto_detect_forwards_paired_sources(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        detect_calls = []
        season_fetch_calls = []

        orig_detect = hazards.fetch_and_analyze_years
        orig_window_fetch = hazards.get_climate_data_for_season
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics

        hazards.fetch_and_analyze_years = lambda lat, lon, start_year, end_year, extra_months=6, source="auto", precip_source=None, temp_source=None, model=None, scenario=None, ee_project_id=None: (
            detect_calls.append(
                {
                    "source": source,
                    "precip_source": precip_source,
                    "temp_source": temp_source,
                    "ee_project_id": ee_project_id,
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

        def fake_window_fetch(lat, lon, start_date, end_date, source="auto", precip_source=None, temp_source=None, model=None, scenario=None, ee_project_id=None):
            season_fetch_calls.append(
                {
                    "source": source,
                    "precip_source": precip_source,
                    "temp_source": temp_source,
                    "ee_project_id": ee_project_id,
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
                source="paired",
                precip_source="tamsat",
                temp_source="agera_5",
            )
        finally:
            hazards.fetch_and_analyze_years = orig_detect
            hazards.get_climate_data_for_season = orig_window_fetch
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval

        self.assertEqual("paired", detect_calls[0]["source"])
        self.assertEqual("tamsat", detect_calls[0]["precip_source"])
        self.assertEqual("agera_5", detect_calls[0]["temp_source"])
        self.assertIsNone(detect_calls[0]["ee_project_id"])
        self.assertEqual("paired", season_fetch_calls[0]["source"])
        self.assertEqual("tamsat", season_fetch_calls[0]["precip_source"])
        self.assertEqual("agera_5", season_fetch_calls[0]["temp_source"])
        self.assertIsNone(season_fetch_calls[0]["ee_project_id"])
        self.assertEqual("paired", result["season_info"]["source"])

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

    def test_calculate_hazards_rejects_paired_source_without_partners(self):
        result = calculate_hazards(
            crop_name="maize",
            location_coord=(-1.286, 36.817),
            date_from="2019-01-01",
            date_to="2020-12-31",
            source="paired",
        )

        self.assertIn("error", result)
        self.assertIn("requires both --precip-source and --temp-source", result["error"])

    def test_calculate_hazards_rejects_precip_only_direct_source(self):
        result = calculate_hazards(
            crop_name="maize",
            location_coord=(-1.286, 36.817),
            date_from="2019-01-01",
            date_to="2020-12-31",
            source="tamsat",
        )

        self.assertIn("error", result)
        self.assertIn("precipitation-only", result["error"])

    def test_calculate_hazards_rejects_out_of_range_era5_before_fetch(self):
        result = calculate_hazards(
            crop_name="maize",
            location_coord=(-1.286, 36.817),
            date_from="2018-01-01",
            date_to="2022-12-31",
            source="era_5",
            fixed_season="03-01:06-30",
        )

        self.assertIn("error", result)
        self.assertIn("Requested range for source 'era_5' is outside current coverage", result["error"])
        self.assertIn("Use 'agera_5' or 'auto' for later periods.", result["error"])

    def test_calculate_hazards_rejects_paired_temp_partner_out_of_range(self):
        result = calculate_hazards(
            crop_name="maize",
            location_coord=(-1.286, 36.817),
            date_from="2019-01-01",
            date_to="2022-12-31",
            source="paired",
            precip_source="chirps_v3_daily_rnl",
            temp_source="era_5",
            fixed_season="03-01:06-30",
        )

        self.assertIn("error", result)
        self.assertIn("Requested range for source 'era_5' is outside current coverage", result["error"])

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
            "No growing season detected. Provide --season-start/--season-end, use --fixed-season, or retry with --calendar-source ggcmi.",
            result["error"],
        )

    def test_calculate_hazards_auto_detect_uses_ggcmi_fallback_when_requested(self):
        import climate_tookit.calculate_hazards.hazards as hazards

        orig_resolve_calendar = hazards.resolve_calendar_preset
        orig_fetch_master = hazards.fetch_master_range_with_tail
        orig_auto_prefetched = hazards.analyze_years_auto_on_prefetched_df
        orig_fixed_prefetched = hazards.analyze_years_fixed_on_prefetched_df
        orig_calc_stats = hazards.calculate_season_statistics
        orig_eval = hazards.evaluate_hazard_metrics
        orig_resolve_soil = hazards._resolve_soil_storage_params
        orig_window_fetch = hazards.get_climate_data_for_season

        master_df = hazards.pd.DataFrame(
            {
                "date": hazards.pd.to_datetime(["2020-01-01", "2020-03-11", "2020-06-13"]),
                "precipitation": [0.0, 10.0, 0.0],
                "max_temperature": [28.0, 29.0, 30.0],
                "min_temperature": [16.0, 17.0, 18.0],
                "ET0_mm_day": [4.0, 4.0, 4.0],
            }
        )

        hazards.resolve_calendar_preset = lambda lat, lon, crop_name, system="rf": {
            "calendar_source": "ggcmi_phase3",
            "crop_name": "Maize",
            "calendar_system": system,
            "fixed_season": "03-11:06-13",
        }
        hazards.fetch_master_range_with_tail = lambda *args, **kwargs: master_df
        hazards.analyze_years_auto_on_prefetched_df = lambda *args, **kwargs: ({2020: []}, {})
        hazards.analyze_years_fixed_on_prefetched_df = lambda *args, **kwargs: (
            {
                2020: [
                    {
                        "onset": hazards.pd.Timestamp("2020-03-11"),
                        "cessation": hazards.pd.Timestamp("2020-06-13"),
                        "length_days": 95,
                        "regime": "fixed",
                        "source_df": master_df,
                        "window_df": master_df,
                        "eto_seasons": [],
                        "eto_detection_note": "none detected",
                    }
                ]
            },
            {2020: {"annual_rain_mm": 800.0, "is_humid": False, "low_rain_months": 4, "result_str": "Not humid"}},
        )
        hazards.calculate_season_statistics = lambda *args, **kwargs: {
            "total_precipitation_mm": 10.0,
            "mean_temperature_c": 22.5,
        }
        hazards.evaluate_hazard_metrics = lambda stats, thresholds: {
            "precipitation": {"status": "no_stress", "value_mm": stats["total_precipitation_mm"]},
            "temperature": {"status": "no_stress", "value_c": stats["mean_temperature_c"]},
        }
        hazards._resolve_soil_storage_params = lambda *args, **kwargs: {
            "soilcp": 100.0,
            "soilsat": 50.0,
            "source": "stub",
        }
        hazards.get_climate_data_for_season = lambda *args, **kwargs: self.fail(
            "fallback path should reuse prefetched master dataframe"
        )
        try:
            result = calculate_hazards(
                crop_name="maize",
                location_coord=(-1.286, 36.817),
                date_from="2020-01-01",
                date_to="2020-12-31",
                source="auto",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            hazards.resolve_calendar_preset = orig_resolve_calendar
            hazards.fetch_master_range_with_tail = orig_fetch_master
            hazards.analyze_years_auto_on_prefetched_df = orig_auto_prefetched
            hazards.analyze_years_fixed_on_prefetched_df = orig_fixed_prefetched
            hazards.calculate_season_statistics = orig_calc_stats
            hazards.evaluate_hazard_metrics = orig_eval
            hazards._resolve_soil_storage_params = orig_resolve_soil
            hazards.get_climate_data_for_season = orig_window_fetch

        self.assertNotIn("error", result)
        self.assertTrue(result["calendar_preset_used"])
        self.assertEqual("ggcmi_phase3", result["calendar_preset"]["calendar_source"])
        self.assertEqual(
            ["calendar_preset_fallback_applied", "fixed_season_override"],
            result["season_detection"]["reasons"],
        )
        self.assertEqual("fixed_season", result["season_info"]["method"])

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
        self.assertEqual(
            "soil_grid_texture_pedotransfer_hwsd_root_depth",
            derived["source"],
        )
        self.assertGreater(derived["soilcp"], DEFAULT_SOILCP)
        self.assertGreater(derived["soilsat"], 20.0)
        self.assertEqual(1.2, derived["root_depth_m"])
        self.assertEqual("min(crop_default,hwsd)", derived["root_depth_source"])
        self.assertEqual("soil_grid", derived["field_capacity_source"])
        self.assertEqual("field_capacity_ratio", derived["wilting_point_source"])
        self.assertIsNotNone(derived["taw_mm"])

    def test_derive_soil_storage_params_from_row_marks_pedotransfer_provenance(self):
        derived = _derive_soil_storage_params_from_row(
            {
                "soil_bulk_density": 1.3,
                "soil_clay_content": 0.32,
                "soil_sand_content": 0.28,
                "soil_organic_carbon": 0.02,
            },
            root_depth_row={"soil_root_depth": 150},
            crop_root_depth_m=1.2,
        )

        self.assertIsNotNone(derived)
        self.assertEqual(
            "soil_grid_texture_pedotransfer_hwsd_root_depth",
            derived["source"],
        )
        self.assertEqual("texture_pedotransfer", derived["field_capacity_source"])
        self.assertEqual("field_capacity_ratio", derived["wilting_point_source"])

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

        def fake_window_fetch(lat, lon, start_date, end_date, source="auto", precip_source=None, temp_source=None, model=None, scenario=None, ee_project_id=None):
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
        self.assertEqual(10.0, wb.loc[0, "CROP_WATER_REQUIREMENT_MM"])
        self.assertLess(wb.loc[0, "ACTUAL_CROP_ET_MM"], wb.loc[0, "CROP_WATER_REQUIREMENT_MM"])

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

    def test_calculate_season_statistics_reports_wrsi_from_shared_water_balance(self):
        stats = calculate_season_statistics(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-03-01"]),
                    "precipitation": [0.0],
                    "max_temperature": [30.0],
                    "min_temperature": [20.0],
                    "ET0_mm_day": [10.0],
                }
            ),
            soilcp=100.0,
            soilsat=50.0,
            kc=1.0,
            kc_init=1.0,
            kc_mid=1.0,
            kc_end=1.0,
            depletion_fraction_p=0.5,
            init_avail=40.0,
            analysis_start="2020-03-01",
            analysis_end="2020-03-01",
        )

        self.assertEqual(10.0, stats["crop_water_requirement_mm"])
        self.assertEqual(8.0, stats["actual_crop_et_mm"])
        self.assertEqual(80.0, stats["WRSI"])
        self.assertIn("ending_soil_water_mm", stats)

    def test_build_actual_vs_ltm_comparisons_carries_wrsi_metric(self):
        assessments = [
            {
                "season_info": {"year": 2020, "season_number": 1, "total_seasons_per_year": 1},
                "season_statistics": {"WRSI": 80.0},
                "hazard_evaluation": {},
            }
        ]
        baseline_ltm = {
            "per_season": [
                {
                    "season_number": 1,
                    "season_statistics": {"WRSI": 70.0},
                    "hazard_evaluation": {},
                }
            ]
        }

        comparisons = build_actual_vs_ltm_comparisons(assessments, baseline_ltm)

        self.assertEqual(1, len(comparisons))
        self.assertEqual(80.0, comparisons[0]["metrics"]["wrsi"]["actual"])
        self.assertEqual(70.0, comparisons[0]["metrics"]["wrsi"]["baseline_ltm"])

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
