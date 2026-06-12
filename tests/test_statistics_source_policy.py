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
    def test_get_climate_data_auto_uses_era5_before_fallback(self):
        calls = []

        def fake_call_preprocess(source, lat, lon, date_from, date_to, model, scenario):
            calls.append(source)
            if source == "era_5":
                return pd.DataFrame(
                    {
                        "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
                        "precipitation": [1.0, 0.0],
                        "max_temperature": [25.0, 26.0],
                        "min_temperature": [15.0, 16.0],
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

        self.assertEqual(["era_5"], calls)
        self.assertIn("precip", frame.columns)
        self.assertIn("tmax", frame.columns)
        self.assertIn("tmin", frame.columns)

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


if __name__ == "__main__":
    unittest.main()
