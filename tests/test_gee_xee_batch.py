from datetime import date
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

from climate_tookit.fetch_data import fetch_gee_xee_batch_data
from climate_tookit.fetch_data.gee_xee_batch import (
    _chunk_dates,
    _coerce_source,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateDataset
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class GeeXeeBatchTests(unittest.TestCase):
    def test_unsupported_source_raises(self):
        with self.assertRaises(ValueError):
            _coerce_source("soil_grid")

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
        self.assertTrue(str(manifest_path).endswith(".manifest.json"))


if __name__ == "__main__":
    unittest.main()
