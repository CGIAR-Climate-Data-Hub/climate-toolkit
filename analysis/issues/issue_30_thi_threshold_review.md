## Issue #30 THI threshold / method review note

Date: 2026-06-24

## Question

Should toolkit keep mean-temperature + RH `THI` as default, or add a
max-temperature screening variant now?

## Sources checked

### Thornton et al. 2021

- DOI: `10.1111/gcb.15825`
- Title: `Increases in extreme heat stress in domesticated livestock species during the twenty-first century`
- Why important:
  - directly livestock-focused
  - projection-oriented
  - species-specific threshold table
  - tropical/temperate threshold discussion

Key points from article text:

- THI is described as most widely used livestock heat-stress index
- paper uses daily temperature and daily relative humidity for projection work
- paper treats Thom (1959) and NRC (1971) forms as algebraically equivalent
- authors explicitly note threshold variation by species, breed, and context
- species thresholds in Table 1 align with current toolkit first-cut profiles

Relevant values reported in Table 1:

- cattle dairy: `72 / 79 / 89`
- cattle general: `72 / 79 / 90`
- cattle beef: `72 / 82 / 94`
- goats: `70 / 79 / 89`
- sheep: `72 / 78 / 90`
- pigs: `75 / 79 / 84`
- poultry broilers: `74 / 79 / 84`
- poultry layers: `71 / 76 / 82`
- poultry general: `73 / 81 / 85`

Relevant tropical extreme thresholds in Table 2:

- cattle: `94`
- goats: `94`
- sheep: `93`
- pigs: `92`
- poultry: `92`

## Interpretation for toolkit

### Default formula

Keep current Thom/NRC-equivalent THI family.

Reason:

- literature support strong
- already used in climate-projection context
- matches current toolkit data structure better than more complex heat-load indices

### Default daily inputs

Keep:

- daily mean temperature
- daily relative humidity

Reason:

- current published projection-oriented workflow already uses daily temperature + RH
- toolkit historical/projection source support is strongest for this path
- current humidity support is already source-constrained; forcing Tmax-style screening now would create extra inconsistency

### Max-temperature THI

Do **not** make default now.

Reason:

- daily `Tmax` often does not coincide with daily mean RH
- daily `Tmax` + daily mean RH is not clean physical pairing
- daily `Tmax` + daily min RH would be closer to afternoon stress screening, but toolkit does not yet have stable, source-consistent path for that pairing across datasets
- promoting this too early risks false precision

Possible future path:

- optional `THI_peak_screen` or similar screening metric
- clearly documented as screening companion, not same as default daily THI series

## Recommendation

1. keep current default:
   - daily mean temperature + daily RH THI
2. keep current Thornton-based thresholds as interim operational defaults
3. document clearly that:
   - thresholds are species-group operational defaults
   - breed/context sensitivity remains unresolved
   - tropical/highland logic is proxy logic, not breed-resolved physiology
4. leave max-temperature screening as follow-up refinement, not current default

## Breed-context wording for package docs

Recommended wording:

- treat THI thresholds as operational screening defaults
- do not imply package resolves breed-level thermotolerance
- do not imply tropical/highland auto rule measures animal adaptation directly
- encourage override where project has breed-specific or veterinary guidance

## Implication for issue #30

Issue should now focus on:

- threshold validation / wording
- source-support limits
- interpretation guidance
- whether to add separate screening variant later
