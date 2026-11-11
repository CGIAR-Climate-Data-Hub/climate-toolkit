# Pastoral climate reporting at a site

[Issue #92](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/92) asks what the toolkit can tell a pastoral adviser about a grazing season. Start with a seasonal weather summary for a named site and a locally chosen window. A second question, how much forage or drinking water a herd can reach, needs observations of vegetation, water points and the area the herd uses.

## First implementation

Build an optional downstream report from the existing historical climate statistics workflow. For one site and one explicit start and end date, show accumulated rainfall (mm), rainy days (at least 1 mm), mean daily maximum and minimum temperature (°C), and livestock temperature-humidity index (THI) where inputs support it. Reuse the existing THI calculation and its livestock profile. Ask the adviser to supply local grazing-season dates. Crop planting and cessation dates can describe a different window. A point estimate describes conditions at that site, including when herds move elsewhere.

Keep calculations in their existing modules. The reporting layer can consume the seasonal values and compute coverage from the corresponding daily inputs before missing-value substitution. This avoids a second weather fetch and gives reports access to a distinction lost in seasonal totals. Existing hazards already owns livestock heat thresholds. A dedicated rangeland module becomes useful when polygon masks, satellite observations and field validation have a shared implementation. Human heat guidance stays in its existing workflow. See the [package architecture](../package_architecture_summary.md) and [seasonal statistics implementation](../../climate_toolkit/climate_statistics/statistics.py).

| Source or output available today | What the report can use | Interpretation or limitation |
| --- | --- | --- |
| Direct CHIRPS v3 final/RNL and CHIRTS-ERA5 | Daily rainfall and maximum/minimum temperature without a Google Earth Engine login | This pair supplies no humidity. Mark THI unavailable unless a compatible humidity source was explicitly supplied and recorded. |
| Historical ERA5-Land through the existing route | Weather and humidity-backed heat metrics where fetched or derived inputs support them | Record actual variable sources, derivation, dates and livestock profile. THI is a weather exposure estimate. Breed, shade and drinking water affect animal response. |
| Stations or custom observations | Check site rainfall and temperature where station records overlap. Use RH only with compatible units, dates and provenance. | Record station location, distance and valid days. One gauge cannot establish conditions across a grazing area. |
| Seasonal water balance and SPEI | Optional background for a later report. SPEI describes climatic water deficit relative to a reference distribution. | Root-zone stress days, waterlogging days and WRSI depend on soil and crop assumptions. Static soil properties cannot establish current moisture. Check the actual product variable, units, depth and cadence before proposing dynamic soil moisture. A generic adapter method is insufficient evidence. |

For the first report, show actual source and units per indicator, valid days and expected calendar days (inclusive). Distinguish observed or source-derived values from filled values. For incomplete rainfall, label the sum and rainy-day count as covering the valid days. With zero valid observations, return an unavailable value and reason. If a saved summary lacks coverage metadata and the original daily values are unavailable, label coverage unknown. Count THI days only where the calculation has both usable temperature and humidity, and show stressed days out of valid THI days alongside the profile. For an anomaly in a later release, compare the same window, footprint and product against a documented multi-year reference period, and report reference coverage, timescale and method.

### Reproducible coverage check

On main at `84eaecc`, the three-day input below yields 8 mm and one rainy day, whether the missing rainfall value is left missing or replaced with zero. Only two days supplied rainfall. With humidity absent, the livestock heat block is omitted. With RH of 65%, missing and 80%, it reports two valid THI days. This exercises the existing seasonal calculation offline with synthetic data.

```python
import pandas as pd
from climate_toolkit.climate_statistics.statistics import season_statistics

window = {"onset": "2020-03-01", "cessation": "2020-03-03"}
daily = pd.DataFrame({
    "date": pd.date_range(window["onset"], window["cessation"]),
    "precip": [0.0, float("nan"), 8.0],
    "tmin": 20.0, "tmax": 30.0,
    "water_balance": [-5.0, float("nan"), 3.0],
})

def summarize(frame):
    return season_statistics(frame, window, shared_water_balance_summary={})

season = summarize(daily)
assert season["precipitation"]["total_mm"] == 8
assert season["precipitation"]["rainy_days"] == 1
assert season["precipitation"] == summarize(daily.fillna({"precip": 0}))["precipitation"]
assert daily["precip"].count() == 2 and season["length_days"] == 3
assert "livestock_heat_stress" not in season
humid = summarize(daily.assign(humidity=[65., float("nan"), 80.]))
assert humid["livestock_heat_stress"]["days_total"] == 2
```

Acceptance for this first implementation: run the report for one fixed grazing window with complete, partial and entirely missing rainfall, then with and without usable humidity. Check that a valid dry day counts toward coverage, an absent day does not, and partial rainfall cannot appear as a complete seasonal total. Check the denominator across a year boundary and verify that a saved legacy report with unknown coverage displays that limitation. Compare two example reports with a pastoral adviser to check season labels and interpretation.

## Field and satellite work

| Question | Candidate and method | Evidence needed before operational use |
| --- | --- | --- |
| Was vegetation unusually green during this grazing season? | Aggregate quality-screened MODIS vegetation indices over a grazing-area polygon. Compare each 16-day composite with the same period in reference years. The 250 m MOD13Q1 product includes NDVI, EVI and quality layers. [NASA product record](https://doi.org/10.5067/MODIS/MOD13Q1.061) | Record rangeland mask, usable pixel fraction and missing composites. Test against local grass cover or field biomass across wet and dry seasons. Woody cover and crops also contribute greenness. |
| Did vegetation productivity or water use change? | Pilot FAO WaPOR net primary productivity and actual evapotranspiration for one documented collection and grazing area. Preserve native time step, units, quality layers and preliminary/final revision. [FAO WaPOR data](https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/) | Verify collection footprint and history at the site. Test download access without GEE credentials, bytes transferred and repeat-use cost. Converting productivity to edible dry matter needs local species, grazing and field data. |
| Where has open surface water been detected? | Use JRC Global Surface Water occurrence as historical context. Use dated observations and their coverage for a specific season. Pin the layer and version since historical series span releases. [JRC data access and version notes](https://global-surface-water.appspot.com/download) | Ground-check detections and small or obscured sources. An assessment of accessible drinking water also needs functioning boreholes and water points, seasonality, quality, routes and access rights from local partners. |

Implement the site report first. Then pilot **one** vegetation product against field observations in a partner-selected grazing area. Record footprint, mask, product revision, valid pixel fraction, cold/repeat extraction times, transfer volume and agreement by season before choosing a backend or promising a forage indicator. Scope drinking-water access separately with local water-point and mobility data. Decisions about herd movement, stocking rates or emergency thresholds require validation against those decisions at the intended scale.
