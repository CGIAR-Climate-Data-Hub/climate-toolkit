# Comparison & validation

## Compare gridded sources

Available as `climate_toolkit.compare_climate_sources`.

Supply a list of sources, a location and a common date window. The result maps each source to its daily DataFrame, which you can pass to `print_report` to compare the series.

::: climate_toolkit.compare_datasets.compare_datasets.compare_sources

## Download station data

Available as `climate_toolkit.download_station_data`.

Supply coordinates, dates and a station source. Use `selection_mode="list"` to inspect the ranked candidates. Automatic or specified selection returns daily observations. Public NOAA station archives are accessible without Earth Engine credentials.

::: climate_toolkit.weather_station.download.download_station_data

## Validate grids against stations

Available as `climate_toolkit.compare_station_to_grids`.

Specify a station source and the historical products in `grid_sources`. The comparison aligns observations and grid values by date. Inspect `metrics` for overlap, bias, MAE, RMSE and correlation, and `grid_failures` for unavailable sources. A product that incorporates station data may share observations with the validation station.

::: climate_toolkit.weather_station.compare.compare_station_to_grids
