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
            stats.detect_seasons_fixed = lambda frame, fixed_defs, start_year, end_year: (
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
            stats.detect_seasons_auto = lambda frame, lat, start_year, end_year: (auto_seasons, annual_dict)

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
            stats.detect_seasons_fixed = lambda frame, fixed_defs, start_year, end_year: (
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
