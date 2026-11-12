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

## Which forage question can each dataset answer?

The [forage dataset comparison](issue_92_forage_dataset_comparison.md) lists resolution, record length, frequency, quality controls and access by product. It also specifies how to report seasonal anomalies and historical trends.

**Productivity** is growth over an interval. **Standing biomass** is dry matter present on a date, including dry grass that may remain after green-up ends. **Available forage** is the edible portion a particular herd can reach and use after grazing, trampling and other losses. **Quality** concerns the nutrients and digestibility of that forage. These quantities need different observations, even within the same grazing area.

| Decision | Dataset to explore | How to use and validate it |
| --- | --- | --- |
| How much vegetation grew this season? | **Copernicus Dry Matter Productivity v2** gives a global 300 m estimate every ten days from 2014, in kg dry matter/ha/day. The West African **ACF/SIG Sahel** annual product offers downloadable biomass estimates in kg dry matter/ha derived from Copernicus DMP. [Copernicus DMP](https://land.copernicus.eu/en/products/vegetation/dry-matter-productivity-v2-0-300m) · [ACF products](https://sigsahel.info/en/download/) | Multiply each valid rate by the actual number of overlapping days, then sum across the season. Retain quality flags and missing days. Mask cropland and distinguish woody from herbaceous growth. Use the ACF series as a regional comparison with shared inputs. Independent validation needs field measurements. |
| Where and when did the pasture green up or senesce? | **MODIS MOD13Q1.061** supplies 250 m normalized difference vegetation index (NDVI), enhanced vegetation index (EVI) and quality flags every 16 days. [NASA product record](https://doi.org/10.5067/MODIS/MOD13Q1.061) | Compare quality-screened composites against the same seasonal period in prior years. Report valid grazing area and flag woody cover and bare soil. Dry standing grass can retain feed value after NDVI falls. |
| How much dry forage remains? | **Sentinel-2** visible, near-infrared and shortwave-infrared observations can be paired with standing herbaceous dry mass. A Senegal study tested these indices against three field campaigns at eleven sites, including dry-season conditions. [Senegal field study](https://doi.org/10.3389/fenvs.2022.931299) | Compare a dry-vegetation index against an NDVI-only baseline using clipped, oven-dried quadrats (kg dry matter/ha). Record green grass, dry grass and browse separately. Match plot date and sampling footprint to the image. Record recent grazing and accessible area before interpreting edible supply. |
| Which vegetation do herders consider palatable and accessible? | **ILRI Rangeland Conditions Photo Dataset** contains Northern Kenya pastoralists’ observations from March–July 2015 on grass, shrubs, colour, palatability, livestock and distance to water. [CGIAR dataset and reuse terms](https://hdl.handle.net/20.500.11766.1/FK2/KDLELY) | Compare satellite anomalies with local condition scores for the same dates and area. Group repeated submissions by locality and respect the dataset’s custom terms. These ordinal observations can validate perceived condition. Nutrient concentration needs a separate measurement. |
| What is the nutritional quality of the edible pasture? | **ILRI SSA Feeds** provides laboratory reference values by feed type, including herbaceous forages and browse. A western Kenya study measured crude protein and neutral detergent fibre across four seasons. Sentinel-2 reflectance has also been tested against crude protein and fibre in a Brazilian experimental pasture. [ILRI feed composition database](https://feedsdatabase.ilri.org/) · [Kenyan field study](https://pubmed.ncbi.nlm.nih.gov/30056650/) · [Brazilian Sentinel-2 study](https://doi.org/10.1038/s41598-024-59160-x) | First use species, maturity and plant part to select reference ranges. For a site estimate, pair dated edible-tissue samples with reflectance and assay crude protein and neutral detergent fibre (% dry matter), plus digestibility with a stated method. Treat any red-edge or other spectral predictor as experimental until it beats a species-and-season baseline on independent sites. |

### First forage pilot

Start with **NDVI/EVI and DMP for the same grazing polygon**, alongside the site weather report. Greenness and accumulated growth can then be compared in a wet period and through dry-down. Calculate anomalies separately on each product’s native grid and interval. Report the baseline years, usable pixel fraction, temporal gaps and revision. Keep provisional observations identifiable. Use a land-cover mask appropriate to the target livestock, since woody browse can matter to goats and camels.

For standing biomass, hold out entire grazing areas and seasons when comparing estimates with quadrat dry mass. Report bias and mean absolute error in kg dry matter/ha, sample counts and performance by season. For crude protein, fibre or digestibility, report errors in percentage points against independent assays. Where field evidence only supports greenness or production, publish those indicators under their measured names. Estimate grazing days only when partners supply accessible hectares, usable forage fraction and herd demand.

**Access checked 11 November 2026.** An anonymous Planetary Computer STAC search near Marsabit, Kenya returned MOD13Q1 tile `h21v08` for May 2015. Its public signing endpoint enabled a 512-byte HTTP range read of the NDVI GeoTIFF (HTTP 206). For the same month, the Copernicus OData catalogue returned a consolidated DMP v2 asset, but its download endpoint returned HTTP 401 without credentials. The CGIAR Dataverse API served the Kenya photo survey’s data dictionary anonymously. These checks establish discovery and a partial MODIS read. The pilot still needs to measure polygon extraction time, bytes, repeat-use cost and independent field agreement. [MODIS STAC collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13Q1-061) · [Copernicus access options](https://land.copernicus.eu/en/products/vegetation/dry-matter-productivity-v2-0-300m) · [Survey files](https://hdl.handle.net/20.500.11766.1/FK2/KDLELY)

## Water-use and drinking-water context

WaPOR net primary productivity and evapotranspiration offer a further comparison of vegetation growth and water use. Verify collection footprint, units, time step, quality flags and preliminary/final status. Prioritize the biomass and greenness pilot above before adding another provider. [FAO WaPOR data](https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/)

Use JRC Global Surface Water occurrence as historical context, and dated detections and observation coverage for a particular season. Pin the version since historical series span releases. Assess drinking-water access separately with local information on functioning water points and boreholes, quality, routes, seasonality and access rights. [JRC data access and version notes](https://global-surface-water.appspot.com/download)
