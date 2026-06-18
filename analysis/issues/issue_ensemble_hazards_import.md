## Summary

Status note:

- this document captures root issue as observed on `origin/main` and `origin/staging`
- later refactor work improved package import contracts and added dedicated import-hygiene coverage on refactor branch
- keep this note as historical branch evidence, not current-state description for `codex/package-refactor-issue-10c`

`climate_tookit.calculate_hazards.ensemble_hazards` is not reliably importable under normal package execution because it still depends on `sys.path` mutation and top-level imports (`preprocess_data`, `utils.models`, `hazards`) instead of consistent package-relative imports.

Confirmed on both:

- `origin/main`
- `origin/staging`

## How this was determined

This finding came from a code audit assisted by GPT-5.4 and then manually verified by tracing the active import path in the repository and checking both `main` and `staging`.

Audit steps:
- inspected import setup in `climate_tookit/calculate_hazards/ensemble_hazards.py`
- traced top-level imports pulled in via `sys.path.insert(...)`
- verified that dependent modules now rely on package-relative import context
- reproduced failure with a minimal package import test
- checked `origin/main` and `origin/staging` to confirm the issue exists on both branches

## Minimal repro

Branch checked:
- `origin/main`
- `origin/staging`

Create a minimal import test:

```python
# tests/test_import_repro.py
import importlib
import unittest

class ImportReproTests(unittest.TestCase):
    def test_ensemble_hazards_importable_as_package(self):
        importlib.import_module("climate_tookit.calculate_hazards.ensemble_hazards")

if __name__ == "__main__":
    unittest.main()
```

Create a clean environment and run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt matplotlib
python -m unittest tests/test_import_repro.py -v
```

Actual result:

```text
ImportError: attempted relative import with no known parent package
```

Expected result:
- `climate_tookit.calculate_hazards.ensemble_hazards` imports successfully under normal package execution

## Evidence

`climate_tookit/calculate_hazards/ensemble_hazards.py` currently:
- mutates `sys.path`
- imports `hazards` as a top-level module
- imports `preprocess_data` as a top-level module
- imports `utils.models` as a top-level module

This makes import behavior depend on execution context rather than package structure.

## Why this matters

This causes brittle behavior in:
- unit tests
- package-style imports
- CI
- notebook/library usage
- any execution path that does not exactly match the script-oriented `sys.path` assumptions

## Proposed fix

- replace `sys.path`-dependent imports with package-relative imports
- make `calculate_hazards` importable as part of normal `climate_tookit` package execution
- keep CLI entrypoints working without requiring alternate module identities
