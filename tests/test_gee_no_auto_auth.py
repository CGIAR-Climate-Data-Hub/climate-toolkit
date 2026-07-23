"""Guard: GEE initialization must never launch interactive auth.

A library must not call ``ee.Authenticate()`` on the user's behalf (it hijacks
the browser and saves credentials without opt-in). ``_ensure_gee_initialized``
should only ``ee.Initialize`` and raise a clear error if EE is not set up.
"""

import unittest
from unittest import mock

import climate_toolkit.fetch_data.source_data.sources.gee as gee


class GeeNoInteractiveAuthTests(unittest.TestCase):
    def setUp(self):
        self._orig_ready = gee._GEE_READY
        gee._GEE_READY = False

    def tearDown(self):
        gee._GEE_READY = self._orig_ready

    def test_initialize_never_authenticates(self):
        fake_ee = mock.MagicMock()
        with mock.patch.object(gee, "ee", fake_ee), mock.patch.object(
            gee, "infer_ee_project_id", return_value="demo-project"
        ):
            gee._ensure_gee_initialized()
        fake_ee.Authenticate.assert_not_called()
        fake_ee.Initialize.assert_called_once_with(project="demo-project")

    def test_setup_failure_is_wrapped_and_still_no_auth(self):
        fake_ee = mock.MagicMock()
        fake_ee.Initialize.side_effect = RuntimeError("no project")
        with mock.patch.object(gee, "ee", fake_ee), mock.patch.object(
            gee, "infer_ee_project_id", return_value="p"
        ):
            with self.assertRaises(RuntimeError):
                gee._ensure_gee_initialized()
        fake_ee.Authenticate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
