import importlib
import logging
import sys
import unittest


def _clear_modules(*module_names):
    for name in module_names:
        sys.modules.pop(name, None)


class LazyPackageRootsTests(unittest.TestCase):
    def test_top_level_package_root_does_not_eager_import_major_subpackages(self):
        _clear_modules(
            "climate_tookit",
            "climate_tookit.fetch_data",
            "climate_tookit.weather_station",
            "climate_tookit.compare_periods",
            "climate_tookit.compare_datasets",
            "climate_tookit.climate_statistics",
            "climate_tookit.calculate_hazards",
        )

        package = importlib.import_module("climate_tookit")

        self.assertEqual("climate_tookit", package.__name__)
        self.assertNotIn("climate_tookit.fetch_data", sys.modules)
        self.assertNotIn("climate_tookit.weather_station", sys.modules)
        self.assertNotIn("climate_tookit.compare_periods", sys.modules)
        self.assertNotIn("climate_tookit.compare_datasets", sys.modules)
        self.assertNotIn("climate_tookit.climate_statistics", sys.modules)
        self.assertNotIn("climate_tookit.calculate_hazards", sys.modules)

        fetch_fn = package.fetch_climate_data
        self.assertTrue(callable(fetch_fn))
        self.assertIn("climate_tookit.fetch_data.fetch_data", sys.modules)

    def test_climatology_xclim_availability_flag_stays_lightweight(self):
        _clear_modules(
            "climate_tookit.climatology",
            "climate_tookit.climatology.xclim_reference",
            "xarray",
            "xclim",
        )

        package = importlib.import_module("climate_tookit.climatology")

        self.assertEqual("climate_tookit.climatology", package.__name__)
        self.assertNotIn("climate_tookit.climatology.xclim_reference", sys.modules)

        available = package.XCLIM_AVAILABLE
        self.assertIsInstance(available, bool)
        self.assertIn("climate_tookit.climatology.xclim_reference", sys.modules)
        self.assertNotIn("xarray", sys.modules)
        self.assertNotIn("xclim", sys.modules)

    def test_crop_calendar_package_root_does_not_eager_import_submodules(self):
        _clear_modules(
            "climate_tookit.crop_calendar",
            "climate_tookit.crop_calendar.ggcmi",
            "climate_tookit.crop_calendar.registry",
        )

        package = importlib.import_module("climate_tookit.crop_calendar")

        self.assertEqual("climate_tookit.crop_calendar", package.__name__)
        self.assertNotIn("climate_tookit.crop_calendar.ggcmi", sys.modules)
        self.assertNotIn("climate_tookit.crop_calendar.registry", sys.modules)

        extract_point_calendar = package.extract_point_calendar
        self.assertTrue(callable(extract_point_calendar))
        self.assertIn("climate_tookit.crop_calendar.ggcmi", sys.modules)

    def test_source_utils_package_root_does_not_eager_import_models_or_settings(self):
        _clear_modules(
            "climate_tookit.fetch_data.source_data.sources.utils",
            "climate_tookit.fetch_data.source_data.sources.utils.models",
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
        )

        package = importlib.import_module("climate_tookit.fetch_data.source_data.sources.utils")

        self.assertEqual(
            "climate_tookit.fetch_data.source_data.sources.utils",
            package.__name__,
        )
        self.assertNotIn(
            "climate_tookit.fetch_data.source_data.sources.utils.models",
            sys.modules,
        )
        self.assertNotIn(
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
            sys.modules,
        )

        parse_variable_token = package.parse_variable_token
        self.assertTrue(callable(parse_variable_token))
        self.assertIn(
            "climate_tookit.fetch_data.source_data.sources.utils.models",
            sys.modules,
        )
        self.assertNotIn(
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
            sys.modules,
        )

        settings_cls = package.Settings
        self.assertTrue(callable(settings_cls))
        self.assertIn(
            "climate_tookit.fetch_data.source_data.sources.utils.settings",
            sys.modules,
        )

    def test_source_utils_set_logging_does_not_mutate_root_logger(self):
        package = importlib.import_module("climate_tookit.fetch_data.source_data.sources.utils")
        before_level = logging.root.level
        before_handlers = list(logging.root.handlers)

        logger = package.set_logging()

        self.assertEqual(before_level, logging.root.level)
        self.assertEqual(before_handlers, list(logging.root.handlers))
        self.assertEqual("climate_tookit", logger.name)
        self.assertEqual(logging.INFO, logger.level)

    def test_source_data_package_root_is_lazy(self):
        _clear_modules(
            "climate_tookit.fetch_data.source_data",
            "climate_tookit.fetch_data.source_data.source_data",
        )

        package = importlib.import_module("climate_tookit.fetch_data.source_data")

        self.assertEqual("climate_tookit.fetch_data.source_data", package.__name__)
        self.assertNotIn("climate_tookit.fetch_data.source_data.source_data", sys.modules)

        source_data_cls = package.SourceData
        self.assertTrue(callable(source_data_cls))
        self.assertIn("climate_tookit.fetch_data.source_data.source_data", sys.modules)

    def test_transform_data_package_root_is_lazy(self):
        _clear_modules(
            "climate_tookit.fetch_data.transform_data",
            "climate_tookit.fetch_data.transform_data.transform_data",
        )

        package = importlib.import_module("climate_tookit.fetch_data.transform_data")

        self.assertEqual("climate_tookit.fetch_data.transform_data", package.__name__)
        self.assertNotIn(
            "climate_tookit.fetch_data.transform_data.transform_data",
            sys.modules,
        )

        transform_fn = package.transform_data
        self.assertTrue(callable(transform_fn))
        self.assertIn(
            "climate_tookit.fetch_data.transform_data.transform_data",
            sys.modules,
        )

    def test_preprocess_data_package_root_is_lazy(self):
        _clear_modules(
            "climate_tookit.fetch_data.preprocess_data",
            "climate_tookit.fetch_data.preprocess_data.preprocess_data",
        )

        package = importlib.import_module("climate_tookit.fetch_data.preprocess_data")

        self.assertEqual("climate_tookit.fetch_data.preprocess_data", package.__name__)
        self.assertNotIn(
            "climate_tookit.fetch_data.preprocess_data.preprocess_data",
            sys.modules,
        )

        preprocess_fn = package.preprocess_data
        self.assertTrue(callable(preprocess_fn))
        self.assertIn(
            "climate_tookit.fetch_data.preprocess_data.preprocess_data",
            sys.modules,
        )


if __name__ == "__main__":
    unittest.main()
