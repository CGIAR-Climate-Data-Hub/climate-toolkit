## Summary

`climate_tookit/climate_statistics/ensemble_statistics.py` accepts SSP scenarios such as `ssp245` for pre-2021 year ranges like `1991-2020`, but `_ltm_header_ensemble()` labels those runs as `BASELINE LTM` using the year window alone.

This creates a semantic mismatch:

- requested scenario: `ssp245`
- underlying per-model fetches: `ssp245`
- displayed header: `BASELINE LTM SEASON SUMMARY`

So the tool can present an SSP-forced run as if it were a historical baseline run.

This issue is present on:

- `origin/main`
- `origin/speed-up-gee-single-getinfo`

This issue does **not** currently reproduce on:

- `origin/staging`  
  `ensemble_statistics.py` is not present there
- `origin/feat/climate_statistics`  
  `ensemble_statistics.py` is not present there

## Issue search summary

Before drafting this, existing issues were checked to avoid duplicates.

Open issues reviewed:

- `#85` NEX-GDDP placeholder implementation still active on main and staging
- `#86` ensemble_hazards includes unsupported default scenario ssp370
- `#87` ensemble_hazards is not reliably importable under normal package execution
- `#88` ERA5 runtime path uses GEE while repo still exposes CDS-based ERA5 setup
- `#89` statistics and long_term_climatology silently disable preprocess pipeline under package import
- `#90` AgERA5 runtime uses generic GEE backend while agera_5.py remains a dead stub
- `#91` ensemble_periods uses future SSP for baseline instead of historical

None of those covers this `ensemble_statistics.py` scenario-year validation / labeling problem.

## How this was determined

This finding came from a code audit assisted by GPT-5.4 at medium reasoning effort and then manually verified with a no-network repro.

Audit steps:

- inspected `climate_tookit/climate_statistics/ensemble_statistics.py`
- traced scenario propagation in `analyze_ensemble_nex_gddp()`
- confirmed `_ltm_header_ensemble()` chooses `BASELINE` / `FUTURE` labels from years alone
- verified that explicit `ssp245` and `historical` requests are both forwarded unchanged to the underlying per-model call path
- built a minimal repro for header output
- ran a failing unittest repro

## Evidence

### Scenario is passed through unchanged

`analyze_ensemble_nex_gddp()` forwards caller scenario directly into each model run:

```python
r = analyze_climate_statistics(
    location_coord=location_coord,
    start_year=start_year, end_year=end_year,
    source='nex_gddp', fixed_season=fixed_season,
    model=model, scenario=scenario,
    extra_months=extra_months,
)
```

So if caller requests `ssp245` for `1991-2020`, the per-model fetch path still receives `ssp245`.

### Header ignores scenario and infers baseline/future from years alone

`_ltm_header_ensemble()`:

```python
def _ltm_header_ensemble(result: Dict[str, Any]) -> str:
    end          = (result.get('period') or {}).get('end_year',   0)
    start        = (result.get('period') or {}).get('start_year', 0)
    baseline_end = BASELINE_DEFAULT_PERIOD[1]
    if start > baseline_end:
        return "FUTURE LTM SEASON SUMMARY (NEX-GDDP CMIP6 ensemble)"
    if end <= baseline_end:
        return "BASELINE LTM SEASON SUMMARY (NEX-GDDP CMIP6 ensemble)"
    return "LTM SEASON SUMMARY (NEX-GDDP CMIP6 ensemble)"
```

No scenario check is involved there.

### Current NEX backend distinguishes `historical` from SSP scenarios

Active `climate_tookit/fetch_data/source_data/sources/nex_gddp.py` treats scenarios differently:

- `historical`: lower warming / neutral precip factor
- `ssp245`, `ssp585`, etc.: warmer / drier factors

So this is not only cosmetic. Even with current placeholder backend, `historical` and `ssp245` are materially different scenario paths.

### `long_term_climatology.py` does not appear to have same labeling bug

`climate_tookit/climatology/long_term_climatology.py` prints explicit scenario context such as:

- `Scenario : <canon>`
- `| scenario=<scenario> |`

It does not infer `BASELINE` / `FUTURE` labels from year window alone in the same way.

## Minimal repro

Branches checked:

- `origin/main`
- `origin/speed-up-gee-single-getinfo`

Run:

```bash
.venv/bin/python - <<'PY'
import io
from contextlib import redirect_stdout
import climate_tookit.climate_statistics.ensemble_statistics as es

result = {
    'period': {'start_year': 1991, 'end_year': 2020},
    'scenario': 'ssp245',
    'location': {'lat': -1.286, 'lon': 36.817},
    'source': 'nex_gddp',
    'mode': 'auto',
    'n_models_ok': 1,
    'models_failed': [],
    'ltm_season_summary': {'windows': []},
    'annual_summary': {},
    'per_model_ltm': {},
}

buf = io.StringIO()
with redirect_stdout(buf):
    es.print_report(result)

print(es._ltm_header_ensemble(result))
print('---')
for line in buf.getvalue().splitlines()[:8]:
    print(line)
PY
```

Actual result:

```text
BASELINE LTM SEASON SUMMARY (NEX-GDDP CMIP6 ensemble)
---
ENSEMBLE: NEX-GDDP CMIP6 (1991-2020)  | scenario=ssp245  | 1/1 models ok
```

That output combines:

- `scenario=ssp245`
- `BASELINE LTM ...`

which is semantically inconsistent.

## Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import unittest
import climate_tookit.climate_statistics.ensemble_statistics as es

class EnsembleHeaderScenarioLabelTests(unittest.TestCase):
    def test_pre2021_ssp_run_is_not_labeled_baseline(self):
        result = {
            'period': {'start_year': 1991, 'end_year': 2020},
            'scenario': 'ssp245',
        }
        header = es._ltm_header_ensemble(result)
        self.assertNotIn('BASELINE', header)

suite = unittest.defaultTestLoader.loadTestsFromTestCase(EnsembleHeaderScenarioLabelTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result:

```text
FAIL: test_pre2021_ssp_run_is_not_labeled_baseline
AssertionError: 'BASELINE' unexpectedly found in 'BASELINE LTM SEASON SUMMARY (NEX-GDDP CMIP6 ensemble)'
```

## Expected behavior

One of these should happen:

1. reject SSP scenarios for baseline-era windows such as `1991-2020`

or

2. allow them, but do not label them as `BASELINE LTM`

At minimum, reporting should not imply a historical baseline when the run scenario is `ssp245` / `ssp585`.

## Actual behavior

`ensemble_statistics.py` accepts pre-2021 SSP runs and labels them `BASELINE LTM` by year alone.

## Why this matters

This can mislead users during alpha testing:

- a scenario-forced run can be mistaken for historical baseline output
- baseline/future terminology becomes inconsistent across toolkit modules
- results are harder to interpret scientifically, especially alongside `#91`

## Proposed fix

- validate scenario-year compatibility in `analyze_ensemble_nex_gddp()`
- or make `_ltm_header_ensemble()` consider both years and scenario
- if scenario is not `historical`, avoid `BASELINE LTM` wording for pre-2021 runs
- add regression coverage for pre-2021 `ssp245` / `ssp585` labeling
