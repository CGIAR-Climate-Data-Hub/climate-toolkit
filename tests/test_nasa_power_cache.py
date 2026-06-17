from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from climate_tookit.fetch_data.source_data.sources.nasa_power import DownloadData
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _payload(precip_scale: float = 1.0) -> dict:
    return {
        "properties": {
            "parameter": {
                "PRECTOTCORR": {
                    "20200101": 1.0 * precip_scale,
                    "20200102": 2.0 * precip_scale,
                    "20200103": 3.0 * precip_scale,
                },
                "T2M_MAX": {
                    "20200101": 25.0,
                    "20200102": 26.0,
                    "20200103": 27.0,
                },
                "T2M_MIN": {
                    "20200101": 15.0,
                    "20200102": 16.0,
                    "20200103": 17.0,
                },
            }
        }
    }


class NasaPowerCacheTests(unittest.TestCase):
    def _downloader(self, cache_dir: str, *, refresh_cache: bool = False) -> DownloadData:
        return DownloadData(
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 3),
            variables=[
                ClimateVariable.precipitation,
                ClimateVariable.max_temperature,
                ClimateVariable.min_temperature,
            ],
            settings=Settings.load(),
            source=ClimateDataset.nasa_power,
            verbose=False,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )

    def test_nasa_power_cache_roundtrip_uses_saved_files(self):
        import climate_tookit.fetch_data.source_data.sources.nasa_power as nasa_power

        calls: list[str] = []
        original_get = nasa_power.requests.get
        nasa_power.requests.get = lambda *args, **kwargs: calls.append(args[0]) or _Response(_payload())
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                first = self._downloader(tmpdir).download_variables()
                second = self._downloader(tmpdir).download_variables()
                data_path, manifest_path = self._downloader(tmpdir)._cache_paths()
                data_exists = Path(data_path).exists()
                manifest_exists = Path(manifest_path).exists()
        finally:
            nasa_power.requests.get = original_get

        self.assertEqual(1, len(calls))
        self.assertEqual([1.0, 2.0, 3.0], first["precipitation"].tolist())
        self.assertEqual([1.0, 2.0, 3.0], second["precipitation"].tolist())
        self.assertTrue(data_exists)
        self.assertTrue(manifest_exists)
        self.assertIn("/nasa_power/", str(data_path))

    def test_nasa_power_refresh_cache_forces_refetch(self):
        import climate_tookit.fetch_data.source_data.sources.nasa_power as nasa_power

        payloads = [_payload(1.0), _payload(10.0)]
        calls: list[str] = []

        def _fake_get(*args, **kwargs):
            calls.append(args[0])
            return _Response(payloads.pop(0))

        original_get = nasa_power.requests.get
        nasa_power.requests.get = _fake_get
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                first = self._downloader(tmpdir).download_variables()
                refreshed = self._downloader(tmpdir, refresh_cache=True).download_variables()
        finally:
            nasa_power.requests.get = original_get

        self.assertEqual(2, len(calls))
        self.assertEqual([1.0, 2.0, 3.0], first["precipitation"].tolist())
        self.assertEqual([10.0, 20.0, 30.0], refreshed["precipitation"].tolist())

    def test_nasa_power_legacy_cache_layout_still_reads(self):
        import climate_tookit.fetch_data.source_data.sources.nasa_power as nasa_power

        original_get = nasa_power.requests.get
        nasa_power.requests.get = lambda *args, **kwargs: _Response(_payload())
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                downloader = self._downloader(tmpdir)
                first = downloader.download_variables()
                new_data_path, new_manifest_path = downloader._cache_paths()
                legacy_paths = downloader._legacy_cache_paths()
                self.assertIsNotNone(legacy_paths)
                legacy_data_path, legacy_manifest_path = legacy_paths
                legacy_data_path.parent.mkdir(parents=True, exist_ok=True)
                legacy_manifest_path.parent.mkdir(parents=True, exist_ok=True)
                Path(new_data_path).replace(legacy_data_path)
                Path(new_manifest_path).replace(legacy_manifest_path)
                second = downloader.download_variables()
        finally:
            nasa_power.requests.get = original_get

        self.assertEqual([1.0, 2.0, 3.0], first["precipitation"].tolist())
        self.assertEqual([1.0, 2.0, 3.0], second["precipitation"].tolist())


if __name__ == "__main__":
    unittest.main()
