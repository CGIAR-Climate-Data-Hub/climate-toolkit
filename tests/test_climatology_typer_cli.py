import sys
import types
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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

    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    ticker = types.ModuleType("matplotlib.ticker")

    class _MaxNLocator:
        def __init__(self, *args, **kwargs):
            pass

    ticker.MaxNLocator = _MaxNLocator
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)
    sys.modules.setdefault("matplotlib.ticker", ticker)


_install_test_stubs()

import climate_tookit.climatology.long_term_climatology as ltc


class ClimatologyTyperCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_typer_help_exposes_existing_root_options_without_completion_noise(self):
        result = self.runner.invoke(ltc.app, ["--help"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Usage:", result.output)
        self.assertIn("[OPTIONS]", result.output)
        self.assertIn("--location", result.output)
        self.assertIn("--start-year", result.output)
        self.assertIn("--end-year", result.output)
        self.assertIn("--source", result.output)
        self.assertNotIn("COMMAND [ARGS]", result.output)
        self.assertNotIn("--install-completion", result.output)
        self.assertNotIn("--show-completion", result.output)

    def test_typer_reports_invalid_format_before_running(self):
        result = self.runner.invoke(
            ltc.app,
            [
                "--location=-1.286,36.817",
                "--start-year=1991",
                "--end-year=2020",
                "--source=era_5",
                "--format=yaml",
            ],
        )

        self.assertEqual(2, result.exit_code)
        self.assertIn("Invalid format", result.output)

    def test_main_entrypoint_still_writes_json_output(self):
        payload = {
            "source": "era_5",
            "period": {"start_year": 1991, "end_year": 2020},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "climatology.json"
            stdout = StringIO()
            with mock.patch.object(ltc, "calculate_climatology", return_value=payload), \
                 mock.patch("sys.stdout", stdout):
                rc = ltc.main(
                    [
                        "--location=-1.286,36.817",
                        "--start-year=1991",
                        "--end-year=2020",
                        "--source=era_5",
                        "--format=json",
                        f"--output={output_path}",
                    ]
                )

            self.assertEqual(0, rc)
            self.assertTrue(output_path.exists())
            self.assertIn("Climatology saved", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
