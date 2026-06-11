## Summary

`climate_tookit.climate_statistics.statistics` and `climate_tookit.climatology.long_term_climatology` import successfully under normal package execution, but silently disable their core preprocessing pipeline by setting `PREPROCESS_AVAILABLE = False`.

This happens because both modules rely on `sys.path` mutation plus top-level imports like `from preprocess_data import preprocess_data` instead of package-relative imports.

Confirmed on:

- `origin/main`
- `origin/staging`

## How this was determined

This finding came from a code audit assisted by GPT-5.4 and then manually verified by tracing the import path and reproducing the behavior locally.

Audit steps:

- inspected import setup in `climate_tookit/climate_statistics/statistics.py`
- inspected import setup in `climate_tookit/climatology/long_term_climatology.py`
- verified both modules mutate `sys.path` and then attempt top-level imports
- imported both modules under normal package execution
- confirmed both modules set `PREPROCESS_AVAILABLE = False`
- reproduced failure with a minimal unittest
- checked `origin/main` and `origin/staging` to confirm the same import pattern exists there

## Evidence

### `statistics.py`

`climate_tookit/climate_statistics/statistics.py`:

- appends `fetch_data/preprocess_data` and `season_analysis` to `sys.path`
- tries `from preprocess_data import preprocess_data`
- if import fails, sets:

```python
PREPROCESS_AVAILABLE = False
print("Warning: preprocess_data pipeline not available")
```

### `long_term_climatology.py`

`climate_tookit/climatology/long_term_climatology.py`:

- inserts `fetch_data/preprocess_data` and `fetch_data/source_data/sources` into `sys.path`
- tries `from preprocess_data import preprocess_data`
- if import fails, sets:

```python
PREPROCESS_AVAILABLE = False
print("Warning: Preprocessing pipeline not available")
```

So package import can appear to succeed while critical functionality is already disabled.

## Minimal repro

Branch checked:

- `origin/main`
- `origin/staging`

Create a clean environment and run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt matplotlib
.venv/bin/python - <<'PY'
import importlib

mods = [
    ('climate_tookit.climate_statistics.statistics', 'PREPROCESS_AVAILABLE'),
    ('climate_tookit.climatology.long_term_climatology', 'PREPROCESS_AVAILABLE'),
]

for mod_name, flag in mods:
    mod = importlib.import_module(mod_name)
    print(mod_name, getattr(mod, flag, None))
PY
```

Actual result:

```text
Warning: preprocess_data pipeline not available
climate_tookit.climate_statistics.statistics False
Warning: Preprocessing pipeline not available
climate_tookit.climatology.long_term_climatology False
```

### Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import unittest
import importlib

class DegradedImportReproTests(unittest.TestCase):
    def test_statistics_preprocess_pipeline_available_under_package_import(self):
        mod = importlib.import_module('climate_tookit.climate_statistics.statistics')
        self.assertTrue(mod.PREPROCESS_AVAILABLE)

    def test_climatology_preprocess_pipeline_available_under_package_import(self):
        mod = importlib.import_module('climate_tookit.climatology.long_term_climatology')
        self.assertTrue(mod.PREPROCESS_AVAILABLE)

suite = unittest.defaultTestLoader.loadTestsFromTestCase(DegradedImportReproTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result:

```text
FAIL: test_climatology_preprocess_pipeline_available_under_package_import
AssertionError: False is not true

FAIL: test_statistics_preprocess_pipeline_available_under_package_import
AssertionError: False is not true
```

## Expected behavior

Under normal package import:

- `climate_tookit.climate_statistics.statistics` should have `PREPROCESS_AVAILABLE = True`
- `climate_tookit.climatology.long_term_climatology` should have `PREPROCESS_AVAILABLE = True`
- no fallback warning should be emitted for core pipeline imports

## Actual behavior

The modules import, but their core preprocessing dependency is silently disabled during package import.

## Why this matters

This is brittle and misleading for:

- unit tests
- notebooks
- package-style imports
- CI
- downstream code that assumes successful import means the module is operational

Instead of failing fast, the modules degrade into a warning state and can later fail deeper into execution.

## Proposed fix

- replace `sys.path`-dependent top-level imports with package-relative imports
- make preprocessing imports fail cleanly if package structure is broken
- ensure successful module import means the core preprocessing pipeline is actually available
