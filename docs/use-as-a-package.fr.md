# Utiliser climate-toolkit dans un projet Python {#using-climate-toolkit-as-a-python-package}

Ce guide explique comment installer `climate_toolkit` et l’utiliser comme bibliothèque dans votre propre code Python. Tous les exemples sans identifiants ont été exécutés avec le paquet et l’API réels.

> **Nom du paquet.** Importez `climate_toolkit` en Python. Le nom distribué sur PyPI est `climate-toolkit`. L’accès direct à CHIRPS v3 et CHIRTS-ERA5 nécessite la version 0.2.0 ou une version ultérieure.

[![Ouvrir dans Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)
Pour essayer les exemples dans votre navigateur, ouvrez le notebook [`examples/climate_toolkit_colab.ipynb`](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb). Il exécute tous les exemples sans identifiants de ce guide dans Google Colab, sans installation ni configuration locale.

---

## Sommaire {#table-of-contents}

1. [Fonctionnalités](#1-what-you-get)
2. [Prérequis](#2-requirements)
3. [Installation](#3-installation)
4. [Vérifier l’installation](#4-verify-the-install)
5. [Identifiants selon la source](#5-credentials-by-data-source)
6. [Démarrage rapide sans identifiants](#6-quick-start-no-credentials)
7. [Configurer Earth Engine](#7-earth-engine-setup)
8. [Sept fonctions d’analyse](#8-seven-analysis-functions)
9. [Sources de données](#9-data-sources-reference)
10. [Variables](#10-variables-reference)
11. [Cache et résultats](#11-caching-and-outputs)
12. [Exemples pratiques](#12-recipes)
13. [Utiliser Jupyter ou son propre projet](#13-using-it-in-jupyter-your-own-project)
14. [Résoudre les problèmes](#14-troubleshooting)
15. [Obtenir de l’aide](#15-getting-more-help)

---

## 1. Fonctionnalités {#1-what-you-get}

!!! tip "Première utilisation ?"
    Le guide [Premiers pas](getting_started.md) propose une installation et une première analyse en cinq minutes. Vous trouverez ici une référence plus complète : fonctions publiques, sources et variables, cache, exemples et résolution des problèmes.

`climate_toolkit` est une bibliothèque d’analyse climatique par site. Une seule instruction `import climate_toolkit as ct` donne accès aux sept fonctions d’analyse suivantes. La [vue d’ensemble de l’API](api/index.md) présente également `run_pipeline` et `backend_policy`.

| Fonction | Utilité |
|----------|--------------|
| `fetch_climate_data` | Télécharger les données quotidiennes d’un point dans un DataFrame pandas |
| `analyze_climate_statistics` | Calculer climatologie saisonnière, bilan hydrique et SPI/SPEI sur plusieurs années |
| `evaluate_hazards` | Évaluer les risques pour les cultures ou le bétail pendant une saison agricole |
| `compare_climate_periods` | Calculer les écarts entre une année étudiée et la climatologie de référence |
| `compare_climate_sources` | Comparer plusieurs produits maillés pour un même site |
| `download_station_data` | Obtenir les observations quotidiennes des stations voisines |
| `compare_station_to_grids` | Valider des produits maillés à partir d’observations en station |

Les sources comprennent CHIRPS, ERA5-Land, TerraClimate, IMERG, TAMSAT, CHIRTS-ERA5, ERA5, NEX-GDDP, NASA POWER, CMIP6, SoilGrids et les stations GHCN-Daily et GSOD.

---

## 2. Prérequis {#2-requirements}

- **Python ≥ 3.10.** Python 3.9 ne convient pas. Utilisez un environnement virtuel en version 3.10 ou ultérieure. [`uv`](https://docs.astral.sh/uv/) simplifie sa création et peut installer Python 3.12 pour l’accès direct aux données cloud.
- Aucun paquet système supplémentaire ni compilateur n’est nécessaire avec les distributions Python au format wheel.
- Pour les sources Earth Engine, prévoyez un projet Google Cloud et une authentification unique (section 7). **NASA POWER et les stations ne nécessitent ni l’un ni l’autre.**

---

## 3. Installation {#3-installation}

Consultez [Premiers pas → Installation](getting_started.md#1-install) pour l’installation depuis GitHub, l’utilisation de `%pip` dans Jupyter et l’environnement de développement `uv`. En bref :

```bash
# Dans votre projet ou notebook :
pip install climate-toolkit

# Ou installer la version en développement depuis Git :
pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"

# Ou développer à partir d’une copie du dépôt :
cd climate-toolkit && uv sync
```

Après installation, `import climate_toolkit` fonctionne depuis tout répertoire. Pour exécuter un script dans l’environnement du dépôt, utilisez `uv run python my_script.py`.

---

## 4. Vérifier l’installation {#4-verify-the-install}

```bash
uv run python -c "import climate_toolkit as ct; print(ct.__version__)"
# Exemple : 0.2.0
```

Vérifiez les noms exportés par le paquet :

```python
import climate_toolkit as ct
print([n for n in ct.__all__ if not n.startswith("__")])
# Inclut les fonctions d’analyse, backend_policy et run_pipeline.
```

---

<a id="5-credentials-nasa-power-vs-earth-engine"></a>

## 5. Identifiants selon la source {#5-credentials-by-data-source}

- **`nasa_power`** et les stations `ghcn_daily` et `gsod` utilisent HTTPS **sans identifiants**. Ce sont de bons points de départ.
- **`chirps_v3_daily_rnl` et `chirts_era5`** permettent un [accès direct sans identifiants](direct_cloud_access.md). Avec Python 3.12 ou ultérieur, exécutez `pip install "climate-toolkit[cloud]"`. Passez `allow_gee=False` pour interdire le recours à Earth Engine.
- Les **sources Earth Engine** (`era5_land`, `era_5`, `chirps_v2` avec l’alias `chirps`, `chirts`, `imerg`, `terraclimate`, `cmip_6`, `nex_gddp`, `soil_grid` et `hwsd`) passent par **Google Earth Engine**. Elles exigent une authentification initiale et un identifiant de projet (section 7).

---

## 6. Démarrage rapide sans identifiants {#6-quick-start-no-credentials}

### Données quotidiennes sous forme de DataFrame {#fetch-daily-data-dataframe}

```python
from datetime import date
import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),      # (lat, lon), Nairobi
    variables=[ClimateVariable.precipitation,
               ClimateVariable.max_temperature,
               ClimateVariable.min_temperature],
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print(df.head())
#         date  precipitation  max_temperature  min_temperature
# 0 2020-01-01           0.04            27.17            14.07
# ...
```

`fetch_climate_data` renvoie un **DataFrame pandas**.

### Statistiques saisonnières sous forme de dictionnaire {#seasonal-statistics-dict}

```python
stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2015, end_year=2020,
    source="nasa_power",
)
print(stats.keys())
# location, period, source, ..., season_statistics, ltm_season_summary, ...
```

`analyze_climate_statistics` renvoie un **dictionnaire imbriqué**. Pour une climatologie de long terme, utilisez au moins une vingtaine d’années. Une série courte déclenche un avertissement.

---

## 7. Configurer Earth Engine {#7-earth-engine-setup}

Les sources Earth Engine de la section 5 nécessitent une configuration initiale. [Premiers pas → Identifiants Earth Engine](getting_started.md#2-google-earth-engine-credentials) décrit notamment l’accès **gratuit** pour les projets non commerciaux admissibles. Exécutez `earthengine authenticate`, définissez `GCP_PROJECT_ID` et vérifiez la configuration avec `climate-toolkit gee-check` (code de sortie 0 en cas de réussite).

Les fonctions peuvent alors utiliser les sources EE :

```python
# ClimateVariable a été importé dans l’exemple précédent.
vars3 = [ClimateVariable.precipitation,
         ClimateVariable.max_temperature,
         ClimateVariable.min_temperature]

df = ct.fetch_climate_data(
    source="era5_land",                       # Earth Engine
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
)

# Les projections NEX-GDDP nécessitent un modèle et un scénario :
proj = ct.fetch_climate_data(
    source="nex_gddp", model="GFDL-ESM4", scenario="ssp245",
    location_coord=(-1.286, 36.817),
    variables=vars3,
    date_from=date(2050, 1, 1), date_to=date(2050, 12, 31),
)
```

---

<a id="8-the-public-api-all-seven-functions"></a>

## 8. Sept fonctions d’analyse {#8-seven-analysis-functions}

L’aide détaillée au format NumPy est accessible pour chaque fonction : `help(ct.<function>)`.

### `fetch_climate_data` {#fetch_climate_data}

```python
ct.fetch_climate_data(
    source, location_coord=None, variables=None,
    date_from=None, date_to=None, model=None, scenario=None,
    stage="preprocessed", cache_dir=None, refresh_cache=False,
    sites=None, sites_csv=None, station_id=None, workers=1, verbose=True,
)
```
Renvoie un DataFrame. `stage` détermine l’étape finale : `"raw"` → `"transformed"` → `"preprocessed"` (par défaut). Pour un téléchargement groupé sur plusieurs sites, passez `sites=` ou `sites_csv=` (sources GEE et NEX-GDDP).

### `analyze_climate_statistics` {#analyze_climate_statistics}

```python
ct.analyze_climate_statistics(
    location_coord, start_year, end_year, source,
    fixed_season=None, crop_name=None,
    spei_scale_months=None, spi_scale_months=None,
    workers=1, verbose=False,
)
```
Renvoie un dictionnaire avec les statistiques par saison, le bilan hydrique (ET0, NDWS, WRSI), les blocs SPI/SPEI facultatifs et les moyennes à long terme.

### `evaluate_hazards` {#evaluate_hazards}

```python
ct.evaluate_hazards(
    crop_name, location_coord, date_from, date_to,   # dates au format ISO sous forme de chaînes
    season_start=None, season_end=None, fixed_season=None,
    source="auto", custom_thresholds=None,
    soilcp=100.0, soilsat=100.0, workers=1,
)
```
Évalue les risques pour les cultures et le bétail sur une saison agricole (chaleur, sécheresse, engorgement…). `date_from` et `date_to` sont des chaînes de dates ISO, par exemple `"2020-03-01"`.

### `compare_climate_periods` {#compare_climate_periods}

```python
ct.compare_climate_periods(
    location, baseline_start, baseline_end, focal_year, source,
    fixed_season=None, crop_name=None, workers=1,
)
```
Compare l’année étudiée à la climatologie de référence et renvoie un dictionnaire des écarts.

### `compare_climate_sources` {#compare_climate_sources}

```python
ct.compare_climate_sources(
    sources, lat=None, lon=None, start=None, end=None,
    output_dir="./outputs", nex_model=None, nex_scenario="ssp245",
    workers=1,
)
```
Compare plusieurs produits maillés pour un même site. `sources` est une liste, par exemple `["nasa_power", "era5_land"]`.

### `download_station_data` (arguments nommés uniquement) {#download_station_data-keyword-only-args}

```python
ct.download_station_data(
    station_source="ghcn_daily",            # ou "gsod"
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    max_distance_km=50.0, auto_select="auto-1",
)
```
Recherche les stations voisines et télécharge leurs observations. Earth Engine n’est pas nécessaire.

### `compare_station_to_grids` (arguments nommés uniquement) {#compare_station_to_grids-keyword-only-args}

```python
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power", "era5_land"],
)
```
Valide les produits maillés par comparaison avec les observations en station et renvoie un dictionnaire.

---

## 9. Sources de données {#9-data-sources-reference}

| Clé `source` | Données | Earth Engine ? |
|--------------|------|:---:|
| `nasa_power` | Données climatiques quotidiennes ponctuelles, depuis 1984 | Non |
| `tamsat` | Pluies en Afrique et humidité du sol (accès facultatif, parfois instable) | Non (téléchargement direct) |
| `ghcn_daily`, `gsod` | Observations météorologiques en station | Non |
| `era5_land` | Agrégats quotidiens ERA5-Land, nombreuses variables, choix recommandé | Oui |
| `era_5` | Réanalyse quotidienne ERA5 | Oui |
| `chirps_v2` (alias `chirps`) | Précipitations CHIRPS v2 | Oui |
| `chirps_v3_daily_rnl` | Précipitations quotidiennes définitives CHIRPS v3 | Recours facultatif |
| `chirts_era5` | Tmax et Tmin quotidiennes CHIRTS-ERA5 | Non (dépendances cloud) |
| `chirts` (obsolète) | Températures de l’ancien CHIRTS-daily, 1983–2016 | Oui |
| `imerg` | Précipitations GPM IMERG | Oui |
| `terraclimate` | Bilan hydrique mensuel | Oui |
| `cmip_6` | Projections GDDP-CMIP6 | Oui |
| `nex_gddp` | Projections NEX-GDDP-CMIP6 (exigent `model` et `scenario`) | Oui |
| `soil_grid`, `hwsd` | Propriétés statiques du sol | Oui |

Les anciens alias (`era5`, `agera5`, `nasapower`, `nexgddp`, `ghcn`, etc.) sont normalisés automatiquement.

---

## 10. Variables {#10-variables-reference}

`variables` accepte une **liste de membres d’énumération**, forme compatible avec toutes les versions :

```python
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

variables=[ClimateVariable.precipitation,
           ClimateVariable.max_temperature,
           ClimateVariable.min_temperature]
```

Les versions récentes acceptent aussi les chaînes (p. ex. `["precipitation", "max_temperature"]` ou `"precipitation,max_temperature"`), comme la ligne de commande. Si vous obtenez `AttributeError: 'str' object has no attribute 'name'`, utilisez les membres de l’énumération ci-dessus : votre version est plus ancienne.

Noms de `ClimateVariable` : `rainfall`, `precipitation`, `max_temperature`, `min_temperature`, `mean_temperature`, `wind_speed`, `solar_radiation`, `humidity`, `soil_moisture`. Les propriétés du sol figurent dans `SoilVariable`.

Si vous omettez `variables`, chaque source utilise sa sélection par défaut et écarte les variables absentes, comme l’humidité du sol pour NASA POWER.

---

## 11. Cache et résultats {#11-caching-and-outputs}

- Les téléchargements sont mis en cache sous **`outputs/cache/<source>/...`**, par site, période et variables. Les exécutions suivantes réutilisent les tableaux en cache.
- Forcer une nouvelle lecture depuis la source : `refresh_cache=True`.
- Déplacer le cache : `cache_dir="/some/stable/path"`.
- Les fonctions d’analyse et de comparaison enregistrent leurs rapports dans `./outputs` par défaut.

Git ignore `outputs/` et `.tmp/`.

---

## 12. Exemples pratiques {#12-recipes}

### Exécuter toute la chaîne avec `run_pipeline` {#one-call-for-the-whole-workflow-run_pipeline}

`run_pipeline` enchaîne la récupération des données, la climatologie à long terme, la comparaison facultative des sources, les statistiques saisonnières, les aléas agricoles et la comparaison facultative des périodes pour un ou plusieurs sites. Il renvoie un tableau de synthèse `summary` et tous les résultats intermédiaires. Par défaut, l’échec d’un site n’interrompt pas le lot.

```python
import climate_toolkit as ct

# Un seul site
result = ct.run_pipeline(
    name="Nairobi", location_coord=(-1.286, 36.817),
    start_year=2019, end_year=2020, source="nasa_power",
    fixed_season="03-01:05-31", crop_name="maize",
)
result.summary                      # une ligne de synthèse par site (DataFrame)
result.site_results[0].climate_statistics   # résultat imbriqué complet par site

# Plusieurs sites (liste de dictionnaires, sites_csv="..." ou site_table=DataFrame)
batch = ct.run_pipeline(
    sites=[{"name": "A", "lat": -1.0, "lon": 36.0},
           {"name": "B", "lat": -2.0, "lon": 37.0}],
    start_year=2019, end_year=2020, source="nasa_power",
)
batch.summary            # une ligne par site
batch.errors             # erreurs enregistrées par site, le lot va à son terme
```

La climatologie utilise par défaut la période de référence 1991–2020 de l’OMM (`climatology_baseline=(1991, 2020)`). Activez les étapes facultatives avec `run_compare_sources=True` et `compare_sources_list=[...]`, ou `run_compare_periods=True` et `baseline_start/baseline_end/focal_year`.

### Comparer deux sources pour un site {#compare-two-sources-at-one-site}

```python
ct.compare_climate_sources(
    sources=["nasa_power", "era5_land"],       # era5_land nécessite Earth Engine
    lat=-1.286, lon=36.817,
    start="2020-01-01", end="2020-12-31",
    output_dir="./outputs",
)
```

### Évaluer les risques pour une saison de maïs {#hazard-screen-for-a-maize-season}

```python
ct.evaluate_hazards(
    crop_name="Maize",
    location_coord=(-1.286, 36.817),
    date_from="2020-03-01", date_to="2020-08-31",
)
```

### Comparer l’année étudiée à la climatologie de référence {#focal-year-vs-baseline-climatology}

```python
ct.compare_climate_periods(
    location=(-1.286, 36.817),
    baseline_start=1991, baseline_end=2020,
    focal_year=2023,
    source="era5_land",
)
```

### Valider un produit maillé à partir d’une station voisine {#validate-a-grid-product-against-a-nearby-station}

```python
from datetime import date
ct.compare_station_to_grids(
    station_source="ghcn_daily",
    station_coord=(-1.286, 36.817),
    date_from=date(2019, 1, 1), date_to=date(2020, 12, 31),
    grid_sources=["nasa_power"],
)
```

---

## 13. Utiliser Jupyter ou son propre projet {#13-using-it-in-jupyter-your-own-project}

Une fois le paquet installé dans votre environnement Python, importez-le normalement :

```python
import climate_toolkit as ct
from datetime import date

from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

df = ct.fetch_climate_data(
    source="nasa_power", location_coord=(-1.286, 36.817),
    variables=[ClimateVariable.precipitation],
    date_from=date(2022, 1, 1), date_to=date(2022, 3, 31),
)
df.set_index("date")["precipitation"].plot()   # tracer la série de précipitations quotidiennes
```

Le notebook démarre rapidement car les dépendances lourdes ne sont chargées qu’au moment de leur utilisation.

---

## 14. Résoudre les problèmes {#14-troubleshooting}

| Symptôme | Cause ou solution |
|---------|-------------|
| `SyntaxError` ou échec de l’importation avec `python3` | Vous utilisez Python 3.9. Utilisez un environnement 3.10 ou ultérieur (`uv sync`). |
| `Earth Engine project ID missing` | Définissez `GCP_PROJECT_ID` (section 7). |
| `Project 'projects/YOUR_PROJECT_ID' not found` | Remplacez la valeur d’exemple par l’identifiant réel du projet. |
| Erreur de renouvellement d’authentification ou de DNS pour une source EE | Relancez `ee.Authenticate()` et vérifiez le réseau. |
| `command not recognized: climate-toolkit-*` | Les commandes du paquet sont disponibles après `uv sync` ou `pip install`. Vous pouvez aussi exécuter `python -m climate_toolkit.<module>`. |
| `OSError: File name too long` lors d’une requête NASA POWER | Précisez une liste `variables=[...]` au lieu d’utiliser toutes les variables par défaut. |
| `AttributeError: 'str' object has no attribute 'name'` pour `variables=` | Fournissez des membres de l’énumération (`ClimateVariable.*`) plutôt que des chaînes. |

Vérifiez la configuration Earth Engine à tout moment avec :

```bash
uv run climate-toolkit gee-check
```

---

## 15. Obtenir de l’aide {#15-getting-more-help}

- Utilisez `help(ct.fetch_climate_data)` (ou le nom de l’une des sept fonctions) pour consulter la documentation complète des paramètres.
- Les liens du fichier `pyproject.toml` et du README du projet mènent à la référence de l’API et aux pages sur les jeux de données.
- Utilisez `uv run climate-toolkit --help` pour afficher les sous-commandes équivalentes.

<!-- source-sha256: c81558de9ebbcd67f883a554df344ae2d19a2c5f625241968c626a68d817e9e7 -->
