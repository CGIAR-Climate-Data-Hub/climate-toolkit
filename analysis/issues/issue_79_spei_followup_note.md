## SPEI follow-up note for `#79`

`SPEI` is not implemented in current `calculate_hazards` workflow and should be treated as a later enhancement, not blocked into current `#79` completion.

Why note this now:

- dry-spell metrics are already covered locally via:
  - `detect_dry_spells(...)`
  - `calculate_dry_spell_statistics(...)`
  - `number_of_dry_spells`
  - `max_dry_spell_length_days`
  - `mean_dry_spell_length_days`
  - dry-spell length distribution
- Adaptation Atlas reference scripts help with `NDD`, `NTx35`, `NTx40`, `NDWS`, `NDWL0`, but do not replace need for a separate `SPEI` design.

When `SPEI` is added later, confirm:

- accumulation scale(s): `1`, `3`, `6`, `12` month
- calibration period
- PET method
- standardization / distribution-fitting method
- whether `SPEI` belongs in:
  - `calculate_hazards`
  - `climatology`
  - both

Recommended sequencing:

1. finish `#79` with existing seasonal hazard metrics and LTM comparisons
2. keep local dry-spell metrics in output surface
3. scope `SPEI` as separate issue / enhancement
