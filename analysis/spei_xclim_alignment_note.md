# SPI / SPEI Alignment Note

Status: working note  
Updated: 2026-06-21

This note records the current relationship between toolkit `SPI` / `SPEI`
outputs and the nearest `xclim` reference workflow.

## Current implementation

Toolkit monthly drought-index helpers live in:

- `climate_tookit.climatology.spei.compute_monthly_spi`
- `climate_tookit.climatology.spei.compute_monthly_spei`

Default behavior:

- month-wise fitting
- generalized-logistic style standardization
- unbiased PWM (`ub-pwm`) default
- optional empirical fallback

## Reference comparison path

Nearest `xclim` reference helpers now live in:

- `climate_tookit.climatology.compute_xclim_spi_reference`
- `climate_tookit.climatology.compute_xclim_spei_reference`

These use `xclim.indices.stats.standardized_index` as a cross-check rather than
as a strict implementation source.

## Interpretation

Treat the relationship as:

- `direct parity`: no
- `method-family alignment`: yes
- `behavioral agreement check`: yes

Why not exact parity:

- toolkit uses its own generalized-logistic / ub-pwm implementation
- `xclim` reference path uses its own standardized-index fitting options
- distribution and estimator internals are therefore close, but not identical

## Current validation outcome

Focused synthetic tests now show:

- very high correlation between toolkit and nearest-reference `SPI`
- very high correlation between toolkit and nearest-reference `SPEI`
- low mean absolute differences at the tested scale

This is strong enough for:

- exploratory package use
- regression protection against accidental implementation drift
- documentation of methodological proximity

It is not strong enough to claim:

- exact xclim equivalence
- exact CRAN `SPEI` parity for every option set

## User-facing wording recommended

Use language like:

- "Toolkit SPI/SPEI follows the standard month-wise fitted-distribution family of methods."
- "Nearest-reference checks against xclim are available and currently track closely."
- "Values should be interpreted as method-aligned rather than exact xclim replicas."

Avoid language like:

- "Toolkit SPI/SPEI is xclim"
- "Toolkit SPI/SPEI exactly reproduces xclim outputs"

