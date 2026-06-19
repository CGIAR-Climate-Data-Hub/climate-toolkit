Status note:

- historical branch note
- later package-refactor work removed stale availability-flag fallback pattern
- import contract now better represented by package/import-hygiene tests than by `PREPROCESS_AVAILABLE` flag checks alone

Branch fix now exists on `codex-nex-gddp-access-rnd`.

What changed:

- `climate_tookit/calculate_hazards/ensemble_hazards.py`

Root fix:

- replaced top-level `hazards`, `preprocess_data`, and `utils.models` imports with package-relative imports first
- kept fallback to `climate_tookit...` absolute imports
- left script-style local fallback only as last resort for direct execution

So normal package import no longer depends on `sys.path` mutation to make:

- `hazards`
- `preprocess_data`
- `utils.models`

appear as top-level modules.

Regression coverage added:

- `tests/test_ensemble_hazards_import.py`

That asserts:

- `import climate_tookit.calculate_hazards.ensemble_hazards`
- imported module name is correct
- `PREPROCESS_AVAILABLE == True`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_ensemble_hazards_import tests.test_preprocess_imports
python3 -m py_compile climate_tookit/calculate_hazards/ensemble_hazards.py tests/test_ensemble_hazards_import.py
.venv/bin/python - <<'PY'
import importlib
mod = importlib.import_module('climate_tookit.calculate_hazards.ensemble_hazards')
print('module ok', mod.__name__)
print('PREPROCESS_AVAILABLE', mod.PREPROCESS_AVAILABLE)
print('HAS_FAY', mod.HAS_FAY)
PY
```

Actual branch result:

```text
module ok climate_tookit.calculate_hazards.ensemble_hazards
PREPROCESS_AVAILABLE True
HAS_FAY True
```

Issue should stay open until merged to target branch.
