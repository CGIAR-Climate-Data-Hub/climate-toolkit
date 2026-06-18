import contextlib
import builtins
import importlib
import io
import logging
import sys
import types
import unittest
import warnings
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

import numpy  # noqa: F401
import pandas  # noqa: F401
import requests  # noqa: F401


class PackageImportHygieneTests(unittest.TestCase):
    MODULES = [
        "climate_tookit.crop_calendar",
        "climate_tookit.climatology",
        "climate_tookit.climatology.long_term_climatology",
        "climate_tookit.fetch_data.gee_xee_batch",
        "climate_tookit.fetch_data",
        "climate_tookit.fetch_data.nex_gddp_batch",
        "climate_tookit.fetch_data.preprocess_data",
        "climate_tookit.fetch_data.transform_data",
        "climate_tookit.fetch_data.source_data.sources.gee",
        "climate_tookit.fetch_data.source_data.sources.soil_grid",
        "climate_tookit.fetch_data.source_data.sources.chirps",
        "climate_tookit.fetch_data.source_data.sources.chirts",
        "climate_tookit.fetch_data.source_data.sources.imerg",
        "climate_tookit.fetch_data.source_data.sources.terraclimate",
        "climate_tookit.fetch_data.source_data.sources.nex_gddp_xee",
        "climate_tookit.season_analysis.seasons",
        "climate_tookit.season_analysis.ensemble",
        "climate_tookit.compare_datasets",
        "climate_tookit.compare_datasets.compare_datasets",
        "climate_tookit.compare_periods.periods",
        "climate_tookit.compare_periods.ensemble_periods",
        "climate_tookit.climate_statistics.statistics",
        "climate_tookit.climate_statistics.ensemble_statistics",
        "climate_tookit.calculate_hazards.hazards",
        "climate_tookit.calculate_hazards.ensemble_hazards",
        "climate_tookit.weather_station",
        "climate_tookit.weather_station.download",
        "climate_tookit.weather_station.compare",
        "climate_tookit.fetch_data.source_data.sources.utils",
    ]

    def test_package_modules_import_without_stdout_or_sys_path_mutation(self):
        for module_name in self.MODULES:
            with self.subTest(module=module_name):
                before_path = list(sys.path)
                before_root_level = logging.root.level
                before_root_handlers = list(logging.root.handlers)
                before_warning_filters = list(warnings.filters)
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
                self.assertEqual(before_root_level, logging.root.level)
                self.assertEqual(before_root_handlers, list(logging.root.handlers))
                self.assertEqual(before_warning_filters, list(warnings.filters))

    def test_compare_datasets_import_does_not_require_matplotlib(self):
        blocked = {"matplotlib", "matplotlib.pyplot", "matplotlib.ticker"}
        saved_modules = {
            name: sys.modules.pop(name)
            for name in list(blocked)
            if name in sys.modules
        }
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in blocked or any(name.startswith(f"{prefix}.") for prefix in blocked):
                raise ModuleNotFoundError(name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            existing = sys.modules.pop("climate_tookit.compare_datasets.compare_datasets", None)
            with mock.patch("builtins.__import__", side_effect=blocked_import):
                module = importlib.import_module("climate_tookit.compare_datasets.compare_datasets")
            self.assertEqual("climate_tookit.compare_datasets.compare_datasets", module.__name__)
            self.assertTrue(callable(module.compare_sources))
            if existing is not None:
                sys.modules["climate_tookit.compare_datasets.compare_datasets"] = existing
        finally:
            sys.modules.update(saved_modules)

    def test_weather_station_compare_import_does_not_require_tabulate(self):
        blocked = {"tabulate"}
        saved_modules = {
            name: sys.modules.pop(name)
            for name in list(blocked)
            if name in sys.modules
        }
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in blocked or any(name.startswith(f"{prefix}.") for prefix in blocked):
                raise ModuleNotFoundError(name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            existing = sys.modules.pop("climate_tookit.weather_station.compare", None)
            with mock.patch("builtins.__import__", side_effect=blocked_import):
                module = importlib.import_module("climate_tookit.weather_station.compare")
            self.assertEqual("climate_tookit.weather_station.compare", module.__name__)
            self.assertTrue(callable(module.compare_station_to_grids))
            if existing is not None:
                sys.modules["climate_tookit.weather_station.compare"] = existing
        finally:
            sys.modules.update(saved_modules)

    def test_sources_utils_package_import_does_not_eager_load_models_or_settings(self):
        for module_name in [
            "climate_tookit.fetch_data.source_data.sources.utils",
            "climate_tookit.fetch_data.source_data.sources.utils.models",
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
        ]:
            sys.modules.pop(module_name, None)

        module = importlib.import_module("climate_tookit.fetch_data.source_data.sources.utils")

        self.assertEqual("climate_tookit.fetch_data.source_data.sources.utils", module.__name__)
        self.assertNotIn(
            "climate_tookit.fetch_data.source_data.sources.utils.models",
            sys.modules,
        )
        self.assertNotIn(
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
            sys.modules,
        )

        _ = module.Settings
        self.assertIn(
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
            sys.modules,
        )


if __name__ == "__main__":
    unittest.main()
