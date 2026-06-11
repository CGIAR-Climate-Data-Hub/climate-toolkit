Branch fix now exists on `codex-nex-gddp-access-rnd`.

Resolution choice:

- AgERA5 is now treated as officially Earth Engine-backed in this branch
- dead source-specific stub was replaced with authoritative EE-backed adapter surface

What changed:

- `climate_tookit/fetch_data/source_data/source_data.py`
  - `ClimateDataset.agera_5` now dispatches explicitly to `sources/agera_5.py`
- `climate_tookit/fetch_data/source_data/sources/agera_5.py`
  - no longer dead `NotImplemented` stub
  - now defines AgERA5 adapter as Earth Engine-backed wrapper over GEE path

Effect:

- active runtime path and source-specific module now agree
- AgERA5 no longer appears to have a dedicated backend that cannot actually run
- maintenance/debugging surface is clearer

Regression coverage added:

- `tests/test_fetch_pipeline.py`
  - `test_agera5_dispatches_to_authoritative_agera5_adapter`

Verification run on branch:

```bash
.venv/bin/python -m unittest tests.test_fetch_pipeline tests.test_preprocess_imports tests.test_ensemble_hazards_import
python3 -m py_compile climate_tookit/fetch_data/source_data/source_data.py climate_tookit/fetch_data/source_data/sources/agera_5.py tests/test_fetch_pipeline.py
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

Actual branch result:

```text
climate_tookit.fetch_data.source_data.sources.agera_5
DownloadData
```

Issue should stay open until merged to target branch.
