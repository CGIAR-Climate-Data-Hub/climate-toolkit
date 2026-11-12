# Utiliser les données de stations météorologiques {#weather-station-workflows}

Statut du guide : en vigueur<br>
Mise à jour : 2026-06-21

Ce guide explique comment utiliser les observations de stations dans `climate_toolkit`.

## À quoi servent les données de stations ? {#what-weather-station-support-is-for}

Le module des stations répond à deux besoins :

1. exploiter directement les observations quotidiennes d’une station
2. comparer les observations aux données historiques sur grille

Ce module **ne valide pas** directement les projections futures de `nex_gddp`. L’évaluation des modèles de circulation générale (GCM) pour le futur relève d’un travail méthodologique distinct.

## Principaux points d’entrée {#main-entry-points}

Ligne de commande :

- `climate-toolkit-weather-station-download`
- `climate-toolkit-weather-station-compare`
- `climate-toolkit-stats`
- `climate-toolkit-seasons`

API Python :

- `climate_toolkit.download_station_data`
- `climate_toolkit.compare_station_to_grids`

## Avant de commencer {#before-you-run}

Distinguez deux jeux de coordonnées :

- coordonnées du site étudié : `--station-lat`, `--station-lon`
- coordonnées de la station d’observation : fournies par la NOAA ou lues dans le fichier de l’utilisateur

À retenir :

- `--station-lat` et `--station-lon` désignent le site étudié
- elles **peuvent différer** de celles de la station retenue
- les limites de distance et de dénivelé se mesurent par rapport au site étudié

Données minimales à fournir selon l’analyse :

### Examiner les stations candidates ou télécharger les données NOAA {#candidate-review-or-noaa-download}

Paramètres obligatoires :

- `--station-source`
- `--station-lat`
- `--station-lon`
- `--start`
- `--end`

Paramètres généralement utiles :

- `--variables`
- `--selection-mode`

### Comparer station et grille {#station-vs-grid-comparison}

Paramètres obligatoires :

- `--station-source`
- `--station-lat`
- `--station-lon`
- `--start`
- `--end`
- au moins une option `--grid-source`

Paramètres généralement utiles :

- `--variables`
- `--selection-mode`
- `--selection-strategy`
- `--precip-source` et `--temp-source` si la comparaison utilise `paired` ou `auto`

### Utiliser un fichier de station personnel {#custom-station-file-workflows}

Paramètres obligatoires :

- `--station-source custom_csv`
- `--custom-station-file`
- `--start`
- `--end`
- au moins une variable à extraire

Paramètres généralement utiles :

- `--custom-temp-unit`
- `--custom-precip-unit`
- `--custom-station-name`
- les coordonnées du site `--station-lat` et `--station-lon` si une comparaison ou une substitution ultérieure dépend de la localisation

## Sources des observations {#station-backends}

`--station-source` indique d’où proviennent les observations.

### `ghcn_daily` {#ghcn_daily}

Utilise uniquement GHCN-Daily de la NOAA.

À privilégier pour :

- les précipitations quotidiennes
- les températures minimales et maximales quotidiennes, lorsqu’elles sont disponibles

### `gsod` {#gsod}

Utilise uniquement GSOD de la NOAA.

À privilégier pour :

- une meilleure couverture des températures quotidiennes dans certaines régions
- des séries se recouvrant sur davantage d’années dans certaines stations d’aéroport

### `auto` {#auto}

Classe les stations des deux archives de la NOAA et renvoie les meilleures candidates selon les critères en vigueur.

À privilégier pour :

- une première exploration
- les sites peu couverts par l’une des archives de la NOAA

### `custom_csv` {#custom_csv}

Utilise un fichier CSV ou JSON fourni par l’utilisateur.

À privilégier pour :

- les mesures de stations locales
- les données de partenaires absentes des archives de la NOAA
- le remplacement des valeurs historiques par des observations

## Modes de sélection {#selection-modes}

`--selection-mode` détermine le traitement des stations candidates.

### `list` {#list}

Examine uniquement les candidates.

Ce mode :

- classe les stations
- calcule la complétude pour chaque variable
- enregistre les fichiers d’examen des candidates si `--report-prefix` est fourni
- s’arrête avant la sélection automatique habituelle

À utiliser pour :

- examiner d’abord les stations voisines
- obtenir la carte et les fichiers CSV et JSON pour les examiner

### `specified` {#specified}

Indiquez l’identifiant exact de la station avec `--station-id`.

À utiliser pour :

- utiliser une station de la NOAA dont vous connaissez déjà l’identifiant

### `auto` {#auto_1}

Le logiciel sélectionne les meilleures stations admissibles.

À utiliser pour :

- sélectionner automatiquement la meilleure station selon les règles en vigueur
- appliquer les mêmes critères à chaque exécution

## Nombre de stations sélectionnées automatiquement {#auto-selection-scope}

`--auto-select` règle le nombre de stations que le logiciel peut retenir.

Valeurs acceptées :

- `auto-1`
- `auto-2`
- `auto-3`
- `auto-<n>`
- `auto-all`

Comportement à connaître :

- `auto-all` respecte aussi la limite `--max-auto-stations`
- la valeur par défaut de `--max-auto-stations` est `10`
- `auto-1` retient la meilleure station admissible
- `auto-2` et les valeurs supérieures permettent de comparer plusieurs stations

## Stratégie de sélection pour la comparaison {#compare-selection-strategy}

`climate-toolkit-weather-station-compare` accepte aussi `--selection-strategy`.

### `all_vars_single_station` {#all_vars_single_station}

Une même station doit fournir toutes les variables demandées.

À privilégier pour :

- une interprétation plus simple
- une comparaison entre une station et une maille

Limite :

- une station utile pour les précipitations peut être écartée si elle ne mesure pas la température

### `best_per_variable` {#best_per_variable}

Le logiciel peut utiliser une station différente pour chaque variable.

Exemple :

- une station pour les précipitations
- une autre pour les températures minimales et maximales

À privilégier pour :

- les régions peu couvertes
- les cas où aucune station ne fournit tous les champs

Limite :

- l’interprétation est plus délicate car les indicateurs proviennent de plusieurs stations physiques

## Critères de sélection par défaut {#default-guardrails}

Les règles par défaut sont les suivantes :

- rayon de recherche : `50 km`
- écart maximal d’altitude : `500 m`
- fraction minimale de données disponibles : `0.70`
- nombre maximal de stations sélectionnées automatiquement : `10`
- nombre maximal de candidates retenues : `10`
- nombre maximal de stations évaluées : `25`

La complétude est évaluée **pour chaque variable**. Une note globale par station ne suffit pas.

Par exemple, si vous demandez :

- `precipitation,max_temperature,min_temperature`

Le logiciel vérifie que chaque variable demandée atteint le seuil de complétude.

## Assouplissement des critères {#guard-relaxation-behavior}

Seuil strict de complétude appliqué par défaut :

- `0.70`

Si aucune station ne passe le filtre, le logiciel abaisse progressivement le seuil :

- `0.50`
- `0.30`
- `0.10`

Si aucune station ne satisfait encore les critères pour toutes les variables, le logiciel peut retenir des candidates qui n’en couvrent qu’une partie, lorsque ce recours est autorisé.

Conséquences :

- selon l’analyse et les variables demandées, `auto` peut retenir une station utile qui mesure uniquement les précipitations ou uniquement la température
- le mode `list` permet souvent de mieux comprendre quelles stations satisfont ou non les critères

## Altitude du site de référence {#anchor-elevation}

Le logiciel peut estimer l’altitude du site étudié à partir d’un modèle numérique de terrain (MNT).

Objectifs :

- comparer l’altitude de chaque candidate à celle du site étudié
- appliquer la limite `--max-elevation-diff-m`

Options :

- `--target-elevation-m` : fournir directement une altitude connue
- `--no-auto-anchor-elevation` : désactiver la recherche automatique dans le MNT

Si la recherche automatique échoue :

- le logiciel poursuit la sélection sans critère d’altitude
- le terminal signale ce changement

## Examiner les stations candidates {#candidate-review-workflow}

Première étape recommandée :

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nairobi_auto_candidates \
  --open-report
```

Fichiers produits :

- CSV
- JSON
- Carte HTML

La carte des candidates indique :

- les coordonnées du site étudié
- les stations candidates à proximité
- les lignes reliant le site aux stations
- le rang
- les stations, avec des symboles proportionnels à la complétude des données
- le nombre de stations par source et le périmètre de la recherche

Limite du fond de carte :

- le fond de carte utilise des tuiles en ligne et nécessite une connexion Internet

Cette carte facilite l’examen visuel et ne constitue pas un produit SIG :

- utilisez-la pour un premier examen rapide
- pour la consulter à nouveau, ouvrez le fichier HTML enregistré
- la taille des symboles reflète la complétude des données
- la carte indique le site étudié, le rang et la distance des candidates et leur source

## Télécharger les observations {#download-workflow}

Exemple :

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --stage preprocessed
```

Options utiles :

- `--stage raw`
- `--stage transformed`
- `--stage preprocessed`
- `--station-id ...` avec `--selection-mode specified`
- `--disable-completeness-guard`
- `--refresh-cache`

Signification des étapes :

- `raw` : valeurs et noms les plus proches des données d’origine
- `transformed` : unités et noms harmonisés
- `preprocessed` : nettoyage et contrôles qualité appliqués

Résumé des données NOAA téléchargées :

- le terminal indique les stations retenues, leur distance, leur altitude et la disponibilité de chaque variable
- le mode liste affiche les candidates à la place des observations quotidiennes
- `--output` permet d’enregistrer un fichier de résultats

## Fichiers de stations de l’utilisateur {#custom-station-files}

Exemple :

```bash
climate-toolkit-weather-station-download \
  --station-source custom_csv \
  --custom-station-file path/to/station.csv \
  --custom-station-name "My station" \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Types de fichiers acceptés :

- `.csv`
- `.json`

Données minimales :

- `date`
- au moins une variable climatique demandée

Autres noms de variables acceptés :

- précipitations :
  - `precipitation`
  - `precip`
  - `rain`
  - `rainfall`
  - `prcp`
- température maximale :
  - `max_temperature`
  - `tmax`
  - `max`
- température minimale :
  - `min_temperature`
  - `tmin`
  - `min`
- température moyenne :
  - `mean_temperature`
  - `tmean`
  - `tavg`
  - `temp`
- humidité :
  - `humidity`
  - `relative_humidity`
  - `rh`
- vent :
  - `wind_speed`
  - `wind`
  - `wdsp`
- rayonnement solaire :
  - `solar_radiation`
  - `solar`
  - `radiation`

Colonnes de métadonnées facultatives :

- `station_id`
- `station_name`
- `station_lat`
- `station_lon`
- `station_elevation_m`

Lorsque des métadonnées manquent :

- le logiciel complète les valeurs dans la mesure du possible à partir des paramètres de la ligne de commande et du nom du fichier

Unités :

- `--custom-temp-unit c|f|k`
- `--custom-precip-unit mm|inch|tenth_mm`

Types de fichiers acceptés :

- `.csv`
- `.json`

Traitement :

- normalisation des colonnes
- lecture des dates et découpage selon la période demandée
- conversion des unités
- calcul de la température moyenne si elle manque et que Tmin et Tmax sont disponibles
- mise en cache du résultat normalisé pour le réutiliser

Si les métadonnées du fichier personnel manquent :

- `station_id` prend la valeur de l’identifiant fourni en ligne de commande ou du nom du fichier sans extension
- `station_name` prend le nom indiqué ou le nom du fichier sans extension
- les coordonnées du site fournies en ligne de commande peuvent servir de remplacement
- l’altitude peut rester indéterminée

Si le fichier ne contient aucune ligne dans la période demandée :

- le téléchargement renvoie une erreur
- les analyses historiques utilisent les valeurs maillées et affichent un avertissement

## Comparer station et grille {#station-vs-grid-comparison_1}

Exemple :

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --selection-mode auto \
  --auto-select auto-1 \
  --selection-strategy all_vars_single_station \
  --grid-source paired \
  --grid-source nasa_power \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid_2011_2020.json
```

Objectifs actuels de la comparaison :

- comparer les observations en station aux produits climatiques historiques maillés
- déterminer quelle source maillée paraît la plus représentative localement

Hors du périmètre actuel :

- validation directe des projections futures des modèles de circulation générale
- comparaison directe de `nex_gddp` aux stations dans cette interface de ligne de commande

### Familles de produits maillés acceptées {#supported-grid-source-family}

La comparaison historique accepte notamment les produits maillés et les réanalyses suivants :

- `era5_land`
- `era_5`
- `nasa_power`
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `chirts_era5` (Tmax et Tmin)
- `imerg`
- `paired`
- `auto`
- `terraclimate`

Sources exclues de la comparaison :

- `nex_gddp`
- les archives de stations elles-mêmes
- `tamsat`

### Indépendance de la validation {#independence-caveat}

Certains produits maillés intègrent des observations de stations.

Exemples :

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `chirts_era5` et l’ancien produit `chirts`
- `paired` si une des sources associées utilise des observations de stations
- `terraclimate`

Une bonne concordance **ne garantit pas** l’indépendance de la validation.

Pour une comparaison historique plus indépendante, on peut souvent utiliser :

- `era5_land`
- `era_5`
- `nasa_power`
- `imerg`

Le logiciel signale les sources dont la validation n’est pas entièrement indépendante.

Choix pratique des sources :

- privilégiez `nasa_power`, `era5_land`, `era_5` ou `imerg` si l’indépendance est prioritaire
- utilisez `paired` pour évaluer une analyse historique en conditions d’usage lorsque l’indépendance stricte n’est pas l’objectif
- si les composantes intègrent des observations, un bon classement de `paired` ne constitue pas une preuve indépendante

## Résultats de la comparaison {#comparison-outputs}

Les résultats texte ou JSON peuvent inclure :

- résumé des stations
- échecs de téléchargement des produits maillés
- indicateurs quotidiens par station
- indicateurs mensuels agrégés
- indicateurs saisonniers agrégés
- résumé du recouvrement annuel
- indicateurs globaux regroupant les stations lorsqu’il y en a plusieurs
- indices annuels de précipitations de référence de xclim si les dates communes sont assez nombreuses
- règles de classement par cas d’usage pour une première évaluation

### Interpréter les résultats {#how-to-read-them}

Indicateurs quotidiens :

- utiles pour situer les événements dans le temps et repérer les jours de pluie
- la corrélation des précipitations quotidiennes est souvent faible, même si le produit reste utile

Indicateurs mensuels et saisonniers :

- souvent plus informatifs pour évaluer l’aptitude climatique et planifier
- plus adaptés pour repérer un biais systématique vers des conditions trop humides ou trop sèches

Résumé annuel :

- utile seulement si la couverture des dates communes est suffisante
- en cas de faible recouvrement, les résultats sont descriptifs et leur portée pour la validation est limitée

Indices annuels de précipitations de référence de xclim :

- calculés uniquement si la couverture commune permet une estimation annuelle défendable
- omis en cas de lacunes trop importantes dans les observations communes

Options utiles pour la comparaison :

- `--wet-day-threshold-mm` : modifie le seuil utilisé pour évaluer la détection des jours de pluie
- `--min-overlap-days` : en dessous de ce nombre de jours communs, les indicateurs sont signalés comme peu fiables
- `--report-prefix` : enregistre aussi les fichiers d’examen des candidates lors de la comparaison
- `--open-report` : tente d’ouvrir automatiquement le rapport HTML sur les candidates

Précaution pour l’interprétation :

- avec `best_per_variable`, les indicateurs de précipitations et de température peuvent provenir de stations différentes
- consultez le résumé des stations avant de classer les produits

## Remplacer les données historiques par des observations {#historical-override-workflow}

Un fichier de station peut remplacer les valeurs de certaines variables historiques dans :

- `climate-toolkit-stats`
- `climate-toolkit-seasons`

Exemple :

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=era5_land \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation,max_temperature,min_temperature \
  --custom-station-name "My station" \
  --custom-temp-unit c \
  --custom-precip-unit mm
```

Fonctionnement actuel :

- les observations remplacent les valeurs historiques choisies aux dates correspondantes
- les valeurs maillées sont conservées pour les variables absentes du fichier de station
- si le fichier ne contient aucune ligne dans la période demandée, le logiciel utilise les valeurs maillées et affiche un avertissement

Périmètre actuel de la substitution :

- analyses historiques uniquement
- aucune substitution directe pour les projections futures `nex_gddp`
- particulièrement utile si la station fournit une ou deux variables fiables et que les données maillées peuvent compléter les autres

## Organisation du cache {#cache-layout}

Répertoires racines du cache local du projet :

- `outputs/cache/weather_stations/ghcn_daily`
- `outputs/cache/weather_stations/gsod`
- `outputs/cache/weather_stations/custom`
- `outputs/cache/weather_stations/dem_anchor`

Contenu habituel :

- métadonnées et inventaires des stations
- fichiers de stations téléchargés depuis la NOAA
- fichiers CSV personnels après normalisation
- manifestes JSON des données personnelles de station
- altitudes des sites obtenues à partir du MNT

Emplacements détaillés :

- index de métadonnées GHCN dans `outputs/cache/weather_stations/ghcn_daily/index`
- fichiers de stations GHCN dans `outputs/cache/weather_stations/ghcn_daily/stations`
- historique des stations GSOD et fichiers annuels dans `outputs/cache/weather_stations/gsod`
- fichiers personnels normalisés dans des sous-dossiers identifiés par empreinte sous `outputs/cache/weather_stations/custom`
- cache des altitudes de référence du MNT dans des sous-dossiers versionnés sous `outputs/cache/weather_stations/dem_anchor`

Cache des fichiers personnels :

- le logiciel calcule une empreinte à partir du chemin, de la taille et de la date de modification du fichier source
- chaque fichier personnel dispose de son propre dossier de cache
- les résultats CSV et JSON sont réutilisés pour une même étape et période, sauf si `--refresh-cache` est activé

Effet de `--refresh-cache` :

- force un nouveau téléchargement ou une régénération lorsque l’analyse le permet
- utile après un changement du code, une exécution incomplète ou l’obsolescence des résultats locaux
- inutile pour répéter normalement une analyse avec le cache existant

## Ordre pratique des opérations {#practical-workflow-order}

Séquence recommandée :

1. lancez `selection-mode list`
2. examinez la carte, le CSV et la complétude par variable
3. déterminez s’il convient d’utiliser une ou plusieurs stations
4. lancez `weather-station-download` ou `weather-station-compare`
5. ensuite seulement, utilisez au besoin vos observations pour remplacer les valeurs historiques

Pour prendre la décision :

1. commencez par `--selection-mode list`
2. vérifiez la complétude **pour chaque variable**
3. déterminez si une seule station suffit
4. sinon, déterminez si `best_per_variable` est acceptable
5. désactivez le critère de complétude uniquement à des fins exploratoires et conservez-le pour les rapports courants

## Limites actuelles {#current-limitations}

- faible couverture des stations dans certaines régions
- aucune archive ne fournit une couverture quotidienne mondiale complète
- certains sites ont assez de mesures de précipitations et peu de températures, ou inversement
- la comparaison porte sur les produits historiques et exclut les projections futures NEX-GDDP
- le mode automatique se limite aux sources NOAA prises en charge et aux fichiers personnels
- la carte HTML facilite la vérification visuelle ; une analyse SIG complète exige d’autres outils
- choisir une station par variable améliore la couverture mais complique l’interprétation

## Problèmes fréquents {#common-failure-modes}

`Error: No ... station passed per-variable completeness threshold`

- commencez par `--selection-mode list`
- augmentez `--max-distance-km`
- demandez moins de variables
- abaissez `--min-completeness-ratio`
- envisagez `best_per_variable`

`Anchor elevation unavailable; continuing without elevation guard`

- Recherche d’altitude par MNT dans Earth Engine indisponible
- renseignez `--target-elevation-m` si vous connaissez l’altitude du site
- ou authentifiez-vous auprès d’Earth Engine et indiquez un `GCP_PROJECT_ID` valide

`Project 'projects/your-ee-project-id' not found or deleted`

- L’environnement contient encore un identifiant de projet Earth Engine fictif
- remplacez-le par l’identifiant réel du projet

`Custom station file has no rows in requested window`

- vérifiez l’interprétation des dates
- vérifiez les valeurs demandées pour `--start` et `--end`
- vérifiez la cohérence des fuseaux horaires et du format des dates du fichier

`Skipped xclim annual precipitation reference indices ... overlap is too gappy`

- les dates communes sont trop peu nombreuses pour établir des indices annuels de référence fiables
- privilégiez les résumés mensuels ou saisonniers pour cette combinaison de station et de produit

## Exemples pratiques courts {#minimal-worked-examples}

### 1. Recenser les stations voisines et enregistrer la carte {#1-discover-nearby-stations-and-save-map}

```bash
climate-toolkit-weather-station-download \
  --station-source auto \
  --selection-mode list \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --report-prefix outputs/weather_station/nairobi_candidates \
  --open-report
```

### 2. Comparer une station sélectionnée à deux produits maillés {#2-compare-one-selected-station-against-two-grid-products}

```bash
climate-toolkit-weather-station-compare \
  --station-source auto \
  --selection-mode auto \
  --auto-select auto-1 \
  --station-lat -1.286 \
  --station-lon 36.817 \
  --start 2011-01-01 \
  --end 2020-12-31 \
  --grid-source nasa_power \
  --grid-source paired \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --variables precipitation,max_temperature,min_temperature \
  --output outputs/weather_station/nairobi_station_vs_grid.json
```

### 3. Remplacer les précipitations historiques par des observations personnelles {#3-override-historical-precipitation-with-custom-observed-data}

```bash
climate-toolkit-stats \
  --location="-1.286,36.817" \
  --start-year=2020 \
  --end-year=2020 \
  --source=paired \
  --precip-source=chirps_v3_daily_rnl \
  --temp-source=era5_land \
  --custom-station-file path/to/station.csv \
  --custom-station-vars precipitation \
  --custom-precip-unit mm
```

## Fichiers associés {#related-files}

- `README.md`
- `analysis/weather_station_module_design_2026-06-15.md`
- `analysis/weather_station_data_access_research_2026-06-15.md`
- `analysis/issues/weather_station_compare_window_guidance.md`

<!-- source-sha256: 50cb70c6e72ac3421887dd577c98ff7da1605c6f212352b440e3c3175125770b -->
