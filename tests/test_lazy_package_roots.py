import importlib
import sys
import unittest


def _clear_modules(*module_names):
    for name in module_names:
        sys.modules.pop(name, None)


class LazyPackageRootsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
