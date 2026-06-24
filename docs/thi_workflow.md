# Livestock THI Workflow

Status: current operational method  
Updated: 2026-06-24

This guide documents current toolkit handling for livestock heat stress through
daily `THI` (temperature-humidity index).

## What toolkit does now

Toolkit currently supports:

- daily livestock `THI`
- daily THI stress-band classification
- period summaries with:
  - mean THI
  - max THI
  - day counts by stress band
  - total stress days
- hazard integration through `calculate_hazards`

Toolkit does **not** yet treat THI as fully finished methodological work. This
is current operational implementation for issue `#30`, with threshold review
and broader livestock refinement still open.

## Current formula

Toolkit uses:

`THI = (1.8*T + 32) - ((0.55 - 0.0055*RH) * ((1.8*T) - 26))`

Where:

- `T` = daily mean dry-bulb air temperature in Celsius
- `RH` = daily relative humidity in percent

Default position:

- keep mean-temperature + RH THI as toolkit default
- do not treat max-temperature THI as default at this stage

Reason:

- current projection-oriented livestock literature support is strongest for daily temperature + RH THI
- toolkit humidity support across historical and future sources is most coherent for this path
- daily `Tmax` does not automatically pair with coincident humidity, so a naive `Tmax` THI path can overstate or distort stress signal

## Temperature input rule

Toolkit uses temperature in this order:

1. explicit mean temperature column when present
2. known mean-temperature aliases such as `mean_temperature`, `tavg`, `tmean`, `temperature`, `temp`
3. fallback derived mean daily temperature from `(tmax + tmin) / 2`

Toolkit does **not** currently expose separate default THI path based on daily
maximum temperature. That remains open refinement work.

## Humidity requirement

THI requires daily relative humidity in percent.

Current assumptions:

- valid humidity range: `0..100`
- missing humidity blocks THI calculation
- projected/future workflows without stable humidity path are unsupported by design

## Climate profile logic

Toolkit supports:

- `auto`
- `temperate`
- `tropical`

`auto` logic:

- use latitude first
- if site lies within tropical latitude band (`|lat| <= 23.5`) and elevation is
  at or above `1500 m`, treat as temperate/highland proxy
- otherwise tropical lowland stays tropical

Elevation may come from:

- explicit user override
- DEM lookup where workflow enables it

## Livestock profiles

Current built-in livestock profiles:

- `cattle_dairy`
- `cattle_general`
- `cattle_beef`
- `goats`
- `sheep`
- `pigs`
- `poultry_broilers`
- `poultry_layers`
- `poultry_general`

Threshold basis:

- Thornton et al. (2021) Table 1 for operational base thresholds
- Thornton et al. (2021) Table 2 for tropical extreme-threshold adjustments where applicable

Important:

- these are operational defaults, not final breed-resolved physiology
- toolkit currently uses species-group thresholds plus simple tropical/highland context logic
- future refinement may still revise some thresholds or interpretation text

## Breed and production-context limits

Toolkit should be read as screening tool here, not veterinary truth engine.

Current limits:

- toolkit does **not** distinguish Bos indicus, Bos taurus, Sanga, or crossbred cattle within one livestock profile
- toolkit does **not** infer breed adaptation from genetics, coat, body size, or management system
- `auto` climate-profile rule is only coarse location proxy using latitude plus highland elevation
- thresholds may not transfer cleanly across locally adapted breeds, production systems, or management conditions

Practical interpretation:

- use package defaults as operational screening bands
- if project has breed-specific or veterinary guidance, prefer custom threshold override
- document any override explicitly in outputs or methods note

Examples where extra caution is needed:

- tropical dairy systems using crossbred cattle
- locally adapted African cattle not well represented by broad dairy/beef defaults
- highland systems where climate exposure and genetic adaptation may diverge

Programmatic inspection:

```python
from climate_tookit.climatology import describe_thi_method

method = describe_thi_method()
print(method["profiles"]["cattle_dairy"])
print(method["profiles"]["pigs"])
```

## Source support

Supported now:

- `agera_5`
  - humidity derived from dewpoint + air temperature in current fetch pipeline
- `nasa_power`
  - humidity available from current POWER fetch path
- `ghcn_daily`
  - when station humidity field exists for chosen station and window
- `gsod`
  - when station humidity field exists for chosen station and window
- `custom_station`
  - when uploaded file includes humidity / RH column
- `nex_gddp`
  - conditionally, when Earth Engine `hurs` is available for selected model / scenario / period

Uncertain / limited:

- `era_5`
  - current toolkit ERA5 fetch configuration does not define a humidity band for operational THI use
  - keep treated as uncertain until fetch/runtime path is explicitly wired and tested

Not supported:

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts`

Programmatic inspection:

```python
from climate_tookit.climatology import describe_thi_method, describe_thi_source_support

print(describe_thi_source_support())
print(describe_thi_method()["source_support"]["nex_gddp"])
```

## CLI surface

Current livestock THI controls appear in multiple workflows:

- `climate-toolkit-seasons`
- `climate-toolkit-stats`
- `climate-toolkit-periods`
- `climate-toolkit-periods-ensemble`
- `climate-toolkit-hazards`
- relevant ensemble variants

Key arguments:

- `--livestock-type`
- `--livestock-climate-profile`
- `--livestock-elevation-override-m`

Example:

```bash
climate-toolkit-periods-ensemble \
  --location="-1.286,36.817" \
  --baseline-start=1995 \
  --baseline-end=2013 \
  --future-start=2041 \
  --future-end=2060 \
  --scenarios=ssp245 \
  --fixed-season="03-01:05-31" \
  --livestock-type cattle_dairy \
  --livestock-climate-profile auto
```

## Threshold override path

Default THI bands are built from livestock profile plus climate context.

Current user override path exists in hazards workflow through
`--thresholds-file`.

This means user can override THI hazard bands even if toolkit default profile
for that livestock type is different.

Example JSON fragment:

```json
{
  "THI": {
    "none": [null, 70],
    "mild": [70, 76],
    "moderate": [76, 84],
    "severe": [84, null]
  }
}
```

Example usage:

```bash
climate-toolkit-hazards \
  --crop maize \
  --location="-1.286,36.817" \
  --date-from 2020-03-01 \
  --date-to 2020-05-31 \
  --source paired \
  --precip-source chirps_v3_daily_rnl \
  --temp-source agera_5 \
  --livestock-type cattle_dairy \
  --thresholds-file custom_thresholds.json
```

Important:

- this override changes hazard evaluation bands
- it does not change underlying THI formula
- custom override should be documented by user because it departs from package operational defaults

## Still open

Remaining `#30` refinement work:

1. validate current thresholds against wider literature and decide whether defaults stay unchanged
2. decide whether toolkit should add separate max-temperature screening variant alongside mean-temperature THI
3. tighten projected-humidity support handling beyond current documented `hurs` limits
4. extend user-facing interpretation guidance for species/breed context
