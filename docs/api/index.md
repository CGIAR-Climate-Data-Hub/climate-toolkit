# Python API overview

Import the package once to use these public functions.

```python
import climate_toolkit as ct
```

| Public name | Guide |
|---|---|
| `ct.fetch_climate_data` | [Fetching data](fetching.md) |
| `ct.analyze_climate_statistics` | [Analysis](analysis.md) |
| `ct.evaluate_hazards` | [Analysis](analysis.md) |
| `ct.compare_climate_periods` | [Analysis](analysis.md) |
| `ct.compare_climate_sources` | [Comparison and validation](comparison.md) |
| `ct.download_station_data` | [Comparison and validation](comparison.md) |
| `ct.compare_station_to_grids` | [Comparison and validation](comparison.md) |
| `ct.backend_policy` | [Backend selection](../direct_cloud_access.md) |
| `ct.run_pipeline` | [Running the pipeline](../use-as-a-package.md#one-call-for-the-whole-workflow-run_pipeline) |

Use the same function names, arguments and output keys in every language. Python help and toolkit CLI messages are in English. For parameter details, run `help(ct.evaluate_hazards)` or open the function reference.
