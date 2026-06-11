Branch fix now exists on `codex-nex-gddp-access-rnd`.

What changed:

- `climate_tookit/compare_periods/ensemble_periods.py`
- `_compare_one_model()` baseline branch now forces `scenario="historical"`
- future branch still uses requested SSP scenario

So scenario routing is now:

- baseline period -> `historical`
- future period -> requested SSP such as `ssp245`

Regression coverage added:

- `tests/test_compare_periods_baseline.py`

That test monkeypatches `analyze_climate_statistics()` and asserts exact call pattern:

- `(1991, 2020, "nex_gddp", "ACCESS-CM2", "historical")`
- `(2040, 2060, "nex_gddp", "ACCESS-CM2", "ssp245")`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_compare_periods_baseline tests.test_nex_gddp_behavior tests.test_fetch_pipeline
python3 -m py_compile climate_tookit/compare_periods/ensemble_periods.py tests/test_compare_periods_baseline.py
```

Result: passing on branch.

This does not by itself mean `main` is fixed yet; issue should stay open until branch work is merged.
