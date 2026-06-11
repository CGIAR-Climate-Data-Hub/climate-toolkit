Branch fix now exists on `codex-nex-gddp-access-rnd`.

What changed:

- `climate_tookit/climate_statistics/ensemble_statistics.py`

Two parts:

1. `analyze_ensemble_nex_gddp()` now validates scenario/year compatibility using NEX rules before running
   - `historical` only through `2014-12-31`
   - SSP scenarios only from `2015-01-01`

2. `_ltm_header_ensemble()` now considers scenario as well as years
   - true historical window -> `BASELINE LTM ...`
   - true SSP future window -> `FUTURE LTM ...`
   - anything else -> generic `LTM ...`

So pre-2015 SSP runs are no longer accepted and mislabeled as baseline.

Regression coverage added:

- `tests/test_ensemble_statistics_scenario_validation.py`

That covers:

- pre-2015 `ssp245` run is not labeled `BASELINE`
- true `historical` window is labeled `BASELINE`
- invalid pre-2015 SSP request is rejected with error

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_ensemble_statistics_scenario_validation tests.test_compare_periods_baseline tests.test_nex_gddp_behavior
python3 -m py_compile climate_tookit/climate_statistics/ensemble_statistics.py tests/test_ensemble_statistics_scenario_validation.py
```

Result: passing on branch.

This does not by itself mean `main` is fixed yet; issue should stay open until branch work is merged.
