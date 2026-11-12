# Analyse {#analysis}

## Statistiques climatiques {#climate-statistics}

Fonction publique : `climate_toolkit.analyze_climate_statistics`.

Pour un site, une source et une période en années, calculez les statistiques saisonnières, le bilan hydrique et les moyennes à long terme. Utilisez `fixed_season` pour comparer les mêmes fenêtres calendaires au fil des ans. Demandez explicitement le SPI ou le SPEI si nécessaire. Les résultats par saison figurent sous `season_statistics`.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.climate_statistics.statistics.analyze_climate_statistics

## Aléas {#hazards}

Fonction publique : `climate_toolkit.evaluate_hazards`.

Indiquez la culture, les coordonnées et la période. L’évaluation compare les conditions de la saison aux seuils thermiques et hydriques de la culture. Avec `fixed_season`, les saisons sont sélectionnées selon leur date de début, même si elles se terminent l’année suivante.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.calculate_hazards.hazards.calculate_hazards

## Comparaison de périodes {#period-comparison}

Fonction publique : `climate_toolkit.compare_climate_periods`.

Choisissez une année à étudier et une période de référence au même site. Le résultat compare chaque saison à sa référence et indique les écarts absolus et en pourcentage lorsque les données le permettent.

Référence détaillée générée depuis la documentation Python (en anglais).

::: climate_toolkit.compare_periods.periods.compare

<!-- source-sha256: 90adf66004980a6a2d2550ccc969e75fc6d986f940a565da49b76ac87d5ff1d0 -->
