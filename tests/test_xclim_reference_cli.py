import sys
import types
import unittest
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import mock

import pandas as pd
from typer.testing import CliRunner


def _install_test_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    ee = types.ModuleType("ee")
    ee.Authenticate = lambda *args, **kwargs: None
    ee.Initialize = lambda *args, **kwargs: None
    sys.modules.setdefault("ee", ee)

    cdsapi = types.ModuleType("cdsapi")
    cdsapi_api = types.ModuleType("cdsapi.api")

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

    cdsapi_api.Client = _Client
    cdsapi.api = cdsapi_api
    sys.modules.setdefault("cdsapi", cdsapi)
    sys.modules.setdefault("cdsapi.api", cdsapi_api)


_install_test_stubs()

import climate_tookit.climatology.xclim_reference as xclim_cli


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class XclimReferenceTyperCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _plain(self, text: str) -> str:
        return ANSI_ESCAPE_RE.sub("", text)

    def test_typer_help_exposes_expected_root_options(self):
        result = self.runner.invoke(xclim_cli.app, ["--help"])
        plain = self._plain(result.output)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Usage:", plain)
        self.assertIn("--location", plain)
        self.assertIn("--source", plain)
        self.assertIn("--mode", plain)
        self.assertIn("--format", plain)
        self.assertNotIn("--install-completion", plain)
        self.assertNotIn("--show-completion", plain)

    def test_typer_reports_invalid_mode_before_running(self):
        result = self.runner.invoke(
            xclim_cli.app,
            [
                "--location=-1.286,36.817",
                "--source=agera_5",
                "--start=2020-01-01",
                "--end=2020-12-31",
                "--mode=not-a-mode",
            ],
        )

        self.assertEqual(2, result.exit_code)
        self.assertIn("Invalid mode", result.output)

    def test_main_entrypoint_writes_json_output_for_readiness(self):
        fetched = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precip": [1.0, 2.0],
                "tmax": [25.0, 26.0],
                "tmin": [15.0, 16.0],
            }
        )

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "xclim_readiness.json"
            with mock.patch.object(xclim_cli, "fetch_standardized_climate_frame", return_value=fetched), \
                 mock.patch.object(
                     xclim_cli,
                     "assess_xclim_precip_annual_readiness",
                     return_value=None,
                 ):
                rc = xclim_cli.main(
                    [
                        "--location=-1.286,36.817",
                        "--source=agera_5",
                        "--start=2020-01-01",
                        "--end=2020-12-31",
                        "--mode=annual-readiness",
                        "--format=json",
                        f"--output={output_path}",
                    ]
                )

            self.assertEqual(0, rc)
            self.assertTrue(output_path.exists())
            saved = output_path.read_text(encoding="utf-8")
            self.assertIn('"tool": "xclim-reference"', saved)
            self.assertIn('"ready": true', saved)


if __name__ == "__main__":
    unittest.main()
