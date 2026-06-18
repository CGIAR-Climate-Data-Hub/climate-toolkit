import logging
import unittest
from datetime import date
from unittest import mock
import tempfile
import zipfile
from io import BytesIO

import requests
import xarray as xr
import numpy as np

from climate_tookit.fetch_data.source_data.sources.tamsat import DownloadTAMSAT
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


class TamsatLoggingTests(unittest.TestCase):
    def test_tamsat_failures_are_summarized_not_spammed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 5),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
                refresh_cache=True,
            )

            class FakeSession:
                headers = {}

                def get(self, url, timeout=30):
                    raise requests.exceptions.RequestException("boom")

                def close(self):
                    return None

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=FakeSession()):
                with self.assertLogs("climate_tookit.fetch_data.source_data.sources.tamsat", level="INFO") as captured:
                    values = downloader.download_precipitation()

        self.assertEqual(5, len(values))
        self.assertTrue(all(value != value for value in values))
        joined = "\n".join(captured.output)
        self.assertIn("TAMSAT fetch start", joined)
        self.assertIn("TAMSAT progress", joined)
        self.assertIn("TAMSAT fetch completed with failures", joined)
        self.assertNotIn("TAMSAT fetch failed for 2020-01-01", joined)

    def test_tamsat_month_cache_avoids_repeat_day_fetches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 3),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
            )

            class FakeSession:
                headers = {}

                def close(self):
                    return None

            first_calls = []

            def fake_fetch_single_day_value(**kwargs):
                first_calls.append(kwargs["url"])
                return float(len(first_calls))

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=FakeSession()):
                with mock.patch.object(downloader, "_fetch_single_day_value", side_effect=fake_fetch_single_day_value):
                    first = downloader.download_precipitation()

            self.assertEqual([1.0, 2.0, 3.0], first)
            self.assertEqual(3, len(first_calls))

            second_downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 3),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
            )

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=FakeSession()):
                with mock.patch.object(second_downloader, "_fetch_single_day_value", side_effect=AssertionError("network fetch should not run on warm cache")):
                    second = second_downloader.download_precipitation()

            self.assertEqual([1.0, 2.0, 3.0], second)

    def test_tamsat_rainfall_uses_yearly_zip_before_daily_fallback(self):
        def build_nc_bytes(value: float) -> bytes:
            ds = xr.Dataset(
                {
                    "rfe": (("lat", "lon"), np.array([[value]], dtype=float)),
                },
                coords={"lat": [-1.286], "lon": [36.817]},
            )
            return ds.to_netcdf()

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as archive:
            archive.writestr("rfe2020_01_01.v3.1.nc", build_nc_bytes(1.0))
            archive.writestr("rfe2020_01_02.v3.1.nc", build_nc_bytes(2.0))
            archive.writestr("rfe2020_01_03.v3.1.nc", build_nc_bytes(3.0))
        zip_payload = zip_buffer.getvalue()

        listing_html = """
        <html><body>
        <a href="TAMSATv3.1_rfe_daily_2020.zip">2020 zip</a>
        </body></html>
        """

        class FakeResponse:
            def __init__(self, *, text=None, content=None, status_code=200):
                self.text = text or ""
                self.content = content or b""
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"status={self.status_code}")

        class FakeSession:
            headers = {}

            def get(self, url, timeout=30):
                if url.endswith("/v3.1"):
                    return FakeResponse(text=listing_html)
                if url.endswith("TAMSATv3.1_rfe_daily_2020.zip"):
                    return FakeResponse(content=zip_payload)
                raise AssertionError(f"unexpected URL {url}")

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 3),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
            )

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=FakeSession()):
                with mock.patch.object(downloader, "_fetch_single_day_value", side_effect=AssertionError("daily fallback should not run when zip covers all dates")):
                    values = downloader.download_precipitation()

            self.assertEqual([1.0, 2.0, 3.0], values)

    def test_tamsat_failed_day_not_cached_as_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 1),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
                refresh_cache=True,
            )

            class FailSession:
                headers = {}

                def get(self, url, timeout=30):
                    raise requests.exceptions.RequestException("boom")

                def close(self):
                    return None

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=FailSession()):
                first = downloader.download_precipitation()

            self.assertTrue(first[0] != first[0])

            second_downloader = DownloadTAMSAT(
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 1),
                variables=[ClimateVariable.precipitation],
                cache_dir=tmpdir,
            )

            class SuccessSession:
                headers = {}

                def get(self, url, timeout=30):
                    return None

                def close(self):
                    return None

            with mock.patch("climate_tookit.fetch_data.source_data.sources.tamsat.requests.Session", return_value=SuccessSession()):
                with mock.patch.object(second_downloader, "_download_rainfall_year_archive", return_value=None):
                    with mock.patch.object(second_downloader, "_fetch_single_day_value", return_value=7.0) as fetch_mock:
                        second = second_downloader.download_precipitation()

            fetch_mock.assert_called_once()
            self.assertEqual([7.0], second)


if __name__ == "__main__":
    unittest.main()
