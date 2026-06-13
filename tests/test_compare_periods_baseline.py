from datetime import date
import json
import sys
import tempfile
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

import climate_tookit.compare_periods.ensemble_periods as ep
import climate_tookit.compare_periods.periods as cp


class ComparePeriodsBaselineScenarioTests(unittest.TestCase):
    def test_main_accepts_json_format_and_creates_output_directory(self):
        orig_compare = cp.compare
        orig_argv = sys.argv[:]
        cp.compare = lambda **kwargs: {
            "focal_year": 2020,
            "baseline_period": "2018-2019",
            "source": "auto",
        }
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = f"{tmpdir}/nested/results/compare_periods.json"
                sys.argv = [
                    "periods.py",
                    "--location=-1.286,36.817",
                    "--baseline-start=2018",
                    "--baseline-end=2019",
                    "--focal-year=2020",
                    "--source=auto",
                    "--format=json",
                    f"--output={output_path}",
                ]
                cp.main()
                with open(output_path) as handle:
                    saved = json.load(handle)
        finally:
            cp.compare = orig_compare
            sys.argv = orig_argv

        self.assertEqual(2020, saved["focal_year"])
        self.assertEqual("auto", saved["source"])

    def test_main_default_pandas_mode_creates_output_directory(self):
        orig_compare = cp.compare
        orig_print_report = cp.print_report
        orig_argv = sys.argv[:]
        cp.compare = lambda **kwargs: {
            "focal_year": 2020,
            "baseline_period": "2018-2019",
            "source": "auto",
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
        }
        cp.print_report = lambda result: None
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = f"{tmpdir}/nested/results/compare_periods.json"
                sys.argv = [
                    "periods.py",
                    "--location=-1.286,36.817",
                    "--baseline-start=2018",
                    "--baseline-end=2019",
                    "--focal-year=2020",
                    "--source=auto",
                    f"--output={output_path}",
                ]
                cp.main()
                with open(output_path) as handle:
                    saved = json.load(handle)
        finally:
            cp.compare = orig_compare
            cp.print_report = orig_print_report
            sys.argv = orig_argv

        self.assertEqual("2018-2019", saved["baseline_period"])

    def test_compare_rejects_auto_detect_when_yearly_season_counts_differ(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append((kwargs["start_year"], kwargs["end_year"]))
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [
                        {"year": 2018, "season_number": 1, "precipitation": {"total_mm": 500}},
                        {"year": 2019, "season_number": 1, "precipitation": {"total_mm": 400}},
                        {"year": 2019, "season_number": 2, "precipitation": {"total_mm": 300}},
                    ],
                    "annual_summary": {},
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [
                    {"year": 2020, "season_number": 1, "precipitation": {"total_mm": 450}},
                ],
                "annual_summary": {},
            }

        orig = cp.analyze_climate_statistics
        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="auto",
                fixed_season=None,
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertEqual([(2018, 2019), (2020, 2020)], calls)
        self.assertIn("error", result)
        self.assertIn("Auto-detected season counts differ", result["error"])
        self.assertIn("Re-run with --fixed-season", result["error"])

    def test_periods_compare_returns_clean_error_when_baseline_fetch_raises(self):
        def fake_analyze_climate_statistics(**kwargs):
            raise RuntimeError("No data returned from source 'era_5'")

        orig = cp.analyze_climate_statistics
        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="era_5",
                fixed_season="03-01:05-31",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertIn("error", result)
        self.assertIn("Baseline fetch/analysis failed", result["error"])
        self.assertIn("No data returned from source 'era_5'", result["error"])

    def test_periods_compare_returns_clean_error_when_focal_payload_has_error(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append((kwargs["start_year"], kwargs["end_year"]))
            if kwargs["start_year"] == 2020:
                return {"error": "No seasons produced by fixed-season mode"}
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        orig = cp.analyze_climate_statistics
        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="era_5",
                fixed_season="03-01:05-31",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertEqual([(2018, 2019), (2020, 2020)], calls)
        self.assertIn("error", result)
        self.assertIn("Focal fetch/analysis failed", result["error"])
        self.assertIn("No seasons produced by fixed-season mode", result["error"])

    def test_compare_one_model_uses_historical_for_baseline_and_ssp_for_future(self):
        calls = []

        def fake_analyze_climate_statistics(
            *,
            location_coord,
            start_year,
            end_year,
            source,
            fixed_season=None,
            model=None,
            scenario=None,
            **kwargs,
        ):
            calls.append((start_year, end_year, source, model, scenario))
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season=None,
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(
            [
                (1991, 2020, "nex_gddp", "ACCESS-CM2", "historical"),
                (2040, 2060, "nex_gddp", "ACCESS-CM2", "ssp245"),
            ],
            calls,
        )

    def test_ensemble_compare_does_not_raise_name_error_for_location_filtering(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2"]
        ep._compare_one_model = lambda **kwargs: {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
        }
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertNotIn("error", result)
        self.assertEqual(result["n_models_ok"], 1)

    def test_ensemble_compare_rejects_single_year_baseline_period(self):
        result = ep.ensemble_compare(
            location=(-1.286, 36.817),
            baseline_start=1991,
            baseline_end=1991,
            future_start=2050,
            future_end=2051,
            scenario="ssp245",
            verbose=False,
        )

        self.assertIn("error", result)
        self.assertIn("Single-year NEX-GDDP baseline/future comparisons are not allowed", result["error"])

    def test_ensemble_compare_rejects_single_year_future_period(self):
        result = ep.ensemble_compare(
            location=(-1.286, 36.817),
            baseline_start=1991,
            baseline_end=1992,
            future_start=2050,
            future_end=2050,
            scenario="ssp245",
            verbose=False,
        )

        self.assertIn("error", result)
        self.assertIn("Single-year NEX-GDDP baseline/future comparisons are not allowed", result["error"])

    def test_compare_one_model_rejects_single_year_periods_before_fetch(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {}

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1991,
                future_start=2050,
                future_end=2050,
                fixed_season=None,
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertIn("error", result)
        self.assertEqual([], calls)

    def test_compare_one_model_rejects_auto_detect_when_period_season_counts_differ(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append((kwargs["start_year"], kwargs["end_year"], kwargs["scenario"]))
            if kwargs["scenario"] == "historical":
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [
                        {"year": 1991, "season_number": 1, "precipitation": {"total_mm": 500}},
                        {"year": 1992, "season_number": 1, "precipitation": {"total_mm": 400}},
                        {"year": 1992, "season_number": 2, "precipitation": {"total_mm": 300}},
                    ],
                    "annual_summary": {},
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [
                    {"year": 2050, "season_number": 1, "precipitation": {"total_mm": 450}},
                    {"year": 2051, "season_number": 1, "precipitation": {"total_mm": 470}},
                ],
                "annual_summary": {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                fixed_season=None,
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(
            [
                (1991, 1992, "historical"),
                (2050, 2051, "ssp245"),
            ],
            calls,
        )
        self.assertIn("error", result)
        self.assertIn("Auto-detected season counts differ", result["error"])
        self.assertIn("Re-run with --fixed-season", result["error"])

    def test_diff_block_uses_baseline_magnitude_for_negative_values(self):
        result = cp._diff_block(
            {"water_balance": {"total_balance": -722.10}},
            {"water_balance": {"total_balance": -705.00}},
            "future_avg",
            "baseline_avg",
        )

        self.assertEqual(-17.1, result["water_balance"]["total_balance"]["diff"])
        self.assertEqual(-2.43, result["water_balance"]["total_balance"]["pct"])

    def test_diff_value_2level_uses_baseline_magnitude_for_negative_values(self):
        result = ep._diff_value_2level(
            {"water_balance": {"total_balance": -722.10}},
            {"water_balance": {"total_balance": -705.00}},
            "future_ltm",
            "baseline_ltm",
        )

        self.assertEqual(-17.1, result["water_balance"]["total_balance"]["diff"])
        self.assertEqual(-2.43, result["water_balance"]["total_balance"]["pct"])


if __name__ == "__main__":
    unittest.main()
