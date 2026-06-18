import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"


class PackagingMetadataTests(unittest.TestCase):
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
        }
        self.assertEqual(expected, scripts)


if __name__ == "__main__":
    unittest.main()
