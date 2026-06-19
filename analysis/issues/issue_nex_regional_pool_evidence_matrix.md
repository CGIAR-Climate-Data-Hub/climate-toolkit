# NEX regional pool evidence matrix and selection rules

## Purpose

We need defensible regional NEX-GDDP model pools that make life easier for
users without turning ensemble selection into hidden ad hoc pruning.

This note records what we can already justify from authoritative sources, what
still needs region-by-region evidence, and how final pools should be
populated.

## Current agreed facts

- Toolkit should default to smaller, explicit pools because NEX-GDDP download
  from GEE is slow.
- Toolkit should not silently mix all available GEE NEX models if that breaks
  intended like-for-like interpretation.
- Current parent candidate universe is:
  - full `18`-model `v1.2`-comparable proxy pool
  - all screened to same intended realization basis used for our package
    interpretation
- Regional subsets may sit inside that parent pool.
- Models outside that `18` may be added only as explicit regional supplements,
  never silently.

## What authoritative sources support

### CORDEX / WCRP style lessons

- Regional climate information should be domain-aware and process-aware, not
  based on one global screening rule.
- Evaluation should focus on regional phenomena and local climate behavior,
  not annual mean only.
- Diversity and documented methodology matter; subset selection should stay
  transparent.

Sources:
- CORDEX vision and goals:
  [https://cordex.org/about/our-vision/](https://cordex.org/about/our-vision/)
- CORDEX Africa domain:
  [https://cordex.org/domains/region-5-africa/](https://cordex.org/domains/region-5-africa/)

### IPCC Atlas style lessons

- Regional projection workflows should be reproducible and explicit about
  methodology.
- Multi-model regional information should keep uncertainty language explicit.
- Reduced subsets can support decisions, but should not be presented as full
  structural uncertainty envelopes.

Source:
- IPCC WGI AR6 Atlas repository paper:
  [https://arxiv.org/abs/2204.14245](https://arxiv.org/abs/2204.14245)

## Peer-reviewed status as of 2026-06-19

We now have enough peer-reviewed support for the **selection framework**, but
not yet enough peer-reviewed support for most **regional named-model
memberships**.

What is already defensible from peer-reviewed literature:

- regional model evaluation should be process-aware and region-aware
- station/location sampling matters for precipitation evaluation
- single-metric model ranking is too weak
- historical skill can inform weighting or shortlisting, but should not be
  overclaimed as future certainty

What is **not** yet defensible enough to encode for most regions:

- exact `regional_standard_<region>` membership for `AFR-WAF`
- exact `regional_standard_<region>` membership for `AFR-MDG`
- exact Andes shortlist membership
- explicit outside-`18` hybrid supplements

Current implication for code:

- keep only `AFR-EAF-FAST-PROVISIONAL` as the one encoded subregional fast
  preset
- keep other regions on fallback policy until named-model evidence is
  documented cleanly

## Peer-reviewed method papers already supporting the workflow

These support **how** we should evaluate and screen models. They do **not** by
themselves justify exact regional pool membership.

### Geographic sampling and station-aware evaluation

- Risser and Wehner (2019):
  [The effect of geographic sampling on evaluation of extreme precipitation in high resolution climate models](https://arxiv.org/abs/1911.05103)
- Operational implication:
  - evaluate at actual station locations where possible
  - do not treat gridded observational products as interchangeable with
    station truth

### Distribution-aware ranking instead of one error metric

- Vissio et al. (2020):
  [Ranking IPCC Models Using the Wasserstein Distance](https://arxiv.org/abs/2006.09304)
- Operational implication:
  - use multi-metric or distribution-aware scoring
  - do not choose or prune GCMs on RMSE alone

### Observation-informed weighting / constraints

- Sansom et al. (2017):
  [On constraining projections of future climate using observations and simulations from multiple climate models](https://arxiv.org/abs/1711.04139)
- Operational implication:
  - historical skill can support weighting or shortlisting
  - do not present the top historical model as the future "winner"

### Regional reproducibility / explicit uncertainty communication

- IPCC AR6 Atlas workflow paper:
  [https://arxiv.org/abs/2204.14245](https://arxiv.org/abs/2204.14245)
- Operational implication:
  - keep regional methodology explicit
  - label reduced subsets as narrower decision pools, not full uncertainty
    envelopes

### NEX product constraints

- Earth Engine `NASA/GDDP-CMIP6` contains broader model availability than our
  selected parent pool.
- Toolkit intentionally uses narrower parent pool for consistent
  interpretation.
- NEX `v1.1` on GEE is current accessible backend; `v1.2` is not current
  working GEE backend for package.

Sources:
- Earth Engine catalog:
  [https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6](https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6)
- NASA tech note:
  [https://www.nccs.nasa.gov/sites/default/files/NEX-GDDP-CMIP6-Tech_Note.pdf](https://www.nccs.nasa.gov/sites/default/files/NEX-GDDP-CMIP6-Tech_Note.pdf)

## What these sources do **not** give us

- Final NEX regional pool membership for Africa or Andes
- Exact include/exclude tables for every subregion
- Evidence-driven justification for outside-18 supplements

Those must come from targeted regional literature review and documented
crosswalks to NEX model IDs.

## Pool hierarchy to implement

### 1. Strict proxy pool

- Name: `strict_proxy_full18`
- Meaning: full `18`-model `v1.2`-comparable proxy pool
- Use case: baseline default outside region-tuned presets
- Interpretation: strongest like-for-like comparability; slower than subset
  presets; still not full archive

### 2. Regional standard pool

- Name pattern: `regional_standard_<region>`
- Meaning: region-tuned subset inside `strict_proxy_full18`
- Use case: default for accessibility and regionally relevant decision support
- Interpretation: narrower uncertainty than full `18`; explicitly conditional
  on regional screening policy

### 3. Regional fast pool

- Name pattern: `regional_fast_<region>`
- Meaning: smaller diverse subset inside regional standard pool
- Use case: quick scoping runs
- Interpretation: fastest, but uncertainty most conditional

### 4. Hybrid regional pool

- Name pattern: `hybrid_regional_<region>`
- Meaning: regional standard pool plus explicit supplement(s) outside `18`
- Use case: only when regional evidence strongly supports extra model(s)
- Interpretation: better regional representation, weaker strict proxy
  comparability

## Selection rules

Regional pools should be populated from evidence matrix below, not memory.

Include model in regional standard pool only if:

- evidence is region-specific
- evidence is process-specific
- evidence maps cleanly to NEX model ID
- model is not obvious near-duplicate of already included family unless
  duplicate retained for clear reason

Priority evaluation criteria:

1. rainfall seasonality and timing
2. onset / cessation behavior
3. wet-day frequency
4. dry-spell structure
5. seasonal totals
6. heavy-rain behavior / extremes
7. temperature seasonality
8. topographic relevance where applicable

Outside-18 supplement rule:

- only add if regional evidence is strong and explicit
- log exact inclusion reason in metadata
- mark final pool as `hybrid_regional`, not `strict_proxy`

## Minimum evidence threshold before encoding a regional pool

Do **not** encode a new `regional_standard_<region>` or
`hybrid_regional_<region>` pool unless all of the following are satisfied:

1. at least one region-specific peer-reviewed source evaluates named CMIP6
   models against processes relevant to that region
2. named models can be cross-walked unambiguously to NEX model IDs
3. the evidence is specific enough to justify include/exclude logic, not just
   general statements that the region is difficult or needs local evaluation
4. process relevance is clear for at least one of:
   - rainfall seasonality / timing
   - onset / cessation
   - monsoon or regime behavior
   - wet-day frequency
   - dry spells
   - heavy rain / extremes
   - temperature seasonality
5. if a model outside the package `18` is proposed, a specific inclusion reason
   is recorded and comparability class is downgraded to `hybrid_regional`

Recommended stronger threshold before declaring a pool "standard" rather than
"provisional":

- two independent region-specific sources, or
- one peer-reviewed region-specific source plus one validated operational
  regional guidance source pointing in the same direction

## Evidence matrix template

Populate one row per source x region x model conclusion.

| region | subregion | source_type | source | variable_or_process | model_name_in_source | NEX_model_id | finding | include_signal | confidence | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Africa | AFR-EAF | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | MAM rainfall / regional ensemble behavior | ACCESS-ESM1-5 | ACCESS-ESM1-5 | explicitly highlighted as strong for EAF shortlist context | provisional_include | medium | needs direct literature backing before hard-coding final pool |
| Africa | AFR-EAF | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | MAM rainfall / regional ensemble behavior | EC-Earth3-Veg-LR | EC-Earth3-Veg-LR | explicitly highlighted as strong for EAF shortlist context | provisional_include | medium | same caveat |
| Africa | AFR-EAF | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | MAM rainfall / regional ensemble behavior | MRI-ESM2-0 | MRI-ESM2-0 | explicitly highlighted as strong for EAF shortlist context | provisional_include | medium | same caveat |
| Africa | AFR-EAF | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | MAM rainfall / regional ensemble behavior | IPSL-CM6A-LR | IPSL-CM6A-LR | explicitly highlighted as strong for EAF shortlist context | provisional_include | medium | same caveat |
| Africa | AFR-EAF | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | MAM rainfall / regional ensemble behavior | MPI-ESM1-2-HR | MPI-ESM1-2-HR | explicitly highlighted as strong for EAF shortlist context | provisional_include | medium | same caveat |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | total rainfall / annual cycle / multi-index regional screening | INM-CM5-0 | INM-CM5-0 | included in best 10 performing models over IGAD region | include_signal | medium | region-specific peer-reviewed support; strong candidate for EAF pool revision |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | total rainfall / annual cycle / multi-index regional screening | IPSL-CM6A-LR | IPSL-CM6A-LR | included in best 10 performing models over IGAD region | include_signal | medium | region-specific peer-reviewed support |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | total rainfall / annual cycle / multi-index regional screening | EC-Earth3 | EC-Earth3 | included in best 10 performing models over IGAD region | include_signal | medium | region-specific peer-reviewed support |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | total rainfall / annual cycle / multi-index regional screening | GFDL-ESM4 | GFDL-ESM4 | included in best 10 performing models over IGAD region | include_signal | medium | region-specific peer-reviewed support |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | total rainfall / annual cycle / multi-index regional screening | TaiESM1 | TaiESM1 | included in best 10 performing models over IGAD region | include_signal | medium | region-specific peer-reviewed support |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP annual precipitation best-five selection | IPSL-CM6A-LR | IPSL-CM6A-LR | selected among annual precipitation best-performing NEX-GDDP models for East Africa | include_signal | medium | direct NEX-GDDP evidence, not raw-CMIP6 only |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP annual precipitation best-five selection | CanESM5 | CanESM5 | selected among annual precipitation best-performing NEX-GDDP models for East Africa | include_signal | medium | direct NEX-GDDP evidence, not raw-CMIP6 only |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP annual temperature best-five selection | EC-Earth3 | EC-Earth3 | selected among annual temperature best-performing NEX-GDDP models for East Africa | include_signal | medium | direct NEX-GDDP evidence, not raw-CMIP6 only |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP MAM temperature best-five selection | INM-CM4-8 | INM-CM4-8 | selected among MAM temperature best-performing NEX-GDDP models for East Africa | include_signal | medium | direct NEX-GDDP evidence, not raw-CMIP6 only |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP annual precipitation best-five selection | MPI-ESM1-2-HR | MPI-ESM1-2-HR | selected among annual precipitation best-performing NEX-GDDP models for East Africa | include_signal | medium | strengthens prior secondary support |
| Africa | AFR-EAF / East Africa | peer_reviewed | Umwali et al. 2024, Estimating the Effects of Climate Fluctuations on Precipitation and Temperature in East Africa, Atmosphere 15(12):1455 | NEX-GDDP annual temperature best-five selection | ACCESS-ESM1-5 | ACCESS-ESM1-5 | selected among annual temperature best-performing NEX-GDDP models for East Africa | mixed_signal | medium | conflicts with IGAD rainfall caution; retain as variable-specific mixed evidence |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | rainfall bias / overestimation across IGAD | ACCESS-ESM1-5 | ACCESS-ESM1-5 | among most over-estimated rainfall models over IGAD region | exclude_signal | medium | direct caution against uncritical EAF inclusion |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | rainfall bias / overestimation across IGAD | MIROC6 | MIROC6 | among most over-estimated rainfall models over IGAD region | exclude_signal | medium | direct caution signal |
| Africa | AFR-EAF / IGAD | peer_reviewed | Omay et al. 2024, CMIP6 rainfall evaluation over IGAD Eastern Africa, doi:10.1007/s44274-023-00012-2 | rainfall bias / underestimation across IGAD | CNRM-CM6-1-HR | CNRM-CM6-1-HR | most under-estimated rainfall model with high negative bias and RMSE | exclude_signal | medium | region-specific caution signal |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | heavy rainfall frequency / 95th percentile extremes | INM-CM5-0 | INM-CM5-0 | smaller discrepancies in extreme rainfall estimates and closer performance to observations | include_signal | medium | West-Africa-specific extremes support; not full all-metric shortlist by itself |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | heavy rainfall frequency RMSE | TaiESM1 | TaiESM1 | among best-performing models for heavy-rainfall frequency against observations | include_signal | medium | West-Africa-specific support in extremes context |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | heavy rainfall frequency RMSE | IPSL-CM6A-LR | IPSL-CM6A-LR | among best-performing models for heavy-rainfall frequency against observations | include_signal | medium | West-Africa-specific support in extremes context |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | heavy rainfall frequency / 95th percentile extremes | MIROC6 | MIROC6 | among largest-error models for heavy-rainfall frequency and 95th percentile extremes | exclude_signal | medium | direct West Africa caution signal |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | heavy rainfall frequency / 95th percentile extremes | GFDL-ESM4 | GFDL-ESM4 | among largest-error models for heavy-rainfall frequency and 95th percentile extremes | exclude_signal | medium | direct West Africa caution signal |
| Africa | AFR-WAF / West Africa | peer_reviewed | Klutse et al. 2021, Summer monsoon extreme precipitation over West Africa in CMIP6 simulations, doi:10.1007/s41748-021-00203-y | mean intensity / 95th percentile extreme bias | FGOALS-f3-L | FGOALS-f3-L | more intensified daily rainfall events and high deviation in rainfall intensity and 95th percentile extremes | exclude_signal | medium | West-Africa-specific caution signal |
| Africa | continental | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | hot/cold extremes / validation | CanESM5 | CanESM5 | explicitly excluded from African default ensemble | include_exclude_signal | medium | good for current `AFR-13` default logic |
| Africa | continental | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | hot/cold extremes / validation | INM-CM4-8 | INM-CM4-8 | explicitly excluded from African default ensemble | include_exclude_signal | medium | good for current `AFR-13` default logic |
| Africa | continental | atlas/wiki secondary | CGIAR African CMIP6 ensembling wiki | hot/cold extremes / validation | INM-CM5-0 | INM-CM5-0 | explicitly excluded from African default ensemble | include_exclude_signal | medium | good for current `AFR-13` default logic |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | ACCESS-ESM1-5 | ACCESS-ESM1-5 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | CMCC-ESM2 | CMCC-ESM2 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | EC-EARTH3 | EC-Earth3 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | KACE-1-0-G | KACE-1-0-G | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | MIROC6 | MIROC6 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | MRI-ESM2-0 | MRI-ESM2-0 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | broad regional screening / subjective + objective evaluation | TaiESM1-0 | TaiESM1 | included in Top7-CMIP6-SA shortlist | include_signal | medium | South America-wide, not Andes-only |
| South America | continental | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | whole-domain precipitation and temperature Taylor-diagram screening | GFDL-ESM4 | GFDL-ESM4 | selected among nine best CMIP6 models over CSA and retained in seven-best SSP5-8.5 subset | include_signal | medium | South America-wide support; not Andes-specific; independent reinforcement of GFDL-ESM4 |
| South America | continental | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | whole-domain precipitation and temperature Taylor-diagram screening | MRI-ESM2-0 | MRI-ESM2-0 | selected among nine best CMIP6 models over CSA and retained in seven-best SSP5-8.5 subset | include_signal | medium | South America-wide support; not Andes-specific; independent reinforcement of MRI-ESM2-0 |
| Andes | Andes hotspot | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | precipitation annual cycle / wet-month bias | ACCESS-ESM1-5 | ACCESS-ESM1-5 | highlighted among models with general wet-month overestimation in Andes hotspot | exclude_signal | medium | Andes-specific caution signal; annual-cycle framing, not full all-metric rejection |
| Andes | Andes hotspot | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | precipitation annual cycle realism | NorESM2-LM | NorESM2-LM | captures observed precipitation annual cycle more realistically in Andes hotspot | include_signal | medium | Andes-specific support row from annual-cycle analysis |
| Andes | Andes hotspot | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | temperature annual cycle realism | MPI-ESM1-2-HR | MPI-ESM1-2-HR | captures mean annual cycle of temperature in Andes more realistically | include_signal | medium | Andes-specific temperature support row |
| Andes | Andes hotspot | peer_reviewed | Ortega et al. 2021, Present-day and future climate over central and South America according to CMIP5/CMIP6 models, Int J Climatol, doi:10.1002/joc.7221 | precipitation annual cycle / wet-month bias | MIROC6 | MIROC6 | highlighted among models with general wet-month overestimation in Andes hotspot | exclude_signal | medium | Andes-specific caution signal; annual-cycle framing, not full all-metric rejection |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | annual precipitation cycle / ensemble subset behavior | Top7-CMIP6-SA ensemble | n/a | Top7 subset outperformed full 28-model ensemble in some AR6 regions, especially north of South America | support_signal | low | ensemble-level support only; useful for subset logic, not direct Andes model membership |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | circulation / ITCZ / subtropical anticyclones | AWI-ESM-1-1-LR | AWI-ESM-1-1-LR | poor representation of key lower-level systems | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | circulation / ITCZ / subtropical anticyclones | BCC-ESM1 | BCC-ESM1 | poor representation of key lower-level systems | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | circulation / ITCZ / subtropical anticyclones | IITM-ESM | IITM-ESM | poor representation of key lower-level systems | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | AWI-ESM-1-1-LR | AWI-ESM-1-1-LR | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | CAS-ESM2-0 | CAS-ESM2-0 | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | CNRM-ESM2-1 | CNRM-ESM2-1 | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | FGOALS-f3-L | FGOALS-f3-L | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | GISS-E2-1-G | GISS-E2-1-G | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | INM-CM5-0 | INM-CM5-0 | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | IPSL-CM6A-LR-INCA | IPSL-CM6A-LR | poor upper-level feature representation | exclude_signal | medium | NEX crosswalk caution: INCA variant naming |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | MPI-ESM-1-2-HAM | MPI-ESM-1-2-HAM | poor upper-level feature representation | exclude_signal | medium | model not in current 18-model parent pool |
| South America | continental | peer_reviewed | Bazzanela et al. 2024, Performance of CMIP6 models over South America, Clim Dyn, doi:10.1007/s00382-023-06979-1 | Bolivian High / Northeast Brazilian Trough | NESM3 | NESM3 | poor upper-level feature representation | exclude_signal | medium | broad South America signal |
| Africa | AFR-WSAF / Southern Africa | peer_reviewed | Climate 2025 Part 2, Southern Africa extreme precipitation evaluation, doi:10.3390/cli13050093 | DJF extreme precipitation / bias-corrected strategy support | EC-Earth3-Veg | EC-Earth3-Veg-LR | among better-performing corrected strategies for Southern Africa extremes | support_signal | medium | support-only row; not raw-CMIP6 shortlist; NEX crosswalk caution from EC-Earth3-Veg to EC-Earth3-Veg-LR |
| Africa | AFR-WSAF / Southern Africa | peer_reviewed | Climate 2025 Part 2, Southern Africa extreme precipitation evaluation, doi:10.3390/cli13050093 | DJF extreme precipitation / bias-corrected strategy support | EC-Earth3 | EC-Earth3 | among better-performing corrected strategies for Southern Africa extremes | support_signal | medium | support-only row; not enough alone for coded pool |
| Africa | AFR-WSAF / Southern Africa | peer_reviewed | Climate 2025 Part 2, Southern Africa extreme precipitation evaluation, doi:10.3390/cli13050093 | DJF extreme precipitation / bias-corrected strategy support | MRI-ESM2 | MRI-ESM2-0 | among better-performing corrected strategies for Southern Africa extremes | support_signal | medium | support-only row; model naming crosswalk MRI-ESM2 -> MRI-ESM2-0 |
| Africa | AFR-WSAF / Southern Africa | peer_reviewed | Ngoma et al. 2025, Africa-wide CMIP6 MMM evaluation, doi:10.1007/s40808-025-02560-3 | broad Africa subregional rainfall and temperature skill | GFDL-ESM4 | GFDL-ESM4 | often strong in Africa-wide evaluation, but not Southern-Africa-only shortlist evidence | support_signal | low | continent-scale support only; insufficient for subregional coding |
| Africa | AFR-WSAF / Southern Africa | peer_reviewed | Climate 2025 Part 2, Southern Africa extreme precipitation evaluation, doi:10.3390/cli13050093 | DJF extreme precipitation / bias-correction sensitivity | multi-model ensemble | n/a | ensemble mean also performs well; supports keeping multi-model framing over single-model claims | support_signal | low | methodological support row; no direct model membership |

## Immediate work plan

### Africa

Build evidence rows for:

- AFR-EAF / Horn
- AFR-WAF
- AFR-CAF
- AFR-WSAF
- AFR-ESAF
- AFR-MDG

Minimum deliverable:

- draft `regional_standard` pool for each subregion
- confidence label per pool
- explicit unresolved gaps

Current status after source check:

- `AFR-EAF` / Horn:
  - now has direct peer-reviewed IGAD support/caution rows plus East Africa
    NEX-GDDP support rows
  - enough evidence to revisit current provisional fast shortlist
  - stronger basis now exists for a revised provisional regional fast pool
- `AFR-WAF`, `AFR-CAF`, `AFR-WSAF`, `AFR-ESAF`, `AFR-MDG`:
  - not enough source-backed exact memberships yet
  - do not hard-code memberships yet

## Literature-harvest protocol for remaining regions

Use this protocol before adding new pools:

1. identify region-specific peer-reviewed evaluation papers
2. extract:
   - region / subregion
   - variable or process evaluated
   - named CMIP6 models
   - whether finding is positive, negative, or mixed
   - any caution on independence or family duplication
3. crosswalk paper model names to NEX model IDs
4. mark whether each supported model lies inside the package `18`-model parent
   proxy pool
5. summarize whether support is strong enough for:
   - `regional_fast`
   - `regional_standard`
   - or no coded pool yet

Priority order for next harvest:

1. `AFR-WAF`
2. `AFR-MDG`
3. Andes
4. `AFR-CAF`
5. `AFR-WSAF`
6. `AFR-ESAF`

### AFR-WAF status note

Latest targeted pass now yields **West-Africa-specific support and caution
rows**, but still not enough exact multi-process evidence to encode a final
`AFR-WAF` pool.

What this means:

- keep `AFR-WAF` on fallback policy for now
- do not infer West Africa membership from East/Horn behavior
- do not translate broad CORDEX/IPCC regional-method lessons into exact NEX
  model names without direct evidence
- West Africa extremes evidence now supports:
  - positive signals for `INM-CM5-0`, `TaiESM1`, `IPSL-CM6A-LR`
  - caution signals for `MIROC6`, `GFDL-ESM4`, `FGOALS-f3-L`

What would be sufficient before coding `AFR-WAF`:

- regional paper or validated guidance naming individual CMIP6 models with
  clear precipitation / monsoon / seasonality performance signal for West
  Africa
- clean crosswalk from paper model names to NEX model IDs inside toolkit's
  `18`-model parent pool
- enough support to justify include/exclude logic, not just generic statement
  that West Africa needs regional evaluation

Current search result:

- targeted literature sweep now recovered source-safe **extremes-focused**
  membership signals from Klutse et al. 2021
- this is enough to populate evidence rows and inform later shortlist logic
- this is still **not** enough for a final West Africa standard pool because
  evidence remains concentrated on monsoon daily extremes, not full seasonal /
  multi-process regional behavior

Gap review:

- strongest current West Africa evidence axis:
  - daily monsoon rainfall extremes
- still missing before final pool:
  - broader annual-cycle / seasonality support
  - onset / cessation support
  - explicit subregional differentiation between Guinea Coast and Sahel

### Revised provisional AFR-WAF candidates from current evidence

This is **not** final coding guidance yet. Current support is too
extremes-concentrated for a stable regional fast pool.

| model | current status | current evidence summary |
| --- | --- | --- |
| `INM-CM5-0` | strongest add candidate | West Africa extremes support; smaller discrepancies and closer performance to observations |
| `IPSL-CM6A-LR` | strong add candidate | West Africa heavy-rainfall-frequency support |
| `TaiESM1` | strong add candidate | West Africa heavy-rainfall-frequency support |
| `ACCESS-CM2` | watchlist candidate | Klutse text says model does well in representing extreme events, but evidence is weaker than top three |
| `MRI-ESM2-0` | watchlist candidate | appears in similar-pattern group for 95th percentile extremes, but not clearly top-ranked |
| `MIROC6` | exclude / caution | largest-error signal for heavy-rainfall frequency and 95th percentile extremes |
| `GFDL-ESM4` | exclude / caution | largest-error signal for heavy-rainfall frequency and 95th percentile extremes |
| `FGOALS-f3-L` | exclude / caution | intensified rainfall-event bias and high deviation in extremes |

Practical implication:

- if forced to build **extremes-focused West Africa watchlist today**, best
  three are:
  - `INM-CM5-0`
  - `IPSL-CM6A-LR`
  - `TaiESM1`
- this is still not enough to define `AFR-WAF-FAST-PROVISIONAL` for general
  toolkit use

### West Africa candidate conclusion

Current evidence supports:

- building a **West Africa extremes watchlist**
- not yet building a general West Africa fast pool

Needed before code candidate becomes reasonable:

- one additional West-Africa-specific paper with annual-cycle / seasonality /
  monsoon-timing relevance
- some signal on Guinea Coast vs Sahel differentiation

### AFR-MDG status note

Latest targeted pass did **not** yield an authoritative, source-verifiable
Madagascar exact shortlist that we can safely encode.

What this means:

- keep `AFR-MDG` on fallback policy for now
- do not infer Madagascar membership from East/Horn or broader Africa default
- do not treat southwest Indian Ocean / generic tropical process papers as
  direct NEX model shortlist evidence

Current search result:

- methodological reason for Madagascar-specific treatment is clear
- exact named-model evidence strong enough for NEX shortlist coding is still
  missing

### AFR-EAF provisional fast-pool check against peer-reviewed evidence

Current coded `AFR-EAF-FAST-PROVISIONAL`:

- `ACCESS-ESM1-5`
- `EC-Earth3-Veg-LR`
- `IPSL-CM6A-LR`
- `MPI-ESM1-2-HR`
- `MRI-ESM2-0`

Direct peer-reviewed East Africa / IGAD signals now available:

- supported:
  - `INM-CM5-0`
  - `IPSL-CM6A-LR`
  - `EC-Earth3`
  - `GFDL-ESM4`
  - `TaiESM1`
- cautioned:
  - `ACCESS-ESM1-5`
  - `MIROC6`
  - `CNRM-CM6-1-HR`

Implication:

- first East Africa peer-reviewed source alone was enough to question current
  coded fast pool
- second East Africa `NEX-GDDP-CMIP6` source now adds variable-specific
  support for `CanESM5`, `MPI-ESM1-2-HR`, `EC-Earth3`, `INM-CM4-8`, and mixed
  evidence for `ACCESS-ESM1-5`

Safe conclusion for now:

- do not silently keep treating current coded EAF fast pool as settled
- East Africa provisional pool revision can now be discussed on two-source
  footing, but should still be labeled provisional rather than final

### AFR-EAF second-source status

Second East Africa reinforcement source is now secured from user-supplied PDF:

- Umwali et al. 2024, Atmosphere 15(12):1455
- direct East Africa `NEX-GDDP-CMIP6` evaluation

Implication:

- East Africa evidence now includes:
  - one region-specific raw/CMIP6 rainfall-evaluation source over IGAD
  - one region-specific `NEX-GDDP-CMIP6` evaluation source over East Africa
- revised East Africa fast-pool discussion remains `provisional`, but no longer
  rests on single-source support

### Revised provisional AFR-EAF fast candidates from current evidence

This is **not** final coding guidance yet. It is current evidence-backed
direction of travel.

| model | current status | current evidence summary |
| --- | --- | --- |
| `IPSL-CM6A-LR` | strong keep candidate | supported by IGAD rainfall paper and East Africa NEX-GDDP paper |
| `EC-Earth3` / `EC-Earth3-Veg-LR` | strong keep candidate with naming caveat | supported by IGAD rainfall paper and East Africa NEX-GDDP annual-temperature paper; variant naming caveat remains |
| `INM-CM5-0` | add candidate | direct peer-reviewed IGAD support; still strongest rainfall-side add candidate |
| `MPI-ESM1-2-HR` | upgrade candidate | East Africa NEX-GDDP annual-precipitation support plus prior secondary Africa support |
| `CanESM5` | add candidate | East Africa NEX-GDDP annual-precipitation support; note Africa secondary guidance caution remains continent-level and for different use context |
| `ACCESS-ESM1-5` | mixed / review | IGAD rainfall caution conflicts with East Africa annual-temperature support |
| `GFDL-ESM4` | watchlist candidate | strong IGAD rainfall support but direct West Africa extremes caution elsewhere; may be region-sensitive |
| `TaiESM1` | watchlist candidate | strong IGAD rainfall support, but not reinforced by East Africa NEX-GDDP paper |
| `INM-CM4-8` | temperature-side add candidate | East Africa NEX-GDDP MAM-temperature support; not reinforced by IGAD rainfall paper |
| `MRI-ESM2-0` | watchlist only | no new East Africa reinforcement in second source |

Practical implication:

- if forced to keep five-model provisional fast pool **today**, evidence now
  points more toward:
  - `IPSL-CM6A-LR`
  - `EC-Earth3` or `EC-Earth3-Veg-LR`
  - `INM-CM5-0`
  - `MPI-ESM1-2-HR`
  - `CanESM5`
- alternative mixed-variable candidate set if rainfall skill is prioritized more
  strongly than temperature:
  - `IPSL-CM6A-LR`
  - `EC-Earth3` or `EC-Earth3-Veg-LR`
  - `INM-CM5-0`
  - `GFDL-ESM4`
  - `TaiESM1`

### Proposed `AFR-EAF-FAST-PROVISIONAL v2`

Recommended provisional update target:

- `IPSL-CM6A-LR`
- `EC-Earth3-Veg-LR`
- `INM-CM5-0`
- `MPI-ESM1-2-HR`
- `CanESM5`

Why this set:

- keeps one EC-Earth branch already aligned with current package naming
- retains `IPSL-CM6A-LR` as strongest cross-source keep
- adds `INM-CM5-0` from direct IGAD rainfall support
- retains `MPI-ESM1-2-HR` because East Africa NEX-GDDP annual-precipitation
  support now reinforces earlier secondary guidance
- adds `CanESM5` because second East Africa source directly supports it for
  NEX-GDDP annual precipitation

Why this is still only provisional:

- `CanESM5` conflicts with continent-level secondary Africa caution used in
  current broader African ensemble logic
- `EC-Earth3-Veg-LR` is supported through `EC-Earth3` family evidence, not yet
  exact same-named-model peer-reviewed East Africa row
- `INM-CM5-0` is strong on rainfall-side evidence but not reinforced in second
  East Africa NEX-GDDP paper
- no explicit independence / family-diversity screen has yet been applied

Why not keep current v1 unchanged:

- `ACCESS-ESM1-5` now has direct East Africa rainfall caution
- `MRI-ESM2-0` did not gain East Africa reinforcement in second source
- current five-model set now looks more legacy-guidance-driven than
  evidence-balanced

Why not choose rainfall-heavier alternative as default:

- `GFDL-ESM4` has East Africa rainfall support but direct West Africa extremes
  caution
- `TaiESM1` has direct IGAD support but no reinforcement from East Africa
  NEX-GDDP paper
- `CanESM5` and `MPI-ESM1-2-HR` now have direct East Africa NEX-GDDP support,
  making them better package-facing fast-pool defaults if mixed precipitation +
  temperature use is expected

Suggested labels if code changes later:

- `AFR-EAF-FAST-PROVISIONAL-V2`
- confidence: `medium`
- rationale class:
  - `two_source_regional_provisional`
  - one raw/CMIP6 rainfall source
  - one NEX-GDDP East Africa source

Suggested metadata note:

> East Africa fast subset is a reduced decision-support pool, not a full
> structural uncertainty envelope. Membership reflects current regional
> peer-reviewed evidence available to this package as of 2026-06-19 and should
> be revisited as additional East Africa and Horn-focused evaluation studies are
> added.

### Next code action for `AFR-EAF`

If package policy is updated, implementation should:

1. keep current v1 subset available for reproducibility in old outputs
2. add explicit v2 subset name rather than silently mutating old one
3. expose evidence note path in metadata or docs
4. log that v2 is East-Africa-specific and provisional
5. avoid promoting v2 as continent-wide Africa default

### Southern Africa status note

Latest targeted pass found **supportive** Southern Africa evidence rows, but
still not enough exact shortlist evidence to encode `AFR-WSAF` or `AFR-ESAF`
as final regional pools.

What this means:

- Climate 2025 Part 2 gives useful Southern Africa support for
  `EC-Earth3-Veg`, `EC-Earth3`, and `MRI-ESM2` in DJF extreme precipitation
  context
- those signals are still tied to bias-corrected / evaluation framing, not a
  clean raw-CMIP6 regional shortlist rule
- Africa-wide MMM support for `GFDL-ESM4` is useful context, but too broad to
  hard-code a Southern Africa pool

Current interpretation:

- add these rows as **support evidence**
- keep confidence low-to-medium
- do not yet code `AFR-WSAF` or `AFR-ESAF`

### Andes

Need dedicated sweep for:

- rainfall seasonality
- topographic sensitivity
- wet/dry season timing
- extremes where evidence exists

Current status after first pass:

- strong methodological reason exists for Andes-specific treatment:
  topography, wet/dry seasonality, and hydroclimate sensitivity
- current sweep now includes one South America-wide peer-reviewed shortlist:
  `ACCESS-ESM1-5`, `CMCC-ESM2`, `EC-Earth3`, `KACE-1-0-G`, `MIROC6`,
  `MRI-ESM2-0`, `TaiESM1`
- this is useful for Andes-facing screening context but remains
  **South America-wide**, not Andes-specific
- therefore Andes still remains evidence-gap for a final coded Andes pool;
  current evidence is strong enough for background support, not final coding

Gap review:

- strongest current Andes evidence axis:
  - annual-cycle realism and wet-month bias
- still missing before final pool:
  - stronger Andes-only multi-metric shortlist paper
  - topography-sensitive seasonal timing support
  - clearer evidence for extreme rainfall and dry-spell behavior in Andes

### Revised provisional Andes candidates from current evidence

This is **not** final coding guidance yet. Andes evidence currently mixes:

- Andes-specific annual-cycle support/caution
- South-America-wide shortlist support

| model | current status | current evidence summary |
| --- | --- | --- |
| `NorESM2-LM` | strongest Andes-specific add candidate | captures Andes hotspot precipitation annual cycle more realistically |
| `MPI-ESM1-2-HR` | strong add candidate | captures Andes hotspot temperature annual cycle more realistically |
| `EC-Earth3` | watchlist candidate | South America-wide shortlist support; no direct Andes-specific row yet |
| `MRI-ESM2-0` | watchlist candidate | South America-wide shortlist support; no direct Andes-specific row yet |
| `KACE-1-0-G` | watchlist candidate | South America-wide shortlist support; no direct Andes-specific row yet |
| `TaiESM1` | watchlist candidate | South America-wide shortlist support; no direct Andes-specific row yet |
| `ACCESS-ESM1-5` | exclude / caution | Andes hotspot wet-month overestimation |
| `MIROC6` | exclude / caution | Andes hotspot wet-month overestimation despite broader South America shortlist support |

Practical implication:

- if forced to form **Andes screening watchlist today**, most defensible mix is:
  - `NorESM2-LM`
  - `MPI-ESM1-2-HR`
  - `EC-Earth3`
  - `MRI-ESM2-0`
  - `KACE-1-0-G`
- this remains weaker than East Africa because only two rows are directly
  Andes-specific

### Andes candidate conclusion

Current evidence supports:

- building an **Andes screening watchlist**
- not yet building a final Andes fast pool

Needed before code candidate becomes reasonable:

- one additional Andes-focused peer-reviewed evaluation source
- preferably one with multi-metric ranking and topographic / seasonal-timing
  relevance

### Supplements outside `18`

Do not populate yet.

First require:

- source-backed candidate list
- process-specific reason
- explicit note that comparability class changes to `hybrid_regional`

## Output/metadata requirements

Toolkit outputs should eventually expose:

- `base_pool`
- `regional_pool`
- `regional_supplements`
- `selection_rationale`
- `comparability_class`
- `evidence_confidence`

## Recommendation

Do not hard-code final Africa or Andes pools yet.

Next safe step:

1. keep `strict_proxy_full18` as parent pool
2. keep current Africa default marked as provisional evidence-based policy
3. fill evidence matrix region by region before locking final memberships

## First coded regional pool

Only one subregional pool is currently safe to encode without inventing
memberships:

- `AFR-EAF-FAST-PROVISIONAL`
  - models:
    - `ACCESS-ESM1-5`
    - `EC-Earth3-Veg-LR`
    - `IPSL-CM6A-LR`
    - `MPI-ESM1-2-HR`
    - `MRI-ESM2-0`
  - evidence basis:
    - secondary African CMIP6 regional guidance already verified in prior
      project work
  - confidence:
    - `medium`
  - interpretation:
    - fast East/Horn screening subset inside `18`-model proxy parent pool
    - not final East Africa standard pool
