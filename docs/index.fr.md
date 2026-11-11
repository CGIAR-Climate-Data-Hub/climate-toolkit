# Climate Toolkit

À partir de la latitude et de la longitude d’un site, téléchargez des données climatiques quotidiennes, calculez des climatologies saisonnières et des indices de sécheresse, évaluez les risques pour les cultures et le bétail, et comparez les résultats entre périodes, sources et stations météorologiques.

!!! tip "Essayer dans le navigateur"
    Le [notebook Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb) installe le paquet dans un environnement gratuit hébergé par Google et exécute les exemples qui ne demandent pas d’identifiants.

## Installation

```bash
pip install climate-toolkit
```

## Démarrage rapide

```python
import climate_toolkit as ct
from datetime import date

df = ct.fetch_climate_data(
    source="nasa_power",              # Accès sans identifiants
    location_coord=(-1.286, 36.817),  # Nairobi
    date_from=date(2020, 1, 1),
    date_to=date(2020, 12, 31),
)
df.head()
```

Pour les précipitations CHIRPS v3 et les températures quotidiennes CHIRTS-ERA5, installez `climate-toolkit[cloud]` avec Python 3.12 ou une version ultérieure. Pour ERA5-Land, ERA5 et NEX-GDDP, configurez Earth Engine. [Guide d’installation et première analyse](getting_started.md) · [Accès direct aux données](direct_cloud_access.md)

## Fonctions principales

| Fonction | Résultat |
|---|---|
| [`fetch_climate_data`](api/fetching.md) | Données climatiques quotidiennes d’un site dans un DataFrame pandas |
| [`analyze_climate_statistics`](api/analysis.md) | Climatologie saisonnière, bilan hydrique et indices SPI/SPEI |
| [`evaluate_hazards`](api/analysis.md) | Évaluation des risques saisonniers pour les cultures et le bétail |
| [`compare_climate_periods`](api/analysis.md) | Comparaison d’une année avec la climatologie de référence |
| [`compare_climate_sources`](api/comparison.md) | Comparaison de jeux de données maillées |
| [`download_station_data`](api/comparison.md) | Observations quotidiennes des stations voisines |
| [`compare_station_to_grids`](api/comparison.md) | Validation des données maillées à partir des observations en station |

Ces sept analyses sont aussi disponibles en ligne de commande. La [vue d’ensemble de l’API Python](api/index.md) présente aussi `run_pipeline` pour exécuter toute la chaîne de traitement et `backend_policy` pour choisir le mode d’accès aux données.

## Financement et remerciements

La [Fondation McKnight](https://www.mcknight.org/) a financé le projet *Advancing Climate Data Integration in Agroecological Research* dans le cadre de son programme [Global Collaboration for Resilient Food Systems](https://www.mcknight.org/programs/global-foods/). L’[Alliance de Bioversity International et du CIAT](https://alliancebioversityciat.org/) a dirigé les travaux en partenariat avec le [Centre de recherche et d’innovation de l’AIMS](https://www.aimsric.org/).

Le [programme Climate Action du CGIAR](https://www.cgiar.org/cgiar-research-portfolio-2025-2030/climate-action/) a soutenu ces travaux par son premier axe, le *Climate Data Hub*, qui finance et coordonne l’infrastructure de données climatiques. Nous remercions le Fonds fiduciaire du CGIAR et [ses contributeurs](https://www.cgiar.org/funders/).

<p style="display:flex; align-items:center; gap:1.5em; flex-wrap:nowrap; margin-top:1.5em;">
  <a href="https://www.mcknight.org/programs/global-foods/">
    <img src="../assets/logos/mcknight.jpg" alt="The McKnight Foundation" style="height:44px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.cgiar.org/news-events/news/the-world-has-changed-so-has-climate-action-at-cgiar">
    <img src="../assets/logos/cgiar-climate-action.png" alt="CGIAR Climate Action" style="height:56px; width:auto; background:#fff; padding:4px;">
  </a>
  <a href="https://www.aimsric.org/">
    <img src="../assets/logos/aims.png" alt="AIMS Research and Innovation Centre (AIMS RIC)" style="height:52px; width:auto; background:#fff; padding:4px;">
  </a>
</p>

<!-- source-sha256: e0949b08482b5ad48627e68bad44aad7bb2ca75c6b396a68a17b68bc73a8c4c8 -->
