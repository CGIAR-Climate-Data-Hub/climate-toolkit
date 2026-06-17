# Weather-Station vs Grid Comparison Window Guidance

## Purpose

This note translates WMO / NOAA climate-normal guidance and station-vs-grid validation literature into practical comparison windows for `climate_tookit.weather_station.compare`.

It is not a claim that one official standard applies to every use case. The recommendations below are an implementation-oriented interpretation for this toolkit.

## Key source points

### WMO / NOAA climatology baseline

- WMO defines:
  - period averages as averages over **at least 10 years**
  - normals as period averages over **at least three consecutive 10-year periods**
  - climatological standard normals as **30-year** periods such as **1991-2020**
- NOAA states official climate normals are calculated for a **uniform 30-year period** and updated each decade.

Implication:

- if the goal is climatology / baseline comparison, the correct target remains **30 years**
- if the goal is a shorter but still seasonally meaningful period-average comparison, **10 years** is the minimum defensible threshold

### Station-vs-grid rainfall validation reality

- point-to-pixel comparison is inherently noisy because gauges measure a point while grid products represent an area-average
- daily precipitation extremes in gridded products are often damped by spatial smoothing
- aggregation to monthly / seasonal summaries is usually more stable and interpretable than raw daily correlation alone

Implication:

- single-year precipitation comparisons are weak evidence
- daily rainfall correlation should not be treated as the main ranking metric by itself
- longer windows are especially important for rainfall and extremes

## Recommended toolkit thresholds

### 1. Quick operational screening

Use when the user wants a rough first look at whether a product is plausible at a site.

- **Absolute floor:** 2 years
- **Preferred minimum:** 3 to 5 years
- below 2 years: show strong warning

Reason:

- 1 year can be dominated by one anomalous season
- 2 to 5 years at least exposes some interannual variability without pretending to be climatology

### 2. Product ranking for seasonal / annual historical use

Use when comparing CHIRPS / IMERG / AgERA5 / POWER / ERA5-style products for practical site use.

- **Minimum recommended:** 5 years
- **Better default:** 10 years
- **Preferred where available:** 10 to 15 years

Reason:

- WMO period-average logic starts at 10 years
- rainfall product evaluation literature typically emphasizes annual totals, seasonal patterns, intensity structure, and multiple years rather than one-year agreement

### 3. Climatology / baseline statements

Use when the user wants to say what is “normal” at a site.

- **Standard target:** 30 years
- **Fallback with warning:** 20+ years only if 30 unavailable
- **Below 20 years:** should not be presented as a full climatological normal

Reason:

- this is the formal WMO / NOAA climate-normal standard

### 4. Extremes and heavy-rain screening

Use when comparing products for `Rx1day`, `Rx5day`, upper quantiles, heavy-rain counts, etc.

- **Minimum recommended:** 10 years
- **Preferred:** 20+ years
- **Best practice / climatological benchmark:** 30 years

Reason:

- daily extremes are the most sensitive to point-to-grid mismatch and smoothing
- shorter records are unstable for upper-tail metrics

## Proposed toolkit behavior

### Warnings by overlap length

- `< 2 years`: very strong warning; descriptive only
- `2 to <5 years`: usable for rough screening only
- `5 to <10 years`: usable for preliminary ranking, caution for rainfall
- `10 to <20 years`: acceptable for period-average comparison
- `20 to <30 years`: strong for climatology-style comparison, but not full standard normal
- `>= 30 years`: climatology-grade

### Variable-specific interpretation

- precipitation:
  - be strict
  - emphasize monthly / seasonal / annual metrics over daily correlation
- temperature:
  - somewhat more stable than precipitation
  - 5 to 10 years can already be useful for ranking products
- extremes:
  - require the longest windows

### Multi-station pooled mode

When multiple stations are selected:

- keep per-station results
- also report a pooled reference series using **same-date mean across selected stations**
- keep pooled metrics separate from stacked station-day metrics

This is now the direction on the active branch.

## Suggested next implementation steps

1. add overlap-window status labels to `weather_station.compare`
2. warn when user requests 1-year rainfall ranking
3. distinguish “screening”, “ranking”, and “climatology” confidence in JSON/text outputs
4. tighten heavy-rain / extremes recommendations separately from general rainfall comparison

## Sources

- WMO Climatological Normals:
  - https://community.wmo.int/en/activity-areas/climate-services/climate-products-and-initiatives/wmo-climatological-normals
- NOAA U.S. Climate Normals:
  - https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals
- Bagiliko et al. 2025, point-to-pixel rainfall validation context:
  - https://arxiv.org/abs/2501.14829
- Risser et al. 2018, daily precipitation extremes and gridding/smoothing issue:
  - https://arxiv.org/abs/1807.04177
- Risser and Wehner 2019, geographic sampling should be accounted for:
  - https://arxiv.org/abs/1911.05103
