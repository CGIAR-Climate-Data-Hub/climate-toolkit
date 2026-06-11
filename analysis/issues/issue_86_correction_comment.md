Correction after second branch check:

This mismatch reproduces on `origin/main`, but I do **not** now see same mismatch on `origin/staging`.

## Updated branch scope

Affected:
- `origin/main`

Not currently affected:
- `origin/staging`

## What changed in evaluation

Initial issue body said mismatch was present on both `main` and `staging`. After deeper follow-up review, including direct branch inspection, `staging` appears to already have different scenario handling in `climate_tookit/calculate_hazards/ensemble_hazards.py`.

On `origin/main`, `ensemble_hazards.py` includes:

```python
SCENARIOS = ['ssp126', 'ssp245', 'ssp370', 'ssp585']
```

On `origin/staging`, file instead defines:

```python
AVAILABLE_SCENARIOS = ['SSP1-2.6', 'SSP2-4.5', 'SSP5-8.5']
```

That `staging` list aligns with active alias support in `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`, so `ssp370` mismatch reported here appears to be `main`-only.

## How this was determined

This re-check was assisted by GPT-5.4 at medium reasoning effort, then manually verified by inspecting branch contents and comparing:
- `origin/main:climate_tookit/calculate_hazards/ensemble_hazards.py`
- `origin/staging:climate_tookit/calculate_hazards/ensemble_hazards.py`
- active scenario validation in `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`

## Minimal repro for `main`

```bash
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
