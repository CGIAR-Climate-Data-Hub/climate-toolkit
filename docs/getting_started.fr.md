# Premiers pas

!!! tip "Suivre le guide dans Colab"
    Le [notebook Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb) permet d’installer le paquet, d’effectuer une première extraction et, si nécessaire, de configurer Earth Engine depuis le navigateur.

## 1. Installer le paquet {#1-install}

Pour installer la version publiée sur PyPI, exécutez la commande suivante.

```bash
pip install climate-toolkit
```

Pour télécharger directement les données définitives de précipitations quotidiennes CHIRPS v3 (`chirps_v3_daily_rnl`) et les températures minimales et maximales CHIRTS-ERA5 (`chirts_era5`), utilisez Python 3.12 ou une version ultérieure et installez les dépendances `cloud`. Cette méthode fonctionne sans compte Earth Engine. [Accès direct aux données](direct_cloud_access.md)

```bash
pip install "climate-toolkit[cloud]"
```

Dans une cellule Jupyter, utilisez `%pip`.

```
%pip install climate-toolkit
```

Pour essayer la version en développement, exécutez `pip install "git+https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git"`. Pour contribuer au code, clonez le dépôt et installez ses dépendances avec [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
cd climate-toolkit
uv sync
```

## 2. Configurer Google Earth Engine {#2-google-earth-engine-credentials}

Passez directement à la [première analyse](#3-first-analysis) si vous utilisez NASA POWER, les stations `ghcn_daily` ou `gsod`, ou l’accès direct à CHIRPS v3 et CHIRTS-ERA5. Suivez cette étape pour `era5_land`, `era_5`, `nex_gddp`, CHIRPS v2 (`chirps_v2` ou `chirps`) ou l’accès de secours à CHIRPS v3 via Earth Engine.

!!! tip "Accès non commercial à Earth Engine"
    Les projets admissibles peuvent bénéficier d’un accès gratuit. Les exigences en matière de compte de facturation dépendent du niveau choisi. [Niveaux d’accès non commercial](https://developers.google.com/earth-engine/guides/noncommercial_tiers)

1. [Enregistrez votre projet Google Cloud](https://code.earthengine.google.com/register). Pour un projet non commercial, remplissez le questionnaire d’admissibilité et choisissez le niveau adapté à vos besoins.
2. Authentifiez-vous une fois sur votre machine.

    ```bash
    earthengine authenticate
    ```

3. Indiquez l’identifiant du projet Cloud en remplaçant `your-ee-project-id` par sa valeur. Le paquet accepte `GCP_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT` ou `EE_PROJECT_ID`.

    ```bash
    # macOS / Linux
    export GCP_PROJECT_ID=your-ee-project-id
    ```

    ```powershell
    # Windows PowerShell
    $env:GCP_PROJECT_ID = "your-ee-project-id"
    ```

4. Vérifiez la configuration.

    ```bash
    climate-toolkit-gee-check
    ```

## 3. Effectuer une première analyse {#3-first-analysis}

Cet exemple télécharge les données quotidiennes de Nairobi pour 2020 avec NASA POWER. Vérifiez le nombre de lignes et les colonnes obtenues.

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",
    location_coord=(-1.286, 36.817),   # Nairobi (latitude, longitude)
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
    verbose=False,
)
print("lignes:", df.shape[0], "| colonnes:", df.columns.tolist())
df.head()
```

La fonction renvoie un **DataFrame pandas**. NASA POWER ne fournit pas de données pédologiques. Un message indique que ces variables ont été omises et le tableau contient les variables climatiques disponibles.

### Présenter les statistiques saisonnières sous forme de tableau

À Nairobi, cet exemple fixe la saison des grandes pluies du 1er mars au 31 mai et affiche les résultats de chaque année. `analyze_climate_statistics` renvoie un dictionnaire imbriqué.

```python
import pandas as pd

stats = ct.analyze_climate_statistics(
    location_coord=(-1.286, 36.817),
    start_year=2016, end_year=2020,
    source="nasa_power",
    fixed_season="03-01:05-31",        # Grandes pluies de mars à mai
)

pd.DataFrame([
    {
        "year": s["year"],
        "rain_mm": (s["precipitation"] or {}).get("total_mm"),
        "NDWS": (s["water_balance"] or {}).get("NDWS"),
        "WRSI": (s["water_balance"] or {}).get("WRSI"),
    }
    for s in stats["season_statistics"]
])
```

!!! note "Comparer la même saison chaque année"
    La détection automatique peut trouver un nombre différent de saisons selon les années. Utilisez `fixed_season="MM-DD:MM-DD"` pour comparer des périodes fixes. Vous pouvez indiquer une ou deux périodes, séparées par une virgule.

## Consulter l’aide

```python
help(ct)                        # Présentation du paquet
help(ct.fetch_climate_data)     # Aide sur une fonction
```

Dans Jupyter ou IPython, saisissez `ct.fetch_climate_data?`. Dans VS Code, placez le pointeur sur le nom de la fonction pour consulter sa documentation.

Les noms des fonctions, les paramètres, les clés des résultats et les commandes sont en anglais. Les messages du paquet et l’aide de Python sont également en anglais. [Vue d’ensemble de l’API](api/index.md)

<!-- source-sha256: ccf419e7fc65933e00c2c468a0413771017699ea8a03ec61cc956f6b22bb03c3 -->
