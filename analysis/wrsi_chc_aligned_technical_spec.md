# CHC-Aligned WRSI Technical Spec

## Purpose

Define `WRSI` integration for `climate-toolkit` aligned with **technical method family** used in FEWS / CHC-style seasonal crop water monitoring.

Not goal:

- bind package to CHC portals
- copy CHC stack
- require CHC-only datasets

Goal:

- use compatible science logic
- keep package modular
- make assumptions explicit

## Confidence Levels

### Confirmed from accessible sources

- CHC precipitation backbone strongly centered on **CHIRPS** for seasonal drought monitoring and early warning.  
  Source: [CHIRPS page](https://www.chc.ucsb.edu/data/chirps)
- CHC temperature hazard work uses **CHIRTS-ERA5** for low-latency monitoring and historical-context hazard analysis.  
  Source: [CHIRTS-ERA5 page](https://www.chc.ucsb.edu/data/chirts-era5)
- Best transparent open crop-water balance reference code found in this pass is **FAO-56-style** `pyfao56`.  
  Source: [pyfao56](https://github.com/kthorp/pyfao56)
- FAO-56 remains strongest open standard for crop coefficients, root-zone depletion, stress coefficient, and daily soil water balance framing.  
  Source: [FAO-56](https://www.fao.org/4/x0490e/x0490e00.htm)

### Not yet pinned to official public CHC / GeoWRSI source in this pass

- exact operational CHC / FEWS WRSI timestep defaults
- exact effective-rainfall rule
- exact soil carry-over rule
- exact default crop-stage lengths and class cutoffs

So spec below should be treated as:

- **aligned target architecture**
- **strong method-family fit**
- **pending final confirmation against GeoWRSI / FEWS documentation if found**

## Method Alignment: Non-Negotiables

If package says `WRSI`, it should behave like seasonal crop water satisfaction model. Means:

1. **Stage-based crop water requirement**
   - crop water demand changes by growth stage
   - use `Kc` or equivalent stage coefficients

2. **Running seasonal accounting**
   - not simple end-of-season rainfall ratio
   - update through season at daily or dekadal resolution

3. **Reference ET / PET backbone**
   - crop water requirement should come from `ETo * Kc`
   - not from rainfall alone

4. **Soil water carry / bucket**
   - unmet demand and stored moisture must matter
   - otherwise no real satisfaction accounting

5. **Crop-season framing**
   - depends on planting / onset / season window
   - should not be computed over arbitrary climate windows without crop meaning

6. **Seasonal satisfaction output**
   - single seasonal score
   - optional running progression curve
   - optional categorical interpretation

## Recommended Package Formulation

### Core state variables

For each site and timestep:

- `P_t`: precipitation
- `ETo_t`: reference evapotranspiration
- `Kc_t`: crop coefficient by stage
- `CWR_t = Kc_t * ETo_t`: crop water requirement
- `S_t`: soil water storage
- `AET_t`: actual evapotranspiration available to crop
- `D_t`: unmet demand or depletion

### Soil bucket

Use simple root-zone bucket:

- `0 <= S_t <= TAW`
- `TAW` from root depth × available water capacity
- incoming water from rainfall effective for root zone
- outgoing water from `AET`
- optional deep drainage cap above field capacity / saturation

This stays compatible with broader FAO-56 logic and later `NDWS` harmonization.

### Seasonal water satisfaction

Recommended primary package formulation:

- `WRSI = 100 * sum(AET_t) / sum(CWR_t)`

with:

- lower bound `0`
- upper bound `100`

Why:

- matches core idea of “requirement satisfaction”
- harmonizes with stage-based ET demand
- easy to explain
- easy to benchmark

Alternative equivalent form:

- accumulate deficits and compute satisfaction from unmet requirement

### Timestep

Internal model:

- **daily**

User-facing rollups:

- **dekadal**
- monthly
- full-season

Reason:

- package already works heavily with daily data
- daily supports `NDWS`, dry spells, rainfall extremes, waterlogging
- dekadal outputs can be derived later for CHC-style reporting

## Data Inputs

### Historical / recent climate

Preferred technical stack:

- rainfall: `chirps_v3_daily_rnl`
- ET drivers: `agera_5` where available

Reason:

- CHIRPS aligns with CHC rainfall practice
- AgERA5 gives better ET support than Tmax/Tmin-only path

### Future climate

For `nex_gddp`:

- available core vars usually `pr`, `tasmax`, `tasmin`

Implication:

- future WRSI likely must use **temperature-based ETo fallback**, probably Hargreaves, unless extra ET drivers added.

This should be explicit in docs and output metadata.

## Crop Parameterization

Each crop should define:

- stage lengths
- `kc_init`
- `kc_dev`
- `kc_mid`
- `kc_late`
- rooting depth progression or max root depth
- depletion fraction `p`

Package should allow:

- crop defaults
- user override file
- direct CLI / API overrides later

## Relationship To NDWS

`WRSI` should not replace `NDWS`.

Recommended split:

- `WRSI`: seasonal satisfaction summary
- `NDWS`: count of daily stress states from root-zone balance
- `NDWL0`: count of waterlogging / saturation stress states

All three should come from **same underlying water-balance engine**.

That prevents conflicting metrics from different hidden methods.

## What Should Change In Package

### New module

Add something like:

- `climate_tookit/calculate_hazards/wrsi.py`

Responsibilities:

- build crop-stage schedule
- compute timestep `CWR`
- run soil bucket
- compute daily / dekadal / seasonal `WRSI`
- emit progression series and final seasonal score

### Shared water-balance engine

Best architecture:

- one common root-zone water-balance engine
- hazard modules derive:
  - `NDWS`
  - `NDWL0`
  - `WRSI`

This better than separate bespoke implementations.

### Output objects

Minimum seasonal output:

- `wrsi_value`
- `wrsi_class`
- `season_start`
- `season_end`
- `season_length_days`
- `cumulative_requirement_mm`
- `cumulative_aet_mm`
- `cumulative_effective_rain_mm`
- `ending_storage_mm`
- `et_method`
- `crop_params_source`
- `soil_params_source`

Optional progression output:

- daily series
- dekadal series

## Recommended Classification Strategy

Do **not** hard-code class thresholds until official method reference pinned down.

For now:

- implement continuous `0-100` WRSI
- keep class mapping configurable

Default class bands can be added later after source confirmation.

## Technical Recommendation

For first package implementation:

1. Build `WRSI` on top of **same FAO-56-like water balance engine** we want for improved `NDWS`.
2. Use **daily internal timestep**.
3. Add **dekadal rollup outputs** to align with CHC-style seasonal monitoring practice.
4. Keep classification external / configurable until exact reference bands confirmed.
5. Keep data backend modular:
   - CHIRPS v3 preferred for rainfall
   - not mandatory if user supplies other rainfall source

## Best Borrowing Targets

### `pyfao56`

Best borrowing target for:

- daily water balance
- crop coefficients
- root-zone accounting
- ET framing

Source:

- [pyfao56](https://github.com/kthorp/pyfao56)

### `AquaCrop-OSPy`

Best benchmark for:

- richer crop stress realism
- later validation against more advanced crop-water model behavior

Source:

- [AquaCrop-OSPy](https://github.com/aquacropos/aquacrop)

## Current Recommendation

If user says:

- “align with CHC technical methods”

Then package should do this:

- **CHC-like seasonal crop water accounting**
- **FAO-style ET and crop coefficients**
- **daily internal, dekadal external**
- **continuous WRSI plus configurable classes**
- **same engine powering NDWS / NDWL0 / WRSI**

Not this:

- arbitrary rainfall ratio
- Atlas thresholds masquerading as WRSI
- fixed-window climate summary labeled as crop satisfaction

## Next Work

1. Implement shared water-balance core.
2. Add continuous `WRSI` output first.
3. Add configurable class mapping.
4. Add dekadal progression output.
5. Keep searching for official GeoWRSI / FEWS method note to tighten defaults and class bands.
