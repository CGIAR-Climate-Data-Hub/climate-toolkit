# Follow-up: source NEX-GDDP 1.2 for package backend

## Summary

Current real `nex_gddp` package backend is now using Earth Engine/Xee with
dataset version `1.1` as documented runtime behavior.

We should track dataset version `1.2` as separate follow-up sourcing task,
instead of treating it as silent expected default in current code.

## Why this needs follow-up

- live package smoke runs currently return `selected_version=1.1`
- current branch behavior is valid and reproducible with `1.1`
- repeated runtime warnings about preferred `1.2` create noise and imply a
  broken state, when current implementation is actually using intended
  supported source
- if `1.2` is scientifically or product-wise preferred, that should be solved
  by explicitly sourcing and validating it, not by warning users on every run

## Current agreed behavior

- document active Earth Engine backend as NEX-GDDP `1.1`
- remove runtime warning about falling back from `1.2`
- preserve `selected_version` in cache manifests for traceability

## Follow-up questions

1. Is Earth Engine catalog access to `1.2` incomplete, missing for some
   model/scenario combinations, or absent entirely in current environment?
2. If `1.2` is required, should it come from:
   - alternate Earth Engine asset
   - direct cloud storage / object-store path
   - toolkit-managed hosted mirror / cache
3. Do model availability, realizations, or metadata differ between `1.1` and
   `1.2` in ways that affect ensemble policy or documentation?

## Suggested acceptance criteria

- identify accessible and stable `1.2` source
- confirm model/scenario/version coverage
- validate point extraction against current package dataframe contract
- benchmark runtime and cache compatibility
- update docs and backend default only after live validation succeeds
