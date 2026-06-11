## Summary

`era_5` currently dispatches to the generic Google Earth Engine backend at runtime, while the repository still exposes a CDS-based ERA5 client, CDS environment variables, and `cdsapi` dependency as if ERA5 were fetched through the Climate Data Store.

This creates a setup/runtime mismatch:

- users can configure `CDS_URL` / `CDS_KEY`
- repository contains `climate_tookit/fetch_data/source_data/sources/era_5.py`
- but active `era_5` execution actually routes through `gee.py` and therefore depends on Earth Engine auth and `GCP_PROJECT_ID`

Confirmed on:

- `origin/main`
- `origin/staging`
- `origin/feat/climate_statistics`
- `origin/feat/compare_periods`

## How this was determined

This finding came from a code audit assisted by GPT-5.4 and then manually verified by tracing the active runtime path and checking multiple branches.

Audit steps:

- inspected active dispatcher in `climate_tookit/fetch_data/source_data/source_data.py`
- verified `ClimateDataset.era_5` is routed to `DownloadGEE`, not to `sources/era_5.py`
- inspected `climate_tookit/fetch_data/source_data/sources/era_5.py` and confirmed it initializes a CDS client from `CDS_URL` / `CDS_KEY`
- searched repository references and found no active runtime import path that uses `sources/era_5.py`
- checked `main`, `staging`, and relevant feature branches to confirm the same mismatch exists there too
- validated the behavior with a no-network runtime repro and a failing unittest repro

## Evidence

### Active runtime dispatch

`climate_tookit/fetch_data/source_data/source_data.py` routes:

- `ClimateDataset.era_5`
- `ClimateDataset.agera_5`

through:

- `DownloadGEE`

not through:

- `climate_tookit/fetch_data/source_data/sources/era_5.py`

### Exposed but inactive CDS ERA5 backend

`climate_tookit/fetch_data/source_data/sources/era_5.py`:

- imports `cdsapi`
- reads `CDS_URL` and `CDS_KEY`
- instantiates `Client(url=url, key=key)`

but is not the active runtime backend used by `SourceData(... source=ClimateDataset.era_5 ...)`

### Repo setup still implies CDS ERA5 access

`.env.example` includes:

- `CDS_URL`
- `CDS_KEY`
- `GCP_PROJECT_ID`

`requirements.txt` includes both:

- `cdsapi`
- `earthengine_api`

This makes ERA5 setup ambiguous even though active runtime chooses GEE.

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
    source=ClimateDataset.era_5,
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

This shows that `era_5` is actively dispatched to the GEE backend.

### Failing unittest repro

Run:

```bash
.venv/bin/python - <<'PY'
import unittest
from datetime import date
from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateDataset, ClimateVariable
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings

class Era5DispatchReproTests(unittest.TestCase):
    def test_era5_should_not_dispatch_to_gee_backend(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.era_5,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )
        self.assertNotEqual(
            type(src.client).__module__,
            'climate_tookit.fetch_data.source_data.sources.gee',
        )

suite = unittest.defaultTestLoader.loadTestsFromTestCase(Era5DispatchReproTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Actual result:

```text
test_era5_should_not_dispatch_to_gee_backend (__main__.Era5DispatchReproTests.test_era5_should_not_dispatch_to_gee_backend) ... FAIL

======================================================================
FAIL: test_era5_should_not_dispatch_to_gee_backend (__main__.Era5DispatchReproTests.test_era5_should_not_dispatch_to_gee_backend)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<stdin>", line 17, in test_era5_should_not_dispatch_to_gee_backend
AssertionError: 'climate_tookit.fetch_data.source_data.sources.gee' == 'climate_tookit.fetch_data.source_data.sources.gee'
```

## Expected behavior

One of these should be true, clearly and consistently:

1. `era_5` is officially Earth Engine-backed
   - docs/setup/examples should say that clearly
   - CDS-specific ERA5 backend and setup surface should be removed or deprecated

or

2. `era_5` is officially CDS-backed
   - runtime dispatch should route to the CDS ERA5 backend
   - setup/docs/examples should match that path

## Actual behavior

- setup surface suggests CDS-based ERA5 is relevant
- active runtime uses Earth Engine instead
- repository still contains an exposed but inactive CDS ERA5 implementation

## Why this matters

This causes confusion during alpha testing and onboarding:

- a user can set `CDS_URL` / `CDS_KEY` correctly and still fail ERA5 runs because runtime actually needs Earth Engine auth
- debugging effort is wasted on the wrong credential path
- repo appears to support two ERA5 backends, but only one is active

## Proposed fix

- choose one authoritative ERA5 backend path
- align runtime dispatch, docs, examples, `.env.example`, and dependencies with that choice
- if Earth Engine is the intended backend:
  - document that clearly
  - remove or deprecate inactive CDS ERA5 client surface
- if CDS is the intended backend:
  - route `ClimateDataset.era_5` to the CDS implementation
  - add integration coverage for that path
