# Téléchargement des données {#fetching-data}

Fonction publique : `climate_toolkit.fetch_climate_data`.

## Exemple {#example}

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",                       # aucun identifiant requis
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

`fetch_climate_data` renvoie un **DataFrame pandas**. Les sources utilisant Earth Engine (`era5_land`, `nex_gddp`, etc.) emploient le même appel une fois la configuration initiale terminée. Voir le guide [Premiers pas](../getting_started.md#2-google-earth-engine-credentials). La référence complète des paramètres figure ci-dessous.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.fetch_data.fetch_data.fetch_data

<!-- source-sha256: 0204f0d3f4feb567b0610034aa2e044165df385574fdc67af5dbe051f5d08232 -->
