# Refactor Investigation: make `climate_tookit` behave like traditional Python package

## Status update (2026-06-19)

This note is now partly historical reference.

Already addressed on merged package-refactor work:

- `pyproject.toml` exists
- top-level `climate_tookit/__init__.py` exists
- console-script entry points exist
- packaged resource loading has install-shape tests
- major `sys.path` hacks and mixed import failures called out here have been reduced substantially
- top-level and several subpackage API surfaces are now explicit and tested

Still relevant remaining work:

- continue shrinking eager package-root imports
- keep separating stable package API from internal helper modules
- continue auditing import-time side effects and compatibility seams
- continue cleaning historical notes that describe already-fixed breakage as current state

## Bottom line

At investigation time, toolkit behaved more like repo-root script collection
with package-shaped folders than normal installable Python package.

At that point it worked mainly because:

- commands run from repository root
- `python -m climate_tookit...` adds cwd to import path
- several modules mutate `sys.path` at runtime
- some modules import siblings as bare top-level modules

Traditional package expectations then not met:

- no `pyproject.toml`
- no `setup.py` / `setup.cfg`
- no declared package data
- no console-script entry points
- no consistent relative import strategy
- no top-level `climate_tookit/__init__.py`

## Concrete findings

### 1. No packaging metadata

Repository has `requirements.txt` only. No build metadata present.

Impact:

- no standard `pip install .`
- no editable-install workflow defined
- no wheel/sdist build
- no dependency groups / optional extras

## 2. Runtime `sys.path` hacks

Examples:

- `climate_tookit/season_analysis/seasons.py`
- `climate_tookit/season_analysis/ensemble.py`
- `climate_tookit/compare_periods/periods.py`
- `climate_tookit/compare_periods/ensemble_periods.py`
- `climate_tookit/climate_statistics/ensemble_statistics.py`
- `climate_tookit/calculate_hazards/hazards.py`

These modules insert parent/project directories into `sys.path`.

Impact:

- import behavior depends on execution context
- installed-package behavior can differ from repo-root behavior
- circular-import and shadowing bugs become harder to reason about
- tests may pass locally but fail after installation

## 3. Mixed import styles

Package uses all of these patterns:

- proper absolute package imports  
  Example: `from climate_tookit.fetch_data.fetch_data import fetch_data`

- proper relative imports  
  Example: `from ..fetch_data.runtime_notes import ...`

- bare repo-root imports after `sys.path` mutation  
  Example: `from fetch_data.preprocess_data.preprocess_data import preprocess_data`

- bare package-like imports without root package name  
  Example: `import season_analysis.seasons as seasons`

Impact:

- module import path not stable
- same code may work in one module and fail in another
- refactor cost rises because import graph unclear

## 4. Script-heavy design

Many modules combine:

- reusable logic
- CLI parsing
- printing/report rendering
- filesystem save behavior

Examples with `if __name__ == "__main__"` blocks:

- `fetch_data/fetch_data.py`
- `season_analysis/seasons.py`
- `climate_statistics/statistics.py`
- `compare_periods/periods.py`
- `compare_periods/ensemble_periods.py`
- `calculate_hazards/hazards.py`
- `weather_station/download.py`

Impact:

- hard to expose stable public API
- CLI behavior and library behavior tightly coupled
- difficult to test without side effects

## 5. Top-level package incomplete

Subpackages have `__init__.py`, but top-level `climate_tookit/__init__.py` absent.

Namespace packages can work, but this is not traditional-package shape and adds ambiguity during packaging/refactor.

Impact:

- package identity less explicit
- no canonical version export
- no top-level public API surface

## 6. Package data likely to break after install unless explicitly declared

Important runtime assets:

- `climate_tookit/fetch_data/transform_data/data_dictionary.yaml`
- `climate_tookit/fetch_data/source_data/sources/utils/config.yaml`
- `climate_tookit/calculate_hazards/crop_water_balance_params.json`
- `climate_tookit/data/ggcmi_phase3/crop_calendar.parquet`
- `climate_tookit/data/ggcmi_phase3/crop_calendar_manifest.json`

Current access mostly uses file-relative paths, which is fine only if assets are included in built distribution.

Impact:

- installed wheel may import but fail at runtime when data files missing

## 7. Fallback import ladders hide packaging problems

Example pattern in `climate_statistics/statistics.py`:

- try relative import
- fall back to absolute package import
- sometimes fall back again to degraded behavior

Impact:

- import bugs become silent
- degraded runtime can look like success
- root cause harder to diagnose

## 8. Public API not clearly defined

Likely user-facing entry points exist, but package does not declare stable import surface such as:

- `climate_tookit.fetch_data.fetch_data`
- `climate_tookit.climate_statistics.analyze_climate_statistics`
- `climate_tookit.compare_periods.compare_periods`

Impact:

- downstream notebooks/scripts must import deep internal modules
- internal refactor becomes breaking change immediately

## Refactor target

Toolkit should behave like this:

1. `pip install -e .` works from clean checkout
2. `python -m climate_tookit...` works without cwd/path hacks
3. all internal imports use one style only
4. data assets ship with package
5. CLI entrypoints exposed via console scripts
6. reusable logic separated from CLI/printing layer
7. tests run against installed package shape, not only repo-root shape

## Recommended phased plan

### Phase 1. Packaging skeleton

- add `pyproject.toml`
- add top-level `climate_tookit/__init__.py`
- define build backend and core dependencies
- declare package data inclusion
- expose version string

Low risk. High leverage.

### Phase 2. Import normalization

- remove `sys.path` mutations
- convert bare imports to package-absolute imports
- keep one import style across package
- remove try/fallback ladders that only exist for path instability

This is core unblocker.

### Phase 3. CLI boundary cleanup

- keep logic in callable functions
- move argparse + printing to thin CLI wrappers
- define console scripts in `pyproject.toml`

Example desired commands:

- `climate-toolkit-fetch`
- `climate-toolkit-seasons`
- `climate-toolkit-stats`
- `climate-toolkit-periods`
- `climate-toolkit-hazards`
- `climate-toolkit-weather-station`

### Phase 4. Resource loading cleanup

- use `importlib.resources` for packaged data where practical
- otherwise keep file-relative paths but ensure package-data config covers them
- add install-shape tests for YAML/JSON/parquet resource availability

### Phase 5. API stabilization

- define supported public functions
- document stable import paths
- mark internal modules as internal

## Suggested first implementation slice

Smallest useful slice:

1. add `pyproject.toml`
2. add `climate_tookit/__init__.py`
3. include YAML/JSON/parquet package data
4. normalize imports in:
   - `season_analysis/seasons.py`
   - `season_analysis/ensemble.py`
   - `compare_periods/periods.py`
   - `compare_periods/ensemble_periods.py`
   - `calculate_hazards/hazards.py`
   - `climate_statistics/ensemble_statistics.py`
5. add smoke test that imports package from installed editable environment

## Risk notes

- `season_analysis`, `climate_statistics`, `compare_periods`, and `hazards` tightly coupled; import cleanup may surface hidden circular dependencies
- data-file packaging must be tested carefully because GGCMI parquet is runtime-critical
- current dirty worktree means package refactor should land as focused branch, not mixed with ongoing feature work

## Recommendation

Treat this as major structural issue, not cleanup chore.

Best next move:

- open dedicated issue
- do packaging skeleton + import normalization first
- avoid more feature additions that deepen path-coupled patterns until this base fixed
