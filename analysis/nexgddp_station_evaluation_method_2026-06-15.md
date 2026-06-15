# NEX-GDDP Station Evaluation Method Note

Date: 2026-06-15

## Purpose

Define a defensible method for using weather station observations to evaluate `NEX-GDDP-CMIP6` model outputs at local to regional scale.

This note is for:

- model screening
- model ranking
- ensemble weighting
- communication of uncertainty

It is not for claiming that one GCM is universally "best".

## What Exactly We Are Evaluating

For NEX-GDDP, station comparison evaluates the skill of the:

`downscaled / bias-corrected NEX-GDDP realization driven by a specific CMIP6 model`

not the raw parent GCM in isolation.

That distinction matters. A good or bad result may reflect:

- the parent CMIP6 model
- the downscaling / bias-correction procedure
- local terrain mismatch
- sparse observational sampling

## Official Dataset Context

The current Google Earth Engine catalog for `NASA/GDDP-CMIP6` states:

- daily data
- global coverage
- 34 models
- historical plus `ssp245` and `ssp585`
- versions `1.0`, `1.1`, `1.2`

Source:

- [Google Earth Engine: NASA/GDDP-CMIP6](https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6)

Important implementation implication:

- station evaluation must use `historical`
- future `ssp*` runs are interpreted through historical skill, not directly validated against observations

## Core Principle

Use stations to answer:

`Which NEX-GDDP model realizations reproduce the local historical climate best for this variable, season, and region?`

Do not use stations to answer:

`Which GCM is objectively the best future model overall?`

## Independence Caveat For Historical References

Some historical climate products used elsewhere in the toolkit are station-informed or interpolated between stations.

Implication:

- agreement between a station and a gridded historical product may partly reflect shared observational input
- that comparison is still useful operationally, but it is not the same as fully independent validation

For NEX-GDDP evaluation this means:

- station vs `NEX-GDDP historical` is the key independent-like comparison
- station vs station-informed historical products is still useful for benchmarking data choices, but should be labeled accordingly

## Why A Careful Method Is Needed

Three issues make naive ranking unsafe.

### 1. Station sampling matters

Risser and Wehner show that model evaluation changes when the geographic sampling of actual weather stations is treated correctly, especially for precipitation extremes.

Source:

- [Risser and Wehner 2019, The effect of geographic sampling on evaluation of extreme precipitation in high resolution climate models](https://arxiv.org/abs/1911.05103)

Implication:

- compare model output at actual station locations
- do not substitute only broad gridded climatologies when station truth exists

### 2. Single-metric ranking is too weak

Different models can perform differently for:

- means
- seasonality
- wet-day frequency
- extremes
- dry spells

Vissio et al. argue for richer distribution-based model evaluation rather than relying on one summary error statistic.

Source:

- [Vissio et al. 2020, Ranking IPCC Models Using the Wasserstein Distance](https://arxiv.org/abs/2006.09304)

Implication:

- use multiple metrics
- do not choose a model on RMSE alone

### 3. Historical skill does not mechanically determine future truth

Observation-constrained and weighting approaches can improve interpretation, but they require explicit uncertainty treatment and should not collapse the ensemble too aggressively.

Source:

- [Sansom et al. 2017, On constraining projections of future climate using observations and simulations from multiple climate models](https://arxiv.org/abs/1711.04139)

Implication:

- use historical skill to weight or shortlist
- do not pretend the highest-ranked historical model is the future winner

## Recommended Evaluation Scope

### Validate only on overlapping historical years

Use:

- station observations
- NEX-GDDP `historical`

Do not validate against:

- `ssp245`
- `ssp585`
- any other future scenario

### Evaluate by variable

At minimum:

- precipitation
- maximum temperature
- minimum temperature

Optional later:

- mean temperature
- wind speed
- humidity

### Evaluate by season

At minimum:

- annual
- primary rainy season
- secondary rainy season where relevant
- user-defined agricultural windows

This matters because a model can perform well annually while failing badly in the onset, cessation, or intensity structure of the rainy season.

### Evaluate by subregion

Especially for Africa and Andes applications, aggregate skill should not hide strong regime differences.

Recommended levels:

- site
- subregion / rainfall regime
- pooled region summary

## Recommended Evaluation Unit

The main evaluation unit should be:

`station x model x variable x season`

Then aggregate upward to:

- `site-level model score`
- `subregional model score`
- `regional model score`

## Station Pairing Rules

### 1. Use actual station coordinates

Extract NEX-GDDP at the station point.

### 2. Respect station overlap

Only score periods with valid overlapping data in both:

- station series
- NEX-GDDP historical series

### 3. Apply station quality filters

Exclude or flag stations with:

- too little overlap
- implausible discontinuities
- excessive missingness
- obvious unit issues

Recommended minimums:

- annual analysis: at least `10` overlapping years
- seasonal analysis: at least `10` valid seasons
- daily completeness: at least `80%` of days within scored windows

### 4. Support user-supplied stations

The method must support uploaded station datasets, not only public station archives.

Practical implications:

- user files may contain only precipitation
- user files may contain only Tmin/Tmax
- records may be incomplete
- metadata may be partial

Therefore:

- metrics must be computed per variable using only valid overlap
- model ranking should be variable-specific
- skipped variables must be reported explicitly

## Metrics

Use a metric suite, not one score.

### A. Precipitation metrics

#### Daily and aggregate structure

- mean annual precipitation bias
- mean seasonal precipitation bias
- daily precipitation RMSE
- daily precipitation correlation
- wet-day frequency bias
- wet-day intensity bias
- 95th percentile wet-day bias
- maximum 1-day precipitation bias

#### Spell behavior

- mean dry-spell length bias
- mean wet-spell length bias
- onset date bias where seasonal onset is relevant
- cessation date bias where relevant

#### Distributional metric

- Wasserstein distance or similar distributional distance for daily precipitation

Why:

- precipitation failure often appears in frequency and intensity separately
- totals alone can hide rainbombs or drizzle bias

### B. Temperature metrics

- mean bias
- RMSE
- correlation
- seasonal cycle amplitude bias
- warm extreme bias
- cold extreme bias
- Tmax bias
- Tmin bias
- diurnal temperature range bias

### C. Optional combined diagnostics

- Kling-Gupta Efficiency for continuous fields
- anomaly correlation
- quantile bias summaries

## Rainbomb Safeguard

Because arid-region downscaling can generate implausibly high daily rainfall values, include a specific diagnostic for suspicious heavy-rain amplification.

For each model-site-season:

- report maximum daily rainfall
- compare upper quantiles to station values
- flag if model extreme tail is implausibly inflated relative to station history

This should be a warning, not silent filtering.

## Scoring Strategy

### Step 1. Compute metric-specific scores

For each metric, transform raw error into a normalized score on `0-1`.

Example:

```text
score = 1 / (1 + scaled_error)
```

or rank-based scaling within the model set for that site/season.

### Step 2. Build variable-specific composite scores

#### Precipitation composite

Suggested weighting:

- 20% seasonal total bias
- 15% wet-day frequency
- 15% wet-day intensity
- 15% dry-spell behavior
- 15% extreme rainfall behavior
- 10% correlation
- 10% distributional distance

#### Temperature composite

Suggested weighting:

- 25% mean bias
- 20% RMSE
- 15% correlation
- 15% Tmax skill
- 15% Tmin skill
- 10% extreme behavior

These weights are defaults, not dogma.

### Step 3. Keep scores separate by variable

Do not combine precipitation and temperature too early.

Outputs should include:

- precipitation score
- temperature score
- optional combined score

### Step 4. Aggregate carefully

Aggregate from:

- season to annual summary
- site to subregion
- subregion to regional summary

Recommended aggregation:

- median score across sites
- IQR or spread across sites

This is more robust than mean alone.

## Recommended Outcome: Weighted Ensemble Or Shortlist

The output should usually be one of these:

### Option A. Top-N shortlist

Keep, for example:

- top 5 models for precipitation
- top 5 models for temperature

Advantages:

- easy to explain
- preserves spread

### Option B. Skill-weighted ensemble

Convert composite scores to weights.

Example:

```text
weight_i = score_i / sum(scores)
```

Optionally damp the differences so one model does not dominate too strongly.

Example:

```text
weight_i = score_i^alpha / sum(score^alpha)
```

with `alpha` around `0.5 to 1.0`.

Recommendation:

- default to a weighted ensemble
- also report the unweighted ensemble for transparency

If uploaded station data contain only one variable:

- create weights only for that variable
- do not invent a combined multi-variable score

## Strong Caution On Over-Selection

Do not reduce to a single "best model" by default.

Why:

- different models may be best for different variables
- different models may be best in different seasons
- future forced response can differ even when historical fit is similar

The safer message is:

- `these models perform better historically at this site or in this regime`

not:

- `this one model is the future truth`

## Independence Caveat

Some CMIP6 models are not truly independent. Closely related models can overweight one modeling lineage if we simply rank by performance.

Implication:

- document model family relationships where possible
- consider a later independence penalty

For now, a pragmatic first phase is:

- rank all models
- warn if several top models come from closely related families

## Africa / Andes Practical Guidance

### Africa

For African climate-rationale work, do not assume one pan-African best model set.

Evaluate within rainfall regimes or subregions where possible:

- humid equatorial
- bimodal East African
- semi-arid Horn / Turkana
- Sahelian
- southern African summer rainfall

### Andes

Elevation and terrain matter strongly.

Use:

- station-specific extraction
- elevation-aware station choice
- caution in interpreting rainfall skill where local topography dominates convective behavior

## Minimum Viable Workflow For The Toolkit

### Phase 1

1. User selects site(s)
2. User selects station(s) or auto-discovers nearby stations
3. Toolkit downloads station observations
4. Toolkit downloads `NEX-GDDP historical` for all candidate models
5. Toolkit computes per-model metrics
6. Toolkit outputs:
   - metrics table
   - ranked model list
   - weighted ensemble weights

### Phase 2

1. Aggregate across multiple sites
2. Produce subregional scorecards
3. Compare weighted vs unweighted ensemble behavior

### Phase 3

1. Add independence adjustment
2. Add advanced distributional metrics
3. Add explicit rainy-season onset/cessation skill scoring

## Recommended Output Tables

### Table 1. Per-model site metrics

Columns:

- `site`
- `station_id`
- `model`
- `variable`
- `season`
- `n_years`
- metric columns
- `composite_score`
- `rank`

### Table 2. Model weights

Columns:

- `site`
- `variable`
- `season`
- `model`
- `score`
- `weight`

### Table 3. Subregional summary

Columns:

- `region`
- `variable`
- `season`
- `model`
- `median_score`
- `iqr_score`
- `n_sites`

## What The Toolkit Should Say To Users

Suggested wording:

> These rankings reflect how well each NEX-GDDP historical model realization reproduces observed station climate over the historical overlap period for the selected variable and season. They are useful for weighting or shortlisting models, but they do not prove that the top-ranked model is the single correct future projection.

## Implementation Guardrails

1. Block station-vs-future direct validation.
2. Keep precipitation and temperature ranking separate.
3. Score seasons separately where seasonality matters.
4. Never ensemble before per-model evaluation.
5. Preserve station and model provenance in every output.
6. Flag suspicious precipitation extremes rather than silently clipping them.

## Recommended Initial Default

If we need one default approach for first implementation:

- evaluate all available NEX-GDDP historical models
- compute separate precipitation and temperature composite scores
- aggregate by site and by user-defined season
- output:
  - unweighted ensemble
  - top-5 shortlist
  - skill-weighted ensemble

That is methodologically defensible and practical.

## References

- [Google Earth Engine: NASA/GDDP-CMIP6](https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6)
- [Risser and Wehner 2019, The effect of geographic sampling on evaluation of extreme precipitation in high resolution climate models](https://arxiv.org/abs/1911.05103)
- [Vissio et al. 2020, Ranking IPCC Models Using the Wasserstein Distance](https://arxiv.org/abs/2006.09304)
- [Sansom et al. 2017, On constraining projections of future climate using observations and simulations from multiple climate models](https://arxiv.org/abs/1711.04139)
- [Virdee et al. 2022, A locally time-invariant metric for climate model ensemble predictions of extreme risk](https://arxiv.org/abs/2211.16367)
