import logging
import unittest
from datetime import date
from unittest import mock

import requests

from climate_tookit.fetch_data.source_data.sources.tamsat import DownloadTAMSAT
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


class TamsatLoggingTests(unittest.TestCase):
    def test_tamsat_failures_are_summarized_not_spammed(self):
        downloader = DownloadTAMSAT(
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 5),
            variables=[ClimateVariable.precipitation],
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


if __name__ == "__main__":
    unittest.main()
