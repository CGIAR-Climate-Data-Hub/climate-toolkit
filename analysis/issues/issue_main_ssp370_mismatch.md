## Summary

`climate_tookit/calculate_hazards/ensemble_hazards.py` on `main` includes `ssp370` in its default scenario list, but the active `nex_gddp` source implementation does not support `ssp370`.

This mismatch is present on:

- `origin/main`

This mismatch does **not** appear to be present on:

- `origin/staging`

`staging` uses a different default scenario list (`SSP1-2.6`, `SSP2-4.5`, `SSP5-8.5`), which aligns with active NEX alias support.

## How this was determined

This finding came from a code audit assisted by GPT-5.4 at medium reasoning effort and then manually verified by checking branch contents and comparing the default scenario list in `ensemble_hazards.py` with the active scenario validation in `nex_gddp.py`.

Audit steps:

- inspected `origin/main:climate_tookit/calculate_hazards/ensemble_hazards.py`
- inspected `origin/staging:climate_tookit/calculate_hazards/ensemble_hazards.py`
- inspected active scenario validation in `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`
- compared the default scenario list in the file against `SCENARIO_MAPPING`
- reproduced the mismatch with a minimal failing unittest

## Evidence

### `main`

`origin/main:climate_tookit/calculate_hazards/ensemble_hazards.py` contains:

```python
SCENARIOS = ['ssp126', 'ssp245', 'ssp370', 'ssp585']
```

### Active NEX support

`climate_tookit/fetch_data/source_data/sources/nex_gddp.py` supports:

- `ssp126`
- `ssp245`
- `ssp585`
- `historical`

via `SCENARIO_MAPPING`

It does **not** include:

- `ssp370`

### `staging`

`origin/staging:climate_tookit/calculate_hazards/ensemble_hazards.py` does not include `ssp370`.

Instead it defines:

```python
AVAILABLE_SCENARIOS = ['SSP1-2.6', 'SSP2-4.5', 'SSP5-8.5']
```

Those values are compatible with active alias support in `nex_gddp.py`.

## Minimal repro

Branch checked:

- `origin/main`
- `origin/staging`

Run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt matplotlib
.venv/bin/python - <<'PY'
import ast
from pathlib import Path
from climate_tookit.fetch_data.source_data.sources.nex_gddp import SCENARIO_MAPPING

path = Path('climate_tookit/calculate_hazards/ensemble_hazards.py')
mod = ast.parse(path.read_text())
scenarios = None

for node in mod.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'SCENARIOS':
                scenarios = ast.literal_eval(node.value)
                break
    if scenarios is not None:
        break

print('ensemble_hazards defaults:', scenarios)
print('nex supported keys:', sorted(SCENARIO_MAPPING.keys()))
print('unsupported defaults:', [s for s in scenarios if s not in SCENARIO_MAPPING])
PY
```

Actual result on `main`:

```text
ensemble_hazards defaults: ['ssp126', 'ssp245', 'ssp370', 'ssp585']
nex supported keys: ['SSP1-2.6', 'SSP2-4.5', 'SSP5-8.5', 'historical', 'ssp126', 'ssp245', 'ssp585']
unsupported defaults: ['ssp370']
```

### Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import ast
import unittest
from pathlib import Path
from climate_tookit.fetch_data.source_data.sources.nex_gddp import SCENARIO_MAPPING

class ScenarioMismatchReproTests(unittest.TestCase):
    def test_ensemble_default_scenarios_are_supported_by_active_nex_backend(self):
        mod = ast.parse(Path('climate_tookit/calculate_hazards/ensemble_hazards.py').read_text())
        scenarios = None
        for node in mod.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'SCENARIOS':
                        scenarios = ast.literal_eval(node.value)
                        break
            if scenarios is not None:
                break
        unsupported = [s for s in scenarios if s not in SCENARIO_MAPPING]
        self.assertEqual([], unsupported)

suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScenarioMismatchReproTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result on `main`:

```text
FAIL: test_ensemble_default_scenarios_are_supported_by_active_nex_backend
AssertionError: Lists differ: [] != ['ssp370']
```

## Expected behavior

The default scenario list in `ensemble_hazards.py` should match the scenarios supported by the active `nex_gddp` implementation.

## Actual behavior

`main` advertises `ssp370` by default even though active NEX validation does not support it.

## Why this matters

This can:

- break default hazard ensemble runs
- mislead users about supported future scenarios
- create confusion because `main` and `staging` behave differently

## Proposed fix

Either:

- remove `ssp370` from `main` default scenario list

or

- merge/adopt the corrected scenario handling already reflected in `staging`

At minimum, `main` should not advertise default scenarios that active NEX validation rejects.
