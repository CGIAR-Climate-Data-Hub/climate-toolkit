import unittest
import importlib
import inspect
from pathlib import Path
from typing import get_type_hints

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"
README_PATH = REPO_ROOT / "README.md"
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-cd.yml"


class PackagingMetadataTests(unittest.TestCase):
    INTERNAL_HELPER_ENTRYPOINTS = {
        "climate_tookit.fetch_data.source_data.source_data:main",
        "climate_tookit.fetch_data.preprocess_data.preprocess_data:main",
        "climate_tookit.fetch_data.transform_data.transform_data:main",
        "climate_tookit.fetch_data.gee_xee_batch:main",
        "climate_tookit.fetch_data.nex_gddp_batch:main",
        "climate_tookit.fetch_data.cache_inventory:main",
    }
    EXPLICIT_SUBPACKAGE_EXPORTS = {
        "climate_tookit.calculate_hazards": {"calculate_hazards"},
        "climate_tookit.climate_statistics": {"analyze_climate_statistics"},
        "climate_tookit.compare_datasets": {"compare_sources", "print_report"},
        "climate_tookit.compare_periods": {"compare"},
        "climate_tookit.crop_calendar": {
            "extract_point_calendar",
            "get_crop_support",
            "normalize_crop_name",
            "resolve_calendar_preset",
        },
        "climate_tookit.fetch_data": {
            "Site",
            "fetch_gee_xee_batch_data",
            "fetch_nex_gddp_batch_data",
            "load_sites",
            "parse_site_spec",
        },
        "climate_tookit.season_analysis": {
            "detect_onset_cessation",
            "fetch_and_analyze_years",
            "fetch_and_analyze_years_fixed",
            "parse_fixed_seasons",
        },
        "climate_tookit.weather_station": {
            "compare_station_to_grids",
            "download_station_data",
            "render_compare_report",
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

    def test_uv_lockfile_exists_for_preferred_install_workflow(self):
        self.assertTrue(UV_LOCK_PATH.exists())
        self.assertGreater(UV_LOCK_PATH.stat().st_size, 0)

    def test_readme_documents_uv_as_locked_preferred_workflow_with_pip_fallback(self):
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("Preferred setup with `uv`", readme)
        self.assertIn("uv sync --locked --group dev", readme)
        self.assertIn("uv lock", readme)
        self.assertIn("Fallback setup with `venv + pip`", readme)
        self.assertIn("python -m pip install -e .", readme)

    def test_ci_uses_locked_uv_sync(self):
        ci_workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("uv sync --locked --group dev", ci_workflow)

    def test_pyproject_declares_console_scripts_for_current_module_clis(self):
        with PYPROJECT_PATH.open("rb") as handle:
            pyproject = tomllib.load(handle)

        scripts = pyproject["project"]["scripts"]
        expected = {
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

    def test_fetch_data_package_root_keeps_internal_run_helpers_off_public_all(self):
        module = importlib.import_module("climate_tookit.fetch_data")
        public_exports = set(getattr(module, "__all__", []))
        self.assertNotIn("run_gee_xee_batch_extraction", public_exports)
        self.assertNotIn("run_batch_extraction", public_exports)

        self.assertTrue(callable(getattr(module, "run_gee_xee_batch_extraction")))
        self.assertTrue(callable(getattr(module, "run_batch_extraction")))

    def test_fetch_data_package_root_does_not_advertise_shadow_prone_fetch_entrypoint(self):
        module = importlib.import_module("climate_tookit.fetch_data")
        public_exports = set(getattr(module, "__all__", []))
        self.assertNotIn("fetch_data", public_exports)

    def test_weather_station_package_root_keeps_backend_helpers_off_public_all(self):
        module = importlib.import_module("climate_tookit.weather_station")
        public_exports = set(getattr(module, "__all__", []))

        self.assertNotIn("fetch_ghcn_daily_records", public_exports)
        self.assertNotIn("fetch_gsod_records", public_exports)
        self.assertNotIn("load_ghcn_inventory", public_exports)
        self.assertNotIn("load_ghcn_stations", public_exports)
        self.assertNotIn("select_ghcn_station", public_exports)

        self.assertTrue(callable(getattr(module, "fetch_ghcn_daily_records")))
        self.assertTrue(callable(getattr(module, "fetch_gsod_records")))

    def test_internal_source_utils_root_does_not_advertise_logging_side_effect_helper(self):
        module = importlib.import_module(
            "climate_tookit.fetch_data.source_data.sources.utils"
        )
        public_exports = set(getattr(module, "__all__", []))
        self.assertNotIn("set_logging", public_exports)
        self.assertTrue(callable(getattr(module, "set_logging")))


if __name__ == "__main__":
    unittest.main()
