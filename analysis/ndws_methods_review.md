# NDWS / Crop Water Stress Methods Review

## Scope

Review focused on better-founded replacements or upgrades for Atlas-inspired `NDWS` / `NDWL0` logic in `climate-toolkit`.

Main question:

- What method should package use for crop water stress / waterlogging assessment?
- Which existing open code bases worth borrowing from, wrapping, or benchmarking against?

## Bottom Line

Best default path for this package:

1. Use **FAO-56 daily root-zone soil water balance** as core transparent method.
2. Use **FAO Penman-Monteith ETo** when inputs available.
3. Fall back to **Hargreaves** only when future-climate inputs lack humidity / wind / radiation.
4. Keep hazard thresholds as **package policy layer**, not method source.
5. Treat current Atlas-style `NDWS` / `NDWL0` as provisional mapping on top of water-balance outputs, not scientific foundation.

If later need higher-fidelity crop response / yield:

- benchmark or wrap **AquaCrop** / **AquaCrop-OSPy**

If later need climate-extreme indicators rather than crop water balance:

- use **xclim**
- add **SPEI** / SPI-style drought layer separately

## Best-Supported Methods

### 1. FAO-56 crop evapotranspiration + soil water balance

Strongest simple standard for package like this.

Why:

- widely used
- transparent
- daily timestep
- moderate data requirements
- easy to explain to users
- easy to wire into site-based workflows
- crop parameters can be overridden cleanly

Core pieces:

- `ETo`
- crop coefficients `Kc`
- optional dual coefficient split (`Kcb + Ke`)
- total available water `TAW`
- readily available water `RAW`
- root-zone depletion `Dr`
- water stress coefficient `Ks`

Practical implication for toolkit:

- `NDWS` should probably come from daily states like `Ks < threshold`, `Dr / TAW > threshold`, or cumulative stress days from standard root-zone balance.
- better than broad fixed-window day counts with generic defaults and no strong literature anchor.

Source:

- FAO-56 official table of contents shows exact sections for Penman-Monteith, dual `Kc`, soil water stress, `TAW`, `RAW`, `Ks`, and soil water balance:
  - https://www.fao.org/4/x0490e/x0490e00.htm

### 2. AquaCrop

Best next step if aim moves beyond hazard counts into crop response, biomass, yield, stress timing, irrigation scenarios.

Why:

- FAO-developed crop water productivity model
- built for water-limited production
- balances realism and usability
- official training covers soil water retention, stress coefficients, transpiration, yield response, irrigation management

Tradeoff:

- heavier than FAO-56 balance
- more parameters
- more model behavior to validate

Source:

- FAO official AquaCrop page:
  - https://www.fao.org/aquacrop/en/

### 3. SPEI / SPI layer

Useful, but different job.

Why:

- good for multi-timescale drought context
- useful companion hazard
- not substitute for crop-season root-zone balance

Use case:

- background drought context
- compare baseline vs future drying tendency
- companion indicator in reports

Not enough alone for crop water stress:

- no crop parameters
- no rooting depth dynamics
- no field water balance

Source:

- SPEI package repo and references:
  - https://github.com/sbegueria/SPEI

### 4. xclim-style climate hazard indices

Good for robust climate-extreme calculations. Not crop model.

Why:

- mature climate-index library
- built for gridded data, ensembles, xarray/dask
- useful for dry spells, heavy rain, heat indices, ensemble workflows

Use case:

- `CDD`, `Rx1day`, heat days, percentile extremes, ensemble climate diagnostics

Not enough alone for `NDWS`:

- no crop root-zone water balance

Source:

- xclim repo:
  - https://github.com/Ouranosinc/xclim

## Best Existing Code Bases

### 1. `pyfao56`

Most directly relevant lightweight code base.

Why strong fit:

- Python
- explicit FAO-56 implementation
- daily soil water balance
- single and dual crop coefficient methods
- irrigation scheduling logic
- easier to borrow from than full crop model

Likely best benchmark / borrowing target for toolkit core.

Source:

- repo:
  - https://github.com/kthorp/pyfao56

### 2. `AquaCrop-OSPy`

Best open Python crop-water model for deeper crop response.

Strengths:

- open-source Python implementation of AquaCrop-OS
- mirrors most features of official FAO AquaCrop 7.1
- designed for irrigation demand, management optimization, climate-change projections

Use:

- benchmark package outputs
- reference for stress logic
- possible advanced backend later

Source:

- repo:
  - https://github.com/aquacropos/aquacrop

### 3. `PCSE`

Good research-grade framework. Bigger, less direct fit.

Strengths:

- mature Python crop simulation environment
- extensible model framework
- useful if project wants model family beyond simple water-balance hazards

Tradeoff:

- heavier architecture
- more than current toolkit likely needs for first stable release

Source:

- repo:
  - https://github.com/ajwdewit/pcse

### 4. `xclim`

Best climate-indicator engine, not crop water engine.

Use:

- climate hazards
- ensemble post-processing
- standard extreme indices

Source:

- repo:
  - https://github.com/Ouranosinc/xclim

### 5. `SPEI`

Best established open drought-index package in this pass.

Use:

- add SPEI later as companion drought context
- not core crop-stress engine

Source:

- repo:
  - https://github.com/sbegueria/SPEI

## Recommendation For `climate-toolkit`

### Near-term

Implement:

- FAO-56-aligned daily root-zone balance
- crop parameter object:
  - `kc_init`
  - `kc_mid`
  - `kc_end`
  - `root_depth`
  - depletion fraction `p`
- soil parameter object:
  - field capacity
  - wilting point
  - available water capacity
  - rooting depth cap
  - drainage class / optional percolation factor

Then define package hazard outputs from standard states:

- `NDWS`: days where stress coefficient `Ks` below chosen threshold, or depletion ratio above chosen threshold
- `NDWL0`: days with near-saturation / logging state above chosen threshold

### Mid-term

Add:

- SPEI as companion drought indicator
- xclim-style rainfall / temperature extremes where helpful
- clear separation:
  - crop water balance hazards
  - climate extremes
  - drought context

### Longer-term

Benchmark against:

- `pyfao56` for water-balance logic
- `AquaCrop-OSPy` for crop-stress realism and irrigation behavior

## Important Design Note For This Repo

Historical pathway:

- AgERA5 gives enough variables for stronger ET method than Hargreaves.

Future NEX-GDDP pathway:

- current package usually has `pr`, `tasmax`, `tasmin`
- so pure FAO Penman-Monteith not available from NEX-GDDP alone

Implication:

- historical runs can use better ETo
- future runs either:
  - use Hargreaves consistently, or
  - blend future temperature/precip with companion assumptions / external ETo drivers

Need documentation clear here. Otherwise baseline vs future stress method may not be methodologically symmetric.

## What I Did Not Find In Quick Pass

- clean, maintained, obvious open Python code base for `WRSI` that looks better than `pyfao56` / `AquaCrop-OSPy` for this package purpose
- strong canonical published basis for current Atlas-style `NDWL0` thresholding as primary method source

## Recommendation Summary

If goal is robust, explainable, package-friendly:

- **borrow from FAO-56 / pyfao56 first**

If goal becomes crop-yield / advanced agronomy:

- **benchmark against AquaCrop**

If goal is climate hazard layer:

- **use xclim + SPEI separately**
