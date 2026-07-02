import unittest
from unittest import mock

from climate_tookit import gee_check


class ProjectResolutionTests(unittest.TestCase):
    def test_explicit_project_wins(self):
        with mock.patch.dict("os.environ", {"GCP_PROJECT_ID": "env-proj"}, clear=False):
            self.assertEqual("explicit-proj", gee_check.resolve_project_id("explicit-proj"))

    def test_env_fallback_order(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.dict("os.environ", {"EE_PROJECT_ID": "ee-proj"}):
                self.assertEqual("ee-proj", gee_check.resolve_project_id(None))

    def test_none_when_unset(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(gee_check.resolve_project_id(None))

    def test_placeholder_detection(self):
        for value in ("YOUR_PROJECT_ID", "your-ee-project-id", "<project-id>", "changeme"):
            self.assertTrue(gee_check.is_placeholder_project_id(value), value)
        for value in ("my-ee-project-123", "cgiar-climate", None):
            self.assertFalse(gee_check.is_placeholder_project_id(value), value)


class ClassifyErrorTests(unittest.TestCase):
    def test_network_beats_auth_when_both_markers(self):
        exc = Exception("Failed to resolve oauth2.googleapis.com: getaddrinfo failed")
        self.assertEqual("network", gee_check.classify_ee_error(exc))

    def test_auth(self):
        self.assertEqual("auth", gee_check.classify_ee_error(Exception("Please authorize access")))

    def test_project(self):
        exc = Exception("Project 'projects/foo' not found or deleted")
        self.assertEqual("project", gee_check.classify_ee_error(exc))

    def test_permission_is_project(self):
        self.assertEqual("project", gee_check.classify_ee_error(Exception("Permission denied")))

    def test_unknown(self):
        self.assertEqual("unknown", gee_check.classify_ee_error(Exception("boom")))


class RunPreflightTests(unittest.TestCase):
    def _lines(self):
        out = []
        return out, out.append

    def test_missing_project(self):
        out, writer = self._lines()
        with mock.patch.dict("os.environ", {}, clear=True):
            code, category = gee_check.run_preflight(None, writer=writer)
        self.assertEqual((1, "project-missing"), (code, category))
        self.assertIn("No Earth Engine project ID", "\n".join(out))

    def test_placeholder_project(self):
        out, writer = self._lines()
        code, category = gee_check.run_preflight("YOUR_PROJECT_ID", writer=writer)
        self.assertEqual((1, "project-placeholder"), (code, category))

    def test_missing_credentials(self):
        out, writer = self._lines()
        fake_ee = mock.Mock()
        with mock.patch.object(gee_check, "import_xee_stack", return_value=(fake_ee, None)), \
             mock.patch.object(gee_check, "_credentials_present", return_value=False):
            code, category = gee_check.run_preflight("real-proj", writer=writer)
        self.assertEqual((1, "auth"), (code, category))

    def test_init_project_error(self):
        out, writer = self._lines()
        fake_ee = mock.Mock()
        with mock.patch.object(gee_check, "import_xee_stack", return_value=(fake_ee, None)), \
             mock.patch.object(gee_check, "_credentials_present", return_value=True), \
             mock.patch.object(
                 gee_check, "initialize_earth_engine",
                 side_effect=Exception("Project 'x' not found or deleted"),
             ):
            code, category = gee_check.run_preflight("real-proj", writer=writer)
        self.assertEqual((1, "project"), (code, category))

    def test_success(self):
        out, writer = self._lines()
        fake_ee = mock.Mock()
        fake_ee.Number.return_value.getInfo.return_value = 1
        with mock.patch.object(gee_check, "import_xee_stack", return_value=(fake_ee, None)), \
             mock.patch.object(gee_check, "_credentials_present", return_value=True), \
             mock.patch.object(gee_check, "initialize_earth_engine", return_value="real-proj"):
            code, category = gee_check.run_preflight("real-proj", writer=writer)
        self.assertEqual((0, "ok"), (code, category))
        self.assertIn("Earth Engine is ready", "\n".join(out))

    def test_roundtrip_unexpected_value(self):
        out, writer = self._lines()
        fake_ee = mock.Mock()
        fake_ee.Number.return_value.getInfo.return_value = 42
        with mock.patch.object(gee_check, "import_xee_stack", return_value=(fake_ee, None)), \
             mock.patch.object(gee_check, "_credentials_present", return_value=True), \
             mock.patch.object(gee_check, "initialize_earth_engine", return_value="real-proj"):
            code, category = gee_check.run_preflight("real-proj", writer=writer)
        self.assertEqual((1, "roundtrip"), (code, category))


if __name__ == "__main__":
    unittest.main()
