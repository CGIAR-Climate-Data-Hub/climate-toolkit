import sys
import unittest
from pathlib import Path
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

from climate_tookit import cli

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


class CliDispatchTests(unittest.TestCase):
    def setUp(self):
        self._orig_argv = sys.argv[:]

    def tearDown(self):
        sys.argv = self._orig_argv

    def test_commands_map_mirrors_standalone_console_scripts(self):
        """Every climate-toolkit-<name> alias has a matching subcommand."""
        with PYPROJECT_PATH.open("rb") as handle:
            scripts = tomllib.load(handle)["project"]["scripts"]

        aliases = {
            name[len("climate-toolkit-"):]: target
            for name, target in scripts.items()
            if name.startswith("climate-toolkit-")
        }
        self.assertEqual(aliases, cli.COMMANDS)

    def test_no_args_prints_usage_and_succeeds(self):
        with mock.patch("builtins.print") as printer:
            self.assertEqual(0, cli.main([]))
        printed = "\n".join(str(c.args[0]) for c in printer.call_args_list)
        self.assertIn("Available commands:", printed)
        self.assertIn("fetch", printed)

    def test_help_flag_prints_usage_and_succeeds(self):
        with mock.patch("builtins.print"):
            self.assertEqual(0, cli.main(["--help"]))

    def test_unknown_command_returns_error_code(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(2, cli.main(["does-not-exist"]))

    def test_dispatch_invokes_target_main_and_forwards_args(self):
        fake_main = mock.Mock(return_value=0)
        with mock.patch("importlib.import_module") as import_module:
            import_module.return_value = mock.Mock(main=fake_main)
            rc = cli.main(["fetch", "--source", "agera_5", "--lat", "1.0"])

        self.assertEqual(0, rc)
        import_module.assert_called_once_with("climate_tookit.fetch_data.fetch_data")
        fake_main.assert_called_once_with()
        # Remaining args are forwarded to the tool's own parser via sys.argv.
        self.assertEqual(
            ["climate-toolkit fetch", "--source", "agera_5", "--lat", "1.0"],
            sys.argv,
        )

    def test_dispatch_defaults_none_return_to_zero(self):
        with mock.patch("importlib.import_module") as import_module:
            import_module.return_value = mock.Mock(main=mock.Mock(return_value=None))
            self.assertEqual(0, cli.main(["spei"]))


if __name__ == "__main__":
    unittest.main()
