# Comparaison et validation {#comparison-validation}

## Comparer des sources maillées {#compare-gridded-sources}

Fonction publique : `climate_toolkit.compare_climate_sources`.

Indiquez une liste de sources, un site et une période commune. Le résultat associe chaque source à un DataFrame quotidien. Transmettez ce dictionnaire à `print_report` pour comparer les séries.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.compare_datasets.compare_datasets.compare_sources

## Télécharger des observations en station {#download-station-data}

Fonction publique : `climate_toolkit.download_station_data`.

Indiquez les coordonnées, les dates et une source d’observations. Utilisez `selection_mode="list"` pour examiner le classement des stations candidates. La sélection automatique ou par identifiant renvoie les observations quotidiennes. Les archives publiques de la NOAA sont accessibles sans identifiants Earth Engine.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.weather_station.download.download_station_data

## Valider des produits maillés à partir de stations {#validate-grids-against-stations}

Fonction publique : `climate_toolkit.compare_station_to_grids`.

Indiquez la source des observations et les produits historiques dans `grid_sources`. La comparaison associe observations et valeurs maillées par date. Consultez `metrics` pour les dates communes, le biais, l’erreur absolue moyenne (MAE), la racine de l’erreur quadratique moyenne (RMSE) et la corrélation. Les échecs de téléchargement figurent dans `grid_failures`. Un produit fondé sur des observations peut avoir intégré les données de la station de validation.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.weather_station.compare.compare_station_to_grids

<!-- source-sha256: 3b38ac7ceec93e28676ba8ef94529b4ac9104bd5ce713a561b3f4ac98421cd06 -->
