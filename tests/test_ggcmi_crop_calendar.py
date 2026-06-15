import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from climate_tookit.crop_calendar import ggcmi
from climate_tookit.crop_calendar.registry import get_crop_support, normalize_crop_name


class CropRegistryTests(unittest.TestCase):
    def test_normalize_aliases(self):
        self.assertEqual("Groundnuts", normalize_crop_name("peanut", require_calendar=True))
        self.assertEqual("Spring Wheat", normalize_crop_name("spring_wheat", require_calendar=True))

    def test_unknown_crop_raises(self):
        with self.assertRaises(ValueError):
            normalize_crop_name("banana")

    def test_support_flags_are_distinct(self):
        cotton = get_crop_support("cotton")
        self.assertTrue(cotton.calendar_supported)
        self.assertFalse(cotton.hazard_thresholds_supported)
        self.assertFalse(cotton.water_balance_params_supported)


class GGCMIPointExtractionTests(unittest.TestCase):
    def _write_asset(self, tmpdir: Path):
        df = pd.DataFrame(
            [
                {
                    "crop_code": "mai",
                    "crop_name": "Maize",
                    "system": "rf",
                    "season_id": 1,
                    "is_multi_season_crop": False,
                    "lat": -1.25,
                    "lon": 36.75,
                    "planting_day": 60,
                    "maturity_day": 151,
                    "growing_season_length_days": 91,
                    "data_source_used_code": 1,
                    "data_source_used_label": "MIRCA",
                    "season_area_fraction": pd.NA,
                    "calendar_version": "1.01",
                    "source_record_url": "https://zenodo.org/records/5062513",
                },
                {
                    "crop_code": "mai",
                    "crop_name": "Maize",
                    "system": "ir",
                    "season_id": 1,
                    "is_multi_season_crop": False,
                    "lat": -1.25,
                    "lon": 36.75,
                    "planting_day": 55,
                    "maturity_day": 145,
                    "growing_season_length_days": 90,
                    "data_source_used_code": 2,
                    "data_source_used_label": "SAGE",
                    "season_area_fraction": pd.NA,
                    "calendar_version": "1.01",
                    "source_record_url": "https://zenodo.org/records/5062513",
                },
                {
                    "crop_code": "ri1",
                    "crop_name": "Rice",
                    "system": "rf",
                    "season_id": 1,
                    "is_multi_season_crop": True,
                    "lat": -1.25,
                    "lon": 36.75,
                    "planting_day": 90,
                    "maturity_day": 180,
                    "growing_season_length_days": 90,
                    "data_source_used_code": 4,
                    "data_source_used_label": "RiceAtlas",
                    "season_area_fraction": 0.7,
                    "calendar_version": "1.01",
                    "source_record_url": "https://zenodo.org/records/5062513",
                },
                {
                    "crop_code": "ri2",
                    "crop_name": "Rice",
                    "system": "rf",
                    "season_id": 2,
                    "is_multi_season_crop": True,
                    "lat": -1.25,
                    "lon": 36.75,
                    "planting_day": 250,
                    "maturity_day": 330,
                    "growing_season_length_days": 80,
                    "data_source_used_code": 4,
                    "data_source_used_label": "RiceAtlas",
                    "season_area_fraction": 0.3,
                    "calendar_version": "1.01",
                    "source_record_url": "https://zenodo.org/records/5062513",
                },
                {
                    "crop_code": "mai",
                    "crop_name": "Maize",
                    "system": "rf",
                    "season_id": 1,
                    "is_multi_season_crop": False,
                    "lat": 10.0,
                    "lon": 10.0,
                    "planting_day": 1,
                    "maturity_day": 90,
                    "growing_season_length_days": 89,
                    "data_source_used_code": 1,
                    "data_source_used_label": "MIRCA",
                    "season_area_fraction": pd.NA,
                    "calendar_version": "1.01",
                    "source_record_url": "https://zenodo.org/records/5062513",
                },
            ]
        )
        parquet_path = tmpdir / "crop_calendar.parquet"
        manifest_path = tmpdir / "crop_calendar_manifest.json"
        df.to_parquet(parquet_path, index=False)
        manifest_path.write_text(json.dumps({"dataset": "test"}), encoding="utf-8")
        return parquet_path, manifest_path

    def test_extract_point_calendar_returns_nearest_grid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path, _ = self._write_asset(Path(tmp))
            result = ggcmi.extract_point_calendar(-1.286, 36.817, "maize", path=parquet_path)
            self.assertEqual(["ir", "rf"], result["system"].tolist())
            self.assertTrue((result["matched_lat"] == -1.25).all())
            self.assertTrue((result["matched_lon"] == 36.75).all())
            self.assertEqual(["02-24:05-25", "03-01:05-31"], result["fixed_season_token"].tolist())

    def test_extract_point_calendar_preserves_rice_seasons_and_fractions(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path, _ = self._write_asset(Path(tmp))
            result = ggcmi.extract_point_calendar(-1.286, 36.817, "rice", system="rf", path=parquet_path)
            self.assertEqual([1, 2], result["season_id"].tolist())
            self.assertEqual([0.7, 0.3], [round(v, 1) for v in result["season_area_fraction"].tolist()])

    def test_build_fixed_season_tokens(self):
        frame = pd.DataFrame(
            [
                {"system": "rf", "season_id": 2, "planting_day": 250, "maturity_day": 330},
                {"system": "rf", "season_id": 1, "planting_day": 90, "maturity_day": 180},
            ]
        )
        self.assertEqual(
            ["03-31:06-29", "09-07:11-26"],
            ggcmi.build_fixed_season_tokens(frame),
        )

    def test_resolve_calendar_preset_deduplicates_both_systems(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path, _ = self._write_asset(Path(tmp))
            preset = ggcmi.resolve_calendar_preset(
                -1.286,
                36.817,
                "maize",
                system="both",
                path=parquet_path,
            )
            self.assertEqual("02-24:05-25,03-01:05-31", preset["fixed_season"])
            self.assertEqual(["ir", "rf"], preset["systems_included"])

    def test_resolve_calendar_preset_rejects_more_than_two_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path, _ = self._write_asset(Path(tmp))
            extra = pd.DataFrame(
                [
                    {
                        "crop_code": "ri1",
                        "crop_name": "Rice",
                        "system": "rf",
                        "season_id": 1,
                        "is_multi_season_crop": True,
                        "lat": -1.25,
                        "lon": 36.75,
                        "planting_day": 220,
                        "maturity_day": 300,
                        "growing_season_length_days": 80,
                        "data_source_used_code": 4,
                        "data_source_used_label": "RiceAtlas",
                        "season_area_fraction": 0.5,
                        "calendar_version": "1.01",
                        "source_record_url": "https://zenodo.org/records/5062513",
                    },
                    {
                        "crop_code": "ri2",
                        "crop_name": "Rice",
                        "system": "rf",
                        "season_id": 2,
                        "is_multi_season_crop": True,
                        "lat": -1.25,
                        "lon": 36.75,
                        "planting_day": 320,
                        "maturity_day": 30,
                        "growing_season_length_days": 75,
                        "data_source_used_code": 4,
                        "data_source_used_label": "RiceAtlas",
                        "season_area_fraction": 0.5,
                        "calendar_version": "1.01",
                        "source_record_url": "https://zenodo.org/records/5062513",
                    },
                    {
                        "crop_code": "ri1",
                        "crop_name": "Rice",
                        "system": "ir",
                        "season_id": 1,
                        "is_multi_season_crop": True,
                        "lat": -1.25,
                        "lon": 36.75,
                        "planting_day": 10,
                        "maturity_day": 60,
                        "growing_season_length_days": 50,
                        "data_source_used_code": 4,
                        "data_source_used_label": "RiceAtlas",
                        "season_area_fraction": 0.4,
                        "calendar_version": "1.01",
                        "source_record_url": "https://zenodo.org/records/5062513",
                    },
                    {
                        "crop_code": "ri2",
                        "crop_name": "Rice",
                        "system": "ir",
                        "season_id": 2,
                        "is_multi_season_crop": True,
                        "lat": -1.25,
                        "lon": 36.75,
                        "planting_day": 120,
                        "maturity_day": 200,
                        "growing_season_length_days": 80,
                        "data_source_used_code": 4,
                        "data_source_used_label": "RiceAtlas",
                        "season_area_fraction": 0.6,
                        "calendar_version": "1.01",
                        "source_record_url": "https://zenodo.org/records/5062513",
                    },
                ]
            )
            df = pd.read_parquet(parquet_path)
            df = df[df["crop_name"] != "Rice"]
            df = pd.concat([df, extra], ignore_index=True)
            df.to_parquet(parquet_path, index=False)
            with self.assertRaises(ValueError):
                ggcmi.resolve_calendar_preset(
                    -1.286,
                    36.817,
                    "rice",
                    system="both",
                    path=parquet_path,
                )


if __name__ == "__main__":
    unittest.main()
