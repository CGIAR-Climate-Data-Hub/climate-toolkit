# Résultats par module {#outputs-by-module}

Retrouvez les **tableaux et figures produits par chaque module**, leur format, les colonnes et les fichiers attendus avant de lancer une analyse. Les signatures et les paramètres des fonctions figurent dans la [référence de l’API Python](api/index.md).

---

## 🌾 fetch_data — acquisition des données climatiques {#fetch_data-climate-data-ingestion}

**Formats :** CSV, JSON

**Tableaux :**

- Séries quotidiennes avec les colonnes `date`, `precipitation`, `max_temperature`, `min_temperature`, `humidity`, `solar_radiation`, `wind_speed` selon la source.

**Figures :** aucune (données brutes uniquement).

---

## 📅 season_analysis — détection des saisons des pluies {#season_analysis-rainy-season-detection}

**Formats :** CSV, JSON

**Tableaux :**

- **Résumé par saison (CSV) :** `year`, `season_number`, `onset`, `cessation`, `regime`, `length_days`, `total_rainfall_mm`, `rainy_days`, `dry_days`, `dry_spells`, `annual_rain_mm`, `humid_result`.
    - Indicateurs pour le bétail lorsque ce mode est activé : `mean_thi`, `max_thi`, `thi_stress_days`.
- **Moyennes à long terme (JSON) :** agrégats par saison, dont date moyenne de début, durée moyenne et précipitations moyennes.

**Figures :** aucune.

---

## 📊 climate_statistics — indicateurs et agrégation {#climate_statistics-climate-metrics-aggregation}

**Formats :** principalement JSON, export possible en CSV

**Tableaux :**

- **`raw_climate_summary` :** moyenne, minimum, maximum et écart-type par variable et par saison.
- **`overall_statistics`** par saison : cumuls et statistiques de précipitations, températures moyenne, maximale et minimale, évapotranspiration de référence (ET0), bilan hydrique (NDWS, NDWL0, WRSI), déficit de pression de vapeur (VPD) et stress thermique (Humidex, THI).
- **`season_statistics` :** principaux indicateurs par saison.
- **`monthly_series` (CSV) :** données quotidiennes agrégées par mois.
- **`spei` / `spi` (CSV) :** indices de sécheresse avec date, valeur et classe.
- **`annual_summary` :** résultats du test d’humidité pour chaque année.

**Figures :** aucune.

---

## 📈 compare_periods — comparaison de périodes historiques {#compare_periods-historical-period-comparison}

**Formats :** JSON, texte dans la console

**Tableaux :**

- **Comparaison** pour chaque variable et saison : `focal` (valeur de l’année étudiée), `baseline_avg` (moyenne de référence), `diff` (année étudiée moins référence), `pct_change` (`diff / baseline × 100`).
- Les comparaisons portent sur les précipitations, la température, le stress hydrique et le stress thermique.

**Figures :** aucune.

---

## ⚠️ calculate_hazards — évaluation des aléas agricoles {#calculate_hazards-crop-hazard-assessment}

Avec `fixed_season`, le début de la saison doit se situer entre les dates demandées, bornes comprises. Ainsi, de `2010-01-01` à `2010-12-31`, la fenêtre `10-01:01-31` inclut toute la saison d’octobre 2010 à janvier 2011. Pour une seule saison, `season_info` et `season_statistics` figurent au premier niveau du résultat. Pour plusieurs saisons, la liste `assessments` comporte une entrée par saison. Consultez `error` si aucune saison ne commence dans la période ou si la couverture est incomplète.

**Formats :** JSON, texte dans la console et CSV facultatif

**Tableaux :**

- **`hazard_indicators`** fournit pour chaque aléa `focal_value`, `baseline_avg`, `diff`, `stress_category` (stress absent, modéré, sévère ou extrême) et `reasoning`.

| Indicateur | Signification |
|--------|---------|
| Précipitations | Cumul saisonnier |
| TAVG | Température moyenne |
| NDD | Nombre de jours secs (précipitations < 1 mm) |
| NTx35 | Jours avec Tmax ≥ 35 °C |
| NTx40 | Jours avec Tmax ≥ 40 °C |
| NDWS | Jours de stress hydrique |
| NDWL0 | Jours d’engorgement du sol |
| WRSI | Satisfaction des besoins en eau (%) |
| THI | Indice de stress thermique du bétail |
| HUMIDEX | Indice de chaleur pour l’être humain |

**Figures :** aucune.

---

## 🌦️ weather_station (téléchargement) — recherche de stations {#weather_station-download-station-discovery}

**Formats :** CSV, JSON, HTML interactif

**Tableaux :**

- **Stations candidates (CSV) :** `station_id`, `station_name`, `distance_km`, `elevation_diff_m`, complétude par variable (`precip_complete_%`, `temp_complete_%`), `data_years`, `selection_status`, `selection_rank`, `selection_reason`.

**Figures :** aucune. Le tableau HTML permet de filtrer et de trier les résultats.

---

## 🔄 weather_station (comparaison) — validation des grilles à partir des stations {#weather_station-compare-station-vs-grid-validation}

**Formats :** JSON, CSV facultatif, HTML et PNG facultatifs

**Tableaux :**

- **Indicateurs de validation (JSON)** pour chaque paire (source maillée, variable) : `n_overlap_days`, `correlation`, `rmse`, `bias`, `mae`, `annual_total_grid`, `annual_total_station`, `pct_diff`, `wet_day_agreement_%`.
- **Comparaison quotidienne (CSV facultatif) :** `date`, `grid_source`, `variable`, `station_value`, `grid_value`, `diff`, `pct_diff`, `quality_flag`.

**Figures (PNG facultatifs) :**

- Comparaison des séries chronologiques de la grille et de la station.
- Nuage de points des valeurs de la grille et de la station.
- Boîtes à moustaches par variable et par source.

---

## 🌍 climatology — normales et indices climatiques {#climatology-climatic-normals-indices}

**Formats :** JSON, CSV par indice et PNG facultatif

**Tableaux :**

- **Normales mensuelles de l’OMM (`ltm_monthly`) :** `month`, `precip_mm`, `tmax_c`, `tmin_c`, `humidity_%`, `solar_rad`, `et0_mm`.
- **Indices de sécheresse (`spei` / `spi`, CSV) :** `date`, `spei_value` / `spi_value`, `classification` (humide, normal, sécheresse modérée, sévère ou extrême).
- **Statistiques du VPD (`vpd`) :** déficit de pression de vapeur mensuel.
- **Stress thermique du bétail (THI, CSV) :** `date`, `daily_thi`, `thi_classification` (cool / thermal_comfort / heat_stress / severe_heat_stress).
- **Stress thermique humain (Humidex, CSV) :** `date`, `daily_humidex`, `humidex_classification` (comfortable / warm / very_warm / hot / very_hot / dangerous / extreme_caution).

**Figures (PNG facultatifs) :**

- Courbes de climatologie mensuelle.
- Séries chronologiques des indices de sécheresse.
- Évolution des classes de stress thermique.

---

## 🔗 compare_datasets — comparaison de plusieurs sources {#compare_datasets-multi-source-comparison}

**Formats :** CSV et PNG par source, PNG regroupant les sources

**Tableaux :**

- **`{source}_annual_timeseries.csv` :** `year`, cumuls ou moyennes annuels par variable.
- **`{source}_monthly_climatology.csv` :** `month`, moyennes mensuelles par variable.
- **Tableau de synthèse dans la console :** moyenne, minimum, maximum, écart-type et coefficient de variation par source.

**Figures (PNG à 150 ppp) :**

- Par source : `{source}_annual_timeseries.png` (tendances annuelles) et `{source}_monthly_climatology.png` (cycle saisonnier).
- Toutes sources : `multisource_annual_{variable}.png` et `multisource_monthly_climatology_{variable}.png` (courbes superposées).

---

## Vue d’ensemble {#quick-summary}

| Module | Format principal | Tableaux | Figures | Rapport |
|--------|----------------|--------|---------|--------|
| **fetch_data** | CSV / JSON | Séries quotidiennes | ❌ | ❌ |
| **season_analysis** | CSV + JSON | Résumé saisonnier et statistiques à long terme | ❌ | Texte dans la console |
| **climate_statistics** | JSON + CSV | Résumés brut, global, saisonnier et mensuel, SPEI/SPI | ❌ | JSON et console |
| **compare_periods** | JSON | Référence et année étudiée, écarts absolus et en % | ❌ | JSON et console |
| **calculate_hazards** | JSON | Indicateurs d’aléas et classes de stress | ❌ | JSON et console |
| **weather_station (téléchargement)** | CSV + JSON + HTML | Stations candidates et indicateurs de qualité | ❌ | HTML interactif |
| **weather_station (comparaison)** | JSON + CSV facultatif | Indicateurs de validation (corrélation, RMSE, biais…) | ⚠️ Facultatives | JSON et HTML facultatif |
| **climatology** | JSON + CSV | Normales mensuelles à long terme, indices de sécheresse et de chaleur | ⚠️ Facultatives | JSON et console |
| **compare_datasets** | CSV par source et PNG | Tableaux annuels et mensuels par source | ✅ Graphiques PNG | Statistiques dans la console |

**Légende :** ❌ aucune figure · ⚠️ figures facultatives · ✅ figures incluses.

<!-- source-sha256: 1f7101684228d6a8cd147ddaee6b0f58398147374f458f332be5a0bf1120eba3 -->
