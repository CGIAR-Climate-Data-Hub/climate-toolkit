Branch update for root issue `#85`:

Active placeholder path is replaced on `codex-nex-gddp-access-rnd`.

Main branch changes:

- `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`
  - no longer serves as standalone synthetic generator
  - now delegates to real adapter
- `climate_tookit/fetch_data/source_data/sources/nex_gddp_xee.py`
  - new Earth Engine + Xee-backed single-site implementation
  - real `historical`, `ssp126`, `ssp245`, `ssp370`, `ssp585`
  - scenario/year validation
  - retry/backoff
  - chunked fetch
  - cache + manifest + integrity checks
- `climate_tookit/fetch_data/nex_gddp_batch.py`
  - package-native many-site batch extraction
  - cache + manifest + resume/integrity behavior
  - `raw` / `transformed` / `preprocessed` stage support

Related package integration work on branch:

- `climate_tookit/fetch_data/source_data/source_data.py`
- `climate_tookit/fetch_data/fetch_data.py`
- `climate_tookit/fetch_data/preprocess_data/preprocess_data.py`
- `climate_tookit/fetch_data/transform_data/transform_data.py`

That means `source='nex_gddp'` on this branch is no longer synthetic placeholder in package fetch path.

Branch verification:

- unit coverage:
  - `tests/test_nex_gddp_xee_poc.py`
  - `tests/test_nex_gddp_behavior.py`
  - `tests/test_fetch_pipeline.py`
  - `tests/test_nex_gddp_batch.py`
- live Earth Engine smoke and benchmark artifacts already saved under `analysis/`
  - `analysis/nex_subset_historical_1985_2014_summary.csv`
  - `analysis/nex_subset_ssp245_2041_2070_summary.csv`
  - `analysis/nex_subset_sites10_historical_1985_2014_summary.csv`
  - `analysis/nex_subset_sites10_ssp245_2041_2070_summary.csv`

Important caveats before closure:

- issue still valid on `main` / `staging` until branch work is merged
- current real path requires Earth Engine auth + project ID on backend side
- current EE route is consistently falling back from preferred NEX version `1.2` to `1.1`
- Africa subregion ensemble-selection policy is not yet wired; current branch only restores real data access

Downstream consequence:

- placeholder-derived symptom issue `#94` no longer reproduces on this branch with real artifacts, but remains valid on branches still using placeholder backend

Suggested disposition:

- keep `#85` open until merge
- after merge, reevaluate/close `#85` and placeholder-symptom issues tied to it
