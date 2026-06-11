Branch update for `#86`:

This mismatch is resolved on `codex-nex-gddp-access-rnd`.

What changed on branch:

- active NEX backend is now `climate_tookit/fetch_data/source_data/sources/nex_gddp_xee.py`
- `climate_tookit/fetch_data/source_data/sources/nex_gddp.py` now delegates to that real adapter
- active `SCENARIO_MAPPING` now includes `ssp370` plus alias `SSP3-7.0`

So current branch state is:

- `climate_tookit/calculate_hazards/ensemble_hazards.py` default scenarios still include `ssp370`
- active NEX backend now accepts `ssp370`
- original default-list/backend mismatch no longer reproduces on branch

Evidence from branch:

- `tests/test_fetch_pipeline.py` includes `test_validate_inputs_accepts_historical_and_ssp370`
- `tests/test_nex_gddp_behavior.py` includes `test_download_data_accepts_ssp370_future_window`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_fetch_pipeline tests.test_nex_gddp_behavior
```

Result: passing on branch.

Important scope note:

- `origin/main` issue description still appears accurate until this branch work is merged there
- `origin/staging` was never same mismatch because its hazard defaults did not advertise `ssp370`

So issue should stay open until merge, but branch work has removed exact defect it described.
