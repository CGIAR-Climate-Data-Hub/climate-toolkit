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

import climate_tookit.climatology.spei as spei_cli


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class SpeiTyperCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _plain(self, text: str) -> str:
        return ANSI_ESCAPE_RE.sub("", text)

    def test_typer_help_exposes_expected_root_options(self):
        result = self.runner.invoke(spei_cli.app, ["--help"])
        plain = self._plain(result.output)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Usage:", plain)
        self.assertIn("--location", plain)
        self.assertIn("--source", plain)
        self.assertIn("--start", plain)
        self.assertIn("--end", plain)
        self.assertIn("--index", plain)
        self.assertNotIn("--install-completion", plain)
        self.assertNotIn("--show-completion", plain)

    def test_typer_reports_invalid_format_before_running(self):
        result = self.runner.invoke(
            spei_cli.app,
            [
                "--location=-1.286,36.817",
                "--source=agera_5",
                "--start=2020-01-01",
                "--end=2020-12-31",
                "--format=yaml",
            ],
        )

        self.assertEqual(2, result.exit_code)
        self.assertIn("Invalid format", result.output)

    def test_main_entrypoint_writes_json_output(self):
        fetched = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precip": [1.0, 2.0],
                "tmax": [25.0, 26.0],
                "tmin": [15.0, 16.0],
            }
        )
        result_frame = pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-02-01"],
                "month": [1, 2],
                "spei": [0.25, -0.1],
            }
        )
        result_frame.attrs["spei_metadata"] = {"index_name": "SPEI", "scale_months": 3}

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "spei.json"
            with mock.patch.object(spei_cli, "fetch_standardized_climate_frame", return_value=fetched), \
                 mock.patch.object(spei_cli, "compute_monthly_spei", return_value=result_frame):
                rc = spei_cli.main(
                    [
                        "--location=-1.286,36.817",
                        "--source=agera_5",
                        "--start=2020-01-01",
                        "--end=2020-12-31",
                        "--index=spei",
                        "--format=json",
                        f"--output={output_path}",
                    ]
                )

            self.assertEqual(0, rc)
            self.assertTrue(output_path.exists())
            saved = output_path.read_text(encoding="utf-8")
            self.assertIn('"tool": "spei"', saved)
            self.assertIn('"mode": "spei"', saved)


if __name__ == "__main__":
    unittest.main()
