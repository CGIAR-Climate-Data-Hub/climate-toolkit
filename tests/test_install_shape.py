import os
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


class InstallShapeSmokeTests(unittest.TestCase):
    def test_package_import_works_outside_repo_root(self):
        code = """
import climate_tookit
assert callable(climate_tookit.fetch_climate_data)
assert callable(climate_tookit.analyze_climate_statistics)
print(climate_tookit.__version__)
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=tmpdir,
                env=_base_env(),
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertTrue(result.stdout.strip())

    def test_module_cli_help_works_outside_repo_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-m", "climate_tookit.fetch_data.fetch_data", "--help"],
                cwd=tmpdir,
                env=_base_env(),
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertIn("Fetch climate data", result.stdout)

    def test_console_script_help_works_outside_repo_root(self):
        script_dir = Path(sysconfig.get_path("scripts"))
        script_path = script_dir / "climate-toolkit-fetch"
        if sys.platform.startswith("win"):
            script_path = script_dir / "climate-toolkit-fetch.exe"
        self.assertTrue(script_path.exists(), f"missing console script {script_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [str(script_path), "--help"],
                cwd=tmpdir,
                env=_base_env(),
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertIn("Fetch climate data", result.stdout)


if __name__ == "__main__":
    unittest.main()
