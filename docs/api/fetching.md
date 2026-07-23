# Fetching data

Available as `climate_toolkit.fetch_climate_data`.

## Example

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",                       # no credentials needed
    location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation,
               ClimateVariable.max_temperature,
               ClimateVariable.min_temperature],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print("rows:", df.shape[0], "| columns:", df.columns.tolist())
print(df.head())
```

`fetch_climate_data` returns a **pandas DataFrame**. Earth Engine-backed sources
(`agera_5`, `nex_gddp`, ...) use the same call after a one-time setup — see
[Getting started](../getting_started.md#2-google-earth-engine-credentials). Full
parameter reference below.

::: climate_toolkit.fetch_data.fetch_data.fetch_data
