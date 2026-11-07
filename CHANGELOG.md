# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [0.2.1](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/compare/v0.2.0...v0.2.1) (2026-11-07)


### Documentation

* correct AIMS RIC partner branding ([#191](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/191)) ([b55f84d](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/b55f84d46c536c97ae751d87cf99b88d1e4ec432))

## [0.2.0](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/compare/v0.1.0...v0.2.0) (2026-11-05)


### Added

* add no-GEE CHIRPS/CHIRTS backends and harden full pipeline ([#181](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/181)) ([0beffcd](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/0beffcd231b25ec0de5030d9040e60e062ac8451))
* **examples:** Adaptation Benefit (AB) analysis in the ERA LTE notebook ([#174](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/174)) ([e2900e3](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/e2900e3d8c32943abb6faaf1315720c3002e46dc))
* **examples:** add lte_id + code identifiers to the ERA rainfall-validation output ([#157](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/157)) ([5b68058](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/5b68058b9290a217275096ae46851aa86f6b5342))
* **examples:** drop multi-year-aggregate yields and add --min-year to the ERA yield analysis ([#169](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/169)) ([eda22b9](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/eda22b9944caeda7b980c84c07bb4a9a558f23b5))
* **examples:** variety markers on multi-site plots, first-year marker for single-variety sites, drop ERA rain_rain_sum validation ([#172](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/172)) ([0456d63](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/0456d6320fa6805a80ad1cb927f9dee3f3d67492))
* **viz:** shared visualization foundation; refactor ERA yield plots onto it ([#159](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/159)) ([d0d5b7e](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/d0d5b7efd0abab0a0169b72f313087af5188a257))


### Fixed

* clarify ERA5-Land sources and synchronize release versions ([#188](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/188)) ([965c0ce](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/965c0cee8a7c87f4ad5b1886abf2613e245d3b56))
* **examples:** Colab setup cell — %cd broke on an inline comment ([#166](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/166)) ([c80a44a](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/c80a44a84bbd9f16ac14ef39c42ee92fb067d8ec))
* **examples:** ERA notebook fails in VS Code — !python has no interpreter on macOS ([#170](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/170)) ([d6726ff](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/d6726ff3bae48ddb6f29abfb798c1302e1a342fc))
* **examples:** put the cloned repo on sys.path in the yield-plot scripts so climate_toolkit.visualization resolves on Colab ([#161](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/161)) ([296095e](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/296095ed988709147a7d9932f1dd15129189a56d))
* **hazards:** thread model/scenario through calculate_hazards and default NEX-GDDP to historical before 2015 ([#182](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/182)) ([36e6182](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/36e6182e2e27248fd8ae3d26830248b080faae9d))


### Changed

* **viz:** climatology plots save through the shared save_figure helper ([#184](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/184)) ([38463dc](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/38463dc081ca005cc5eea6cd51cb51841a653376))


### Documentation

* add Outputs by module reference (closes [#115](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/115)); fix RELEASING.md link ([#171](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/171)) ([e1524b5](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/e1524b53a976b5fbe7f6621de20c1fcf77fedbdb))
* **examples:** add title + Colab badge header to ERA LTE notebook, install from PyPI ([#155](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/155)) ([02db89e](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/02db89eddcd4f724560161c20ab47231af746048))
* **examples:** drop the author byline from the ERA notebook intro ([#187](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/187)) ([7dc1841](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/7dc1841eb54320bd0351ac082cb271bac9ad40e3))
* **examples:** ERA LTE Colab notebook ([#152](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/152)) ([16f6b5b](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/16f6b5b6a2c4c1a045816c86d9766c43efb8b54b))
* **examples:** ERA notebook round-2 (Rwema) — env-aware setup, quiet output, drop section 6, mark crop-variety changes on yield plots ([#165](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/165)) ([17f73a4](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/17f73a462eb58885163e18ca3eeaeb55c1aca0be))
* **examples:** list the available yield-trend sites in the ERA LTE notebook ([#162](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/162)) ([78506be](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/78506be89be2c7a2565b6636f39fb9e6fe8ff24b))
* **examples:** lte_final.csv preview + safe GEE defaults in the ERA LTE notebook ([#156](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/156)) ([d753ae6](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/d753ae6c1e08cf3c21c619b73c323ee86b3bc341))
* **examples:** replace ERA LTE notebook with Rwema's Release 2026.1 version ([#186](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/186)) ([cdd80e3](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/cdd80e33fd58ca7c6c303a0a7be28098261a9293))
* **examples:** Rwema's ERA yield-section edits (era_5 comparison + Zimuto site) ([#163](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/163)) ([b8239ea](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/b8239ea04e254feb1bb4a640fe8fb2ac4062e343))
* point install instructions at the published PyPI package ([#153](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/153)) ([6532f6e](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/commit/6532f6efa3b1160cf1216d37f73204d84bb29771))

## [Unreleased]

### Changed

- **ERA5-Land source naming:** use `era5_land` in new code. The former
  `agera_5` and `agera5` string keys remain compatible through 0.2.x and emit
  a deprecation warning. Defaults, reports, CLI help and web forms now use
  ERA5-Land. Existing enum, configuration and module aliases are retained.
  The adapter has always read `ECMWF/ERA5_LAND/DAILY_AGGR`, not the separate
  Copernicus AgERA5 product. The dataset, units and existing cache contents
  are unchanged; existing cache paths are reused. Earth Engine access is
  still required for this source. ([#188](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/pull/188))

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
