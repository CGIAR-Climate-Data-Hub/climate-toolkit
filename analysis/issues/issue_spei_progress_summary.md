Title: SPEI implementation progress summary

Branch

- `codex/issue-3-spei-4-ndws`

Key commits

- `d40a68d` `fix: align SPEI with standard method`
- `ba10ece` `feat: expose SPEI in climate statistics`
- `5c02108` `feat: add SPEI period comparisons`

What is now implemented

1. Core SPEI helper
- monthly climatic water balance
- scale aggregation
- month-wise generalized logistic fit
- unbiased PWM (`ub-pwm`) default
- optional empirical fallback
- optional reference period

2. Climate statistics integration
- optional SPEI block in `climate_statistics.statistics`
- CLI flags for scale / fit / reference period
- JSON output plus SPEI CSV sidecar

3. Compare-periods integration
- optional SPEI comparison in `compare_periods.periods`
- summary diff plus monthly focal-vs-baseline rows

4. Ensemble compare-periods integration
- optional SPEI comparison in `compare_periods.ensemble_periods`
- ensemble-mean monthly and summary SPEI deltas
- focal-vs-baseline and focal-vs-future SPEI blocks supported

Reference basis used

- Vicente-Serrano et al. (2010), DOI `10.1175/2009JCLI2909.1`
- Begueria et al. (2014)
- CRAN SPEI manual
  - <https://cran.r-project.org/web/packages/SPEI/SPEI.pdf>
- CRAN / upstream SPEI source
  - <https://raw.githubusercontent.com/sbegueria/SPEI/master/R/spei.R>
- `lmomco` generalized-logistic parameter helper
  - <https://raw.githubusercontent.com/cran/lmomco/master/R/parglo.R>

What changed methodologically

Earlier provisional helper used empirical month-wise z-scores. That was not standard SPEI.

Current default is much closer to established method:
- generalized logistic / log-logistic family
- month-wise fitting
- unbiased PWM parameter estimation
- Gaussian transform from fitted CDF

Current limits

- no `max-lik` fit yet
- no alternate distributions yet
- no live validation yet on:
  - humid site
  - arid site
  - bimodal site
- no final user-facing interpretation guidance yet

Current test status

- targeted SPEI-related sweep passing:
  - `tests.test_spei`
  - `tests.test_statistics_source_policy`
  - `tests.test_compare_periods_baseline`
- latest combined run: `47 tests OK`

Recommended next live validation

1. humid DRC site
2. arid north Kenya site
3. bimodal East Africa site

For each:
- run `climate_statistics.statistics` with SPEI enabled
- inspect monthly SPEI trace
- run `compare_periods.periods`
- inspect baseline/focal deltas
- then decide whether ensemble-period SPEI values remain sensible
