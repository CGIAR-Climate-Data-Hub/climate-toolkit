import sys
import types
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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

import climate_tookit.climate_statistics.statistics as stats


class StatisticsSourcePolicyTests(unittest.TestCase):
    def test_overall_statistics_includes_shared_root_zone_metrics(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                "precip": [5.0, 0.0],
                "tmax": [25.0, 26.0],
                "tmin": [15.0, 16.0],
                "ET0_mm_day": [4.0, 4.0],
                "water_balance": [1.0, -4.0],
            }
        )

        orig_shared = stats._shared_water_balance_summary
        stats._shared_water_balance_summary = lambda *args, **kwargs: {
            "NDWS": 3,
            "NDWL0": 1,
            "WRSI": 80.0,
            "crop_water_requirement_mm": 10.0,
            "actual_crop_et_mm": 8.0,
        }
        try:
            result = stats.overall_statistics(df)
        finally:
            stats._shared_water_balance_summary = orig_shared

        water_balance = result["water_balance"]
        self.assertEqual(3, water_balance["NDWS"])
        self.assertEqual(1, water_balance["NDWL0"])
        self.assertEqual(80.0, water_balance["WRSI"])
        self.assertEqual(10.0, water_balance["crop_water_requirement_mm"])
        self.assertEqual(8.0, water_balance["actual_crop_et_mm"])

    def test_overall_statistics_reuses_supplied_shared_root_zone_summary(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                "precip": [5.0, 0.0],
                "tmax": [25.0, 26.0],
                "tmin": [15.0, 16.0],
                "ET0_mm_day": [4.0, 4.0],
                "water_balance": [1.0, -4.0],
            }
        )

        calls = []
        orig_shared = stats._shared_water_balance_summary
        stats._shared_water_balance_summary = lambda *args, **kwargs: calls.append("called") or {}
        try:
            result = stats.overall_statistics(
                df,
                shared_water_balance_summary={
                    "NDWS": 4,
                    "NDWL0": 2,
                    "WRSI": 75.0,
                },
            )
        finally:
            stats._shared_water_balance_summary = orig_shared

        self.assertEqual([], calls)
        self.assertEqual(4, result["water_balance"]["NDWS"])
        self.assertEqual(2, result["water_balance"]["NDWL0"])
        self.assertEqual(75.0, result["water_balance"]["WRSI"])

    def test_season_statistics_includes_shared_root_zone_metrics(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2018-03-01", "2018-03-02", "2018-03-03"]),
                "precip": [5.0, 0.0, 1.0],
                "tmax": [25.0, 26.0, 27.0],
                "tmin": [15.0, 16.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0],
                "water_balance": [1.0, -4.0, -3.0],
            }
        )
        season = {
            "onset": pd.Timestamp("2018-03-01"),
            "cessation": pd.Timestamp("2018-03-03"),
            "length_days": 3,
        }

        orig_shared = stats._shared_water_balance_summary
        stats._shared_water_balance_summary = lambda *args, **kwargs: {
            "NDWS": 2,
            "NDWL0": 0,
            "WRSI": 66.7,
            "crop_water_requirement_mm": 12.0,
            "actual_crop_et_mm": 8.0,
        }
        try:
            result = stats.season_statistics(df, season)
        finally:
            stats._shared_water_balance_summary = orig_shared

        water_balance = result["water_balance"]
        self.assertEqual(2, water_balance["NDWS"])
        self.assertEqual(0, water_balance["NDWL0"])
        self.assertEqual(66.7, water_balance["WRSI"])
        self.assertEqual(12.0, water_balance["crop_water_requirement_mm"])
        self.assertEqual(8.0, water_balance["actual_crop_et_mm"])

    def test_season_statistics_reuses_supplied_shared_root_zone_summary(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2018-03-01", "2018-03-02", "2018-03-03"]),
                "precip": [5.0, 0.0, 1.0],
                "tmax": [25.0, 26.0, 27.0],
                "tmin": [15.0, 16.0, 17.0],
                "ET0_mm_day": [4.0, 4.0, 4.0],
                "water_balance": [1.0, -4.0, -3.0],
            }
        )
        season = {
            "onset": pd.Timestamp("2018-03-01"),
            "cessation": pd.Timestamp("2018-03-03"),
            "length_days": 3,
        }

        calls = []
        orig_shared = stats._shared_water_balance_summary
        stats._shared_water_balance_summary = lambda *args, **kwargs: calls.append("called") or {}
        try:
            result = stats.season_statistics(
                df,
                season,
                shared_water_balance_summary={
                    "NDWS": 5,
                    "NDWL0": 1,
                    "WRSI": 55.0,
                },
            )
        finally:
            stats._shared_water_balance_summary = orig_shared

        self.assertEqual([], calls)
        self.assertEqual(5, result["water_balance"]["NDWS"])
        self.assertEqual(1, result["water_balance"]["NDWL0"])
        self.assertEqual(55.0, result["water_balance"]["WRSI"])

    def test_compile_season_results_reuses_main_window_root_zone_summary(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2018-03-01", periods=5, freq="D"),
                "precip": [5.0, 0.0, 1.0, 2.0, 0.0],
                "tmax": [25.0, 26.0, 27.0, 28.0, 29.0],
                "tmin": [15.0, 16.0, 17.0, 18.0, 19.0],
                "ET0_mm_day": [4.0, 4.0, 4.0, 4.0, 4.0],
                "water_balance": [1.0, -4.0, -3.0, -2.0, -4.0],
            }
        )
        seasons_dict = {
            2018: [
                {
                    "onset": "2018-03-01",
                    "cessation": "2018-03-05",
                    "length_days": 5,
                    "regime": "unimodal",
                }
            ]
        }

        calls = []
        orig_shared = stats._shared_water_balance_summary

        def fake_shared(*args, **kwargs):
            calls.append((kwargs.get("analysis_start"), kwargs.get("analysis_end")))
            return {"NDWS": 2, "NDWL0": 0, "WRSI": 66.7}

        stats._shared_water_balance_summary = fake_shared
        try:
            result = stats._compile_season_results(df, seasons_dict)
        finally:
            stats._shared_water_balance_summary = orig_shared

        self.assertEqual([("2018-03-01", "2018-03-05")], calls)
        self.assertEqual(1, len(result))
        self.assertEqual(2, result[0]["water_balance"]["NDWS"])
        self.assertEqual(2, result[0]["overall_statistics"]["water_balance"]["NDWS"])

    def test_get_climate_data_paired_mode_merges_precip_and_temperature_sources(self):
        calls = []

        def fake_call_preprocess(source, lat, lon, date_from, date_to, model, scenario):
            calls.append(source)
            if source == "chirps_v2":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "precipitation": [1.0, 0.0],
                    }
                )
            if source == "era_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
                        "humidity": [70.0, 72.0],
                    }
                )
            raise AssertionError(f"unexpected source {source}")

        orig_call = stats._call_preprocess
        stats._call_preprocess = fake_call_preprocess
        try:
            frame = stats.get_climate_data(
                -1.286,
                36.817,
                "2018-01-01",
                "2018-01-02",
                "paired",
                precip_source="chirps_v2",
                temp_source="era_5",
            )
        finally:
            stats._call_preprocess = orig_call

        self.assertEqual(["chirps_v2", "era_5"], calls)
        self.assertEqual(["date", "precip", "tmax", "tmin", "humidity"], list(frame.columns))

    def test_get_climate_data_paired_mode_accepts_tamsat_as_precip_partner(self):
        calls = []

        def fake_call_preprocess(source, lat, lon, date_from, date_to, model, scenario):
            calls.append(source)
            if source == "tamsat":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "precipitation": [3.0, 1.0],
                        "soil_moisture": [22.0, 21.0],
                    }
                )
            if source == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
                    }
                )
            raise AssertionError(f"unexpected source {source}")

        orig_call = stats._call_preprocess
        stats._call_preprocess = fake_call_preprocess
        try:
            frame = stats.get_climate_data(
                -1.286,
                36.817,
                "2018-01-01",
                "2018-01-02",
                "paired",
                precip_source="tamsat",
                temp_source="agera_5",
            )
        finally:
            stats._call_preprocess = orig_call

        self.assertEqual(["tamsat", "agera_5"], calls)
        self.assertEqual([3.0, 1.0], frame["precip"].tolist())
        self.assertEqual([25.0, 26.0], frame["tmax"].tolist())

    def test_analyze_climate_statistics_rejects_tamsat_single_source(self):
        result = stats.analyze_climate_statistics(
            location_coord=(-1.286, 36.817),
            start_year=2018,
            end_year=2019,
            source="tamsat",
            fixed_season="03-01:05-31",
        )

        self.assertIn("error", result)
        self.assertIn("paired with a temperature source", result["error"])

    def test_get_climate_data_rejects_all_missing_precipitation(self):
        def fake_call_preprocess(source, lat, lon, date_from, date_to, model, scenario):
            if source == "tamsat":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "precipitation": [None, None],
                    }
                )
            if source == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
                    }
                )
            raise AssertionError(f"unexpected source {source}")

        orig_call = stats._call_preprocess
        stats._call_preprocess = fake_call_preprocess
        try:
            with self.assertRaises(RuntimeError) as ctx:
                stats.get_climate_data(
                    -1.286,
                    36.817,
                    "2018-01-01",
                    "2018-01-02",
                    "paired",
                    precip_source="tamsat",
                    temp_source="agera_5",
                )
        finally:
            stats._call_preprocess = orig_call

        self.assertIn("no usable daily values", str(ctx.exception))

    def test_analyze_climate_statistics_rejects_incomplete_paired_args(self):
        result = stats.analyze_climate_statistics(
            location_coord=(-1.286, 36.817),
            start_year=2018,
            end_year=2019,
            source="paired",
            precip_source="chirps_v2",
        )

        self.assertIn("error", result)
        self.assertIn("Provide both precip_source and temp_source together", result["error"])

    def test_get_climate_data_auto_prefers_chirps_v3_plus_agera5(self):
        calls = []

        def fake_call_preprocess(source, lat, lon, date_from, date_to, model, scenario):
            calls.append(source)
            if source == "chirps_v3_daily_rnl":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "precipitation": [1.0, 0.0],
                    }
                )
            if source == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
                        "humidity": [70.0, 72.0],
                    }
                )
            raise AssertionError("auto should stop after first successful source")

        orig_call = stats._call_preprocess
        orig_merge = stats._fetch_chirps_chirts
        stats._call_preprocess = fake_call_preprocess
        stats._fetch_chirps_chirts = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("chirps+chirts fallback should not run")
        )
        try:
            frame = stats.get_climate_data(
                -1.286,
                36.817,
                "2018-01-01",
                "2018-01-02",
                "auto",
            )
        finally:
            stats._call_preprocess = orig_call
            stats._fetch_chirps_chirts = orig_merge

        self.assertEqual(["chirps_v3_daily_rnl", "agera_5"], calls)
        self.assertIn("precip", frame.columns)
        self.assertIn("tmax", frame.columns)
        self.assertIn("tmin", frame.columns)
        self.assertIn("humidity", frame.columns)

    def test_get_climate_data_auto_reports_chirts_limit_after_2016(self):
        def fake_call_preprocess(*args, **kwargs):
            raise RuntimeError("upstream unavailable")

        orig_call = stats._call_preprocess
        stats._call_preprocess = fake_call_preprocess
        try:
            with self.assertRaises(RuntimeError) as ctx:
                stats.get_climate_data(
                    -1.286,
                    36.817,
                    "2018-01-01",
                    "2019-12-31",
                    "auto",
                )
        finally:
            stats._call_preprocess = orig_call

        self.assertIn("CHIRTS daily coverage ends", str(ctx.exception))
        self.assertIn("2016", str(ctx.exception))

    def test_analyze_climate_statistics_rejects_terraclimate(self):
        result = stats.analyze_climate_statistics(
            location_coord=(-1.286, 36.817),
            start_year=2018,
            end_year=2019,
            source="terraclimate",
            fixed_season="03-01:05-31",
        )
        self.assertIn("error", result)
        self.assertIn("monthly-cadence", result["error"])

    def test_analyze_climate_statistics_returns_clean_fetch_error(self):
        orig_get = stats.get_climate_data
        stats.get_climate_data = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("No data returned from source 'era_5'")
        )
        try:
            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2018,
                end_year=2019,
                source="era_5",
                fixed_season="03-01:05-31",
            )
        finally:
            stats.get_climate_data = orig_get

        self.assertIn("error", result)
        self.assertIn("Climate data fetch failed", result["error"])
        self.assertIn("No data returned from source 'era_5'", result["error"])

    def test_analyze_climate_statistics_uses_requested_ggcmi_calendar_directly(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2021-01-01", "2021-01-02"]),
                "precip": [1.0, 0.0, 2.0, 0.0],
                "tmax": [25.0, 26.0, 27.0, 28.0],
                "tmin": [15.0, 16.0, 17.0, 18.0],
                "humidity": [70.0, 72.0, 74.0, 76.0],
                "solar_radiation": [200.0, 205.0, 210.0, 215.0],
                "wind_speed": [1.0, 1.1, 1.2, 1.3],
            }
        )

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_calc_wb = stats.calculate_water_balance
        orig_detect_auto = stats.detect_seasons_auto
        orig_detect_fixed = stats.detect_seasons_fixed
        orig_season_stats = stats.season_statistics
        orig_raw = stats.raw_climate_summary
        orig_overall = stats.overall_statistics
        orig_ltm = stats.ltm_season_summary
        orig_preset = stats.resolve_calendar_preset

        stats.get_climate_data = lambda *args, **kwargs: frame.copy()
        stats.add_et0 = lambda df, lat: df.assign(ET0_mm_day=0.0)
        stats.calculate_water_balance = lambda df: df.assign(water_balance=0.0)
        stats.detect_seasons_auto = lambda *args, **kwargs: (
            {2020: [], 2021: []},
            {
                2020: {
                    "annual_rain_mm": 100.0,
                    "is_humid": False,
                    "low_rain_months": 6,
                    "result_str": "Not humid",
                    "season_skip_reason": "Perhumid location. No clear onset/cessation.",
                },
                2021: {
                    "annual_rain_mm": 110.0,
                    "is_humid": False,
                    "low_rain_months": 6,
                    "result_str": "Not humid",
                    "season_skip_reason": "Perhumid location. No clear onset/cessation.",
                },
            },
        )
        stats.detect_seasons_fixed = lambda df, fixed_defs, start_year, end_year, **kwargs: (
            {
                2020: [{"onset": pd.Timestamp("2020-03-01"), "cessation": pd.Timestamp("2020-05-31"), "length_days": 92, "regime": "fixed", "eto_seasons": []}],
                2021: [{"onset": pd.Timestamp("2021-03-01"), "cessation": pd.Timestamp("2021-05-31"), "length_days": 92, "regime": "fixed", "eto_seasons": []}],
            },
            {
                2020: {"annual_rain_mm": 100.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
                2021: {"annual_rain_mm": 110.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
            },
        )
        stats.season_statistics = lambda df, season: {
            "onset": pd.to_datetime(season["onset"]).strftime("%Y-%m-%d"),
            "cessation": pd.to_datetime(season["cessation"]).strftime("%Y-%m-%d"),
            "length_days": int(season["length_days"]),
            "precipitation": {"total_mm": 100.0, "max_daily": 10.0, "rainy_days": 20, "intensity": 5.0},
            "temperature": {"mean_tmax": 25.0, "mean_tmin": 15.0, "mean_tavg": 20.0, "max_tmax": 30.0, "min_tmin": 10.0},
            "water_balance": {"total_balance": -10.0, "deficit_days": 5, "surplus_days": 10, "stress_ratio": 0.2},
        }
        stats.raw_climate_summary = lambda df: []
        stats.overall_statistics = lambda *args, **kwargs: {
            "total_days": 1,
            "precipitation": {"total_mm": 1.0, "rainy_days": 1, "dry_days": 0, "max_daily": 1.0},
            "temperature": {"mean_tmax": 25.0, "mean_tmin": 15.0, "mean_tavg": 20.0, "max_tmax": 25.0, "min_tmin": 15.0},
            "et0": {"total_mm": 0.0},
            "water_balance": {"total_balance": 0.0, "deficit_days": 0, "surplus_days": 0, "max_deficit": 0.0, "max_surplus": 0.0},
        }
        stats.ltm_season_summary = lambda season_results, fixed_season=None: {
            "mode": "fixed" if fixed_season else "auto",
            "windows": [{"window": fixed_season or "auto", "season_number": 1, "n_years": 2, "years": [2020, 2021]}],
        }
        stats.resolve_calendar_preset = lambda lat, lon, crop_name, system="rf": {
            "calendar_source": "ggcmi_phase3",
            "crop_name": "Maize",
            "calendar_system": system,
            "fixed_season": "03-01:05-31",
            "fixed_season_tokens": ["03-01:05-31"],
            "matched_lat": -1.25,
            "matched_lon": 36.75,
            "distance_deg": 0.08,
            "systems_included": ["rf"],
            "calendar_rows": [],
        }
        try:
            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2020,
                end_year=2021,
                source="paired",
                precip_source="chirps_v2",
                temp_source="agera_5",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_calc_wb
            stats.detect_seasons_auto = orig_detect_auto
            stats.detect_seasons_fixed = orig_detect_fixed
            stats.season_statistics = orig_season_stats
            stats.raw_climate_summary = orig_raw
            stats.overall_statistics = orig_overall
            stats.ltm_season_summary = orig_ltm
            stats.resolve_calendar_preset = orig_preset

        self.assertTrue(result["calendar_preset_used"])
        self.assertFalse(result["calendar_preset_fallback"])
        self.assertEqual("fixed", result["mode"])
        self.assertEqual("03-01:05-31", result["fixed_season"])
        self.assertEqual("calendar_preset_direct_requested", result["season_detection_reasons"][0])
        self.assertIn("crop-calendar preset", result["season_detection_guidance"][0])
        self.assertIn("03-01:05-31", result["season_detection_guidance"][0])

    def test_analyze_climate_statistics_rejects_nex_historical_window_after_2014(self):
        result = stats.analyze_climate_statistics(
            location_coord=(-1.286, 36.817),
            start_year=1991,
            end_year=2020,
            source="nex_gddp",
            model="MRI-ESM2-0",
            scenario="historical",
        )

        self.assertIn("error", result)
        self.assertIn("2014-12-31", result["error"])

    def test_analyze_climate_statistics_uses_requested_calendar_directly_without_auto(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-03-01", "2020-05-31", "2021-12-31"]),
                "precip": [1.0, 2.0, 0.0, 0.0],
                "tmax": [25.0, 26.0, 27.0, 28.0],
                "tmin": [15.0, 16.0, 17.0, 18.0],
                "humidity": [70.0, 72.0, 74.0, 76.0],
                "solar_radiation": [200.0, 205.0, 210.0, 215.0],
                "wind_speed": [1.0, 1.1, 1.2, 1.3],
            }
        )

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_calc_wb = stats.calculate_water_balance
        orig_detect_fixed = stats.detect_seasons_fixed
        orig_detect_auto = stats.detect_seasons_auto
        orig_season_stats = stats.season_statistics
        orig_raw = stats.raw_climate_summary
        orig_overall = stats.overall_statistics
        orig_ltm = stats.ltm_season_summary
        orig_preset = stats.resolve_calendar_preset
        fixed_kwargs_seen = []

        stats.get_climate_data = lambda *args, **kwargs: frame.copy()
        stats.add_et0 = lambda df, lat: df.assign(ET0_mm_day=0.0)
        stats.calculate_water_balance = lambda df: df.assign(water_balance=0.0)
        stats.detect_seasons_auto = lambda *args, **kwargs: self.fail("auto detect should be skipped")
        def fake_detect_fixed(df, fixed_defs, start_year, end_year, **kwargs):
            fixed_kwargs_seen.append(kwargs)
            return (
                {
                    2020: [{"onset": pd.Timestamp("2020-03-01"), "cessation": pd.Timestamp("2020-05-31"), "length_days": 92, "regime": "fixed", "eto_seasons": None}],
                    2021: [{"onset": pd.Timestamp("2021-03-01"), "cessation": pd.Timestamp("2021-05-31"), "length_days": 92, "regime": "fixed", "eto_seasons": None}],
                },
                {
                    2020: {"annual_rain_mm": 100.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
                    2021: {"annual_rain_mm": 110.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
                },
            )
        stats.detect_seasons_fixed = fake_detect_fixed
        stats.season_statistics = lambda df, season: {
            "onset": pd.to_datetime(season["onset"]).strftime("%Y-%m-%d"),
            "cessation": pd.to_datetime(season["cessation"]).strftime("%Y-%m-%d"),
            "length_days": int(season["length_days"]),
            "precipitation": {"total_mm": 100.0},
            "temperature": {"mean_tavg": 20.0},
            "water_balance": {"total_balance": -10.0},
        }
        stats.raw_climate_summary = lambda df: []
        stats.overall_statistics = lambda *args, **kwargs: {
            "total_days": 1,
            "precipitation": {"total_mm": 1.0, "rainy_days": 1, "dry_days": 0, "max_daily": 1.0},
            "temperature": {"mean_tmax": 25.0, "mean_tmin": 15.0, "mean_tavg": 20.0, "max_tmax": 25.0, "min_tmin": 15.0},
            "et0": {"total_mm": 0.0},
            "water_balance": {"total_balance": 0.0, "deficit_days": 0, "surplus_days": 0, "max_deficit": 0.0, "max_surplus": 0.0},
        }
        stats.ltm_season_summary = lambda season_results, fixed_season=None: {
            "mode": "fixed",
            "windows": [{"window": fixed_season, "season_number": 1, "n_years": 2, "years": [2020, 2021]}],
        }
        stats.resolve_calendar_preset = lambda lat, lon, crop_name, system="rf": {
            "calendar_source": "ggcmi_phase3",
            "crop_name": "Maize",
            "calendar_system": system,
            "fixed_season": "03-01:05-31",
            "fixed_season_tokens": ["03-01:05-31"],
            "matched_lat": -1.25,
            "matched_lon": 36.75,
            "distance_deg": 0.08,
            "systems_included": ["rf"],
            "calendar_rows": [],
        }
        try:
            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2020,
                end_year=2021,
                source="paired",
                precip_source="chirps_v2",
                temp_source="agera_5",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_calc_wb
            stats.detect_seasons_fixed = orig_detect_fixed
            stats.detect_seasons_auto = orig_detect_auto
            stats.season_statistics = orig_season_stats
            stats.raw_climate_summary = orig_raw
            stats.overall_statistics = orig_overall
            stats.ltm_season_summary = orig_ltm
            stats.resolve_calendar_preset = orig_preset

        self.assertNotIn("error", result)
        self.assertTrue(result["calendar_preset_used"])
        self.assertFalse(result["calendar_preset_fallback"])
        self.assertEqual("fixed", result["mode"])
        self.assertEqual("03-01:05-31", result["fixed_season"])
        self.assertEqual("calendar_preset_direct_requested", result["season_detection_reasons"][0])
        self.assertEqual("user_requested_calendar_preset", result["calendar_preset"]["direct_applied_reason"])
        self.assertFalse(fixed_kwargs_seen[0]["include_eto_subseasons"])

    def test_analyze_climate_statistics_uses_direct_calendar_mode_for_nex_historical_2014_edge(self):
        fetch_calls = []
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["1995-01-01", "2014-03-01", "2014-06-13", "2014-12-31"]),
                "precip": [1.0, 2.0, 0.0, 0.0],
                "tmax": [25.0, 26.0, 27.0, 28.0],
                "tmin": [15.0, 16.0, 17.0, 18.0],
                "humidity": [70.0, 72.0, 74.0, 76.0],
                "solar_radiation": [200.0, 205.0, 210.0, 215.0],
                "wind_speed": [1.0, 1.1, 1.2, 1.3],
            }
        )

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_calc_wb = stats.calculate_water_balance
        orig_detect_fixed = stats.detect_seasons_fixed
        orig_detect_auto = stats.detect_seasons_auto
        orig_season_stats = stats.season_statistics
        orig_raw = stats.raw_climate_summary
        orig_overall = stats.overall_statistics
        orig_ltm = stats.ltm_season_summary
        orig_preset = stats.resolve_calendar_preset

        def fake_get(*args, **kwargs):
            fetch_calls.append((args[2], args[3], kwargs.get("source"), kwargs.get("scenario")))
            return frame.copy()

        stats.get_climate_data = fake_get
        stats.add_et0 = lambda df, lat: df.assign(ET0_mm_day=0.0)
        stats.calculate_water_balance = lambda df: df.assign(water_balance=0.0)
        stats.detect_auto = lambda *args, **kwargs: self.fail("auto detect should be skipped")
        stats.detect_seasons_auto = lambda *args, **kwargs: self.fail("auto detect should be skipped")
        stats.detect_seasons_fixed = lambda df, fixed_defs, start_year, end_year, **kwargs: (
            {
                1995: [{"onset": pd.Timestamp("1995-03-01"), "cessation": pd.Timestamp("1995-06-13"), "length_days": 105, "regime": "fixed", "eto_seasons": []}],
                2014: [{"onset": pd.Timestamp("2014-03-01"), "cessation": pd.Timestamp("2014-06-13"), "length_days": 105, "regime": "fixed", "eto_seasons": []}],
            },
            {
                1995: {"annual_rain_mm": 100.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
                2014: {"annual_rain_mm": 110.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
            },
        )
        stats.season_statistics = lambda df, season: {
            "onset": pd.to_datetime(season["onset"]).strftime("%Y-%m-%d"),
            "cessation": pd.to_datetime(season["cessation"]).strftime("%Y-%m-%d"),
            "length_days": int(season["length_days"]),
            "precipitation": {"total_mm": 100.0},
            "temperature": {"mean_tavg": 20.0},
            "water_balance": {"total_balance": -10.0},
        }
        stats.raw_climate_summary = lambda df: []
        stats.overall_statistics = lambda *args, **kwargs: {
            "total_days": 1,
            "precipitation": {"total_mm": 1.0, "rainy_days": 1, "dry_days": 0, "max_daily": 1.0},
            "temperature": {"mean_tmax": 25.0, "mean_tmin": 15.0, "mean_tavg": 20.0, "max_tmax": 25.0, "min_tmin": 15.0},
            "et0": {"total_mm": 0.0},
            "water_balance": {"total_balance": 0.0, "deficit_days": 0, "surplus_days": 0, "max_deficit": 0.0, "max_surplus": 0.0},
        }
        stats.ltm_season_summary = lambda season_results, fixed_season=None: {
            "mode": "fixed",
            "windows": [{"window": fixed_season, "season_number": 1, "n_years": 2, "years": [1995, 2014]}],
        }
        stats.resolve_calendar_preset = lambda lat, lon, crop_name, system="rf": {
            "calendar_source": "ggcmi_phase3",
            "crop_name": "Maize",
            "calendar_system": system,
            "fixed_season": "03-01:06-13",
            "fixed_season_tokens": ["03-01:06-13"],
            "matched_lat": -1.25,
            "matched_lon": 36.75,
            "distance_deg": 0.08,
            "systems_included": ["rf"],
            "calendar_rows": [],
        }
        try:
            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=1995,
                end_year=2014,
                source="nex_gddp",
                model="MRI-ESM2-0",
                scenario="historical",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_calc_wb
            stats.detect_seasons_fixed = orig_detect_fixed
            stats.detect_seasons_auto = orig_detect_auto
            stats.season_statistics = orig_season_stats
            stats.raw_climate_summary = orig_raw
            stats.overall_statistics = orig_overall
            stats.ltm_season_summary = orig_ltm
            stats.resolve_calendar_preset = orig_preset

        self.assertNotIn("error", result)
        self.assertEqual("2014-12-31", fetch_calls[0][1])
        self.assertTrue(result["calendar_preset_used"])
        self.assertEqual("fixed", result["mode"])
        self.assertEqual("calendar_preset_direct_applied", result["season_detection_reasons"][0])
        self.assertIn("crop-calendar preset", result["season_detection_guidance"][0])
        self.assertIn("03-01:06-13", result["season_detection_guidance"][0])

    def test_cli_json_error_saves_error_report_not_success_banner(self):
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "stats_error.json"
            argv = [
                "statistics.py",
                "--location=-1.286,36.817",
                "--start-year=2018",
                "--end-year=2019",
                "--source=terraclimate",
                "--fixed-season=03-01:05-31",
                "--format=json",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), mock.patch("sys.stdout", stdout):
                with self.assertRaises(SystemExit) as ctx:
                    stats.main()

            self.assertEqual(1, ctx.exception.code)
            rendered = stdout.getvalue()
            self.assertIn("Saved error report to", rendered)
            self.assertNotIn("Saved to ", rendered)
            self.assertTrue(output_path.exists())

    def test_cli_json_output_creates_missing_directory(self):
        payload = {
            "period": {"start_year": 2018, "end_year": 2019},
            "raw_climate_summary": [],
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "stats.json"
            argv = [
                "statistics.py",
                "--location=-1.286,36.817",
                "--start-year=2018",
                "--end-year=2019",
                "--source=era_5",
                "--format=json",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(stats, "analyze_climate_statistics", return_value=payload):
                stats.main()

            self.assertTrue(output_path.exists())
            self.assertIn("Saved to", stdout.getvalue())

    def test_analyze_climate_statistics_includes_optional_spei_block(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2018-01-01", "2019-12-31", freq="D"),
                "precip": [1.0] * 730,
                "tmax": [25.0] * 730,
                "tmin": [15.0] * 730,
                "ET0_mm_day": [4.0] * 730,
                "water_balance": [-3.0] * 730,
            }
        )
        spei_calls = []

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_wb = stats.calculate_water_balance
        orig_detect_fixed = stats.detect_seasons_fixed
        orig_spei = stats._spei_block
        try:
            stats.get_climate_data = lambda *args, **kwargs: df.copy()
            stats.add_et0 = lambda frame, lat: frame
            stats.calculate_water_balance = lambda frame: frame
            stats.detect_seasons_fixed = lambda frame, fixed_defs, start_year, end_year, **kwargs: (
                {2018: []},
                {2018: {"annual_rain_mm": 365.0, "is_humid": False, "low_rain_months": 12, "result_str": "Not humid"}},
            )

            def fake_spei(frame, **kwargs):
                spei_calls.append({"rows": len(frame), **kwargs})
                return {
                    "config": kwargs,
                    "summary": {"n_months": 24, "n_valid_spei": 22},
                    "metadata": {"standardization_method": "generalized_logistic_ub_pwm_by_calendar_month"},
                    "monthly_series": [
                        {"date": "2018-01-01", "water_balance_accumulated_mm": -30.0, "spei": -1.2}
                    ],
                }

            stats._spei_block = fake_spei
            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2018,
                end_year=2019,
                source="era_5",
                fixed_season="03-01:05-31",
                spei_scale_months=3,
                spei_fit="ub-pwm",
                spei_ref_start="2018-01-01",
                spei_ref_end="2019-12-31",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_wb
            stats.detect_seasons_fixed = orig_detect_fixed
            stats._spei_block = orig_spei

        self.assertEqual(1, len(spei_calls))
        self.assertEqual(730, spei_calls[0]["rows"])
        self.assertEqual(3, spei_calls[0]["scale_months"])
        self.assertEqual("ub-pwm", spei_calls[0]["fit"])
        self.assertEqual("2018-01-01", spei_calls[0]["ref_start"])
        self.assertEqual("2019-12-31", spei_calls[0]["ref_end"])
        self.assertEqual(22, result["spei"]["summary"]["n_valid_spei"])

    def test_cli_json_output_saves_spei_sidecar_csv(self):
        payload = {
            "period": {"start_year": 2018, "end_year": 2019},
            "raw_climate_summary": [],
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
            "spei": {
                "config": {"scale_months": 3, "fit": "ub-pwm"},
                "summary": {"n_months": 2, "n_valid_spei": 2},
                "metadata": {},
                "monthly_series": [
                    {"date": "2018-01-01", "water_balance_accumulated_mm": -10.0, "spei": -1.0},
                    {"date": "2018-02-01", "water_balance_accumulated_mm": -5.0, "spei": -0.5},
                ],
            },
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "stats.json"
            spei_csv = output_path.with_name("stats_spei.csv")
            argv = [
                "statistics.py",
                "--location=-1.286,36.817",
                "--start-year=2018",
                "--end-year=2019",
                "--source=era_5",
                "--format=json",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(stats, "analyze_climate_statistics", return_value=payload):
                stats.main()

            self.assertTrue(output_path.exists())
            self.assertTrue(spei_csv.exists())
            rendered = stdout.getvalue()
            self.assertIn("Saved to", rendered)
            self.assertIn("Saved SPEI CSV to", rendered)

    def test_print_pandas_renders_spei_preview(self):
        payload = {
            "location": {"lat": -1.286, "lon": 36.817},
            "period": {"start_year": 2018, "end_year": 2019},
            "source": "era_5",
            "mode": "fixed",
            "fixed_season": "03-01:05-31",
            "season_statistics": [],
            "ltm_season_summary": {"windows": []},
            "annual_summary": {},
            "spei": {
                "config": {"scale_months": 3, "fit": "ub-pwm"},
                "summary": {"n_months": 24, "n_valid_spei": 20},
                "metadata": {},
                "monthly_series": [
                    {"date": "2019-01-01", "water_balance_accumulated_mm": -10.0, "spei": -1.0},
                    {"date": "2019-02-01", "water_balance_accumulated_mm": -5.0, "spei": -0.5},
                ],
            },
        }

        stdout = StringIO()
        with mock.patch("sys.stdout", stdout):
            stats.print_pandas(payload)

        rendered = stdout.getvalue()
        self.assertIn("SPEI-3 | fit=ub-pwm", rendered)
        self.assertIn("2019-01-01", rendered)

    def test_fixed_window_eto_subseason_is_capped_to_window_end_not_dataset_tail(self):
        dates = pd.date_range("2018-01-01", "2020-12-31", freq="D")
        df = pd.DataFrame(
            {
                "date": dates,
                "precip": [1.0] * len(dates),
                "tmax": [25.0] * len(dates),
                "tmin": [15.0] * len(dates),
                "ET0_mm_day": [4.0] * len(dates),
                "water_balance": [-1.0] * len(dates),
            }
        )

        parent_onset = pd.Timestamp("2018-03-01")
        parent_cess = pd.Timestamp("2018-06-30")
        open_eto = {
            "onset": parent_onset,
            "cessation": None,
            "length_days": 122,
            "regime": "eto",
        }
        fixed_parent = {
            "onset": parent_onset,
            "cessation": parent_cess,
            "length_days": 122,
            "regime": "fixed",
            "eto_seasons": [open_eto],
        }

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_wb = stats.calculate_water_balance
        orig_detect_fixed = stats.detect_seasons_fixed
        try:
            stats.get_climate_data = lambda *args, **kwargs: df.copy()
            stats.add_et0 = lambda frame, lat: frame
            stats.calculate_water_balance = lambda frame: frame
            stats.detect_seasons_fixed = lambda frame, fixed_defs, start_year, end_year, **kwargs: (
                {2018: [fixed_parent]},
                {
                    2018: {
                        "annual_rain_mm": 365.0,
                        "is_humid": False,
                        "low_rain_months": 6,
                        "result_str": "Not humid",
                    }
                },
            )

            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2018,
                end_year=2018,
                source="era_5",
                fixed_season="03-01:06-30",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_wb
            stats.detect_seasons_fixed = orig_detect_fixed

        eto_subs = result["season_statistics"][0]["eto_sub_seasons"]
        self.assertEqual(1, len(eto_subs))
        self.assertEqual("2018-03-01", eto_subs[0]["onset"])
        self.assertEqual("2018-06-30", eto_subs[0]["cessation"])
        self.assertEqual(122, eto_subs[0]["length_days"])

    def test_auto_mode_suppresses_ltm_windows_when_yearly_season_counts_differ(self):
        dates = pd.date_range("2018-01-01", "2019-12-31", freq="D")
        df = pd.DataFrame(
            {
                "date": dates,
                "precip": [1.0] * len(dates),
                "tmax": [25.0] * len(dates),
                "tmin": [15.0] * len(dates),
                "ET0_mm_day": [4.0] * len(dates),
                "water_balance": [-1.0] * len(dates),
            }
        )

        auto_seasons = {
            2018: [
                {
                    "onset": pd.Timestamp("2018-03-01"),
                    "cessation": pd.Timestamp("2018-05-31"),
                    "length_days": 92,
                    "regime": "unimodal",
                }
            ],
            2019: [
                {
                    "onset": pd.Timestamp("2019-03-01"),
                    "cessation": pd.Timestamp("2019-05-31"),
                    "length_days": 92,
                    "regime": "unimodal",
                },
                {
                    "onset": pd.Timestamp("2019-10-01"),
                    "cessation": pd.Timestamp("2019-12-31"),
                    "length_days": 92,
                    "regime": "bimodal",
                },
            ],
        }
        annual_dict = {
            2018: {"annual_rain_mm": 700.0, "is_humid": False, "low_rain_months": 6, "result_str": "Not humid"},
            2019: {"annual_rain_mm": 900.0, "is_humid": False, "low_rain_months": 5, "result_str": "Not humid"},
        }

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_wb = stats.calculate_water_balance
        orig_detect_auto = stats.detect_seasons_auto
        try:
            stats.get_climate_data = lambda *args, **kwargs: df.copy()
            stats.add_et0 = lambda frame, lat: frame
            stats.calculate_water_balance = lambda frame: frame
            stats.detect_seasons_auto = lambda frame, lat, start_year, end_year, **kwargs: (auto_seasons, annual_dict)

            result = stats.analyze_climate_statistics(
                location_coord=(-1.286, 36.817),
                start_year=2018,
                end_year=2019,
                source="era_5",
            )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_wb
            stats.detect_seasons_auto = orig_detect_auto

        self.assertEqual(3, len(result["season_statistics"]))
        self.assertEqual([], result["ltm_season_summary"]["windows"])
        self.assertIn("Auto-detected season counts differ across years", result["season_slot_warning"])
        self.assertEqual(
            "regime:unimodal|onset_month:03",
            result["season_statistics"][0]["season_identity"]["experimental_alignment_key"],
        )

    def test_analyze_climate_statistics_prints_historical_cache_note_for_auto(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                "precip": [1.0, 0.0],
                "tmax": [25.0, 26.0],
                "tmin": [15.0, 16.0],
                "ET0_mm_day": [4.0, 4.0],
                "water_balance": [-3.0, -4.0],
            }
        )

        orig_get = stats.get_climate_data
        orig_add_et0 = stats.add_et0
        orig_wb = stats.calculate_water_balance
        orig_detect_fixed = stats.detect_seasons_fixed
        try:
            stats.get_climate_data = lambda *args, **kwargs: df.copy()
            stats.add_et0 = lambda frame, lat: frame
            stats.calculate_water_balance = lambda frame: frame
            stats.detect_seasons_fixed = lambda frame, fixed_defs, start_year, end_year, **kwargs: (
                {2018: []},
                {2018: {"annual_rain_mm": 1.0, "is_humid": False, "low_rain_months": 12, "result_str": "Not humid"}},
            )

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                stats.analyze_climate_statistics(
                    location_coord=(-1.286, 36.817),
                    start_year=2018,
                    end_year=2018,
                    source="auto",
                    fixed_season="03-01:05-31",
                )
        finally:
            stats.get_climate_data = orig_get
            stats.add_et0 = orig_add_et0
            stats.calculate_water_balance = orig_wb
            stats.detect_seasons_fixed = orig_detect_fixed

        rendered = stdout.getvalue()
        self.assertIn("Historical GEE/Xee fetch note", rendered)
        self.assertIn("outputs/cache/...", rendered)


if __name__ == "__main__":
    unittest.main()
