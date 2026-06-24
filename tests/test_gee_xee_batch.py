from datetime import date
import sys
import tempfile
import types
import unittest
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


_install_test_stubs()

from climate_tookit.fetch_data import fetch_gee_xee_batch_data
import climate_tookit.fetch_data.gee_xee_batch as gee_batch
from climate_tookit.fetch_data.gee_xee_batch import (
    _chunk_dates,
    _coerce_source,
    _maybe_unbounded_collection,
    _resolve_batch_workers,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateDataset
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class GeeXeeBatchTests(unittest.TestCase):
    def test_main_creates_missing_output_directory(self):
        raw_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2020-01-01"]), "precipitation": [1.2]})
        summary_df = pd.DataFrame({"site": ["Nairobi"]})
        manifest_df = pd.DataFrame({"cache_hit": [False]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "gee_batch.json"
            argv = [
                "gee_xee_batch.py",
                "--source=chirps",
                "--site=Nairobi,-1.286,36.817",
                "--start=2020-01-01",
                "--end=2020-01-01",
                f"--output={output_path}",
                "--format=json",
            ]

            with mock.patch("sys.argv", argv), mock.patch.object(
                gee_batch,
                "fetch_gee_xee_batch_data",
                return_value=(raw_df, summary_df, manifest_df),
            ):
                rc = gee_batch.main()

            self.assertEqual(0, rc)
            self.assertTrue(output_path.exists())

    def test_main_passes_workers_argument(self):
        raw_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2020-01-01"]), "precipitation": [1.2]})
        summary_df = pd.DataFrame({"site": ["Nairobi"]})
        manifest_df = pd.DataFrame({"cache_hit": [False]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "gee_batch.json"
            argv = [
                "gee_xee_batch.py",
                "--source=chirps",
                "--site=Nairobi,-1.286,36.817",
                "--start=2020-01-01",
                "--end=2020-01-01",
                "--workers=3",
                f"--output={output_path}",
                "--format=json",
            ]

            with mock.patch("sys.argv", argv), mock.patch.object(
                gee_batch,
                "fetch_gee_xee_batch_data",
                return_value=(raw_df, summary_df, manifest_df),
            ) as fetch_mock:
                rc = gee_batch.main()

            self.assertEqual(0, rc)
            self.assertEqual(3, fetch_mock.call_args.kwargs["workers"])

    def test_resolve_batch_workers_clamps_to_safe_max(self):
        requested, effective = _resolve_batch_workers(8, total_batches=10)

        self.assertEqual(8, requested)
        self.assertEqual(4, effective)

    def test_unsupported_source_raises(self):
        with self.assertRaises(ValueError):
            _coerce_source("soil_grid")

    def test_chirps_v3_daily_rnl_is_supported_source(self):
        self.assertEqual(
            ClimateDataset.chirps_v3_daily_rnl,
            _coerce_source("chirps_v3_daily_rnl"),
        )

    def test_monthly_source_uses_single_chunk_window(self):
        settings = Settings.load()
        chunks = _chunk_dates(
            getattr(settings, "terraclimate"),
            date(2000, 1, 15),
            date(2001, 5, 20),
            chunk_days=31,
        )

        self.assertEqual([(date(2000, 1, 15), date(2001, 5, 20))], chunks)

    def test_transformed_stage_uses_package_variable_mapping(self):
        raw_df = pd.DataFrame(
            {
                "site": ["Nairobi"],
                "lat": [-1.286],
                "lon": [36.817],
                "date": pd.to_datetime(["2020-01-01"]),
                "precipitation": [1.2],
            }
        )
        summary_df = pd.DataFrame({"site": ["Nairobi"]})
        manifest_df = pd.DataFrame({"cache_hit": [False]})

        with mock.patch(
            "climate_tookit.fetch_data.gee_xee_batch.run_gee_xee_batch_extraction",
            return_value=(raw_df, summary_df, manifest_df),
        ):
            data_df, returned_summary, returned_manifest = fetch_gee_xee_batch_data(
                source="chirps",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
                stage="transformed",
                verbose=False,
            )

        self.assertEqual(
            list(data_df.columns),
            ["site", "lat", "lon", "date", "precipitation"],
        )
        self.assertIs(returned_summary, summary_df)
        self.assertIs(returned_manifest, manifest_df)

    def test_fetch_gee_xee_batch_data_clips_bounded_era5_window_before_extraction(self):
        raw_df = pd.DataFrame(
            {
                "site": ["Nairobi"],
                "lat": [-1.286],
                "lon": [36.817],
                "date": pd.to_datetime(["2020-07-09"]),
                "precipitation": [1.2],
            }
        )
        summary_df = pd.DataFrame({"site": ["Nairobi"]})
        manifest_df = pd.DataFrame({"cache_hit": [False]})

        with mock.patch(
            "climate_tookit.fetch_data.gee_xee_batch.run_gee_xee_batch_extraction",
            return_value=(raw_df, summary_df, manifest_df),
        ) as extraction_mock:
            data_df, returned_summary, returned_manifest = fetch_gee_xee_batch_data(
                source="era_5",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 12, 31),
                stage="raw",
                verbose=False,
            )

        self.assertIs(data_df, raw_df)
        self.assertIs(returned_summary, summary_df)
        self.assertIs(returned_manifest, manifest_df)
        self.assertEqual(
            extraction_mock.call_args.kwargs["date_from"],
            date(2020, 1, 1),
        )
        self.assertEqual(
            extraction_mock.call_args.kwargs["date_to"],
            date(2020, 7, 9),
        )
        self.assertEqual(
            extraction_mock.call_args.kwargs["requested_date_from"],
            date(2020, 1, 1),
        )
        self.assertEqual(
            extraction_mock.call_args.kwargs["requested_date_to"],
            date(2020, 12, 31),
        )
        self.assertIn(
            "Adjusted: 2020-01-01..2020-07-09",
            extraction_mock.call_args.kwargs["coverage_warning"],
        )

    def test_fetch_gee_xee_batch_data_rejects_zero_overlap_window(self):
        with self.assertRaisesRegex(ValueError, "No overlapping dates remain after clipping"):
            fetch_gee_xee_batch_data(
                source="era_5",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 12, 1),
                date_to=date(2020, 12, 31),
                stage="raw",
                verbose=False,
            )

    def test_preprocessed_stage_does_not_fill_across_sites(self):
        raw_df = pd.DataFrame(
            {
                "site": ["A", "A", "B", "B"],
                "lat": [0.0, 0.0, 1.0, 1.0],
                "lon": [36.0, 36.0, 37.0, 37.0],
                "date": pd.to_datetime(
                    ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"]
                ),
                "maximum_temperature": [None, 20.0, 35.0, 36.0],
                "minimum_temperature": [None, 10.0, 18.0, 19.0],
            }
        )

        with mock.patch(
            "climate_tookit.fetch_data.gee_xee_batch.run_gee_xee_batch_extraction",
            return_value=(raw_df, pd.DataFrame(), pd.DataFrame()),
        ):
            data_df, _, _ = fetch_gee_xee_batch_data(
                source="chirts",
                sites=[("A", 0.0, 36.0), ("B", 1.0, 37.0)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                stage="preprocessed",
                verbose=False,
            )

        site_a = data_df.loc[data_df["site"] == "A"].sort_values("date").reset_index(drop=True)
        site_b = data_df.loc[data_df["site"] == "B"].sort_values("date").reset_index(drop=True)

        self.assertEqual(site_a.loc[0, "max_temperature"], 20.0)
        self.assertEqual(site_a.loc[0, "min_temperature"], 10.0)
        self.assertEqual(site_b.loc[0, "max_temperature"], 35.0)
        self.assertEqual(site_b.loc[0, "min_temperature"], 18.0)

    def test_cache_paths_default_when_cache_dir_is_none(self):
        from climate_tookit.fetch_data.gee_xee_batch import _cache_paths

        data_path, manifest_path = _cache_paths(
            cache_dir=None,
            source=ClimateDataset.chirps,
            site=type("SiteStub", (), {"name": "Nairobi Hub", "lat": -1.286, "lon": 36.817})(),
            start=date(2020, 1, 1),
            end=date(2020, 1, 10),
            bands=["precipitation"],
        )

        self.assertIn("outputs/cache/gee_xee_batch", str(data_path))
        self.assertIn("nairobi-hub_lat_m1p2860_lon_36p8170", str(data_path))
        self.assertTrue(str(manifest_path).endswith(".manifest.json"))

    def test_empty_bounds_filtered_collection_falls_back_to_date_only(self):
        class FakeSized:
            def __init__(self, value):
                self.value = value

            def getInfo(self):
                return self.value

        class FakeCollection:
            def __init__(self, label):
                self.label = label

            def size(self):
                return FakeSized(0 if self.label == "bounded" else 5)

            def select(self, bands):
                return FakeCollection(f"{self.label}|select:{','.join(bands)}")

            def filterDate(self, start, end):
                return self

        class FakeImageCollectionFactory:
            def __call__(self, image_name):
                return FakeCollection(f"fallback:{image_name}")

        class FakeEe:
            ImageCollection = FakeImageCollectionFactory()

        bounded = FakeCollection("bounded")
        fallback = _maybe_unbounded_collection(
            FakeEe,
            bounded,
            image_name="UCSB-CHG/CHIRTS/DAILY",
            start="2020-01-01",
            end="2020-01-11",
            point=None,
            bands=["maximum_temperature", "minimum_temperature"],
            verbose_label="Daily GEE collection",
        )

        self.assertIn("fallback:UCSB-CHG/CHIRTS/DAILY", fallback.label)

    def test_empty_bounded_and_unbounded_collection_raises_clear_error(self):
        class FakeSized:
            def __init__(self, value):
                self.value = value

            def getInfo(self):
                return self.value

        class FakeCollection:
            def size(self):
                return FakeSized(0)

            def select(self, bands):
                return self

            def filterDate(self, start, end):
                return self

        class FakeImageCollectionFactory:
            def __call__(self, image_name):
                return FakeCollection()

        class FakeEe:
            ImageCollection = FakeImageCollectionFactory()

        with self.assertRaises(ValueError) as ctx:
            _maybe_unbounded_collection(
                FakeEe,
                FakeCollection(),
                image_name="UCSB-CHG/CHIRTS/DAILY",
                start="2020-01-01",
                end="2020-01-11",
                point=None,
                bands=["maximum_temperature", "minimum_temperature"],
                verbose_label="Daily GEE collection",
            )

        self.assertIn("No data available from UCSB-CHG/CHIRTS/DAILY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
