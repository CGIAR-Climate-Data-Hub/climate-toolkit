Title: SPEI method alignment update

Summary

SPEI support in `climate_tookit` has moved from provisional empirical month-wise z-score groundwork to a much closer match to established SPEI practice.

What changed

- New `climate_tookit.climatology.spei.compute_monthly_spei()` default now uses:
  - monthly climatic water balance `P - ET0`
  - rolling accumulation by `scale_months`
  - month-wise generalized logistic fit
  - unbiased probability-weighted moments (`ub-pwm`)
  - Gaussian transform of fitted cumulative probabilities

- Old empirical approach still exists, but only as explicit fallback:
  - `fit="empirical"`

- SPEI is now exposed through:
  - `climate_tookit.climate_statistics.statistics`
  - `climate_tookit.compare_periods.periods`

Why previous version was not sufficient

Earlier helper produced month-wise empirical normal scores from accumulated water balance. Useful as groundwork, but not standard SPEI.

Established SPEI references define standardization via fitted distribution, not simple empirical ranking, with default SPEI implementations commonly using log-logistic / generalized logistic fitting and PWM estimation.

References used for correction

- Vicente-Serrano, Begueria, Lopez-Moreno (2010)
  - SPEI concept and original method
  - DOI: `10.1175/2009JCLI2909.1`

- Begueria et al. (2014)
  - SPEI revisited: fitting, ET models, tools, datasets, monitoring

- CRAN SPEI package manual
  - <https://cran.r-project.org/web/packages/SPEI/SPEI.pdf>

- CRAN / upstream SPEI implementation source
  - <https://raw.githubusercontent.com/sbegueria/SPEI/master/R/spei.R>

- L-moment generalized-logistic helper used for formula cross-check
  - <https://raw.githubusercontent.com/cran/lmomco/master/R/parglo.R>

Current behavior

- Default fit:
  - `ub-pwm`
- Default distribution metadata:
  - `generalized_logistic`
- Optional reference period:
  - `ref_start`
  - `ref_end`
- Optional fallback:
  - `fit="empirical"`

Current limits

- No `max-lik` fit yet
- No alternate distributions yet
- No full parity with R `SPEI` package options
- No live validation yet on:
  - humid site
  - arid site
  - bimodal East African site
- No hazard-threshold semantics built on SPEI yet

Why this is still acceptable now

Current implementation is materially closer to established SPEI computation than previous shortcut, and is now safe to expose for package-level exploratory comparison outputs, as long as remaining gaps are stated clearly.

Recommended next validation

1. Run live SPEI smoke tests on:
   - humid DRC
   - arid north Kenya
   - bimodal East Africa
2. Inspect monthly SPEI traces for:
   - seasonal coherence
   - reasonable drought / wet anomalies
   - stable baseline reference behavior
3. Decide whether to add:
   - `max-lik`
   - alternate distributions
   - ensemble-period SPEI support

2026-06-21 update

- nearest-reference `xclim` comparison helpers now exist:
  - `compute_xclim_spei_reference`
  - `compute_xclim_spi_reference`
- synthetic regression tests now show toolkit `SPEI` / `SPI` track those
  nearest-reference outputs very closely
- package metadata now states clearly that this is method-family alignment, not
  exact `xclim` parity
- supporting note:
  - `analysis/spei_xclim_alignment_note.md`
