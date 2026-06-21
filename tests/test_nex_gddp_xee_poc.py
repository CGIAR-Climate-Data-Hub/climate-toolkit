from datetime import date
from io import StringIO
import tempfile
from pathlib import Path
import sys
import types
import unittest
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


_install_test_stubs()

from climate_tookit.fetch_data.source_data.sources import nex_gddp, nex_gddp_xee
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class NexGddpXeePocTests(unittest.TestCase):
    def test_normalize_scenario_accepts_catalog_aliases(self):
        self.assertEqual(nex_gddp_xee._normalize_scenario("SSP3-7.0"), "ssp370")
        self.assertEqual(nex_gddp_xee._normalize_scenario("ssp2-4.5"), "ssp245")
        self.assertEqual(nex_gddp_xee._normalize_scenario(None), "ssp245")

    def test_validate_period_rejects_historical_after_2014(self):
        with self.assertRaises(ValueError):
            nex_gddp_xee._validate_period_against_scenario(
                "historical",
                date(2014, 1, 1),
                date(2015, 1, 1),
            )

    def test_validate_period_rejects_future_before_2015(self):
        with self.assertRaises(ValueError):
            nex_gddp_xee._validate_period_against_scenario(
                "ssp245",
                date(2014, 12, 31),
                date(2015, 12, 31),
            )

    def test_manual_point_grid_is_single_pixel(self):
        grid = nex_gddp_xee._manual_point_grid(lon=36.817, lat=-1.286, pixel_size_meters=5566)
        self.assertEqual(grid["crs"], "EPSG:4326")
        self.assertEqual(grid["shape_2d"], (1, 1))
        self.assertEqual(len(grid["crs_transform"]), 6)

    def test_africa_coordinate_detection(self):
        self.assertTrue(nex_gddp_xee._is_africa_coordinate(-1.286, 36.817))
        self.assertFalse(nex_gddp_xee._is_africa_coordinate(-13.5319, -71.9675))

    def test_horn_of_africa_detection(self):
        self.assertTrue(nex_gddp_xee._is_horn_of_africa_coordinate(-1.286, 36.817))
        self.assertFalse(nex_gddp_xee._is_horn_of_africa_coordinate(12.639, -8.002))

    def test_resolve_dataset_version_prefers_1_1(self):
        class FakeHistogram:
            def getInfo(self):
                return {"1.1": 5, "1.2": 7}

        class FakeCollection:
            def aggregate_histogram(self, *args, **kwargs):
                return FakeHistogram()

        selected = nex_gddp_xee._resolve_dataset_version(FakeCollection())
        self.assertEqual(selected, nex_gddp_xee.DEFAULT_DATASET_VERSION)

    def test_resolve_dataset_version_falls_back_to_highest_available(self):
        class FakeHistogram:
            def getInfo(self):
                return {"1.1": 5, "null": 2}

        class FakeCollection:
            def aggregate_histogram(self, *args, **kwargs):
                return FakeHistogram()

        selected = nex_gddp_xee._resolve_dataset_version(FakeCollection())
        self.assertEqual(selected, "1.1")

    def test_coerce_version_filter_value_uses_float_for_numeric_versions(self):
        self.assertEqual(nex_gddp_xee._coerce_version_filter_value("1.2"), 1.2)

    def test_warn_on_suspicious_precipitation_logs_absolute_rainbomb_warning_for_arid_series(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2050-01-01", periods=10, freq="D"),
                "pr": [0.0, 0.0, 0.2, 0.0, 0.4, 0.0, 0.8, 0.0, 650.0, 0.0],
            }
        )

        with self.assertLogs(nex_gddp_xee.logger, level="WARNING") as captured:
            nex_gddp_xee._warn_on_suspicious_precipitation(
                frame,
                model="MRI-ESM2-0",
                scenario="ssp245",
            )

        message = "\n".join(captured.output)
        self.assertIn("rainbomb", message.lower())
        self.assertIn("650.00 mm/day", message)
        self.assertIn("MRI-ESM2-0", message)

    def test_warn_on_suspicious_precipitation_ignores_absolute_spike_without_arid_signature(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2050-01-01", periods=10, freq="D"),
                "pr": [20.0, 35.0, 28.0, 44.0, 60.0, 22.0, 31.0, 27.0, 650.0, 18.0],
            }
        )

        with mock.patch.object(nex_gddp_xee.logger, "warning") as warning_mock:
            nex_gddp_xee._warn_on_suspicious_precipitation(
                frame,
                model="MRI-ESM2-0",
                scenario="ssp245",
            )

        warning_mock.assert_not_called()

    def test_warn_on_suspicious_precipitation_logs_arid_ratio_rainbomb_warning(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2050-01-01", periods=10, freq="D"),
                "pr": [0.0, 0.0, 0.2, 0.0, 0.4, 0.0, 0.8, 0.0, 75.0, 0.0],
            }
        )

        with self.assertLogs(nex_gddp_xee.logger, level="WARNING") as captured:
            nex_gddp_xee._warn_on_suspicious_precipitation(
                frame,
                model="MRI-ESM2-0",
                scenario="ssp245",
            )

        message = "\n".join(captured.output)
        self.assertIn("arid-zone rainbomb", message.lower())
        self.assertIn("75.00 mm/day", message)
        self.assertIn("ratio", message.lower())

    def test_warn_on_suspicious_precipitation_ignores_normal_precip(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2050-01-01", periods=5, freq="D"),
                "pr": [0.0, 3.0, 8.0, 12.0, 6.0],
            }
        )

        with mock.patch.object(nex_gddp_xee.logger, "warning") as warning_mock:
            nex_gddp_xee._warn_on_suspicious_precipitation(
                frame,
                model="MRI-ESM2-0",
                scenario="ssp245",
                threshold_mm_day=500.0,
            )

        warning_mock.assert_not_called()

    def test_africa_default_ensemble_excludes_canesm5(self):
        models = nex_gddp.default_ensemble_models_for_location((-1.286, 36.817))
        self.assertNotIn("CanESM5", models)
        self.assertNotIn("INM-CM4-8", models)
        self.assertNotIn("INM-CM5-0", models)
        self.assertNotIn("KACE-1-0-G", models)
        self.assertNotIn("TaiESM1", models)
        self.assertEqual(len(models), len(nex_gddp.AFRICA_DEFAULT_ENSEMBLE_MODELS))
        self.assertEqual(len(models), 13)

    def test_non_africa_default_ensemble_keeps_canesm5(self):
        models = nex_gddp.default_ensemble_models_for_location((-13.5319, -71.9675))
        self.assertIn("CanESM5", models)
        self.assertEqual(models, nex_gddp.AVAILABLE_MODELS)

    def test_africa_policy_metadata_marks_horn_context_and_paradox_caution(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location((-1.286, 36.817))
        self.assertEqual(policy["policy_id"], "AFR-13")
        self.assertEqual(policy["regional_context"], "AFR-EAF")
        self.assertTrue(policy["east_african_paradox_caution"])
        self.assertEqual(policy["realization"], "r1i1p1f1")
        self.assertIn("CanESM5", policy["excluded_models"])

    def test_non_africa_policy_metadata_uses_full_pool(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location((-13.5319, -71.9675))
        self.assertEqual(policy["policy_id"], "FULL-18")
        self.assertIsNone(policy["regional_context"])
        self.assertFalse(policy["east_african_paradox_caution"])
        self.assertEqual(policy["models"], nex_gddp.AVAILABLE_MODELS)

    def test_africa_eaf_regional_fast_profile_uses_provisional_shortlist(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (-1.286, 36.817),
            policy_profile="regional_fast",
        )
        self.assertEqual(policy["policy_id"], "AFR-EAF-FAST-PROVISIONAL-V2")
        self.assertEqual(policy["regional_context"], "AFR-EAF")
        self.assertEqual(policy["models"], nex_gddp.AFR_EAF_FAST_PROVISIONAL_MODELS)
        self.assertEqual(policy["comparability_class"], "strict_proxy")
        self.assertEqual(policy["evidence_confidence"], "medium")
        self.assertEqual(policy["warning_level"], "warning")
        self.assertIn("screening", policy["runtime_disclaimer"].lower())

    def test_waf_regional_fast_profile_uses_warning_watchlist(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (5.56, -0.20),
            policy_profile="regional_fast",
        )
        self.assertEqual(policy["policy_id"], "AFR-WAF-FAST-WARNING")
        self.assertEqual(policy["regional_context"], "AFR-WAF")
        self.assertEqual(policy["models"], nex_gddp.AFR_WAF_FAST_WARNING_MODELS)
        self.assertEqual(policy["evidence_confidence"], "low")
        self.assertEqual(policy["warning_level"], "warning")

    def test_andes_regional_fast_profile_uses_warning_watchlist(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (-13.5319, -71.9675),
            policy_profile="regional_fast",
        )
        self.assertEqual(policy["policy_id"], "ANDES-FAST-WARNING")
        self.assertEqual(policy["regional_context"], "ANDES")
        self.assertEqual(policy["models"], nex_gddp.ANDES_FAST_WARNING_MODELS)
        self.assertEqual(policy["evidence_confidence"], "low")
        self.assertEqual(policy["warning_level"], "warning")

    def test_non_codified_regional_fast_profile_still_falls_back_with_note(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (-2.0, 20.0),
            policy_profile="regional_fast",
        )
        self.assertEqual(policy["policy_id"], "AFR-13")
        self.assertTrue(policy["policy_fallback"])
        self.assertEqual(policy["requested_policy_profile"], "regional_fast")
        self.assertIn("no source-backed fast shortlist", " ".join(policy["notes"]))

    def test_policy_runtime_messages_include_disclaimer_and_memo(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (-1.286, 36.817),
            policy_profile="regional_fast",
        )
        lines = nex_gddp.policy_runtime_messages(policy)
        self.assertTrue(any("provisional" in line.lower() for line in lines))
        self.assertTrue(any("decision memo" in line.lower() for line in lines))

    def test_user_supplied_models_preserve_manual_override_but_keep_africa_context(self):
        policy = nex_gddp.resolve_ensemble_policy_for_location(
            (-1.286, 36.817),
            models=["MRI-ESM2-0", "EC-Earth3-Veg-LR"],
        )
        self.assertEqual(policy["policy_id"], "USER_SUPPLIED")
        self.assertEqual(policy["regional_context"], "AFR-EAF")
        self.assertEqual(policy["models"], ["MRI-ESM2-0", "EC-Earth3-Veg-LR"])

    def test_africa_subregion_classification_examples(self):
        self.assertEqual(nex_gddp.africa_subregion_for_coordinate(-1.286, 36.817), "AFR-EAF")
        self.assertEqual(nex_gddp.africa_subregion_for_coordinate(5.56, -0.20), "AFR-WAF")
        self.assertEqual(nex_gddp.africa_subregion_for_coordinate(-18.8792, 47.5079), "AFR-MDG")

    def test_available_models_matches_documented_nex_18_pool(self):
        self.assertEqual(len(nex_gddp.AVAILABLE_MODELS), 18)
        self.assertIn("IPSL-CM6A-LR", nex_gddp.AVAILABLE_MODELS)
        self.assertIn("MPI-ESM1-2-HR", nex_gddp.AVAILABLE_MODELS)

    def test_retryable_error_detection(self):
        self.assertTrue(nex_gddp_xee._is_retryable_ee_error(RuntimeError("429 Too Many Requests")))
        self.assertTrue(nex_gddp_xee._is_retryable_ee_error(RuntimeError("Computation timed out")))
        self.assertFalse(nex_gddp_xee._is_retryable_ee_error(RuntimeError("unsupported scenario")))

    def test_chunk_overflow_error_detection(self):
        self.assertTrue(nex_gddp_xee._is_chunk_overflow_error(RuntimeError("User memory limit exceeded")))
        self.assertTrue(nex_gddp_xee._is_chunk_overflow_error(RuntimeError("Collection query aborted after accumulating over 5000 elements")))
        self.assertFalse(nex_gddp_xee._is_chunk_overflow_error(RuntimeError("permission denied")))

    def test_progress_bar_reaches_full_width(self):
        self.assertEqual(nex_gddp_xee._progress_bar(5, 5, width=5), "[#####]")

    def test_log_progress_prints_cleanly_without_info_logger_prefix(self):
        downloader = nex_gddp_xee.DownloadData(
            variables=[ClimateVariable.precipitation],
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2050, 1, 1),
            date_to_utc=date(2050, 1, 1),
            settings=Settings.load(),
            source=ClimateDataset.nex_gddp,
            model="MRI-ESM2-0",
            scenario="ssp245",
            verbose=True,
        )

        stdout = StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch.object(
            nex_gddp_xee.logger,
            "debug",
        ) as debug_mock:
            downloader._log_progress("chunk ready")

        self.assertEqual("chunk ready\n", stdout.getvalue())
        debug_mock.assert_called_once_with("chunk ready")

    def test_cache_coord_normalization_treats_equivalent_precision_as_same_fragment(self):
        a = nex_gddp_xee._safe_coord_fragment(31.111111111111)
        b = nex_gddp_xee._safe_coord_fragment(31.11111)
        self.assertEqual(a, b)

    def test_cache_manifest_roundtrip_requires_complete_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2050, 1, 1),
                date_to_utc=date(2050, 1, 3),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="ssp245",
                cache_dir=tmpdir,
                verbose=False,
            )

            frame = pd.DataFrame(
                {
                    "date": pd.date_range("2050-01-01", "2050-01-03", freq="D"),
                    "pr": [1.0, 2.0, 3.0],
                }
            )
            manifest = downloader._build_manifest(
                frame,
                date(2050, 1, 1),
                date(2050, 1, 3),
                "1.1",
            )
            data_path, manifest_path = downloader._cache_paths(date(2050, 1, 1), date(2050, 1, 3))
            downloader._write_chunk_cache(frame, manifest, data_path, manifest_path)

            loaded_frame, loaded_manifest = downloader._load_valid_cached_chunk(
                date(2050, 1, 1),
                date(2050, 1, 3),
            )
            self.assertIsNotNone(loaded_frame)
            self.assertIsNotNone(loaded_manifest)
            self.assertEqual(len(loaded_frame), 3)
            self.assertTrue(loaded_manifest["integrity"]["complete"])

    def test_cache_manifest_rejects_incomplete_chunk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2050, 1, 1),
                date_to_utc=date(2050, 1, 3),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="ssp245",
                cache_dir=tmpdir,
                verbose=False,
            )

            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(["2050-01-01", "2050-01-03"]),
                    "pr": [1.0, 3.0],
                }
            )
            manifest = downloader._build_manifest(
                frame,
                date(2050, 1, 1),
                date(2050, 1, 3),
                "1.1",
            )
            data_path, manifest_path = downloader._cache_paths(date(2050, 1, 1), date(2050, 1, 3))
            downloader._write_chunk_cache(frame, manifest, data_path, manifest_path)

            loaded_frame, loaded_manifest = downloader._load_valid_cached_chunk(
                date(2050, 1, 1),
                date(2050, 1, 3),
            )
            self.assertIsNone(loaded_frame)
            self.assertIsNone(loaded_manifest)

    def test_download_variables_reuses_annual_cache_for_subwindow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            annual = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2041, 1, 1),
                date_to_utc=date(2041, 12, 31),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="ssp245",
                cache_dir=tmpdir,
                verbose=False,
            )
            annual_frame = pd.DataFrame(
                {
                    "date": pd.date_range("2041-01-01", "2041-12-31", freq="D"),
                    "pr": range(365),
                }
            )
            annual_manifest = annual._build_manifest(
                annual_frame,
                date(2041, 1, 1),
                date(2041, 12, 31),
                "1.1",
            )
            data_path, manifest_path = annual._cache_paths(date(2041, 1, 1), date(2041, 12, 31))
            annual._write_chunk_cache(annual_frame, annual_manifest, data_path, manifest_path)

            seasonal = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2041, 3, 1),
                date_to_utc=date(2041, 5, 31),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="ssp245",
                cache_dir=tmpdir,
                verbose=False,
            )

            with mock.patch.object(
                seasonal,
                "_fetch_chunk_with_resilience",
                side_effect=AssertionError("should not fetch when annual cache covers window"),
            ):
                frame = seasonal.download_variables()

            self.assertEqual(92, len(frame))
            self.assertEqual(pd.Timestamp("2041-03-01"), frame["date"].min())
            self.assertEqual(pd.Timestamp("2041-05-31"), frame["date"].max())

    def test_download_variables_reuses_covering_chunk_cache_for_subwindow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            covering = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(1992, 1, 1),
                date_to_utc=date(1992, 12, 30),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="historical",
                cache_dir=tmpdir,
                verbose=False,
            )
            covering_frame = pd.DataFrame(
                {
                    "date": pd.date_range("1992-01-01", "1992-12-30", freq="D"),
                    "pr": range(365),
                }
            )
            covering_manifest = covering._build_manifest(
                covering_frame,
                date(1992, 1, 1),
                date(1992, 12, 30),
                "1.1",
            )
            data_path, manifest_path = covering._cache_paths(date(1992, 1, 1), date(1992, 12, 30))
            covering._write_chunk_cache(covering_frame, covering_manifest, data_path, manifest_path)

            seasonal = nex_gddp_xee.DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(1992, 1, 1),
                date_to_utc=date(1992, 6, 30),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="historical",
                cache_dir=tmpdir,
                verbose=False,
            )

            with mock.patch.object(
                seasonal,
                "_fetch_chunk_with_resilience",
                side_effect=AssertionError("should not fetch when covering cache exists"),
            ):
                frame = seasonal.download_variables()

            self.assertEqual(182, len(frame))
            self.assertEqual(pd.Timestamp("1992-01-01"), frame["date"].min())
            self.assertEqual(pd.Timestamp("1992-06-30"), frame["date"].max())


if __name__ == "__main__":
    unittest.main()
