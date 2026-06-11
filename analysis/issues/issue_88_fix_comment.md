Branch fix now exists on `codex-nex-gddp-access-rnd`.

Resolution choice:

- ERA5 is now treated as officially Earth Engine-backed in this branch
- inactive CDS setup surface was removed so runtime path and setup path match

What changed:

- `climate_tookit/fetch_data/source_data/source_data.py`
  - `ClimateDataset.era_5` now dispatches explicitly to `sources/era_5.py`
- `climate_tookit/fetch_data/source_data/sources/era_5.py`
  - no longer exposes dead CDS client
  - now defines ERA5 adapter as Earth Engine-backed wrapper over GEE path
- `.env.example`
  - removed `CDS_URL`
  - removed `CDS_KEY`
  - kept `GCP_PROJECT_ID` with comment explaining EE-backed sources use it
- `requirements.txt`
  - removed `cdsapi`

Effect:

- active runtime path and module surface now agree
- ERA5 setup expectation is Earth Engine / `GCP_PROJECT_ID`, not CDS credentials
- direct inspection no longer shows live CDS-era setup artifacts in repo runtime surface

Regression coverage added:

- `tests/test_fetch_pipeline.py`
  - `test_era5_dispatches_to_authoritative_era5_adapter`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_fetch_pipeline tests.test_preprocess_imports tests.test_ensemble_hazards_import
python3 -m py_compile climate_tookit/fetch_data/source_data/source_data.py climate_tookit/fetch_data/source_data/sources/era_5.py tests/test_fetch_pipeline.py
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

Actual branch result:

```text
climate_tookit.fetch_data.source_data.sources.era_5
DownloadData
```

Also rechecked repo runtime surface:

```bash
rg -n "CDS_URL|CDS_KEY|cdsapi" climate_tookit .env.example requirements.txt README.md
```

Result: no matches in live repo files after branch fix.

Issue should stay open until merged to target branch.
