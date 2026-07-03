"""Unified ``climate-toolkit`` command-line entry point.

Historically every tool shipped as its own console script
(``climate-toolkit-fetch``, ``climate-toolkit-seasons``, ...). This module
adds a single ``climate-toolkit`` dispatcher so the tools can also be invoked
as subcommands, e.g.::

    climate-toolkit fetch --source agera_5 ...
    climate-toolkit hazards Maize ...
    climate-toolkit --help            # lists all available commands

Each subcommand simply hands the remaining arguments to the corresponding
module's ``main()``, which keeps its own argument parser. That means
``climate-toolkit fetch --help`` shows the real ``fetch`` options (not a
generic wrapper help), and the standalone ``climate-toolkit-*`` scripts remain
available as aliases for backward compatibility.
"""

from __future__ import annotations

import importlib
import sys
from typing import List, Optional

# Subcommand name -> "module:function". The subcommand names mirror the
# ``climate-toolkit-<name>`` console scripts declared in pyproject.toml.
COMMANDS = {
    "gee-check": "climate_tookit.gee_check:main",
    "fetch": "climate_tookit.fetch_data.fetch_data:main",
    "seasons": "climate_tookit.season_analysis.seasons:main",
    "seasons-ensemble": "climate_tookit.season_analysis.ensemble:main",
    "stats": "climate_tookit.climate_statistics.statistics:main",
    "stats-ensemble": "climate_tookit.climate_statistics.ensemble_statistics:main",
    "periods": "climate_tookit.compare_periods.periods:main",
    "periods-ensemble": "climate_tookit.compare_periods.ensemble_periods:main",
    "hazards": "climate_tookit.calculate_hazards.hazards:main",
    "hazards-ensemble": "climate_tookit.calculate_hazards.ensemble_hazards:main",
    "weather-station-download": "climate_tookit.weather_station.download:main",
    "weather-station-compare": "climate_tookit.weather_station.compare:main",
    "compare-datasets": "climate_tookit.compare_datasets.compare_datasets:main",
    "climatology": "climate_tookit.climatology.long_term_climatology:main",
    "spei": "climate_tookit.climatology.spei:main",
    "xclim-reference": "climate_tookit.climatology.xclim_reference:main",
}


def _usage() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = [
        "usage: climate-toolkit <command> [options]",
        "",
        "Available commands:",
    ]
    for name, target in COMMANDS.items():
        lines.append(f"  {name.ljust(width)}  ({target.split(':')[0]})")
    lines += [
        "",
        "Run 'climate-toolkit <command> --help' for command-specific options.",
        "Each command is also available as a standalone 'climate-toolkit-<command>' script.",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return 0

    command = argv[0]
    if command not in COMMANDS:
        sys.stderr.write(f"climate-toolkit: unknown command '{command}'\n\n")
        sys.stderr.write(_usage() + "\n")
        return 2

    module_path, func_name = COMMANDS[command].split(":")
    func = getattr(importlib.import_module(module_path), func_name)

    # Hand the remaining arguments to the tool's own parser via sys.argv so
    # that the command behaves exactly like its standalone script, including
    # its native --help output.
    sys.argv = [f"climate-toolkit {command}", *argv[1:]]
    result = func()
    return int(result) if result is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
