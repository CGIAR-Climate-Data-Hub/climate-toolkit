Branch fix now exists on `codex-nex-gddp-access-rnd`.

What changed:

- `climate_tookit/climate_statistics/statistics.py`
- `climate_tookit/climatology/long_term_climatology.py`

Root fix:

- removed `sys.path`-dependent top-level imports for preprocess pipeline
- switched to package-relative imports first
- kept small `climate_tookit...` fallback for direct script-style execution

So under normal package import these modules now keep core pipeline active instead of silently degrading to:

- `PREPROCESS_AVAILABLE = False`

Regression coverage added:

- `tests/test_preprocess_imports.py`

That asserts:

- `import climate_tookit.climate_statistics.statistics` -> `PREPROCESS_AVAILABLE == True`
- `import climate_tookit.climatology.long_term_climatology` -> `PREPROCESS_AVAILABLE == True`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_preprocess_imports tests.test_compare_periods_baseline tests.test_ensemble_statistics_scenario_validation
python3 -m py_compile climate_tookit/climate_statistics/statistics.py climate_tookit/climatology/long_term_climatology.py tests/test_preprocess_imports.py
.venv/bin/python - <<'PY'
import importlib
for mod_name in [
    'climate_tookit.climate_statistics.statistics',
    'climate_tookit.climatology.long_term_climatology',
]:
    mod = importlib.import_module(mod_name)
    print(mod_name, mod.PREPROCESS_AVAILABLE)
PY
```

Actual branch result now:

```text
climate_tookit.climate_statistics.statistics True
climate_tookit.climatology.long_term_climatology True
```

Issue should stay open until merged to target branch.
