# Analysis

## Climate statistics

Available as `climate_toolkit.analyze_climate_statistics`.

For a location, source and range of years, compute seasonal statistics, water balance and long-term means. Set `fixed_season` to compare the same calendar windows across years. Request SPI or SPEI explicitly when needed. Results include per-season records under `season_statistics`.

::: climate_toolkit.climate_statistics.statistics.analyze_climate_statistics

## Hazards

Available as `climate_toolkit.evaluate_hazards`.

Supply the crop, coordinates and date window. The assessment compares seasonal conditions with crop-specific heat and water thresholds. With `fixed_season`, the request selects seasons by their start date, including seasons that finish the following year.

::: climate_toolkit.calculate_hazards.hazards.calculate_hazards

## Period comparison

Available as `climate_toolkit.compare_climate_periods`.

Choose a focal year and a baseline period at the same location. The result compares each season with its baseline and reports absolute and percentage differences where available.

::: climate_toolkit.compare_periods.periods.compare
