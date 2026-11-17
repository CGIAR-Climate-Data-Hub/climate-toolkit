# Exemple d’analyse de bout en bout {#example-end-to-end-workflow}

Cet exemple permet de découvrir le logiciel, depuis le téléchargement des données brutes jusqu’aux projections d’aléas pour les cultures.

> [!IMPORTANT]
> **Les commandes ci-dessous commencent par `uv run` pour pouvoir être copiées telles quelles.** Exécutez-les depuis la racine du dépôt après `uv sync`.
>
> - Les commandes `climate-toolkit-*` ne sont disponibles qu’après installation (`uv sync` ou `pip install -e .`). Lancer `climate-toolkit-fetch ...` directement, sans `uv run` ou depuis un dépôt non installé, peut donner l’erreur « command not recognized ».
> - Depuis un dépôt sans installation, vous pouvez appeler le module : chaque `climate-toolkit-<name>` correspond à `python -m climate_toolkit.<module>` (p. ex. `python -m climate_toolkit.season_analysis.seasons ...`).
> - Remplacez les coordonnées, les dates et toute valeur `<PLACEHOLDER>` par vos propres valeurs.

## Prérequis {#prerequisites}

1. **Google Earth Engine** (pour les sources qui passent par GEE) :
   - Créez un compte sur [earthengine.google.com](https://earthengine.google.com)
   - Authentifiez-vous une fois : `earthengine authenticate`
   - Indiquez votre projet Cloud pour initialiser Earth Engine. Le logiciel lit l’identifiant dans l’environnement. Il **ne charge pas** automatiquement un fichier `.env` :
     ```bash
     # macOS / Linux
     export GCP_PROJECT_ID=your-ee-project-id
     ```
     ```powershell
     # Windows PowerShell
     $env:GCP_PROJECT_ID = "your-ee-project-id"
     ```
     (Ou utilisez `uv run --env-file .env ...` si vous conservez cette valeur dans un fichier `.env`.)
2. **Installation** : `uv sync` (recommandé) ou `pip install -e .`
3. **Données à fournir** : latitude et longitude. Vous indiquerez la culture et les dates plus loin.

---

## Étape 1 — Télécharger les données climatiques {#step-1-fetch-raw-climate-data}

`climate-toolkit-fetch` utilise `--lat` et `--lon` pour un site et `--start` et `--end` pour les dates.

```bash
uv run climate-toolkit-fetch \
  --source era5_land \
  --lat -1.286 --lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/climate_data.csv
```

- Téléchargement à la source, normalisation des noms de variables, puis prétraitement (unités et contrôle qualité).
- **Couverture des sources :** ERA5-Land depuis 1950, avec humidité dérivée ; archive ERA5 de 1979 au 2020-07-09 ; CHIRPS v3 `chirps_v3_daily_rnl` depuis 1981 pour les précipitations ; NASA POWER depuis 1984 ; projections NEX-GDDP avec `--scenario` et `--model` ou `--models`.
- **Plusieurs modèles NEX-GDDP en une seule exécution :** passez une liste séparée par des virgules ou `all` avec `--models` ou `--model`. Un fichier est enregistré par modèle :
  ```bash
  uv run climate-toolkit-fetch --source nex_gddp --lat -1.286 --lon 36.817 \
    --start 2050-01-01 --end 2050-12-31 \
    --variables precipitation,max_temperature,min_temperature \
    --models ACCESS-CM2,EC-Earth3,MRI-ESM2-0 --scenario ssp245 \
    --format csv -o outputs/nex_2050.csv
  ```

---

## Étape 2 — Valider avec des observations en station (facultatif) {#step-2-validate-against-weather-stations-optional}

Rechercher les stations voisines :

```bash
uv run climate-toolkit-weather-station-download \
  --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --max-distance-km 100 \
  --report-prefix outputs/weather_station/nearby_candidates \
  --open-report
```

Comparer données maillées et observations :

```bash
uv run climate-toolkit-weather-station-compare \
  --grid-source era5_land \
  --station-source gsod \
  --station-id <STATION_ID> \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2020-01-01 --end 2020-12-31 \
  --format json
```

---

## Étape 3 — Climatologie (la « normale » locale) {#step-3-climatology-the-local-normal}

```bash
uv run climate-toolkit-climatology \
  --location "-1.286,36.817" \
  --source era5_land \
  --start-year 1991 --end-year 2020
```

Pour NEX-GDDP, `--source nex_gddp` utilise l’ensemble CMIP6 et calcule la moyenne des modèles. Ajoutez `--model-workers` pour paralléliser.

---

## Étape 4 — Détecter les saisons des pluies {#step-4-detect-rainy-seasons}

```bash
uv run climate-toolkit-seasons \
  --location "-1.286,36.817" \
  --source era5_land \
  --start-year 2015 --end-year 2020
```

- Détection du début et de la fin de saison pour chaque année à partir du bilan hydrique (ET0 de Hargreaves).
- Enregistrez les figures et les fichiers de résultats avec `--output-dir outputs/seasons`.
- **Si la détection automatique est peu fiable** (climat très humide ou irrégulier), définissez une fenêtre calendaire fixe avec `--fixed-season`, comme à l’étape 5.

---

## Étape 5 — Statistiques climatiques par saison {#step-5-climate-statistics-by-season}

Saisons détectées automatiquement :

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/climate_stats_2015_2020.json
```

Saisons fixes (p. ex. mars–mai et octobre–décembre) :

```bash
uv run climate-toolkit-stats \
  --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --fixed-season "03-01:05-31,10-01:12-31" \
  --output outputs/climate_stats_fixed.json
```

Les résultats incluent les précipitations saisonnières, les températures extrêmes, les indicateurs de bilan hydrique (NDWS, NDWL0), les indices de stress thermique et, sur demande, le SPEI.

---

## Étape 6 — Comparer les périodes {#step-6-compare-periods}

`climate-toolkit-periods` accepte `--baseline-start`, `--baseline-end` et `--focal-year`. Les deux premières options ne portent pas le suffixe `*-year`.

```bash
uv run climate-toolkit-periods \
  --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/2020_vs_2001_2015.json
```

Pour comparer des périodes avec NEX-GDDP, ajoutez `--uncertainty-html ensemble.html` à `climate-toolkit periods-ensemble`. Pour chaque scénario, le rapport présente, par an et par saison, les précipitations, les moyennes des températures maximales et minimales quotidiennes, et les précipitations moins l’évapotranspiration de référence. Chaque point représente un modèle. La médiane et les intervalles entre les 25e et 75e et entre les 10e et 90e percentiles résument la dispersion des modèles ayant fourni des valeurs pour les deux périodes. Les changements sont calculés pour chaque modèle. Le tableau des contributions et le CSV indiquent les valeurs manquantes et les modèles en échec. Ces intervalles décrivent la dispersion entre modèles et ne donnent pas de probabilités de prévision. Pour tracer les résultats à partir d’un fichier JSON enregistré sans télécharger de données climatiques :

```python
import json
from pathlib import Path
from climate_toolkit.visualization.ensemble import write_ensemble_uncertainty

result = json.loads(Path("ensemble.json").read_text())
write_ensemble_uncertainty(result, "ensemble.html")
```

---

## Étape 7 — Évaluer les aléas agricoles {#step-7-crop-hazards}

`climate-toolkit-hazards` reçoit la **culture en argument positionnel**. Pour les dates, utilisez `--date-from` et `--date-to` et évitez `--start-date` et `--end-date`.

```bash
uv run climate-toolkit-hazards Maize \
  --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/maize_hazards_2020.json
```

Cultures prises en charge : haricot (Beans), manioc (Cassava), arachide (Groundnuts), maïs (Maize), mil (Millet), riz (Rice) et sorgho (Sorghum). Les indicateurs incluent NDWS, NDWL0, NTx35/NTx40, NDD et les seuils de précipitations et de température propres à chaque culture.

---

## Étape 8 — Projeter les aléas (ensemble NEX-GDDP) {#step-8-project-hazards-nex-gddp-ensemble}

`climate-toolkit-hazards-ensemble` prend la culture en argument positionnel. Indiquez `--start-year` et `--end-year`, `--models` (liste séparée par des virgules ou `all`), `--scenarios` (liste séparée par des virgules) et `--model-workers` pour l’exécution parallèle.

```bash
uv run climate-toolkit-hazards-ensemble Maize \
  --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 \
  --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245,ssp585 \
  --model-workers 8 \
  --output outputs/maize_hazards_2050_2060.json
```

---

## Exemple complet : aptitude à la culture du maïs près de Nairobi {#complete-walkthrough-maize-suitability-near-nairobi}

```bash
# 1. Télécharger les données climatiques
uv run climate-toolkit-fetch --source era5_land --lat -1.286 --lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --format csv -o outputs/nairobi_climate.csv

# 2. Rechercher les stations voisines (facultatif)
uv run climate-toolkit-weather-station-download --station-source auto \
  --station-lat -1.286 --station-lon 36.817 \
  --start 2015-01-01 --end 2020-12-31 \
  --variables precipitation,max_temperature,min_temperature \
  --report-prefix outputs/nairobi_stations --open-report

# 3. Climatologie de référence
uv run climate-toolkit-climatology --location "-1.286,36.817" --source era5_land \
  --start-year 1991 --end-year 2020

# 4. Détecter les saisons des pluies
uv run climate-toolkit-seasons --location "-1.286,36.817" --source era5_land \
  --start-year 2015 --end-year 2020

# 5. Statistiques climatiques
uv run climate-toolkit-stats --location "-1.286,36.817" \
  --start-year 2015 --end-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_stats.json

# 6. Comparer 2020 à la période de référence
uv run climate-toolkit-periods --location "-1.286,36.817" \
  --baseline-start 2001 --baseline-end 2015 --focal-year 2020 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_2020_vs_baseline.json

# 7. Évaluer les aléas pour le maïs en 2020
uv run climate-toolkit-hazards Maize --location "-1.286,36.817" \
  --date-from 2020-01-01 --date-to 2020-12-31 \
  --source paired --precip-source chirps_v3_daily_rnl --temp-source era5_land \
  --output outputs/nairobi_maize_2020.json

# 8. Projeter les aléas pour le maïs sur 2050-2060
uv run climate-toolkit-hazards-ensemble Maize --location "-1.286,36.817" \
  --start-year 2050 --end-year 2060 --fixed-season "03-01:05-31" \
  --models MPI-ESM1-2-LR,GFDL-ESM4 --scenarios ssp245 --model-workers 8 \
  --output outputs/nairobi_maize_2050_2060.json
```

---

## Précisions et difficultés fréquentes {#notes-gotchas}

- **Les commandes du paquet nécessitent une installation** (`uv sync` ou `pip install -e .`). Installer les dépendances de `requirements.txt` ne les crée pas. Utilisez alors `python -m climate_toolkit.<module>`.
- L’**identifiant de projet Earth Engine** doit être défini dans l’environnement (`GCP_PROJECT_ID`), ou fourni avec `uv run --env-file .env`. Le fichier `.env` n’est pas chargé automatiquement.
- **Source historique quotidienne** : en mode automatique standard, la paire est `chirps_v3_daily_rnl` pour les précipitations et `era5_land` pour la température. En mode apparié, indiquez les deux sources.
- **Noms CHIRPS** : `chirps_v3_daily_rnl` est la v3 recommandée. L’ancienne `chirps_v2` est un produit distinct. La date de fin 2016 concerne les températures de l’ancien CHIRTS-daily. Utilisez `chirts_era5` pour les nouvelles analyses de température.
- **Accès sans GEE** : installez les dépendances cloud et passez `--no-gee`. Le mode historique `auto` associe alors CHIRPS v3 à CHIRTS-ERA5. Voir l’[accès direct](direct_cloud_access.md).
- Le **premier appel à GEE** est lent en raison de la négociation d’authentification. Les exécutions suivantes réutilisent le cache.
- **Les options dépendent de la commande.** Vérifiez-les avec `--help`. Par exemple, `fetch` utilise `--lat/--lon` ; `stats`, `seasons` et `hazards` utilisent `--location` ; `hazards` reçoit la culture en argument positionnel et les dates via `--date-from` et `--date-to` ; `periods` utilise `--baseline-start` et `--baseline-end`.

<!-- source-sha256: 25c651b76dfbc54c9c8458822a7d2eb00fe44cc741e8c6dafe4e1155ed090547 -->
