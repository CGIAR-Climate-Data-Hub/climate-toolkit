## Summary

`ClimateDataset.agera_5` does not use its source-specific module at runtime. Instead, it always dispatches to the generic GEE backend, while `climate_tookit/fetch_data/source_data/sources/agera_5.py` remains in the repository as a fully unimplemented dead stub.

Confirmed on:

- `origin/main`
- `origin/staging`
- `origin/feat/climate_statistics`
- `origin/feat/compare_periods`

## How this was determined

This finding came from a code audit assisted by GPT-5.4 and then manually verified by tracing the active runtime path and checking multiple branches.

Audit steps:

- inspected active dispatcher in `climate_tookit/fetch_data/source_data/source_data.py`
- verified `ClimateDataset.agera_5` is routed to `DownloadGEE`
- inspected `climate_tookit/fetch_data/source_data/sources/agera_5.py`
- confirmed all AgERA5 download methods, including `download_variables()`, are `NotImplemented`
- checked `main`, `staging`, and relevant feature branches to confirm the same structure exists there
- validated active dispatch with a no-network runtime repro and a failing unittest repro

## Evidence

### Active runtime dispatch

`climate_tookit/fetch_data/source_data/source_data.py` routes `ClimateDataset.agera_5` through:

- `DownloadGEE`

not through:

- `climate_tookit/fetch_data/source_data/sources/agera_5.py`

### Dead source-specific AgERA5 module

`climate_tookit/fetch_data/source_data/sources/agera_5.py`:

- describes itself as AgERA5 downloader
- defines `DownloadData`
- leaves every download method as `NotImplemented`
- leaves `download_variables()` as `NotImplemented`

So the module exists as an apparent backend, but cannot actually serve as one.

## Minimal repro

Branch checked:

- `origin/main`
- `origin/staging`
- `origin/feat/climate_statistics`
- `origin/feat/compare_periods`

### Behavior proof script

Run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt matplotlib
.venv/bin/python - <<'PY'
from datetime import date
from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateDataset, ClimateVariable
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings

src = SourceData(
    location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation],
    source=ClimateDataset.agera_5,
    date_from_utc=date(2020, 1, 1),
    date_to_utc=date(2020, 1, 2),
    settings=Settings.load(),
)

print(type(src.client).__module__)
print(type(src.client).__name__)
PY
```

Actual result:

```text
climate_tookit.fetch_data.source_data.sources.gee
DownloadData
```

This shows that `agera_5` is actively dispatched to the generic GEE backend.

### Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import unittest
from datetime import date
from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateDataset, ClimateVariable
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings

class Agera5DispatchReproTests(unittest.TestCase):
    def test_agera5_should_not_dispatch_to_gee_backend(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.agera_5,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )
        self.assertNotEqual(
            type(src.client).__module__,
            'climate_tookit.fetch_data.source_data.sources.gee',
        )

suite = unittest.defaultTestLoader.loadTestsFromTestCase(Agera5DispatchReproTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result:

```text
test_agera5_should_not_dispatch_to_gee_backend (__main__.Agera5DispatchReproTests.test_agera5_should_not_dispatch_to_gee_backend) ... FAIL

======================================================================
FAIL: test_agera5_should_not_dispatch_to_gee_backend (__main__.Agera5DispatchReproTests.test_agera5_should_not_dispatch_to_gee_backend)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<stdin>", line 17, in test_agera5_should_not_dispatch_to_gee_backend
AssertionError: 'climate_tookit.fetch_data.source_data.sources.gee' == 'climate_tookit.fetch_data.source_data.sources.gee'
```

## Expected behavior

One of these should be true, clearly and consistently:

1. AgERA5 is officially handled by the generic GEE backend
   - source-specific `agera_5.py` stub should be removed or deprecated
   - docs and architecture should reflect that there is no separate backend

or

2. AgERA5 is supposed to have its own source-specific backend
   - runtime dispatch should use it
   - `agera_5.py` should be implemented

## Actual behavior

- runtime always uses generic GEE backend
- source-specific `agera_5.py` remains present but unusable

## Why this matters

This creates confusion for:

- maintenance
- debugging
- onboarding
- architecture review

The repo appears to support a dedicated AgERA5 source module, but active runtime behavior says otherwise.

## Proposed fix

- choose one authoritative AgERA5 backend path
- if generic GEE is the intended path:
  - remove or deprecate dead `agera_5.py` stub
  - document that AgERA5 is handled by the generic GEE backend
- if source-specific AgERA5 backend is intended:
  - implement `agera_5.py`
  - route `ClimateDataset.agera_5` to it
