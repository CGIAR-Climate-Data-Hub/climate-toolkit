# Decision Memo: Andes NEX-GDDP Screening Watchlist

## Status

Warning-only screening watchlist. Not final Andes fast pool.

## Policy ID

`ANDES-FAST-WARNING`

## Model set

- `NorESM2-LM`
- `MPI-ESM1-2-HR`
- `EC-Earth3`
- `MRI-ESM2-0`
- `KACE-1-0-G`

## Why this subset

Current Andes evidence mixes:

- Andes-specific annual-cycle support/caution
- broader South America shortlist support

Most defensible current mix:

- `NorESM2-LM`: Andes hotspot precipitation annual-cycle support
- `MPI-ESM1-2-HR`: Andes hotspot temperature annual-cycle support
- `EC-Earth3`, `MRI-ESM2-0`, `KACE-1-0-G`: broader South America shortlist
  support, useful as screening candidates until stronger Andes-only paper is
  harvested

## Models explicitly cautioned

- `ACCESS-ESM1-5`
- `MIROC6`

Both show Andes hotspot wet-month overestimation in current Andes-specific
evidence.

## Why this is warning-only

- only two current rows are directly Andes-specific
- stronger Andes-only multi-metric shortlist still missing
- topography-sensitive seasonal timing and extremes evidence still thin

## Intended use

- exploratory Andes screening
- not final Andes uncertainty pool
- not full regional decision default

## Evidence basis

- Ortega et al. 2021: Andes hotspot annual-cycle support/caution
- Bazzanela et al. 2024: broader South America shortlist context
- package evidence matrix:
  [analysis/issues/issue_nex_regional_pool_evidence_matrix.md](./issues/issue_nex_regional_pool_evidence_matrix.md)
