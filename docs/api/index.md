# Python API overview

Import the package and call any of the seven public functions:

```python
import climate_toolkit as ct
```

| Public name | Documented on |
|-------------|---------------|
| `ct.fetch_climate_data` | [Fetching data](fetching.md) |
| `ct.analyze_climate_statistics` | [Analysis](analysis.md) |
| `ct.evaluate_hazards` | [Analysis](analysis.md) |
| `ct.compare_climate_periods` | [Analysis](analysis.md) |
| `ct.compare_climate_sources` | [Comparison & validation](comparison.md) |
| `ct.download_station_data` | [Comparison & validation](comparison.md) |
| `ct.compare_station_to_grids` | [Comparison & validation](comparison.md) |

The same documentation is available interactively via `help()`, e.g.
`help(ct.evaluate_hazards)`.
