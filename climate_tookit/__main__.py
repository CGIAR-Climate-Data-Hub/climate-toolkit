"""Top-level entry point for ``python -m climate_tookit``."""

from __future__ import annotations

import argparse
from typing import Sequence

from . import __version__


PUBLIC_API_NAMES = [
    "fetch_climate_data",
    "analyze_climate_statistics",
    "compare_climate_periods",
    "compare_climate_sources",
    "evaluate_hazards",
    "download_station_data",
    "compare_station_to_grids",
]

CONSOLE_SCRIPTS = [
    "climate-toolkit-fetch",
    "climate-toolkit-seasons",
    "climate-toolkit-seasons-ensemble",
    "climate-toolkit-stats",
    "climate-toolkit-stats-ensemble",
    "climate-toolkit-periods",
    "climate-toolkit-periods-ensemble",
    "climate-toolkit-hazards",
    "climate-toolkit-hazards-ensemble",
    "climate-toolkit-weather-station-download",
    "climate-toolkit-weather-station-compare",
    "climate-toolkit-compare-datasets",
    "climate-toolkit-climatology",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m climate_tookit",
        description=(
            "Climate toolkit package entry point. Use installed console scripts "
            "for task-specific CLIs, or import top-level Python API helpers."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print package version and exit",
    )
    return parser


def _format_overview() -> str:
    api_lines = "\n".join(f"  - {name}" for name in PUBLIC_API_NAMES)
    cli_lines = "\n".join(f"  - {name}" for name in CONSOLE_SCRIPTS)
    return (
        "\nTop-level Python API\n"
        f"{api_lines}\n\n"
        "Installed console scripts\n"
        f"{cli_lines}\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    print(parser.format_help().rstrip())
    print(_format_overview().rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
