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

from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    SoilVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class SoilGridCacheTests(unittest.TestCase):
    def test_soil_grid_snapshot_written_then_reused_for_same_site(self):
        settings = Settings.load()
        remote_calls = []

        def fake_get_gee_data_static(self, image_name, location_coord, scale=None, **kwargs):
            remote_calls.append(image_name)
            if "wv0033" in image_name:
                return pd.DataFrame([{"wv0033_0-5cm_mean": 0.34}])
            if "wv1500" in image_name:
                return pd.DataFrame([{"wv1500_0-5cm_mean": 0.14}])
            if "cfvo_mean" in image_name:
                return pd.DataFrame([{"cfvo_0-5cm_mean": 0.08}])
            if "silt_mean" in image_name:
                return pd.DataFrame([{"silt_0-5cm_mean": 41.0}])
            if "cec_mean" in image_name:
                return pd.DataFrame([{"cec_0-5cm_mean": 18.0}])
            return pd.DataFrame([{"b0": 12.0}])

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch(
            "climate_tookit.fetch_data.source_data.sources.gee.DownloadData.get_gee_data_static",
            new=fake_get_gee_data_static,
        ):
            first = SourceData(
                location_coord=(-1.2860001, 36.8170001),
                variables=[SoilVariable.bulk_density, SoilVariable.clay_content],
                source=ClimateDataset.soil_grid,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=False,
            ).download()

            self.assertIn("bulk_density", first.columns)
            self.assertIn("clay_content", first.columns)
            self.assertGreater(len(remote_calls), 0)

            cache_root = Path(tmpdir) / "v1" / "lat_m1p2860_lon_36p8170"
            self.assertTrue((cache_root / "soil_grid_snapshot.json").exists())
            self.assertTrue((cache_root / "soil_grid_snapshot.json.manifest.json").exists())

            remote_calls_before = len(remote_calls)

            second = SourceData(
                location_coord=(-1.28600009, 36.81700009),
                variables=[SoilVariable.bulk_density],
                source=ClimateDataset.soil_grid,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=False,
            ).download()

            self.assertEqual(remote_calls_before, len(remote_calls))
            self.assertIn("bulk_density", second.columns)

    def test_soil_grid_refresh_cache_forces_refetch(self):
        settings = Settings.load()
        remote_calls = []

        def fake_get_gee_data_static(self, image_name, location_coord, scale=None, **kwargs):
            remote_calls.append(image_name)
            if "wv0033" in image_name:
                return pd.DataFrame([{"wv0033_0-5cm_mean": 0.34}])
            if "wv1500" in image_name:
                return pd.DataFrame([{"wv1500_0-5cm_mean": 0.14}])
            if "cfvo_mean" in image_name:
                return pd.DataFrame([{"cfvo_0-5cm_mean": 0.08}])
            if "silt_mean" in image_name:
                return pd.DataFrame([{"silt_0-5cm_mean": 41.0}])
            if "cec_mean" in image_name:
                return pd.DataFrame([{"cec_0-5cm_mean": 18.0}])
            return pd.DataFrame([{"b0": 12.0}])

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch(
            "climate_tookit.fetch_data.source_data.sources.gee.DownloadData.get_gee_data_static",
            new=fake_get_gee_data_static,
        ):
            SourceData(
                location_coord=(-1.286, 36.817),
                variables=[SoilVariable.bulk_density],
                source=ClimateDataset.soil_grid,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=False,
            ).download()

            first_call_count = len(remote_calls)

            SourceData(
                location_coord=(-1.286, 36.817),
                variables=[SoilVariable.bulk_density],
                source=ClimateDataset.soil_grid,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=True,
            ).download()

            self.assertGreater(len(remote_calls), first_call_count)

    def test_hwsd_root_depth_snapshot_written_then_reused_for_same_site(self):
        settings = Settings.load()
        remote_calls = []

        def fake_get_gee_data_static(self, image_name, location_coord, scale=None, **kwargs):
            remote_calls.append(image_name)
            return pd.DataFrame(
                [
                    {
                        "ROOT_DEPTH": 150,
                        "AWC": 120,
                        "DRAINAGE": 4,
                        "BULK_DENSITY": 1.35,
                    }
                ]
            )

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch(
            "climate_tookit.fetch_data.source_data.sources.gee.DownloadData.get_gee_data_static",
            new=fake_get_gee_data_static,
        ):
            first = SourceData(
                location_coord=(-1.286, 36.817),
                variables=[SoilVariable.root_depth],
                source=ClimateDataset.hwsd,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=False,
            ).download()

            self.assertIn("ROOT_DEPTH", first.columns)
            self.assertEqual(1, len(remote_calls))

            cache_root = Path(tmpdir) / "v1" / "lat_m1p2860_lon_36p8170"
            self.assertTrue((cache_root / "static_snapshot.json").exists())
            self.assertTrue((cache_root / "static_snapshot.json.manifest.json").exists())

            second = SourceData(
                location_coord=(-1.28600001, 36.81700001),
                variables=[SoilVariable.root_depth],
                source=ClimateDataset.hwsd,
                date_from_utc=date(2000, 1, 1),
                date_to_utc=date(2000, 1, 1),
                settings=settings,
                cache_dir=tmpdir,
                refresh_cache=False,
            ).download()

            self.assertEqual(1, len(remote_calls))
            self.assertIn("ROOT_DEPTH", second.columns)


if __name__ == "__main__":
    unittest.main()
