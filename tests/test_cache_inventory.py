import json
import tempfile
import unittest
from pathlib import Path

from climate_tookit.fetch_data.cache_inventory import (
    cache_dedup_audit,
    cache_inventory,
    cache_summary,
)


class CacheInventoryTests(unittest.TestCase):
    def _write_manifest(self, data_path: Path, payload: dict) -> None:
        data_path.write_text("[]", encoding="utf-8")
        data_path.with_name(f"{data_path.name}.manifest.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_inventory_lists_single_site_xee_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "outputs" / "cache" / "nex_gddp_xee" / "v1" / "ssp245" / "MRI-ESM2-0" / "lat_m1p2860_lon_36p8170"
            root.mkdir(parents=True)
            data_path = root / "2050-01-01_2050-01-03_pr-tasmax-tasmin.json"
            self._write_manifest(
                data_path,
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_xee",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "selected_version": "1.1",
                    "lat": -1.286,
                    "lon": 36.817,
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-03",
                    "bands": ["pr", "tasmax", "tasmin"],
                    "integrity": {
                        "complete": True,
                        "row_count": 3,
                        "expected_rows": 3,
                    },
                },
            )

            frame = cache_inventory(cache_root=Path(tmpdir) / "outputs" / "cache")

        self.assertEqual(1, len(frame))
        self.assertEqual("nex_gddp_xee", frame.loc[0, "dataset"])
        self.assertEqual(-1.286, frame.loc[0, "lat"])
        self.assertEqual(36.817, frame.loc[0, "lon"])
        self.assertEqual(1, frame.loc[0, "site_count"])

    def test_inventory_expands_batch_manifest_to_per_site_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "outputs" / "cache" / "nex_gddp_batch" / "v1" / "ssp245" / "MRI-ESM2-0"
            root.mkdir(parents=True)
            data_path = root / "2050-01-01_2050-01-07_nairobi_to_cusco_sites2_hash_pr-tasmax-tasmin.json"
            self._write_manifest(
                data_path,
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_batch",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "selected_version": "1.1",
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-07",
                    "site_count": 2,
                    "sites": [
                        {"name": "Nairobi", "lat": -1.286, "lon": 36.817},
                        {"name": "Cusco", "lat": -13.5319, "lon": -71.9675},
                    ],
                    "bands": ["pr", "tasmax", "tasmin"],
                    "integrity": {
                        "complete": True,
                        "row_count": 14,
                        "expected_rows": 14,
                    },
                },
            )

            frame = cache_inventory(cache_root=Path(tmpdir) / "outputs" / "cache")

        self.assertEqual(2, len(frame))
        self.assertEqual({"Nairobi", "Cusco"}, set(frame["site_name"]))
        self.assertTrue((frame["dataset"] == "nex_gddp_batch").all())

    def test_inventory_can_filter_to_one_dataset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir) / "outputs" / "cache"
            (cache_root / "nex_gddp_xee" / "v1" / "ssp245" / "MRI-ESM2-0" / "lat_m1p2860_lon_36p8170").mkdir(parents=True)
            (cache_root / "nex_gddp_batch" / "v1" / "ssp245" / "MRI-ESM2-0").mkdir(parents=True)

            xee_data = cache_root / "nex_gddp_xee" / "v1" / "ssp245" / "MRI-ESM2-0" / "lat_m1p2860_lon_36p8170" / "a.json"
            self._write_manifest(
                xee_data,
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_xee",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "lat": -1.286,
                    "lon": 36.817,
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-01",
                    "bands": ["pr"],
                    "integrity": {"complete": True, "row_count": 1, "expected_rows": 1},
                },
            )

            batch_data = cache_root / "nex_gddp_batch" / "v1" / "ssp245" / "MRI-ESM2-0" / "b.json"
            self._write_manifest(
                batch_data,
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_batch",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-01",
                    "site_count": 1,
                    "sites": [{"name": "Nairobi", "lat": -1.286, "lon": 36.817}],
                    "bands": ["pr"],
                    "integrity": {"complete": True, "row_count": 1, "expected_rows": 1},
                },
            )

            frame = cache_inventory(cache_root=cache_root, dataset="nex_gddp_batch")

        self.assertEqual(1, len(frame))
        self.assertEqual("nex_gddp_batch", frame.loc[0, "dataset"])

    def test_summary_aggregates_manifest_level_sizes_without_batch_site_double_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir) / "outputs" / "cache" / "nex_gddp_batch" / "v1" / "ssp245" / "MRI-ESM2-0"
            cache_root.mkdir(parents=True)
            data_path = cache_root / "batch.json"
            data_path.write_text("[1]", encoding="utf-8")
            data_size = data_path.stat().st_size
            data_path.with_name(f"{data_path.name}.manifest.json").write_text(
                json.dumps(
                    {
                        "cache_schema_version": "v1",
                        "dataset": "nex_gddp_batch",
                        "model": "MRI-ESM2-0",
                        "scenario": "ssp245",
                        "start_date": "2050-01-01",
                        "end_date": "2050-01-02",
                        "site_count": 2,
                        "sites": [
                            {"name": "Nairobi", "lat": -1.286, "lon": 36.817},
                            {"name": "Cusco", "lat": -13.5319, "lon": -71.9675},
                        ],
                        "bands": ["pr"],
                        "integrity": {"complete": True, "row_count": 4, "expected_rows": 4},
                    }
                ),
                encoding="utf-8",
            )

            summary = cache_summary(cache_root=Path(tmpdir) / "outputs" / "cache")

        self.assertEqual(1, len(summary))
        self.assertEqual(1, summary.loc[0, "cache_files"])
        self.assertEqual(data_size, summary.loc[0, "total_size_bytes"])

    def test_dedup_audit_flags_normalized_coordinate_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir) / "outputs" / "cache" / "nex_gddp_xee" / "v1" / "ssp245" / "MRI-ESM2-0"
            a_root = cache_root / "lat_31p1111_lon_36p8170"
            b_root = cache_root / "lat_31p11111_lon_36p81700"
            a_root.mkdir(parents=True)
            b_root.mkdir(parents=True)

            self._write_manifest(
                a_root / "2050-01-01_2050-01-03_pr.json",
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_xee",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "lat": 31.11111111111,
                    "lon": 36.8170000000,
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-03",
                    "bands": ["pr"],
                    "integrity": {"complete": True, "row_count": 3, "expected_rows": 3},
                },
            )
            self._write_manifest(
                b_root / "2050-01-01_2050-01-03_pr.json",
                {
                    "cache_schema_version": "v1",
                    "dataset": "nex_gddp_xee",
                    "model": "MRI-ESM2-0",
                    "scenario": "ssp245",
                    "lat": 31.11111,
                    "lon": 36.817,
                    "start_date": "2050-01-01",
                    "end_date": "2050-01-03",
                    "bands": ["pr"],
                    "integrity": {"complete": True, "row_count": 3, "expected_rows": 3},
                },
            )

            audit = cache_dedup_audit(cache_root=Path(tmpdir) / "outputs" / "cache")

        self.assertEqual(2, len(audit))
        self.assertTrue((audit["duplicate_group_size"] == 2).all())
        self.assertEqual(1, audit["site_count"].iloc[0])


if __name__ == "__main__":
    unittest.main()
