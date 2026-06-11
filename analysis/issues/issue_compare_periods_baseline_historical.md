## Summary

`climate_tookit/compare_periods/ensemble_periods.py` says each model should be compared against its own **historical** baseline run, but `_compare_one_model()` currently passes the selected future SSP to both the baseline period and the future period.

This means baseline-vs-future comparisons are structurally using:

- baseline: `ssp245` / `ssp585` / etc.
- future:   `ssp245` / `ssp585` / etc.

instead of:

- baseline: `historical`
- future:   selected SSP

This issue is present on:

- `origin/main`
- `origin/speed-up-gee-single-getinfo`

This issue does **not** currently reproduce on:

- `origin/staging`  
  `ensemble_periods.py` is not present there
- `origin/feat/compare_periods`  
  `ensemble_periods.py` is not present there
- `origin/feat/climate_statistics`  
  `ensemble_periods.py` is not present there

This is concrete follow-up to concerns already raised in closed issue `#70`, which noted that baseline/future comparisons should use NEX-GDDP historical data. This issue documents exact code path and a minimal failing repro.

## Issue search summary

Before drafting this, existing issues were checked to avoid duplicates.

Open issues reviewed:

- `#85` NEX-GDDP placeholder implementation still active on main and staging
- `#86` ensemble_hazards includes unsupported default scenario ssp370
- `#87` ensemble_hazards is not reliably importable under normal package execution
- `#88` ERA5 runtime path uses GEE while repo still exposes CDS-based ERA5 setup
- `#89` statistics and long_term_climatology silently disable preprocess pipeline under package import
- `#90` AgERA5 runtime uses generic GEE backend while agera_5.py remains a dead stub

None of those covers this baseline-scenario routing defect in `ensemble_periods.py`.

Related closed issue reviewed:

- `#70` Feedback on Compare_periods module

`#70` raised the broader requirement that NEX-GDDP baseline/future comparisons should use historical data for the baseline. This new issue is narrower and code-specific: it shows that `ensemble_periods.py` still forwards the future SSP into the baseline branch.

## How this was determined

This finding came from a code audit assisted by GPT-5.4 at medium reasoning effort and then manually verified by inspecting the runtime path and intercepting `_compare_one_model()` calls in a no-network repro.

Audit steps:

- inspected `climate_tookit/compare_periods/ensemble_periods.py`
- compared module docstring/comments against `_compare_one_model()` implementation
- verified both baseline and future branches forward the same `scenario` argument
- checked branch contents to confirm where `ensemble_periods.py` exists
- checked file history to see whether this was introduced recently or has existed since the module first appeared
- built a minimal repro that monkeypatches `analyze_climate_statistics()` and records which scenario each branch receives
- ran a failing unittest repro

## Evidence

### Module contract says baseline should be historical

At top of `climate_tookit/compare_periods/ensemble_periods.py`:

- `Both baseline and future data come from NEX-GDDP, so each model is compared against its own historical run`

`ensemble_compare()` also repeats:

- `All data (baseline + future) comes from NEX-GDDP, so each model is compared against its own historical run`

### Official NEX-GDDP dataset distinguishes historical from SSP runs

Google Earth Engine's official `NASA/GDDP-CMIP6` catalog lists the `scenario` property as:

- `historical` — retrospective model runs pre-2015
- `ssp245`
- `ssp585`

So baseline-vs-future logic is expected to split historical and future scenario branches, not reuse one SSP for both periods.

### Implementation uses same SSP for both periods

In `_compare_one_model()`:

```python
base = analyze_climate_statistics(
    location_coord=location,
    start_year=baseline_start, end_year=baseline_end,
    source="nex_gddp",
    model=model, scenario=scenario,
    **fs_kw,
)
future = analyze_climate_statistics(
    location_coord=location,
    start_year=future_start, end_year=future_end,
    source="nex_gddp",
    model=model, scenario=scenario,
    **fs_kw,
)
```

So baseline branch receives future SSP unchanged.

### Current synthetic NEX backend makes this materially wrong today too

Active `climate_tookit/fetch_data/source_data/sources/nex_gddp.py` applies scenario-specific factors directly:

- `historical`: lower warming / neutral precip factor
- `ssp245`, `ssp585`, etc.: warmer / drier factors

So even with current placeholder backend, baseline period results are shifted by future-scenario assumptions if `_compare_one_model()` passes `ssp245` or `ssp585`.

### CLI surface does not give users a workaround

`ensemble_periods.py` only accepts one scenario selector for the comparison:

```python
p.add_argument("--scenarios", default="ssp245", ...)
```

There is no separate `--baseline-scenario` argument.

So if code does not force baseline to `historical`, users cannot request the intended historical-vs-future split through the public interface.

### File history suggests this bug has been present since the module was introduced

The mismatch is not a latest-refactor accident. Earlier history already combined:

- comments saying each model is compared against its own historical run
- implementation forwarding `scenario=scenario` into both baseline and focal/future branches

This pattern is visible in earlier `ensemble_periods.py` history, including:

- `778faae`
- `762b2e6`
- current `origin/main`

## Minimal repro

Branches checked:

- `origin/main`
- `origin/speed-up-gee-single-getinfo`

Run:

```bash
.venv/bin/python - <<'PY'
from climate_tookit.compare_periods.ensemble_periods import _compare_one_model
import climate_tookit.compare_periods.ensemble_periods as ep

calls = []

def fake_analyze_climate_statistics(*, location_coord, start_year, end_year, source,
                                    fixed_season=None, model=None, scenario=None, **kwargs):
    calls.append({
        'start_year': start_year,
        'end_year': end_year,
        'source': source,
        'model': model,
        'scenario': scenario,
    })
    return {
        'raw_climate_summary': [],
        'overall_statistics': {},
        'season_statistics': [],
        'annual_summary': {},
    }

orig = ep.analyze_climate_statistics
ep.analyze_climate_statistics = fake_analyze_climate_statistics
try:
    _compare_one_model(
        location=(-1.286, 36.817),
        baseline_start=1991,
        baseline_end=2020,
        future_start=2040,
        future_end=2060,
        fixed_season=None,
        model='ACCESS-CM2',
        scenario='ssp245',
    )
finally:
    ep.analyze_climate_statistics = orig

print(calls)
PY
```

Actual result:

```text
[{'start_year': 1991, 'end_year': 2020, 'source': 'nex_gddp', 'model': 'ACCESS-CM2', 'scenario': 'ssp245'},
 {'start_year': 2040, 'end_year': 2060, 'source': 'nex_gddp', 'model': 'ACCESS-CM2', 'scenario': 'ssp245'}]
```

Expected result:

```text
[{'start_year': 1991, 'end_year': 2020, 'source': 'nex_gddp', 'model': 'ACCESS-CM2', 'scenario': 'historical'},
 {'start_year': 2040, 'end_year': 2060, 'source': 'nex_gddp', 'model': 'ACCESS-CM2', 'scenario': 'ssp245'}]
```

## Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import unittest
import climate_tookit.compare_periods.ensemble_periods as ep

class BaselineScenarioReproTests(unittest.TestCase):
    def test_baseline_should_use_historical_not_future_ssp(self):
        calls = []

        def fake_analyze_climate_statistics(*, location_coord, start_year, end_year, source,
                                            fixed_season=None, model=None, scenario=None, **kwargs):
            calls.append((start_year, end_year, scenario))
            return {
                'raw_climate_summary': [],
                'overall_statistics': {},
                'season_statistics': [],
                'annual_summary': {},
            }

        orig = ep.analyze_climate_statistics
        ep.analyze_climate_statistics = fake_analyze_climate_statistics
        try:
            ep._compare_one_model(
                location=(-1.286, 36.817),
                baseline_start=1991,
                baseline_end=2020,
                future_start=2040,
                future_end=2060,
                fixed_season=None,
                model='ACCESS-CM2',
                scenario='ssp245',
            )
        finally:
            ep.analyze_climate_statistics = orig

        self.assertEqual((1991, 2020, 'historical'), calls[0])
        self.assertEqual((2040, 2060, 'ssp245'), calls[1])

suite = unittest.defaultTestLoader.loadTestsFromTestCase(BaselineScenarioReproTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result:

```text
FAIL: test_baseline_should_use_historical_not_future_ssp
AssertionError: (1991, 2020, 'historical') != (1991, 2020, 'ssp245')
```

## Expected behavior

For NEX-GDDP future-vs-baseline comparisons:

- baseline period should use `historical`
- future period should use selected SSP

## Actual behavior

Both baseline and future periods use same future SSP.

## Why this matters

This makes reported baseline-vs-future differences scientifically misleading:

- baseline is not model historical baseline
- future-minus-baseline deltas are not comparing historical vs future forcing paths
- output contradicts module description and earlier review intent in `#70`
- once real NEX-GDDP backend is enabled, this will become more serious, because historical and SSP periods are distinct data branches

## Proposed fix

- in `_compare_one_model()`, force baseline branch to use `scenario='historical'`
- keep future branch on selected SSP
- add regression coverage asserting baseline/future scenario split
- consider validating that baseline years map to historical runs and future years map to SSP runs
