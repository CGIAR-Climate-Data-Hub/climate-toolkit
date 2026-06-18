import unittest
from importlib.resources import files

from climate_tookit.calculate_hazards.hazards import load_crop_water_balance_params
from climate_tookit.crop_calendar import ggcmi
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings
from climate_tookit.fetch_data.transform_data.transform_data import load_variable_mappings


class PackageResourceTests(unittest.TestCase):
    def test_resource_files_present_via_package_loader(self):
        checks = [
            (
                "climate_tookit.calculate_hazards",
                "crop_water_balance_params.json",
            ),
            (
                "climate_tookit.fetch_data.transform_data",
                "data_dictionary.yaml",
            ),
            (
                "climate_tookit.fetch_data.source_data.sources.utils",
                "config.yaml",
            ),
            (
                "climate_tookit.data.ggcmi_phase3",
                "crop_calendar.parquet",
            ),
            (
                "climate_tookit.data.ggcmi_phase3",
                "crop_calendar_manifest.json",
            ),
        ]
        for package_name, resource_name in checks:
            with self.subTest(package=package_name, resource=resource_name):
                resource = files(package_name).joinpath(resource_name)
                self.assertTrue(resource.is_file(), f"missing resource {package_name}:{resource_name}")

    def test_crop_water_balance_params_load_from_packaged_json(self):
        params = load_crop_water_balance_params()
        self.assertIn("Maize", params)
        self.assertIn("kc_mid", params["Maize"])

    def test_variable_mappings_load_from_packaged_yaml(self):
        mappings = load_variable_mappings()
        self.assertIsInstance(mappings, dict)
        self.assertTrue(mappings)

    def test_settings_load_from_packaged_yaml(self):
        settings = Settings.load()
        self.assertEqual("daily", settings.chirps_v2.cadence)
        self.assertEqual("daily", settings.nex_gddp.cadence)

    def test_ggcmi_manifest_loads_from_packaged_data(self):
        manifest = ggcmi.load_calendar_manifest()
        self.assertIn("calendar_versions", manifest)
        self.assertTrue(manifest["calendar_versions"])


if __name__ == "__main__":
    unittest.main()
