import unittest
import importlib
import inspect
import io
import contextlib
from pathlib import Path
from typing import get_type_hints

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"


class PackagingMetadataTests(unittest.TestCase):
    INTERNAL_HELPER_ENTRYPOINTS = {
        "climate_tookit.fetch_data.source_data.source_data:main",
        "climate_tookit.fetch_data.preprocess_data.preprocess_data:main",
        "climate_tookit.fetch_data.transform_data.transform_data:main",
        "climate_tookit.fetch_data.gee_xee_batch:main",
        "climate_tookit.fetch_data.nex_gddp_batch:main",
        "climate_tookit.fetch_data.cache_inventory:main",
    }
    INTERNAL_HELPER_PACKAGE_EXPORTS = {
        "climate_tookit.fetch_data.preprocess_data": {
            "run_preprocess_data",
            "run_preprocess_transformed_data",
        },
        "climate_tookit.fetch_data.transform_data": {
            "default_variables",
            "load_variable_mappings",
            "run_transform_data",
        },
        "climate_tookit.fetch_data.source_data": {
            "SourceData",
        },
        "climate_tookit.fetch_data.source_data.sources.utils": {
            "Settings",
            "ClimateDataset",
            "ClimateVariable",
            "parse_variable_token",
            "canonical_climate_variable_name",
        },
    }
    EXPLICIT_SUBPACKAGE_EXPORTS = {
        "climate_tookit.calculate_hazards": {"calculate_hazards"},
        "climate_tookit.climate_statistics": {"analyze_climate_statistics"},
        "climate_tookit.compare_datasets": {"compare_sources", "print_report"},
        "climate_tookit.compare_periods": {"compare"},
        "climate_tookit.crop_calendar": {
            "asset_available",
            "extract_point_calendar",
            "load_calendar_manifest",
            "load_calendar_table",
            "normalize_crop_name",
            "resolve_calendar_preset",
            "supported_crop_names",
        },
        "climate_tookit.fetch_data": {
            "Site",
            "fetch_climate_data",
            "fetch_gee_xee_batch_data",
            "fetch_nex_gddp_batch_data",
            "load_sites",
            "parse_site_spec",
            "run_batch_extraction",
            "run_gee_xee_batch_extraction",
        },
        "climate_tookit.season_analysis": {
            "detect_onset_cessation",
            "fetch_and_analyze_years",
            "fetch_and_analyze_years_fixed",
            "parse_fixed_seasons",
        },
        "climate_tookit.weather_station": {
            "compare_station_to_grids",
            "fetch_ghcn_daily_records",
            "fetch_gsod_records",
            "load_ghcn_inventory",
            "load_ghcn_stations",
            "render_compare_report",
            "select_ghcn_station",
        },
    }

    def test_pyproject_runtime_dependencies_cover_requirements_runtime_set(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)
        pyproject_deps = set(pyproject["project"]["dependencies"])

        requirement_lines = []
        with REQUIREMENTS_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                requirement_lines.append(stripped)

        runtime_requirements = {
            line
            for line in requirement_lines
            if not line.startswith("setuptools")
            and line != "wheel"
        }

        self.assertEqual(runtime_requirements, pyproject_deps)

    def test_pyproject_declares_console_scripts_for_current_module_clis(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)

        scripts = pyproject["project"]["scripts"]
        expected = {
            "climate-toolkit": "climate_tookit.__main__:main",
            "climate-toolkit-fetch": "climate_tookit.fetch_data.fetch_data:main",
            "climate-toolkit-seasons": "climate_tookit.season_analysis.seasons:main",
            "climate-toolkit-seasons-ensemble": "climate_tookit.season_analysis.ensemble:main",
            "climate-toolkit-stats": "climate_tookit.climate_statistics.statistics:main",
            "climate-toolkit-stats-ensemble": "climate_tookit.climate_statistics.ensemble_statistics:main",
            "climate-toolkit-periods": "climate_tookit.compare_periods.periods:main",
            "climate-toolkit-periods-ensemble": "climate_tookit.compare_periods.ensemble_periods:main",
            "climate-toolkit-hazards": "climate_tookit.calculate_hazards.hazards:main",
            "climate-toolkit-hazards-ensemble": "climate_tookit.calculate_hazards.ensemble_hazards:main",
            "climate-toolkit-weather-station-download": "climate_tookit.weather_station.download:main",
            "climate-toolkit-weather-station-compare": "climate_tookit.weather_station.compare:main",
            "climate-toolkit-compare-datasets": "climate_tookit.compare_datasets.compare_datasets:main",
            "climate-toolkit-climatology": "climate_tookit.climatology.long_term_climatology:main",
        }
        self.assertEqual(expected, scripts)

    def test_pyproject_declares_optional_dependency_groups_for_truly_optional_features(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)

        project = pyproject["project"]
        core_deps = set(project["dependencies"])
        extras = project["optional-dependencies"]

        self.assertNotIn("tabulate==0.9.0", core_deps)
        self.assertTrue(all("matplotlib" not in dep for dep in core_deps))
        self.assertEqual(["matplotlib>=3.8"], extras["plot"])
        self.assertEqual(["tabulate==0.9.0"], extras["tables"])
        self.assertEqual(
            ["matplotlib>=3.8", "tabulate==0.9.0"],
            extras["full"],
        )

    def test_console_script_modules_expose_main_as_int_returning_entrypoint(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)

        scripts = pyproject["project"]["scripts"]
        for entrypoint in scripts.values():
            module_name, function_name = entrypoint.split(":")
            with self.subTest(entrypoint=entrypoint):
                module = importlib.import_module(module_name)
                entrypoint_fn = getattr(module, function_name)
                self.assertTrue(callable(entrypoint_fn))
                self.assertEqual(int, get_type_hints(entrypoint_fn).get("return"))

    def test_internal_helper_clis_are_not_promoted_as_public_console_scripts(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)

        scripts = set(pyproject["project"]["scripts"].values())
        self.assertTrue(self.INTERNAL_HELPER_ENTRYPOINTS.isdisjoint(scripts))

    def test_top_level_package_exposes_stable_public_api(self):
        package = importlib.import_module("climate_tookit")
        self.assertTrue(hasattr(package, "__version__"))
        self.assertIsInstance(package.__version__, str)

        expected_exports = {
            "fetch_climate_data",
            "analyze_climate_statistics",
            "compare_climate_sources",
            "compare_climate_periods",
            "evaluate_hazards",
            "download_station_data",
            "compare_station_to_grids",
        }
        self.assertTrue(expected_exports.issubset(set(package.__all__)))

        for export_name in expected_exports:
            with self.subTest(export=export_name):
                exported = getattr(package, export_name)
                self.assertTrue(callable(exported))
                self.assertIn(export_name, dir(package))

    def test_top_level_module_entrypoint_prints_package_overview(self):
        module = importlib.import_module("climate_tookit.__main__")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = module.main([])

        rendered = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Climate toolkit package entry point", rendered)
        self.assertIn("Top-level Python API", rendered)
        self.assertIn("Installed console scripts", rendered)
        self.assertIn("climate-toolkit", rendered)
        self.assertIn("climate-toolkit-fetch", rendered)
        self.assertIn("fetch_climate_data", rendered)

    def test_main_public_subpackages_have_explicit_init_and_lazy_exports(self):
        for module_name, expected_exports in self.EXPLICIT_SUBPACKAGE_EXPORTS.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                module_path = Path(inspect.getfile(module))
                self.assertEqual("__init__.py", module_path.name)
                self.assertTrue(expected_exports.issubset(set(getattr(module, "__all__", []))))
                for export_name in expected_exports:
                    exported = getattr(module, export_name)
                    self.assertTrue(callable(exported))
                    self.assertIn(export_name, dir(module))

    def test_internal_helper_packages_remain_importable_under_installed_package_shape(self):
        for module_name, expected_exports in self.INTERNAL_HELPER_PACKAGE_EXPORTS.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                module_path = Path(inspect.getfile(module))
                self.assertEqual("__init__.py", module_path.name)
                self.assertTrue(expected_exports.issubset(set(getattr(module, "__all__", []))))
                for export_name in expected_exports:
                    exported = getattr(module, export_name)
                    self.assertIsNotNone(exported)
                    self.assertIn(export_name, dir(module))


if __name__ == "__main__":
    unittest.main()
