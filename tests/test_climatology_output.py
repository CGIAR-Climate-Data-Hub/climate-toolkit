import sys
import types
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


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


class ClimatologyOutputTests(unittest.TestCase):
    def test_main_single_source_json_creates_missing_output_directory(self):
        payload = {
            "source": "era_5",
            "period": {"start_year": 1991, "end_year": 2020},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "climatology.json"
            argv = [
                "long_term_climatology.py",
                "--location=-1.286,36.817",
                "--start-year=1991",
                "--end-year=2020",
                "--source=era_5",
                "--format=json",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(ltc, "calculate_climatology", return_value=payload):
                ltc.main()

            self.assertTrue(output_path.exists())
            self.assertIn("Climatology saved", stdout.getvalue())

    def test_main_nex_text_mode_output_creates_missing_directory(self):
        payload = {
            "scenario": "ssp245",
            "n_models_ok": 1,
            "models_failed": [],
            "climatology": {},
        }

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "climatology_ensemble.json"
            argv = [
                "long_term_climatology.py",
                "--location=-1.286,36.817",
                "--start-year=2040",
                "--end-year=2060",
                "--source=nex_gddp",
                "--scenarios=ssp245",
                f"--output={output_path}",
            ]

            stdout = StringIO()
            with mock.patch("sys.argv", argv), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(ltc, "calculate_climatology_ensemble", return_value=payload), \
                 mock.patch.object(ltc, "print_ensemble_climatology_report", return_value=None):
                ltc.main()

            self.assertTrue(output_path.exists())
            self.assertIn("JSON data saved", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
