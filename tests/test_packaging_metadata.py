import tomllib
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
