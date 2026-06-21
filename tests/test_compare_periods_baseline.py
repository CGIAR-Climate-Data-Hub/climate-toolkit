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
        self.assertNotIn("Category", stdout.getvalue())
        self.assertIn("metric", stdout.getvalue())

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
            cp.print_report(payload, detailed=True)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("--- 5. SPEI (monthly/period summary, not seasonal) ---", rendered)
        self.assertIn("2019-01-01", rendered)

    def test_print_report_compact_hides_monthly_spei_table(self):
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
            cp.print_report(payload, detailed=False)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("Mean SPEI", rendered)
        self.assertIn("hidden in compact mode", rendered)
        self.assertNotIn("2019-01-01", rendered)

    def test_print_report_emits_custom_water_balance_note(self):
        payload = {
            "focal_year": 2019,
            "baseline_period": "2018-2018",
            "source": "auto",
            "fixed_season": None,
            "temperature_excluded": False,
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": {
                "windows": [
                    {
                        "window": "03-01:05-31",
                        "season_number": 1,
                        "n_baseline": 1,
                        "n_focal": 1,
                        "diff": {
                            "water_balance": {
                                "NDWS": {"focal": 4, "baseline_avg": 2, "diff": 2, "pct": 100.0}
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
            cp.print_report(payload, detailed=False)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("custom crop-water-balance metrics", rendered)

    def test_print_report_renders_xclim_reference_block(self):
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
            "xclim_references": {
                "status": {
                    "baseline_avg": {
                        "available": True,
                        "core_period_status": "computed",
                        "precip_reference_status": "computed",
                    },
                    "focal": {
                        "available": True,
                        "core_period_status": "computed",
                        "precip_reference_status": "computed",
                    },
                },
                "diff": {
                    "core_period_metrics": {
                        "total_mm": {"focal": 100.0, "baseline_avg": 80.0, "diff": 20.0, "pct": 25.0}
                    }
                },
            },
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            cp.print_report(payload, detailed=False)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("--- XCLIM STANDARD REFERENCES ---", rendered)
        self.assertIn("Core standard period metrics", rendered)

    def test_ensemble_print_report_hides_per_model_breakdown_in_compact_mode(self):
        payload = {
            "baseline_period": "1995-2013",
            "future_period": "2041-2060",
            "scenario": "ssp245",
            "n_models_ok": 2,
            "models_failed": [],
            "crop_name": "maize",
            "calendar_source": "ggcmi",
            "calendar_system": "rf",
            "season_detection": {"compare_status": "ok", "baseline": {}, "focal": {}, "guidance": []},
            "per_model_results": [
                {
                    "_model": "ACCESS-CM2",
                    "overall_statistics": {"precipitation": {"total_mm": {"future_avg": 10.0, "baseline_avg": 9.0, "diff": 1.0, "pct": 11.11}}},
                    "annual_summary": {"annual_rain_mm": {"future": 10.0, "baseline_avg": 9.0, "diff": 1.0, "pct": 11.11}},
                }
            ],
            "raw_climate_summary": {"precipitation": {"mean": {"future_ltm_ensemble_mean": 1.0, "baseline_ltm_ensemble_mean": 0.9, "diff_ensemble_mean": 0.1, "pct_ensemble_mean": 11.11}}},
            "overall_statistics": {"precipitation": {"total_mm": {"future_avg_ensemble_mean": 10.0, "baseline_avg_ensemble_mean": 9.0, "diff_ensemble_mean": 1.0, "pct_ensemble_mean": 11.11}}},
            "season_statistics": None,
            "annual_summary": {
                "annual_rain_mm_future": {"mean": 10.0},
                "annual_rain_mm_baseline": {"mean": 9.0},
                "annual_rain_mm_diff": {"mean": 1.0},
                "annual_rain_mm_pct": {"mean": 11.11},
                "humid_future": "0/2 (0.0%)",
                "humid_baseline": "0/2 (0.0%)",
            },
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            ep.print_report(payload, detailed=False)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("ENSEMBLE: Baseline LTM 1995-2013 vs Future LTM 2041-2060", rendered)
        self.assertNotIn("PER-MODEL BREAKDOWN", rendered)
        self.assertNotIn("RAW CLIMATE SUMMARY", rendered)
        self.assertIn("OVERALL STATISTICS", rendered)

    def test_run_stats_call_suppresses_inner_stdout_in_compact_mode(self):
        orig = ep.analyze_climate_statistics

        def fake_analyze_climate_statistics(**kwargs):
            print("Fetching climate data: noisy inner log")
            return {"overall_statistics": {}, "season_statistics": [], "annual_summary": {}}

        stdout = StringIO()
        orig_stdout = sys.stdout
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            sys.stdout = stdout
            ep._run_stats_call(diagnostic_verbose=False, location_coord=(-1.286, 36.817))
        finally:
            sys.stdout = orig_stdout
            ep.analyze_climate_statistics = orig

        self.assertNotIn("Fetching climate data", stdout.getvalue())

    def test_run_stats_call_preserves_inner_stdout_in_verbose_mode(self):
        orig = ep.analyze_climate_statistics

        def fake_analyze_climate_statistics(**kwargs):
            print("Fetching climate data: verbose inner log")
            return {"overall_statistics": {}, "season_statistics": [], "annual_summary": {}}

        stdout = StringIO()
        orig_stdout = sys.stdout
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            sys.stdout = stdout
            ep._run_stats_call(diagnostic_verbose=True, location_coord=(-1.286, 36.817))
        finally:
            sys.stdout = orig_stdout
            ep.analyze_climate_statistics = orig

        self.assertIn("Fetching climate data", stdout.getvalue())

    def test_spread_includes_ipcc_style_likely_percentiles(self):
        spread = ep._spread([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertIn("p17", spread)
        self.assertIn("p83", spread)
        self.assertAlmostEqual(1.68, spread["p17"], places=2)
        self.assertAlmostEqual(4.32, spread["p83"], places=2)

    def test_print_2level_renders_delta_uncertainty_columns(self):
        payload = {
            "precipitation": {
                "total_mm": {
                    "future_avg_ensemble_mean": 10.0,
                    "baseline_avg_ensemble_mean": 8.0,
                    "diff_ensemble_mean": 2.0,
                    "pct_ensemble_mean": 25.0,
                    "model_spread": {
                        "future_avg": {"std": 1.1, "p17": 8.5, "p83": 11.5},
                        "baseline_avg": {"std": 0.9, "p17": 7.2, "p83": 8.8},
                        "diff": {"std": 0.7, "p17": 1.2, "p83": 2.8},
                        "pct": {"std": 5.0, "p17": 15.0, "p83": 35.0},
                    },
                }
            }
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            ep._print_2level(payload)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("σΔ", rendered)
        self.assertIn("likely_Δ", rendered)
        self.assertIn("[1.20, 2.80]", rendered)

    def test_print_report_error_renders_season_detection_details(self):
        payload = {
            "error": "Auto season detection not reliable enough.",
            "season_detection": {
                "compare_status": "prompt_required",
                "baseline": {
                    "status": "prompt_required",
                    "reasons": ["perhumid_no_clear_onset"],
                    "details": {
                        "diagnostics": {
                            "counts_by_year": {"2020": 0},
                            "skip_reasons_by_year": {
                                "2020": "Perhumid location. No clear onset/cessation."
                            },
                        }
                    },
                },
                "focal": {
                    "status": "prompt_required",
                    "reasons": ["no_seasons_detected_all_years"],
                    "details": {
                        "diagnostics": {
                            "counts_by_year": {"2021": 0},
                        }
                    },
                },
                "guidance": ["Use --fixed-season."],
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
        self.assertIn("baseline_counts=2020:0", rendered)
        self.assertIn("baseline_notes:", rendered)
        self.assertIn("Perhumid location. No clear onset/cessation.", rendered)
        self.assertIn("focal_counts=2021:0", rendered)
        self.assertIn("Use --fixed-season.", rendered)

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
        cp.print_report = lambda result, **kwargs: None
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

    def test_compare_computes_xclim_reference_diffs(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "xclim_references": {
                        "available": True,
                        "core_period_metrics": [{"period_start": "2018-01-01", "total_mm": 80.0, "mean_tmax": 25.0}],
                        "core_period_status": "computed",
                        "core_period_skip_reason": None,
                        "precip_reference_indices": [{"period_start": "2018-01-01", "rx1day_mm": 10.0}],
                        "precip_reference_status": "computed",
                        "precip_reference_skip_reason": None,
                    },
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "xclim_references": {
                    "available": True,
                    "core_period_metrics": [{"period_start": "2019-01-01", "total_mm": 100.0, "mean_tmax": 27.0}],
                    "core_period_status": "computed",
                    "core_period_skip_reason": None,
                    "precip_reference_indices": [{"period_start": "2019-01-01", "rx1day_mm": 14.0}],
                    "precip_reference_status": "computed",
                    "precip_reference_skip_reason": None,
                },
            }

        orig_analyze = cp.analyze_climate_statistics
        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2018,
                focal_year=2019,
                source="auto",
            )
        finally:
            cp.analyze_climate_statistics = orig_analyze

        self.assertEqual(2, len(calls))
        self.assertIn("xclim_references", result)
        diff = result["xclim_references"]["diff"]
        self.assertAlmostEqual(20.0, diff["core_period_metrics"]["total_mm"]["diff"])
        self.assertAlmostEqual(4.0, diff["precip_reference_indices"]["rx1day_mm"]["diff"])

    def test_compare_forwards_optional_spi_args(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spi": {
                    "config": {"scale_months": kwargs.get("spi_scale_months")},
                    "summary": {"n_months": 12, "n_valid_spi": 12},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2019-01-01", "month": 1, "spi": -1.0}
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
                spi_scale_months=3,
                spi_fit="ub-pwm",
                spi_ref_start="1991-01-01",
                spi_ref_end="2020-12-31",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual(3, calls[0]["spi_scale_months"])
        self.assertEqual("ub-pwm", calls[0]["spi_fit"])
        self.assertEqual("1991-01-01", calls[0]["spi_ref_start"])
        self.assertEqual("2020-12-31", calls[0]["spi_ref_end"])
        self.assertEqual(3, result["spi_scale_months"])

    def test_compare_forwards_calendar_preset_args_and_carries_usage_flags(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "calendar_preset_used": True,
                "calendar_preset": {
                    "calendar_source": "ggcmi_phase3",
                    "crop_name": "Maize",
                    "calendar_system": "rf",
                    "fixed_season": "03-11:06-13",
                },
                "season_detection_status": "ok",
                "season_detection_reasons": ["calendar_preset_fallback_applied", "fixed_season_override"],
                "season_detection_guidance": [],
                "season_detection": {"status": "ok", "reasons": []},
            }

        orig = cp.analyze_climate_statistics
        cp.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = cp.compare(
                location=(-1.286, 36.817),
                baseline_start=2018,
                baseline_end=2019,
                focal_year=2020,
                source="paired",
                precip_source="chirps_v2",
                temp_source="agera_5",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            cp.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual("maize", calls[0]["crop_name"])
        self.assertEqual("ggcmi", calls[0]["calendar_source"])
        self.assertEqual("rf", calls[0]["calendar_system"])
        self.assertTrue(result["baseline_calendar_preset_used"])
        self.assertTrue(result["focal_calendar_preset_used"])
        self.assertEqual("ggcmi_phase3", result["baseline_calendar_preset"]["calendar_source"])

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
                baseline_end=2014,
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
                (1991, 2014, "nex_gddp", "ACCESS-CM2", "historical"),
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
                baseline_end=2014,
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

    def test_compare_one_model_forwards_optional_spi_args(self):
        calls = []

        def fake_analyze_climate_statistics(*, start_year, end_year, source, model=None, scenario=None, **kwargs):
            calls.append((start_year, end_year, source, kwargs))
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "spi": {
                    "config": {"scale_months": kwargs.get("spi_scale_months")},
                    "summary": {"n_months": 12, "n_valid_spi": 12},
                    "metadata": {},
                    "monthly_series": [
                        {"date": "2050-01-01", "month": 1, "spi": -0.4}
                    ],
                },
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2014,
                future_start=2040,
                future_end=2060,
                fixed_season="03-01:05-31",
                model="ACCESS-CM2",
                scenario="ssp245",
                spi_scale_months=6,
                spi_fit="ub-pwm",
                spi_ref_start="1991-01-01",
                spi_ref_end="2020-12-31",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual(6, calls[0][3]["spi_scale_months"])
        self.assertEqual("ub-pwm", calls[0][3]["spi_fit"])
        self.assertEqual("1991-01-01", calls[0][3]["spi_ref_start"])
        self.assertEqual("2020-12-31", calls[0][3]["spi_ref_end"])
        self.assertEqual(6, result["spi_scale_months"])
        self.assertIn("spi", result)

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
                baseline_end=2014,
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
                (1991, 2014, "nex_gddp", "ACCESS-CM2", "historical"),
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
                baseline_end=2014,
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

    def test_ensemble_compare_aggregates_xclim_reference_diffs(self):
        def fake_compare_one_model(*args, **kwargs):
            model = kwargs["model"]
            return {
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "xclim_references": {
                    "status": {
                        "baseline_avg": {
                            "core_period_status": "computed",
                            "precip_reference_status": "computed",
                        },
                        "future_avg": {
                            "core_period_status": "computed",
                            "precip_reference_status": "computed",
                        },
                    },
                    "diff": {
                        "core_period_metrics": {
                            "total_mm": {
                                "future_avg": 120.0 if model == "ACCESS-CM2" else 140.0,
                                "baseline_avg": 80.0 if model == "ACCESS-CM2" else 90.0,
                                "diff": 40.0 if model == "ACCESS-CM2" else 50.0,
                                "pct": 50.0 if model == "ACCESS-CM2" else 55.56,
                            }
                        }
                    },
                },
                "spei": None,
                "spi": None,
                "season_detection": {"compare_status": "ok", "baseline": {}, "focal": {}, "guidance": []},
                "timing_breakdown": {
                    "baseline": {},
                    "future": {},
                    "baseline_total_seconds": 1.0,
                    "future_total_seconds": 1.0,
                    "compare_seconds": 0.1,
                },
                "_elapsed_seconds": 2.1,
                "_model": model,
            }

        orig_compare_one_model = ep._compare_one_model
        orig_execute = ep._execute_model_tasks
        ep._compare_one_model = fake_compare_one_model
        ep._execute_model_tasks = lambda tasks, model_workers, verbose, diagnostic_verbose: (
            [fake_compare_one_model(model=task["model"]) for task in tasks],
            [],
            1,
            4.2,
        )
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2041,
                future_end=2042,
                scenario="ssp245",
                models=["ACCESS-CM2", "MRI-ESM2-0"],
                verbose=False,
            )
        finally:
            ep._compare_one_model = orig_compare_one_model
            ep._execute_model_tasks = orig_execute

        self.assertIn("xclim_references", result)
        self.assertAlmostEqual(45.0, result["xclim_references"]["diff"]["core_period_metrics"]["total_mm"]["diff_ensemble_mean"])
        self.assertEqual(2, result["xclim_references"]["status"]["n_models"])

    def test_ensemble_compare_aggregates_spi_from_per_model_results(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2", "MRI-ESM2-0"]
        ep._compare_one_model = lambda **kwargs: {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
            "spi": {
                "summary": {
                    "focal_avg_spi": -0.5 if kwargs["model"] == "ACCESS-CM2" else -1.5,
                    "baseline_avg_spi": -0.2 if kwargs["model"] == "ACCESS-CM2" else -0.4,
                    "diff": -0.3 if kwargs["model"] == "ACCESS-CM2" else -1.1,
                    "pct": -150.0 if kwargs["model"] == "ACCESS-CM2" else -275.0,
                },
                "monthly": [
                    {
                        "date": "2050-01-01",
                        "month": 1,
                        "focal_spi": -0.5 if kwargs["model"] == "ACCESS-CM2" else -1.5,
                        "baseline_avg_spi": -0.2 if kwargs["model"] == "ACCESS-CM2" else -0.4,
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
                spi_scale_months=3,
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertAlmostEqual(-1.0, result["spi"]["summary"]["focal_avg_spi"])
        self.assertAlmostEqual(-0.3, result["spi"]["summary"]["baseline_avg_spi"])
        self.assertAlmostEqual(-0.7, result["spi"]["summary"]["diff"])
        self.assertEqual(2, result["spi"]["n_models"])

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

    def test_print_focal_vs_ltm_renders_spi_block(self):
        payload = {
            "focal_year": 2019,
            "focal_source": "era_5",
            "ltm_label": "future_ltm",
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
            "spi": {
                "summary": {
                    "focal_avg_spi": -0.8,
                    "baseline_avg_spi": -0.2,
                    "diff": -0.6,
                    "pct": -300.0,
                },
                "monthly": [
                    {
                        "date": "2019-01-01",
                        "month": 1,
                        "focal_spi": -1.0,
                        "baseline_avg_spi": -0.3,
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
        self.assertIn("Mean SPI", rendered)

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

    def test_ensemble_print_report_renders_runtime_summary(self):
        payload = {
            "baseline_period": "1995-2013",
            "future_period": "2041-2060",
            "scenario": "ssp245",
            "n_models_ok": 2,
            "models_failed": [],
            "per_model_results": [],
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
            "metadata": {
                "timing": {
                    "runtime_summary": {
                        "models_ok": 2,
                        "models_failed": 0,
                        "total_elapsed_seconds": 38.0,
                        "mean_model_seconds": 19.0,
                        "median_model_seconds": 19.0,
                        "slowest_models": [{"model": "ACCESS-CM2", "total_seconds": 21.4}],
                        "stage_summary": {
                            "baseline_total": {"mean_seconds": 10.0},
                            "future_total": {"mean_seconds": 8.0},
                            "compare": {"mean_seconds": 0.3},
                            "baseline_fetch": {"mean_seconds": 6.0},
                            "future_fetch": {"mean_seconds": 5.0},
                        },
                    }
                }
            },
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            ep.print_report(payload, detailed=False)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("--- Runtime Summary ---", rendered)
        self.assertIn("mean=19.0s", rendered)
        self.assertIn("ACCESS-CM2(21.4s)", rendered)

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

    def test_ensemble_compare_records_model_worker_metadata_in_serial_mode(self):
        orig_resolve = ep._resolve_models_and_policy
        orig_task_runner = ep._run_compare_one_model_task

        ep._resolve_models_and_policy = lambda *args, **kwargs: (
            ["ACCESS-CM2", "MRI-ESM2-0"],
            {"policy_id": "unit-test"},
        )

        def fake_task_runner(task):
            model = task["model"]
            return {
                "model": model,
                "ok": True,
                "elapsed_seconds": 0.25,
                "result": {
                    "_model": model,
                    "_elapsed_seconds": 0.25,
                    "raw_climate_summary": {},
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": None,
                },
            }

        ep._run_compare_one_model_task = fake_task_runner
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                model_workers=1,
                verbose=False,
            )
        finally:
            ep._resolve_models_and_policy = orig_resolve
            ep._run_compare_one_model_task = orig_task_runner

        timing = result["metadata"]["timing"]
        self.assertEqual(1, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])

    def test_compare_one_model_records_stage_timing_breakdown(self):
        orig_run_stats_call = ep._run_stats_call

        calls = []

        def fake_run_stats_call(**kwargs):
            calls.append(kwargs)
            if kwargs["scenario"] == "historical":
                return {
                    "timing": {
                        "fetch_seconds": 5.2,
                        "season_reduction_seconds": 1.3,
                        "total_seconds": 8.4,
                    },
                    "raw_climate_summary": [],
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                }
            return {
                "timing": {
                    "fetch_seconds": 4.8,
                    "season_reduction_seconds": 1.1,
                    "total_seconds": 7.6,
                },
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        ep._run_stats_call = fake_run_stats_call
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
            ep._run_stats_call = orig_run_stats_call

        self.assertEqual(2, len(calls))
        timing = result["timing_breakdown"]
        self.assertEqual(5.2, timing["baseline"]["fetch_seconds"])
        self.assertEqual(4.8, timing["future"]["fetch_seconds"])
        self.assertTrue(timing["baseline_total_seconds"] >= 0.0)
        self.assertTrue(timing["future_total_seconds"] >= 0.0)
        self.assertTrue(timing["compare_seconds"] >= 0.0)

    def test_compare_one_model_requests_compact_statistics_payloads(self):
        orig_run_stats_call = ep._run_stats_call
        calls = []

        def fake_run_stats_call(**kwargs):
            calls.append(kwargs)
            return {
                "timing": {"fetch_seconds": 1.0, "season_reduction_seconds": 0.5, "total_seconds": 1.8},
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
            }

        ep._run_stats_call = fake_run_stats_call
        try:
            ep._compare_one_model(
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
            ep._run_stats_call = orig_run_stats_call

        self.assertEqual(2, len(calls))
        for kwargs in calls:
            self.assertFalse(kwargs["include_season_raw_summary"])
            self.assertFalse(kwargs["include_season_overall_statistics"])
            self.assertFalse(kwargs["include_ltm_season_summary"])

    def test_ensemble_compare_parallel_path_uses_executor_and_suppresses_child_stdout(self):
        orig_resolve = ep._resolve_models_and_policy
        orig_task_runner = ep._run_compare_one_model_task
        orig_executor = ep.ProcessPoolExecutor
        orig_as_completed = ep.as_completed

        ep._resolve_models_and_policy = lambda *args, **kwargs: (
            ["ACCESS-CM2", "MRI-ESM2-0"],
            {"policy_id": "unit-test"},
        )

        tasks_seen = []

        def fake_task_runner(task):
            tasks_seen.append(task)
            model = task["model"]
            return {
                "model": model,
                "ok": True,
                "elapsed_seconds": 0.5,
                "result": {
                    "_model": model,
                    "_elapsed_seconds": 0.5,
                    "raw_climate_summary": {},
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": None,
                },
            }

        class _FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class _FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, task):
                return _FakeFuture(fn(task))

        ep._run_compare_one_model_task = fake_task_runner
        ep.ProcessPoolExecutor = _FakeExecutor
        ep.as_completed = lambda futures: list(futures)
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                model_workers=8,
                verbose=False,
            )
        finally:
            ep._resolve_models_and_policy = orig_resolve
            ep._run_compare_one_model_task = orig_task_runner
            ep.ProcessPoolExecutor = orig_executor
            ep.as_completed = orig_as_completed

        timing = result["metadata"]["timing"]
        self.assertEqual(8, timing["model_workers_requested"])
        self.assertEqual(2, timing["model_workers_used"])
        self.assertEqual(2, len(tasks_seen))
        self.assertTrue(all(task["suppress_child_stdout"] for task in tasks_seen))

    def test_ensemble_compare_parallel_falls_back_to_serial_when_process_pool_unavailable(self):
        orig_resolve = ep._resolve_models_and_policy
        orig_task_runner = ep._run_compare_one_model_task
        orig_executor = ep.ProcessPoolExecutor

        ep._resolve_models_and_policy = lambda *args, **kwargs: (
            ["ACCESS-CM2", "MRI-ESM2-0"],
            {"policy_id": "unit-test"},
        )

        def fake_task_runner(task):
            model = task["model"]
            return {
                "model": model,
                "ok": True,
                "elapsed_seconds": 0.5,
                "result": {
                    "_model": model,
                    "_elapsed_seconds": 0.5,
                    "raw_climate_summary": {},
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": None,
                },
            }

        class _BrokenExecutor:
            def __init__(self, max_workers):
                raise PermissionError("blocked semaphore")

        ep._run_compare_one_model_task = fake_task_runner
        ep.ProcessPoolExecutor = _BrokenExecutor
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                model_workers=4,
                verbose=False,
            )
        finally:
            ep._resolve_models_and_policy = orig_resolve
            ep._run_compare_one_model_task = orig_task_runner
            ep.ProcessPoolExecutor = orig_executor

        timing = result["metadata"]["timing"]
        self.assertEqual(4, timing["model_workers_requested"])
        self.assertEqual(1, timing["model_workers_used"])
        self.assertEqual(2, result["n_models_ok"])

    def test_ensemble_compare_records_runtime_summary_metadata(self):
        orig_resolve = ep._resolve_models_and_policy
        orig_task_runner = ep._run_compare_one_model_task

        ep._resolve_models_and_policy = lambda *args, **kwargs: (
            ["ACCESS-CM2", "MRI-ESM2-0"],
            {"policy_id": "unit-test"},
        )

        outcomes = {
            "ACCESS-CM2": {
                "baseline_total_seconds": 11.2,
                "future_total_seconds": 9.8,
                "compare_seconds": 0.4,
                "baseline": {"fetch_seconds": 7.0, "season_reduction_seconds": 1.0},
                "future": {"fetch_seconds": 6.1, "season_reduction_seconds": 0.9},
            },
            "MRI-ESM2-0": {
                "baseline_total_seconds": 8.8,
                "future_total_seconds": 7.5,
                "compare_seconds": 0.3,
                "baseline": {"fetch_seconds": 5.0, "season_reduction_seconds": 0.8},
                "future": {"fetch_seconds": 4.5, "season_reduction_seconds": 0.7},
            },
        }

        def fake_task_runner(task):
            model = task["model"]
            elapsed = 21.4 if model == "ACCESS-CM2" else 16.6
            return {
                "model": model,
                "ok": True,
                "elapsed_seconds": elapsed,
                "timing_breakdown": outcomes[model],
                "result": {
                    "_model": model,
                    "_elapsed_seconds": elapsed,
                    "timing_breakdown": outcomes[model],
                    "raw_climate_summary": {},
                    "overall_statistics": {},
                    "season_statistics": [],
                    "annual_summary": {},
                    "spei": None,
                },
            }

        ep._run_compare_one_model_task = fake_task_runner
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                model_workers=1,
                verbose=False,
            )
        finally:
            ep._resolve_models_and_policy = orig_resolve
            ep._run_compare_one_model_task = orig_task_runner

        timing = result["metadata"]["timing"]
        runtime = timing["runtime_summary"]
        self.assertEqual(19.0, timing["mean_model_seconds"])
        self.assertEqual(19.0, timing["median_model_seconds"])
        self.assertEqual("ACCESS-CM2", runtime["slowest_models"][0]["model"])
        self.assertEqual(5.3, runtime["stage_summary"]["future_fetch"]["mean_seconds"])
        self.assertEqual(2, runtime["models_ok"])

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

    def test_ensemble_compare_rejects_historical_baseline_after_2014(self):
        result = ep.ensemble_compare(
            location=(-1.286, 36.817),
            baseline_start=1991,
            baseline_end=2020,
            future_start=2041,
            future_end=2060,
            scenario="ssp245",
            verbose=False,
        )

        self.assertIn("error", result)
        self.assertIn("2014-12-31", result["error"])
        self.assertIn("Use historical baseline years ending no later than 2014", result["error"])

    def test_ensemble_compare_rejects_year_crossing_ggcmi_historical_boundary_once(self):
        orig_resolve = ep.resolve_calendar_preset
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        calls = []

        ep.resolve_calendar_preset = lambda lat, lon, crop_name, system="rf": {
            "calendar_source": "ggcmi_phase3",
            "crop_name": "Maize",
            "calendar_system": system,
            "fixed_season": "10-22:01-09",
        }
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2"]
        ep._compare_one_model = lambda **kwargs: calls.append(kwargs) or {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
        }
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1995,
                baseline_end=2014,
                future_start=2041,
                future_end=2060,
                scenario="ssp245",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
                verbose=False,
            )
        finally:
            ep.resolve_calendar_preset = orig_resolve
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertIn("error", result)
        self.assertIn("10-22:01-09", result["error"])
        self.assertIn("--baseline-end=2013", result["error"])
        self.assertEqual([], calls)

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

    def test_compare_one_model_forwards_calendar_preset_args(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {
                "raw_climate_summary": [],
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {},
                "calendar_preset_used": True,
                "calendar_preset": {
                    "calendar_source": "ggcmi_phase3",
                    "crop_name": "Maize",
                    "calendar_system": "rf",
                    "fixed_season": "03-11:06-13",
                },
                "season_detection_status": "ok",
                "season_detection_reasons": ["calendar_preset_fallback_applied", "fixed_season_override"],
                "season_detection_guidance": [],
                "season_detection": {"status": "ok", "reasons": []},
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
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(2, len(calls))
        self.assertEqual("maize", calls[0]["crop_name"])
        self.assertEqual("ggcmi", calls[0]["calendar_source"])
        self.assertEqual("rf", calls[0]["calendar_system"])
        self.assertTrue(result["baseline_calendar_preset_used"])
        self.assertTrue(result["future_calendar_preset_used"])

    def test_build_focal_summary_forwards_calendar_preset_args(self):
        calls = []

        def fake_analyze_climate_statistics(**kwargs):
            calls.append(kwargs)
            return {
                "overall_statistics": {},
                "season_statistics": [],
                "annual_summary": {
                    "2020": {
                        "annual_rain_mm": 700.0,
                        "is_humid": False,
                        "humid_test": "Not humid",
                    }
                },
                "calendar_preset_used": True,
                "calendar_preset": {
                    "calendar_source": "ggcmi_phase3",
                    "crop_name": "Maize",
                    "calendar_system": "rf",
                    "fixed_season": "03-11:06-13",
                },
                "season_detection_status": "ok",
                "season_detection_reasons": ["calendar_preset_fallback_applied", "fixed_season_override"],
                "season_detection_guidance": [],
                "season_detection": {"status": "ok", "reasons": []},
                "spei": None,
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            result = ep._build_focal_summary(
                location=(-1.286, 36.817),
                focal_year=2020,
                focal_source="paired",
                fixed_season=None,
                precip_source="chirps_v2",
                temp_source="agera_5",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual(1, len(calls))
        self.assertEqual("maize", calls[0]["crop_name"])
        self.assertEqual("ggcmi", calls[0]["calendar_source"])
        self.assertEqual("rf", calls[0]["calendar_system"])
        self.assertTrue(result["calendar_preset_used"])
        self.assertEqual("ggcmi_phase3", result["calendar_preset"]["calendar_source"])

    def test_ensemble_compare_carries_calendar_request_fields(self):
        orig_filter = ep._filter_models
        orig_compare = ep._compare_one_model
        ep._filter_models = lambda location, models, exclude_models: ["ACCESS-CM2"]
        ep._compare_one_model = lambda **kwargs: {
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": [],
            "annual_summary": {},
            "crop_name": kwargs.get("crop_name"),
            "calendar_source": kwargs.get("calendar_source"),
            "calendar_system": kwargs.get("calendar_system"),
        }
        try:
            result = ep.ensemble_compare(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=1992,
                future_start=2050,
                future_end=2051,
                scenario="ssp245",
                crop_name="maize",
                calendar_source="ggcmi",
                calendar_system="rf",
                verbose=False,
            )
        finally:
            ep._filter_models = orig_filter
            ep._compare_one_model = orig_compare

        self.assertEqual("maize", result["crop_name"])
        self.assertEqual("ggcmi", result["calendar_source"])
        self.assertEqual("rf", result["calendar_system"])

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

    def test_compare_carries_water_balance_methodology_summary(self):
        orig = cp.analyze_climate_statistics

        def _method(counted_days):
            return {
                "count_window": {
                    "requested_mode": "full_window",
                    "applied_mode": "full_window",
                    "counted_days": counted_days,
                    "counted_subseasons": 0,
                },
                "warnings": [
                    "climate_statistics shared NDWS/WRSI uses default full-window root-zone settings."
                ],
            }

        def fake_analyze_climate_statistics(**kwargs):
            if kwargs["start_year"] == 2018:
                return {
                    "raw_climate_summary": [],
                    "overall_statistics": {"water_balance": {"NDWS": 10}},
                    "season_statistics": [
                        {
                            "year": 2018,
                            "season_number": 1,
                            "water_balance": {"NDWS": 10},
                            "water_balance_methodology": _method(92),
                        }
                    ],
                    "annual_summary": {},
                }
            return {
                "raw_climate_summary": [],
                "overall_statistics": {"water_balance": {"NDWS": 8}},
                "season_statistics": [
                    {
                        "year": 2019,
                        "season_number": 1,
                        "water_balance": {"NDWS": 8},
                        "water_balance_methodology": _method(92),
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

        methodology = result["season_statistics"]["windows"][0]["water_balance_methodology"]
        self.assertEqual(["full_window"], methodology["focal"]["applied_modes"])
        self.assertEqual(["full_window"], methodology["baseline_avg"]["applied_modes"])
        self.assertEqual(92.0, methodology["focal"]["counted_days"]["mean"])

    def test_print_report_renders_water_balance_methodology_summary(self):
        payload = {
            "focal_year": 2019,
            "baseline_period": "2018-2018",
            "source": "auto",
            "fixed_season": "03-01:05-31",
            "temperature_excluded": False,
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": {
                "windows": [
                    {
                        "window": "03-01:05-31",
                        "season_number": 1,
                        "n_baseline": 1,
                        "n_focal": 1,
                        "water_balance_methodology": {
                            "focal": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                            "baseline_avg": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                        },
                        "diff": {
                            "water_balance": {
                                "NDWS": {
                                    "focal": 8.0,
                                    "baseline_avg": 10.0,
                                    "diff": -2.0,
                                    "pct": -20.0,
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

        rendered = stdout.getvalue()
        self.assertIn("NDWS/WRSI method:", rendered)
        self.assertIn("mode=full_window", rendered)

    def test_print_report_renders_calendar_fallback_summary(self):
        payload = {
            "focal_year": 2020,
            "baseline_period": "2018-2019",
            "source": "paired",
            "precip_source": "chirps_v2",
            "temp_source": "agera_5",
            "crop_name": "maize",
            "calendar_source": "ggcmi",
            "calendar_system": "rf",
            "baseline_calendar_preset_used": True,
            "baseline_calendar_preset": {
                "calendar_source": "ggcmi_phase3",
                "crop_name": "Maize",
                "calendar_system": "rf",
                "fixed_season": "03-11:06-13",
            },
            "focal_calendar_preset_used": True,
            "focal_calendar_preset": {
                "calendar_source": "ggcmi_phase3",
                "crop_name": "Maize",
                "calendar_system": "rf",
                "fixed_season": "03-11:06-13",
            },
            "fixed_season": None,
            "temperature_excluded": False,
            "season_detection": {
                "compare_status": "ok",
                "baseline": {"status": "ok", "reasons": ["calendar_preset_fallback_applied"]},
                "focal": {"status": "ok", "reasons": ["calendar_preset_fallback_applied"]},
                "guidance": [],
            },
            "raw_climate_summary": {},
            "overall_statistics": {},
            "season_statistics": None,
            "annual_summary": {},
        }

        stdout = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = stdout
            cp.print_report(payload)
        finally:
            sys.stdout = orig_stdout

        rendered = stdout.getvalue()
        self.assertIn("Calendar req. : ggcmi | system=rf", rendered)
        self.assertIn("Baseline cal. : ggcmi_phase3 | crop=Maize | system=rf | fixed=03-11:06-13", rendered)
        self.assertIn("Focal cal.    : ggcmi_phase3 | crop=Maize | system=rf | fixed=03-11:06-13", rendered)

    def test_ensemble_aggregate_seasons_carries_methodology_summary(self):
        aggregated = ep._aggregate_seasons([
            {
                "windows": [
                    {
                        "window": "03-01:05-31",
                        "season_number": 1,
                        "water_balance_methodology": {
                            "future_avg": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                            "baseline_avg": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                        },
                        "diff": {"water_balance": {"NDWS": {"diff": -2.0, "pct": -20.0}}},
                    }
                ]
            },
            {
                "windows": [
                    {
                        "window": "03-01:05-31",
                        "season_number": 1,
                        "water_balance_methodology": {
                            "future_avg": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                            "baseline_avg": {
                                "applied_modes": ["full_window"],
                                "counted_days": {"mean": 92.0, "min": 92, "max": 92},
                            },
                        },
                        "diff": {"water_balance": {"NDWS": {"diff": -1.0, "pct": -10.0}}},
                    }
                ]
            },
        ])

        methodology = aggregated["windows"][0]["water_balance_methodology"]
        self.assertEqual(["full_window"], methodology["future_avg"]["applied_modes"])
        self.assertEqual(92.0, methodology["future_avg"]["counted_days"]["mean"])

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
