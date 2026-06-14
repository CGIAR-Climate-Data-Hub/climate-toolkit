from datetime import date
import json
from io import StringIO
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
    def test_percent_change_returns_none_when_comparison_crosses_zero(self):
        self.assertIsNone(cp._percent_change(-835.0, 15.2))
        self.assertEqual(-100.0, cp._percent_change(-15.2, 15.2))

    def test_print_report_renders_missing_pct_as_na(self):
        payload = {
            "focal_year": 2019,
            "baseline_period": "2018-2018",
            "source": "auto",
            "fixed_season": "03-01:06-30",
            "temperature_excluded": False,
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": {
                "windows": [
                    {
                        "window": "03-01:06-30",
                        "season_number": 1,
                        "n_baseline": 1,
                        "n_focal": 1,
                        "diff": {
                            "water_balance": {
                                "total_balance": {
                                    "focal": -819.8,
                                    "baseline_avg": 15.2,
                                    "diff": -835.0,
                                    "pct": None,
                                }
                            }
                        },
                    }
                ]
            },
            "annual_summary": {},
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            cp.print_report(payload)
        finally:
            sys.stdout = orig_stdout

        self.assertIn("n/a", stdout.getvalue())

    def test_print_report_renders_spei_block(self):
        payload = {
            "focal_year": 2019,
            "baseline_period": "2018-2018",
            "source": "auto",
            "fixed_season": None,
            "temperature_excluded": False,
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
            "spei": {
                "summary": {
                    "focal_avg_spei": -0.8,
                    "baseline_avg_spei": -0.2,
                    "diff": -0.6,
                    "pct": -300.0,
                },
                "monthly": [
                    {
                        "date": "2019-01-01",
                        "month": 1,
                        "focal_spei": -1.0,
                        "baseline_avg_spei": -0.3,
                        "diff": -0.7,
                        "pct": -233.33,
                    }
                ],
            },
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            cp.print_report(payload)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("--- 5. SPEI (monthly/period summary, not seasonal) ---", rendered)
        self.assertIn("2019-01-01", rendered)

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

    def test_compare_forwards_optional_spei_args(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spei": {
                    "config": {"scale_months": kwargs.get("spei_scale_months")},
                    "summary": {"n_months": 12, "n_valid_spei": 12},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2019-01-01", "month": 1, "spei": -1.0}
                    ],
                },
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
                spei_scale_months=3,
                spei_fit="ub-pwm",
                spei_ref_start="1991-01-01",
                spei_ref_end="2020-12-31",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual(3, calls[0]["spei_scale_months"])
        self.assertEqual("ub-pwm", calls[0]["spei_fit"])
        self.assertEqual("1991-01-01", calls[0]["spei_ref_start"])
        self.assertEqual("2020-12-31", calls[0]["spei_ref_end"])
        self.assertEqual(3, result["spei_scale_months"])

    def test_compare_computes_spei_monthly_and_summary_diffs(self):
        orig = cp.analyze_climate_statistics

        def fake_analyze_climate_statistics(**kwargs):
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": {
                        "config": {"scale_months": 3},
                        "summary": {"n_months": 24, "n_valid_spei": 24},
                        "metadata": {},
                        "monthly_series": [
                            {"date": "2018-01-01", "month": 1, "spei": -0.5},
                            {"date": "2019-01-01", "month": 1, "spei": -1.5},
                            {"date": "2018-02-01", "month": 2, "spei": 0.0},
                            {"date": "2019-02-01", "month": 2, "spei": 0.5},
                        ],
                    },
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spei": {
                    "config": {"scale_months": 3},
                    "summary": {"n_months": 12, "n_valid_spei": 12},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2020-01-01", "month": 1, "spei": -1.0},
                        {"date": "2020-02-01", "month": 2, "spei": 1.0},
                    ],
                },
            }

        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="era_5",
                fixed_season="03-01:05-31",
                spei_scale_months=3,
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertAlmostEqual(-1.0, result["spei"]["monthly"][0]["baseline_avg_spei"])
        self.assertAlmostEqual(0.0, result["spei"]["monthly"][0]["diff"])
        self.assertAlmostEqual(-0.375, result["spei"]["summary"]["baseline_avg_spei"])
        self.assertAlmostEqual(0.0, result["spei"]["summary"]["focal_avg_spei"])
        self.assertAlmostEqual(0.375, result["spei"]["summary"]["diff"])

    def test_compare_injects_fixed_season_spei_into_season_block(self):
        orig = cp.analyze_climate_statistics

        def fake_analyze_climate_statistics(**kwargs):
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": {
                        "config": {"scale_months": 3},
                        "summary": {"n_months": 6, "n_valid_spei": 6},
                        "metadata": {},
                        "monthly_series": [
                            {"date": "2018-03-01", "month": 3, "spei": -1.0},
                            {"date": "2018-04-01", "month": 4, "spei": -0.5},
                            {"date": "2018-05-01", "month": 5, "spei": 0.0},
                            {"date": "2019-03-01", "month": 3, "spei": -0.5},
                            {"date": "2019-04-01", "month": 4, "spei": 0.0},
                            {"date": "2019-05-01", "month": 5, "spei": 0.5},
                        ],
                    },
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spei": {
                    "config": {"scale_months": 3},
                    "summary": {"n_months": 3, "n_valid_spei": 3},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2020-03-01", "month": 3, "spei": 0.5},
                        {"date": "2020-04-01", "month": 4, "spei": 1.0},
                        {"date": "2020-05-01", "month": 5, "spei": 1.5},
                    ],
                },
            }

        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="era_5",
                fixed_season="03-01:05-31",
                spei_scale_months=3,
            )
        finally:
            cp.analyze_climate_statistics = orig

        season_spei = result["season_statistics"]["windows"][0]["diff"]["spei"]["mean_spei"]
        self.assertAlmostEqual(1.0, season_spei["focal"])
        self.assertAlmostEqual(-0.25, season_spei["baseline_avg"])
        self.assertAlmostEqual(1.25, season_spei["diff"])
        self.assertIsNone(season_spei["pct"])

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

    def test_compare_one_model_forwards_optional_spei_args(self):
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
            calls.append((start_year, end_year, scenario, kwargs))
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spei": {
                    "config": {"scale_months": kwargs.get("spei_scale_months")},
                    "summary": {"n_months": 12, "n_valid_spei": 12},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2050-01-01", "month": 1, "spei": -0.4}
                    ],
                },
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season="03-01:05-31",
                model="ACCESS-CM2",
                scenario="ssp245",
                spei_scale_months=6,
                spei_fit="ub-pwm",
                spei_ref_start="1991-01-01",
                spei_ref_end="2020-12-31",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual(6, calls[0][3]["spei_scale_months"])
        self.assertEqual("ub-pwm", calls[0][3]["spei_fit"])
        self.assertEqual("1991-01-01", calls[0][3]["spei_ref_start"])
        self.assertEqual("2020-12-31", calls[0][3]["spei_ref_end"])
        self.assertEqual(6, result["spei_scale_months"])
        self.assertIn("spei", result)

    def test_compare_one_model_injects_fixed_season_spei_into_season_block(self):
        orig = ep.analyze_climate_statistics

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
            if scenario == "historical":
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": {
                        "config": {"scale_months": 3},
                        "summary": {"n_months": 6, "n_valid_spei": 6},
                        "metadata": {},
                        "monthly_series": [
                            {"date": "1991-03-01", "month": 3, "spei": -1.0},
                            {"date": "1991-04-01", "month": 4, "spei": -0.5},
                            {"date": "1991-05-01", "month": 5, "spei": 0.0},
                            {"date": "1992-03-01", "month": 3, "spei": -0.5},
                            {"date": "1992-04-01", "month": 4, "spei": 0.0},
                            {"date": "1992-05-01", "month": 5, "spei": 0.5},
                        ],
                    },
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spei": {
                    "config": {"scale_months": 3},
                    "summary": {"n_months": 6, "n_valid_spei": 6},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2041-03-01", "month": 3, "spei": 0.5},
                        {"date": "2041-04-01", "month": 4, "spei": 1.0},
                        {"date": "2041-05-01", "month": 5, "spei": 1.5},
                        {"date": "2042-03-01", "month": 3, "spei": 0.0},
                        {"date": "2042-04-01", "month": 4, "spei": 0.5},
                        {"date": "2042-05-01", "month": 5, "spei": 1.0},
                    ],
                },
            }

        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2041,
                future_end=2042,
                fixed_season="03-01:05-31",
                model="ACCESS-CM2",
                scenario="ssp245",
                spei_scale_months=3,
            )
        finally:
            ep.analyze_climate_statistics = orig

        season_spei = result["season_statistics"]["windows"][0]["diff"]["spei"]["mean_spei"]
        self.assertAlmostEqual(0.75, season_spei["future_avg"])
        self.assertAlmostEqual(-0.25, season_spei["baseline_avg"])
        self.assertAlmostEqual(1.0, season_spei["diff"])
        self.assertIsNone(season_spei["pct"])

    def test_compare_one_model_returns_clean_error_when_future_payload_has_error(self):
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
            if scenario == "ssp245":
                return {"error": "Climate data fetch failed for source='nex_gddp'"}
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season="03-01:05-31",
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
        self.assertIn("error", result)
        self.assertIn("Future fetch/analysis failed", result["error"])
        self.assertIn("ACCESS-CM2", result["error"])

    def test_compare_one_model_returns_clean_error_when_baseline_payload_has_error(self):
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
            if scenario == "historical":
                return {"error": "Historical baseline unavailable"}
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season="03-01:05-31",
                model="ACCESS-CM2",
                scenario="ssp245",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertIn("error", result)
        self.assertIn("Baseline fetch/analysis failed", result["error"])
        self.assertIn("historical", result["error"])

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

    def test_ensemble_compare_aggregates_spei_from_per_model_results(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2", "MRI-ESM2-0"]
        ep._compare_one_model = lambda **kwargs: {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
            "spei": {
                "summary": {
                    "focal_avg_spei": -0.5 if kwargs["model"] == "ACCESS-CM2" else -1.5,
                    "baseline_avg_spei": -0.2 if kwargs["model"] == "ACCESS-CM2" else -0.4,
                    "diff": -0.3 if kwargs["model"] == "ACCESS-CM2" else -1.1,
                    "pct": -150.0 if kwargs["model"] == "ACCESS-CM2" else -275.0,
                },
                "monthly": [
                    {
                        "date": "2050-01-01",
                        "month": 1,
                        "focal_spei": -0.5 if kwargs["model"] == "ACCESS-CM2" else -1.5,
                        "baseline_avg_spei": -0.2 if kwargs["model"] == "ACCESS-CM2" else -0.4,
                        "diff": -0.3 if kwargs["model"] == "ACCESS-CM2" else -1.1,
                        "pct": -150.0 if kwargs["model"] == "ACCESS-CM2" else -275.0,
                    }
                ],
            },
        }
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                spei_scale_months=3,
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertAlmostEqual(-1.0, result["spei"]["summary"]["focal_avg_spei"])
        self.assertAlmostEqual(-0.3, result["spei"]["summary"]["baseline_avg_spei"])
        self.assertAlmostEqual(-0.7, result["spei"]["summary"]["diff"])
        self.assertEqual(2, result["spei"]["n_models"])

    def test_ensemble_compare_keeps_wrsi_only_in_season_blocks(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2", "MRI-ESM2-0"]

        def fake_compare_one_model(**kwargs):
            if kwargs["model"] == "ACCESS-CM2":
                wrsi_future, wrsi_base, wrsi_diff = 74.0, 68.0, 6.0
                ndws_future, ndws_base, ndws_diff = 12.0, 18.0, -6.0
            else:
                wrsi_future, wrsi_base, wrsi_diff = 82.0, 72.0, 10.0
                ndws_future, ndws_base, ndws_diff = 8.0, 14.0, -6.0
            return {
                "raw_climate_summary": {},
                "overall_statistics": {
                    "water_balance": {
                        "WRSI": {
                            "future_avg": wrsi_future,
                            "baseline_avg": wrsi_base,
                            "diff": wrsi_diff,
                            "pct": ep._percent_change(wrsi_diff, wrsi_base),
                        },
                        "NDWS": {
                            "future_avg": ndws_future,
                            "baseline_avg": ndws_base,
                            "diff": ndws_diff,
                            "pct": ep._percent_change(ndws_diff, ndws_base),
                        },
                    }
                },
                "season_statistics": {
                    "windows": [
                        {
                            "window": "03-01:05-31",
                            "season_number": 1,
                            "n_baseline": 2,
                            "n_future": 2,
                            "diff": {
                                "water_balance": {
                                    "WRSI": {
                                        "future_avg": wrsi_future - 2.0,
                                        "baseline_avg": wrsi_base - 1.0,
                                        "diff": wrsi_diff - 1.0,
                                        "pct": ep._percent_change(wrsi_diff - 1.0, wrsi_base - 1.0),
                                    }
                                }
                            },
                        }
                    ]
                },
                "annual_summary": {},
                "spei": None,
            }

        ep._compare_one_model = fake_compare_one_model
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                fixed_season="03-01:05-31",
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertNotIn("water_balance", result["overall_statistics"])
        season_wb = result["season_statistics"]["windows"][0]["diff"]["water_balance"]
        self.assertEqual(76.0, season_wb["WRSI"]["future_avg_ensemble_mean"])
        self.assertEqual(69.0, season_wb["WRSI"]["baseline_avg_ensemble_mean"])
        self.assertEqual(7.0, season_wb["WRSI"]["diff_ensemble_mean"])

    def test_diff_focal_vs_future_keeps_wrsi_only_in_season_block(self):
        focal = {
            "focal_year": 2019,
            "source": "era_5",
            "overall": {"water_balance": {"WRSI": 84.0}},
            "seasons": {
                "windows": [
                    {
                        "season_number": 1,
                        "block": {"water_balance": {"WRSI": 80.0}},
                    }
                ]
            },
            "annual_rain": None,
            "is_humid": None,
            "humid_test": None,
            "spei": None,
        }
        ensemble = {
            "overall_statistics": {
                "water_balance": {
                    "WRSI": {
                        "future_avg_ensemble_mean": 76.0,
                        "baseline_avg_ensemble_mean": 68.0,
                    }
                }
            },
            "season_statistics": {
                "windows": [
                    {
                        "window": "03-01:05-31",
                        "season_number": 1,
                        "diff": {
                            "water_balance": {
                                "WRSI": {
                                    "future_avg_ensemble_mean": 74.0,
                                    "baseline_avg_ensemble_mean": 69.0,
                                }
                            }
                        },
                    }
                ]
            },
            "annual_summary": {},
            "spei": None,
        }

        result = ep._diff_focal_vs_future(focal, ensemble)

        self.assertNotIn("water_balance", result["overall_statistics"])
        season_wb = result["season_statistics"]["windows"][0]["diff"]["water_balance"]
        self.assertEqual(80.0, season_wb["WRSI"]["focal"])
        self.assertEqual(74.0, season_wb["WRSI"]["future_ltm"])
        self.assertEqual(6.0, season_wb["WRSI"]["diff"])

    def test_print_focal_vs_ltm_renders_spei_block(self):
        payload = {
            "focal_year": 2019,
            "focal_source": "era_5",
            "ltm_label": "future_ltm",
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
            "spei": {
                "summary": {
                    "focal_avg_spei": -0.8,
                    "baseline_avg_spei": -0.2,
                    "diff": -0.6,
                    "pct": -300.0,
                },
                "monthly": [
                    {
                        "date": "2019-01-01",
                        "month": 1,
                        "focal_spei": -1.0,
                        "baseline_avg_spei": -0.3,
                        "diff": -0.7,
                        "pct": -233.33,
                    }
                ],
            },
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            ep._print_focal_vs_ltm(payload)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("2019-01-01", rendered)
        self.assertIn("Mean SPEI", rendered)

    def test_annotate_cli_timing_promotes_command_total_and_preserves_core_timer(self):
        result = {
            "metadata": {
                "timing": {
                    "total_seconds": 0.358,
                    "mean_model_seconds": 0.178,
                }
            }
        }

        annotated = ep._annotate_cli_timing(
            result,
            command_total_seconds=30.6,
            focal_prefetch_seconds=12.4,
        )

        timing = annotated["metadata"]["timing"]
        self.assertEqual(30.6, timing["total_seconds"])
        self.assertEqual(30.6, timing["command_total_seconds"])
        self.assertEqual(12.4, timing["focal_prefetch_seconds"])
        self.assertEqual(0.358, timing["ensemble_compare_seconds"])
        self.assertEqual(0.178, timing["mean_model_seconds"])

    def test_main_json_output_uses_command_wall_clock_timing(self):
        payload = {
            "scenario": "ssp245",
            "metadata": {
                "timing": {
                    "total_seconds": 0.358,
                    "mean_model_seconds": 0.178,
                }
            },
        }
        orig_argv = sys.argv[:]
        orig_ensemble_compare = ep.ensemble_compare
        orig_print_report = ep.print_report
        orig_perf_counter = ep.perf_counter

        ep.ensemble_compare = lambda **kwargs: json.loads(json.dumps(payload))
        ep.print_report = lambda result: None
        perf_values = iter([10.0, 40.6])
        ep.perf_counter = lambda: next(perf_values)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = f"{tmpdir}/nested/results/ensemble_periods.json"
                sys.argv = [
                    "ensemble_periods.py",
                    "--location=-1.286,36.817",
                    "--baseline-start=1991",
                    "--baseline-end=1993",
                    "--future-start=2040",
                    "--future-end=2042",
                    "--scenarios=ssp245",
                    f"--output={output_path}",
                ]
                ep.main()
                with open(output_path) as handle:
                    saved = json.load(handle)
        finally:
            sys.argv = orig_argv
            ep.ensemble_compare = orig_ensemble_compare
            ep.print_report = orig_print_report
            ep.perf_counter = orig_perf_counter

        timing = saved["metadata"]["timing"]
        self.assertEqual(30.6, timing["total_seconds"])
        self.assertEqual(30.6, timing["command_total_seconds"])
        self.assertEqual(0.0, timing["focal_prefetch_seconds"])
        self.assertEqual(0.358, timing["ensemble_compare_seconds"])

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

    def test_compare_keeps_wrsi_only_in_season_diffs(self):
        orig = cp.analyze_climate_statistics

        def fake_analyze_climate_statistics(**kwargs):
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {
                        "water_balance": {
                            "WRSI": 72.0,
                            "NDWS": 12,
                        }
                    },
                    "season_statistics": [
                        {
                            "year": 2018,
                            "season_number": 1,
                            "water_balance": {
                                "WRSI": 70.0,
                                "NDWS": 10,
                            },
                        }
                    ],
                    "annual_summary": {},
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {
                    "water_balance": {
                        "WRSI": 80.0,
                        "NDWS": 8,
                    }
                },
                "season_statistics": [
                    {
                        "year": 2019,
                        "season_number": 1,
                        "water_balance": {
                            "WRSI": 78.0,
                            "NDWS": 7,
                        },
                    }
                ],
                "annual_summary": {},
            }

        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2018,
                focal_year=2019,
                source="era_5",
                fixed_season="03-01:05-31",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertNotIn("water_balance", result["overall_statistics"])
        season_diff = result["season_statistics"]["windows"][0]["diff"]["water_balance"]
        self.assertEqual(78.0, season_diff["WRSI"]["focal"])
        self.assertEqual(70.0, season_diff["WRSI"]["baseline_avg"])
        self.assertEqual(8.0, season_diff["WRSI"]["diff"])

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
