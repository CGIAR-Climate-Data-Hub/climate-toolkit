# Jeux de données {#datasets}

Sources acceptées par l’argument `source` de [`fetch_climate_data`](api/fetching.md) et des autres fonctions de l’API.

**Authentification** : les sources « EE » passent par Google Earth Engine et nécessitent une [configuration initiale](getting_started.md#2-google-earth-engine-credentials). La mention « Aucune » indique un accès sans identifiants.

| `source` | Jeu de données | Type | Résolution native | Couverture | Variables | Authentification |
|----------|---------|------|-------------------|----------|-----------|------|
| `era5_land` | Agrégats quotidiens ERA5-Land | Réanalyse | 0,1° (≈11 km) | Du 1950-01-02 à une date proche du présent | Précipitations, Tmax/Tmin/Tmoy, humidité, vent, rayonnement solaire | EE |
| `era_5` | ERA5 quotidien | Réanalyse | 0,25° (≈28 km) | 1979-01-02 au 2020-07-09 (archive statique, disponibilité vérifiée à l’exécution) | Précipitations, Tmax/Tmin, vent | EE |
| `terraclimate` | TerraClimate | Climat et bilan hydrique mensuels | 1/24° (≈4 km) | Depuis 1958, mensuelle | Précipitations, Tmax/Tmin, vent, rayonnement solaire, humidité du sol | EE |
| `imerg` | GPM IMERG v07 | Précipitations par satellite | 0,1° (≈11 km) | Depuis 2000 | Précipitations | EE |
| `chirps_v2` (alias `chirps`) | CHIRPS v2 quotidien | Précipitations combinant satellites et pluviomètres | 0,05° (≈5,5 km) | Depuis 1981 | Précipitations | EE |
| `chirps_v3_daily_rnl` | CHIRPS v3 quotidien définitif/RNL | Précipitations combinant satellites et pluviomètres | 0,05° (≈5,5 km) | De 1981 à la dernière date disponible chez le fournisseur | Précipitations | Aucune avec l’option cloud, recours facultatif à EE |
| `chirts_era5` | CHIRTS-ERA5 quotidien | Température ERA5 étalonnée à partir de CHIRTS | 0,05° (≈5,5 km) | Archive hébergée de 1981 à la dernière date disponible | Tmax/Tmin | Aucune avec l’option cloud |
| `chirts` (obsolète) | CHIRTS quotidien | Température combinant satellites et stations | 0,05° (≈5,5 km) | 1983–2016 | Tmax/Tmin | EE |
| `cmip_6` | NASA GDDP-CMIP6 | Projections régionalisées | 0,25° (≈27 km) | Période historique et scénarios | Précipitations, Tmax/Tmin | EE |
| `nex_gddp` | NEX-GDDP-CMIP6 | Projections régionalisées par combinaison GCM × SSP | 0,25° (≈27 km) | Historique jusqu’au 2014-12-31, scénarios dès le 2015-01-01 | Précipitations, Tmax/Tmin, humidité | EE |
| `nasa_power` | NASA POWER quotidien | API ponctuelle issue de réanalyses | ≈0,5° | Depuis 1984 | Précipitations, Tmax/Tmin/Tmoy, humidité | Aucune |
| `tamsat` | TAMSAT v3.1 | Pluies en Afrique (satellite) | 0,05° (≈4 km), Afrique uniquement | Depuis 1983 | Précipitations, humidité du sol | Aucune |
| `ghcn_daily` | GHCN-Daily | Observations en station | Ponctuelle | Selon la station | Précipitations, Tmax/Tmin | Aucune |
| `gsod` | NOAA GSOD | Observations en station | Ponctuelle | Selon la station | Précipitations, Tmax/Tmin | Aucune |
| `soil_grid` | ISRIC SoilGrids / OpenLandMap | Propriétés statiques du sol | 250 m | Statique | Texture, masse volumique apparente, pH, carbone organique, capacité d’échange cationique | EE |
| `hwsd` | FAO HWSD v2 | Propriétés statiques du sol | ≈1 km | Statique | Profondeur racinaire, réserve utile en eau, drainage, masse volumique apparente | EE |

!!! note "`era5_land` fournit les données ERA5-Land"
    Les anciens noms `agera_5` et `agera5` restent des alias obsolètes dans les versions 0.2.x. Ils déclenchent un avertissement et renvoient les mêmes données ERA5-Land. Utilisez `era5_land` pour vos nouvelles requêtes. Les caches existants restent compatibles. La source `era5_land` lit la collection Earth Engine `ECMWF/ERA5_LAND/DAILY_AGGR` (agrégats quotidiens) sur la grille ERA5-Land à 0,1°. Elle est recommandée pour les analyses quotidiennes récentes car elle couvre de nombreuses variables et est mise à jour en continu. AgERA5 de Copernicus est un produit distinct. La date de début provient du [catalogue GEE](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR) : vérifiez la couverture de chaque requête. L’accès officiel CDS ARCO exige une clé CDS. Son intégration est [en suspens](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_180_era5_land_access.md) et aucun autre mode d’accès n’est encore intégré.

Dépendances cloud, choix du fournisseur et migration depuis CHIRTS : [accès direct aux données](direct_cloud_access.md).

## Choisir une source {#choosing-a-source}

- **Données quotidiennes récentes, nombreuses variables** → `era5_land` (nécessite EE).
- **Démarrage sans configuration** → `nasa_power` (sans identifiants, grille plus grossière).
- **Précipitations à haute résolution** → `chirps_v3_daily_rnl` (0,05°, précipitations seules). Associez une source de température via `precip_source` et `temp_source`.
- **Climat futur** → `nex_gddp` avec `model` (p. ex. `'GFDL-ESM4'`) et `scenario` (p. ex. `'ssp245'`). Pour un ensemble, indiquez `models="all"` en ligne de commande.
- **Validation avec des observations au sol** → stations `ghcn_daily` ou `gsod`, puis [`compare_station_to_grids`](api/comparison.md).
- **Données de sol pour le bilan hydrique** → les fonctions d’évaluation des aléas et de statistiques les récupèrent automatiquement. Pour les demander explicitement, utilisez les membres de `SoilVariable`.

## Variables {#variables}

Pour demander des variables, utilisez les membres de l’énumération `ClimateVariable` :

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    SoilVariable,
)
```

`ClimateVariable`: `precipitation`, `max_temperature`, `min_temperature`, `mean_temperature`, `rainfall`, `wind_speed`, `solar_radiation`, `humidity`, `soil_moisture`.

`SoilVariable` (pour `soil_grid` et `hwsd`) : `root_depth`, `available_water_capacity`, `drainage`, `bulk_density`, `coarse_fragments`, `field_capacity`, `wilting_point`, `ph`, `sand_content`, `clay_content`, `silt_content`, `organic_carbon`, `organic_carbon_stock`, `cation_exchange_capacity`, `soil_moisture`.

Les variables disponibles dépendent de la source (voir tableau). Pour les anciennes sources, une requête dépassant la période disponible peut être tronquée avec un avertissement. L’accès direct exige toute la période demandée : le logiciel essaie une autre source autorisée ou renvoie une erreur si la couverture est incomplète.

<!-- source-sha256: 87d5c9f03caa8d6f328073e3fabb052d94d4fa8a4f56cf1f730ea7f6f0701b49 -->
