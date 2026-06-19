# Decision Memo: East Africa NEX-GDDP Regional Fast Pool

## Status

Provisional. Suitable for rapid East Africa screening. Not final uncertainty
envelope.

## Policy ID

`AFR-EAF-FAST-PROVISIONAL-V2`

## Model set

- `IPSL-CM6A-LR`
- `EC-Earth3-Veg-LR`
- `INM-CM5-0`
- `MPI-ESM1-2-HR`
- `CanESM5`

## Why this subset

- `IPSL-CM6A-LR`: supported by IGAD rainfall evaluation and East Africa
  NEX-GDDP evaluation.
- `EC-Earth3-Veg-LR`: supported through `EC-Earth3` family evidence plus prior
  package-aligned regional guidance.
- `INM-CM5-0`: strong IGAD rainfall support.
- `MPI-ESM1-2-HR`: East Africa NEX-GDDP annual-precipitation support plus prior
  secondary East Africa guidance.
- `CanESM5`: direct East Africa NEX-GDDP annual-precipitation support.

## Key caveats

- `ACCESS-ESM1-5` has mixed evidence:
  - IGAD rainfall caution
  - East Africa annual-temperature support
- `CanESM5` conflicts with continent-level secondary African guidance used in
  broader Africa default logic.
- `EC-Earth3-Veg-LR` is backed partly by family-level `EC-Earth3` evidence, not
  exact same-name East Africa paper row.

## Intended use

- rapid regional screening
- package-facing mixed precipitation + temperature runs
- not final model weighting
- not full structural uncertainty envelope

## Evidence basis

- Omay et al. 2024: IGAD rainfall model evaluation
- Umwali et al. 2024: East Africa `NEX-GDDP-CMIP6` precipitation/temperature
  evaluation
- package evidence matrix:
  [analysis/issues/issue_nex_regional_pool_evidence_matrix.md](./issues/issue_nex_regional_pool_evidence_matrix.md)
