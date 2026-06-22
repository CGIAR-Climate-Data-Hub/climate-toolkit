import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, script_name: str) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / f"{script_name}.exe"
    return venv_dir / "bin" / script_name


class DistributionArtifactSmokeTests(unittest.TestCase):
    def _build_artifacts(self, dist_dir: Path) -> tuple[Path, Path]:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(dist_dir),
            ],
            cwd=REPO_ROOT,
            env=_base_env(),
            text=True,
            capture_output=True,
            check=True,
        )

        wheels = sorted(dist_dir.glob("climate_tookit-*.whl"))
        sdists = sorted(dist_dir.glob("climate_tookit-*.tar.gz"))
        self.assertEqual(1, len(wheels), wheels)
        self.assertEqual(1, len(sdists), sdists)
        return wheels[0], sdists[0]

    def _create_temp_venv(self, target_dir: Path) -> Path:
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(target_dir)
        return _venv_python(target_dir)

    def _install_artifact(self, python_path: Path, artifact_path: Path) -> None:
        install_cmd = [str(python_path), "-m", "pip", "install", str(artifact_path)]

        subprocess.run(
            install_cmd,
            cwd=REPO_ROOT,
            env=_base_env(),
            text=True,
            capture_output=True,
            check=True,
        )

    def _assert_installed_contract(self, venv_dir: Path) -> None:
        python_path = _venv_python(venv_dir)
        code = """
import climate_tookit
assert callable(climate_tookit.fetch_climate_data)
print(climate_tookit.__version__)
""".strip()
        result = subprocess.run(
            [str(python_path), "-c", code],
            cwd=venv_dir,
            env=_base_env(),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertTrue(result.stdout.strip())

        fetch_script = _venv_script(venv_dir, "climate-toolkit-fetch")
        self.assertTrue(fetch_script.exists(), fetch_script)
        help_result = subprocess.run(
            [str(fetch_script), "--help"],
            cwd=venv_dir,
            env=_base_env(),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("Fetch climate data", help_result.stdout)

    def test_build_produces_wheel_and_sdist_with_expected_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir) / "dist"
            dist_dir.mkdir()
            wheel_path, sdist_path = self._build_artifacts(dist_dir)

            with zipfile.ZipFile(wheel_path) as archive:
                names = archive.namelist()
            self.assertIn("climate_tookit/__init__.py", names)
            self.assertTrue(any(name.endswith("entry_points.txt") for name in names))
            self.assertTrue(any(name.endswith("METADATA") for name in names))
            self.assertTrue(
                any(
                    name.endswith("fetch_data/source_data/sources/utils/config.yaml")
                    for name in names
                )
            )

            with tarfile.open(sdist_path, "r:gz") as archive:
                sdist_names = archive.getnames()
            self.assertTrue(any(name.endswith("pyproject.toml") for name in sdist_names))
            self.assertTrue(any(name.endswith("README.md") for name in sdist_names))
            self.assertTrue(any(name.endswith("LICENSE") for name in sdist_names))

    def test_wheel_install_smoke_works_in_fresh_venv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dist_dir = tmp_path / "dist"
            dist_dir.mkdir()
            wheel_path, _ = self._build_artifacts(dist_dir)
            venv_dir = tmp_path / "wheel-venv"
            python_path = self._create_temp_venv(venv_dir)
            self._install_artifact(python_path, wheel_path)
            self._assert_installed_contract(venv_dir)

    def test_sdist_install_smoke_works_in_fresh_venv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dist_dir = tmp_path / "dist"
            dist_dir.mkdir()
            _, sdist_path = self._build_artifacts(dist_dir)
            venv_dir = tmp_path / "sdist-venv"
            python_path = self._create_temp_venv(venv_dir)
            self._install_artifact(python_path, sdist_path)
            self._assert_installed_contract(venv_dir)


if __name__ == "__main__":
    unittest.main()
