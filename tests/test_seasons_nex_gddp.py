from datetime import date
import sys
import tempfile
import types
import unittest
from io import StringIO
from pathlib import Path
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

import climate_tookit.season_analysis.seasons as seasons
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


class SeasonsNexGddpTests(unittest.TestCase):
    def test_print_summary_creates_missing_output_directory(self):
        seasons_dict = {
            2020: [
                {
                    "onset": pd.Timestamp("2020-03-01"),
                    "cessation": pd.Timestamp("2020-05-31"),
                    "regime": "unimodal",
                    "length_days": 92,
                    "total_rainfall_mm": 120.0,
                    "rainy_days": 20,
                    "dry_days": 72,
                    "dry_spells": 2,
                    "params_used": "test",
                }
            ]
        }
        annual_dict = {
            2020: {
                "annual_rainfall_mm": 700.0,
                "humid_result": "Not humid",
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "seasons.csv"
            seasons.print_summary(seasons_dict, annual_dict, save_path=str(output_path))
            self.assertTrue(output_path.exists())

    def test_detect_regime_labels_single_late_peak_as_late_peak_unimodal(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [f"2020-{month:02d}-01" for month in range(1, 13)]
                ),
                "precip": [5, 10, 20, 25, 30, 35, 40, 45, 70, 130, 60, 25],
            }
        )

        labels = seasons.detect_regime(df)

        self.assertTrue((labels == "late_peak_unimodal").all())

    def test_run_eto_in_window_caps_open_season_at_window_end(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2020-03-01", "2020-06-30", freq="D"),
                "precip": [5.0] * 122,
                "ET0_mm_day": [4.0] * 122,
            }
        )

        orig = seasons.detect_onset_cessation
        seasons.detect_onset_cessation = lambda frame: [
            {
                "onset": pd.Timestamp("2020-03-15"),
                "cessation": None,
                "length_days": 108,
                "regime": "unimodal",
            }
        ]
        try:
            eto = seasons.run_eto_in_window(df, "2020-03-01", "2020-06-30")
        finally:
            seasons.detect_onset_cessation = orig

        self.assertEqual(1, len(eto))
        self.assertEqual(pd.Timestamp("2020-06-30"), pd.to_datetime(eto[0]["cessation"]))
        self.assertEqual(108, eto[0]["length_days"])

    def test_fetch_and_analyze_years_fixed_prefetches_spinup_padding(self):
        calls = []

        orig = seasons.get_climate_data
        def fake_get_climate_data(lat, lon, start_date, end_date, **kwargs):
            calls.append((start_date, end_date))
            raise Exception("stop")

        seasons.get_climate_data = fake_get_climate_data
        try:
            seasons.fetch_and_analyze_years_fixed(
                -1.286,
                36.817,
                fixed_seasons=seasons.parse_fixed_seasons("03-01:05-31"),
                start_year=2020,
                end_year=2020,
                source="era_5",
                prefetch_pad_days=60,
            )
        finally:
            seasons.get_climate_data = orig

        self.assertEqual([("2020-01-01", "2020-12-31")], calls)

    def test_get_climate_data_passes_model_and_scenario_for_nex(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2041-01-01", "2041-01-02"]),
                    "max_temperature": [30.0, 31.0],
                    "min_temperature": [20.0, 21.0],
                    "precipitation": [1.0, 2.0],
                }
            )

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            frame = seasons.get_climate_data(
                -1.286,
                36.817,
                "2041-01-01",
                "2041-01-02",
                force_source="nex_gddp",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            seasons.preprocess_data = orig

        self.assertEqual("ACCESS-CM2", calls[0]["model"])
        self.assertEqual("ssp245", calls[0]["scenario"])
        self.assertEqual(
            ["precipitation", "max_temperature", "min_temperature"],
            [variable.name for variable in calls[0]["variables"]],
        )
        self.assertIn("tmax", frame.columns)
        self.assertIn("tmin", frame.columns)
        self.assertIn("precip", frame.columns)

    def test_get_climate_data_requests_minimal_variables_for_historical_source(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                    "max_temperature": [25.0, 26.0],
                    "min_temperature": [15.0, 16.0],
                    "precipitation": [3.0, 1.0],
                }
            )

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-01-01",
                "2020-01-02",
                force_source="era_5",
            )
        finally:
            seasons.preprocess_data = orig

        self.assertEqual(
            ["precipitation", "max_temperature", "min_temperature"],
            [variable.name for variable in calls[0]["variables"]],
        )

    def test_get_climate_data_rejects_malformed_empty_source_payload(self):
        def fake_preprocess_data(**kwargs):
            return pd.DataFrame({"precipitation": []})

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            with self.assertRaisesRegex(RuntimeError, "No climate data returned from source 'era_5'"):
                seasons.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-02",
                    force_source="era_5",
                )
        finally:
            seasons.preprocess_data = orig

    def test_get_climate_data_rejects_malformed_chirps_chirts_fallback_payload(self):
        def fake_preprocess_data(**kwargs):
            source = kwargs["source"]
            if source in {"chirps", "chirps_v2"}:
                return pd.DataFrame({"precipitation": []})
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01"]),
                    "max_temperature": [25.0],
                    "min_temperature": [15.0],
                }
            )

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            with self.assertRaisesRegex(RuntimeError, "No CHIRPS precipitation data returned"):
                seasons.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-02",
                    force_source="chirps+chirts",
                )
        finally:
            seasons.preprocess_data = orig

    def test_get_climate_data_auto_prefers_chirps_v3_plus_agera5(self):
        calls = []

        def fake_preprocess_data(**kwargs):
            calls.append(kwargs["source"])
            if kwargs["source"] == "chirps_v3_daily_rnl":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                        "precipitation": [3.0, 1.0],
                    }
                )
            if kwargs["source"] == "agera_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
                    }
                )
            raise AssertionError(f"unexpected source {kwargs['source']}")

        orig = seasons.preprocess_data
        seasons.preprocess_data = fake_preprocess_data
        try:
            frame = seasons.get_climate_data(
                -1.286,
                36.817,
                "2020-01-01",
                "2020-01-02",
            )
        finally:
            seasons.preprocess_data = orig

        self.assertEqual(["chirps_v3_daily_rnl", "agera_5"], calls)
        self.assertIn("precip", frame.columns)
        self.assertIn("tmax", frame.columns)
        self.assertIn("tmin", frame.columns)

    def test_fetch_and_analyze_years_prints_historical_cache_note_for_auto(self):
        orig_fetch = seasons.fetch_full_year_plus_cessation
        orig_detect = seasons.detect_onset_cessation
        orig_reassign = seasons.reassign_spillover_seasons
        orig_dedup = seasons.remove_duplicate_seasons
        try:
            seasons.fetch_full_year_plus_cessation = lambda *args, **kwargs: pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                    "precip": [1.0, 0.0],
                    "tmax": [25.0, 26.0],
                    "tmin": [15.0, 16.0],
                    "ET0_mm_day": [4.0, 4.0],
                }
            )
            seasons.detect_onset_cessation = lambda df: []
            seasons.reassign_spillover_seasons = lambda results_dict, **kwargs: results_dict
            seasons.remove_duplicate_seasons = lambda results_dict: results_dict

            stdout = StringIO()
            with mock.patch("sys.stdout", stdout):
                seasons.fetch_and_analyze_years(
                    -1.286,
                    36.817,
                    start_year=2020,
                    end_year=2020,
                    source="auto",
                )
        finally:
            seasons.fetch_full_year_plus_cessation = orig_fetch
            seasons.detect_onset_cessation = orig_detect
            seasons.reassign_spillover_seasons = orig_reassign
            seasons.remove_duplicate_seasons = orig_dedup

        rendered = stdout.getvalue()
        self.assertIn("Historical GEE/Xee fetch note", rendered)
        self.assertIn("outputs/cache/...", rendered)

    def test_fetch_and_analyze_years_forwards_nex_model_and_scenario(self):
        calls = []

        def fake_fetch_full_year_plus_cessation(
            lat,
            lon,
            year,
            source="auto",
            extra_months=6,
            model=None,
            scenario=None,
        ):
            calls.append(
                {
                    "year": year,
                    "source": source,
                    "model": model,
                    "scenario": scenario,
                }
            )
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2041-01-01", "2041-01-02"]),
                    "precip": [0.0, 0.0],
                    "tmax": [30.0, 30.0],
                    "tmin": [20.0, 20.0],
                    "ET0_mm_day": [5.0, 5.0],
                }
            )

        orig_fetch = seasons.fetch_full_year_plus_cessation
        orig_detect = seasons.detect_onset_cessation
        orig_reassign = seasons.reassign_spillover_seasons
        orig_dedup = seasons.remove_duplicate_seasons
        seasons.fetch_full_year_plus_cessation = fake_fetch_full_year_plus_cessation
        seasons.detect_onset_cessation = lambda df: []
        seasons.reassign_spillover_seasons = lambda results_dict, **kwargs: results_dict
        seasons.remove_duplicate_seasons = lambda results_dict: results_dict
        try:
            seasons.fetch_and_analyze_years(
                -1.286,
                36.817,
                2041,
                2041,
                source="nex_gddp",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            seasons.fetch_full_year_plus_cessation = orig_fetch
            seasons.detect_onset_cessation = orig_detect
            seasons.reassign_spillover_seasons = orig_reassign
            seasons.remove_duplicate_seasons = orig_dedup

        self.assertEqual(
            [
                {
                    "year": 2041,
                    "source": "nex_gddp",
                    "model": "ACCESS-CM2",
                    "scenario": "ssp245",
                }
            ],
            calls,
        )

    def test_remove_duplicate_seasons_prefers_closed_resolution_over_open_spillover(self):
        results = {
            2019: [
                {
                    "onset": pd.Timestamp("2019-05-08"),
                    "cessation": None,
                    "length_days": 54,
                    "regime": "erratic",
                },
                {
                    "onset": pd.Timestamp("2019-05-08"),
                    "cessation": pd.Timestamp("2019-06-25"),
                    "length_days": 49,
                    "regime": "late_peak_unimodal",
                },
            ]
        }

        deduped = seasons.remove_duplicate_seasons(results)

        self.assertEqual(1, len(deduped[2019]))
        self.assertEqual(pd.Timestamp("2019-06-25"), pd.to_datetime(deduped[2019][0]["cessation"]))

    def test_remove_duplicate_seasons_keeps_distinct_seasons(self):
        results = {
            2019: [
                {
                    "onset": pd.Timestamp("2019-03-02"),
                    "cessation": pd.Timestamp("2019-06-05"),
                    "length_days": 96,
                    "regime": "unimodal",
                },
                {
                    "onset": pd.Timestamp("2019-10-09"),
                    "cessation": pd.Timestamp("2019-12-29"),
                    "length_days": 82,
                    "regime": "late_peak_unimodal",
                },
            ]
        }

        deduped = seasons.remove_duplicate_seasons(results)

        self.assertEqual(2, len(deduped[2019]))


if __name__ == "__main__":
    unittest.main()
