import os
import unittest
from unittest import mock

from climate_tookit.fetch_data.source_data.sources import xee_common


class XeeCommonTests(unittest.TestCase):
    def test_infer_ee_project_id_prefers_explicit_value(self):
        with mock.patch.dict(
            os.environ,
            {
                "GCP_PROJECT_ID": "env-project",
                "GOOGLE_CLOUD_PROJECT": "cloud-project",
                "EE_PROJECT_ID": "ee-project",
            },
            clear=False,
        ):
            self.assertEqual(
                "explicit-project",
                xee_common.infer_ee_project_id("explicit-project"),
            )

    def test_infer_ee_project_id_reads_supported_env_vars(self):
        with mock.patch.dict(os.environ, {"GCP_PROJECT_ID": "env-project"}, clear=True):
            self.assertEqual("env-project", xee_common.infer_ee_project_id(None))

        with mock.patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "cloud-project"}, clear=True):
            self.assertEqual("cloud-project", xee_common.infer_ee_project_id(None))

        with mock.patch.dict(os.environ, {"EE_PROJECT_ID": "ee-project"}, clear=True):
            self.assertEqual("ee-project", xee_common.infer_ee_project_id(None))

    def test_initialize_earth_engine_uses_high_volume_endpoint(self):
        calls = []

        class FakeEe:
            @staticmethod
            def Initialize(*, project, opt_url):
                calls.append((project, opt_url))

        resolved = xee_common.initialize_earth_engine(FakeEe, project_id="demo-project")

        self.assertEqual("demo-project", resolved)
        self.assertEqual(
            [("demo-project", xee_common.DEFAULT_EE_OPT_URL)],
            calls,
        )

    def test_manual_point_grid_returns_single_pixel_grid(self):
        grid = xee_common.manual_point_grid(
            lon=36.817,
            lat=-1.286,
            pixel_size_meters=5566,
        )

        self.assertEqual("EPSG:4326", grid["crs"])
        self.assertEqual((1, 1), grid["shape_2d"])
        self.assertEqual(6, len(grid["crs_transform"]))

    def test_format_ee_setup_error_simplifies_auth_refresh_network_failures(self):
        message = xee_common.format_ee_setup_error(
            RuntimeError(
                "google.auth.exceptions.TransportError: HTTPSConnectionPool(host='oauth2.googleapis.com', "
                "port=443): Max retries exceeded with url: /token (Caused by NameResolutionError("
                "\"HTTPSConnection(host='oauth2.googleapis.com', port=443): Failed to resolve "
                "'oauth2.googleapis.com'\"))"
            )
        )

        self.assertIn("Earth Engine auth refresh failed.", message)
        self.assertIn("ee.Authenticate()", message)
        self.assertIn(xee_common.EARTH_ENGINE_SETUP_URL, message)

    def test_format_ee_setup_error_adds_setup_guide_for_missing_project_id(self):
        message = xee_common.format_ee_setup_error(
            ValueError(
                "Earth Engine project ID is required. Pass ee_project_id or set one of "
                "GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or EE_PROJECT_ID."
            )
        )

        self.assertIn("Earth Engine project ID missing.", message)
        self.assertIn("GCP_PROJECT_ID", message)
        self.assertIn(xee_common.EARTH_ENGINE_SETUP_URL, message)


if __name__ == "__main__":
    unittest.main()
