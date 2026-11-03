# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-07

### Changed

- **BREAKING:** renamed the package from `climate_tookit` to
  `climate_toolkit` (typo fix) ahead of first PyPI publication.
  Update imports (`import climate_toolkit`) and install commands
  (`pip install climate-toolkit`). Console script names are unchanged.

### Added

- NumPy-style docstrings for all seven public API functions and a
  package-level `help()` index.
- MkDocs documentation site with auto-generated API reference.
- `examples/basic_usage.py` walkthrough script.

## [0.1.0a0]

Initial alpha. Functional Python API (`fetch_climate_data`,
`analyze_climate_statistics`, `evaluate_hazards`, `compare_climate_periods`,
`compare_climate_sources`, `download_station_data`,
`compare_station_to_grids`), unified `climate-toolkit` CLI, human and
livestock heat-stress metrics, weather-station validation, and NEX-GDDP
projection support.
