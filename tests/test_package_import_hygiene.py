import contextlib
import importlib
import io
import sys
import types
import unittest


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


class PackageImportHygieneTests(unittest.TestCase):
    MODULES = [
        "climate_tookit.season_analysis.seasons",
        "climate_tookit.season_analysis.ensemble",
        "climate_tookit.compare_periods.periods",
        "climate_tookit.compare_periods.ensemble_periods",
        "climate_tookit.climate_statistics.statistics",
        "climate_tookit.climate_statistics.ensemble_statistics",
        "climate_tookit.calculate_hazards.hazards",
        "climate_tookit.calculate_hazards.ensemble_hazards",
    ]

    def test_package_modules_import_without_stdout_or_sys_path_mutation(self):
        for module_name in self.MODULES:
            with self.subTest(module=module_name):
                before_path = list(sys.path)
                existing = sys.modules.get(module_name)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    if existing is None:
                        mod = importlib.import_module(module_name)
                    else:
                        mod = importlib.reload(existing)
                self.assertEqual(module_name, mod.__name__)
                self.assertEqual("", stdout.getvalue())
                self.assertEqual(before_path, list(sys.path))


if __name__ == "__main__":
    unittest.main()
