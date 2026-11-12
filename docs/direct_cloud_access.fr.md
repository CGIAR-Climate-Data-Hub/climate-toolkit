# Accès direct aux données et fournisseurs de secours {#direct-cloud-access-and-provider-fallback}

Référence : [architecture du paquet](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/package_architecture_summary.md). Le développement est suivi dans les tickets [#176](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/176), [#177](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/177) et [#178](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/178).

## Installer et télécharger {#install-and-fetch}

L’accès direct nécessite **Python 3.12 ou ultérieur** et les dépendances cloud facultatives :

```sh
pip install 'climate-toolkit[cloud]'
# Depuis une copie du dépôt :
uv sync --extra cloud
```

Le paquet de base reste compatible avec Python 3.10 et versions ultérieures. Sur les versions antérieures à 3.12, les requêtes directes signalent cette exigence. Les accès GEE explicitement configurés restent disponibles.

```python
from datetime import date
import climate_toolkit as ct

rain = ct.fetch_climate_data(
    "chirps_v3_daily_rnl",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
temperature = ct.fetch_climate_data(
    "chirts_era5",
    location_coord=(-1.286, 36.817),
    date_from=date(2020, 1, 1), date_to=date(2020, 12, 31),
    allow_gee=False,
)
print(rain.attrs["data_provenance"])
```

Avec `sites=[("Nairobi", -1.286, 36.817), ...]` ou `sites_csv=...`, les mêmes règles de sélection du fournisseur s’appliquent. Les lectures différées de points sont regroupées par blocs de stockage partagés. `workers` limite le nombre de tâches simultanées (1 à 8 en accès direct).

## Produits et fournisseurs {#products-and-providers}

| Source | Ordre de sélection automatique | Vérification de la couverture |
| --- | --- | --- |
| `chirps_v3_daily_rnl` | Cache compatible complet, puis produit définitif de Dynamical, Hugging Face, enfin GEE si autorisé | Dates réellement disponibles : toute la période demandée est requise |
| `chirts_era5` | Cache complet, puis Hugging Face | Dates réellement disponibles : l’archive hébergée commence en 1981 |

Dynamical a utilisé moins de bande passante dans toutes les configurations CHIRPS d’un an mesurées. Pour Nairobi en 2020, Dynamical a transféré 3,39 Mo en 20 requêtes, contre 21,54 Mo en 26 requêtes pour Hugging Face. Dans les deux cas, la répétition depuis le cache n’a nécessité aucune requête distante. Lors de la vérification, l’archive définitive de Dynamical couvrait aussi des dates plus récentes. Hugging Face peut être plus rapide pour des périodes courtes. Voir les [mesures de transfert CHIRPS](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirps-http-benchmark-2026-11-09) pour les charges plus importantes et les limites. Si nécessaire, sélectionnez `backend="huggingface"` ou `backend="dynamical"` : un choix explicite empêche le changement automatique de fournisseur.

Les deux adaptateurs CHIRPS lisent la **v3 définitive/RNL**. Le produit préliminaire de Dynamical est SAT et reste exclu. Ni CHIRPS v2 ni un autre produit de précipitations ne sert de miroir de secours.

Dynamical stocke un taux moyen journalier de précipitations que l’adaptateur convertit en mm/jour. Pour Hugging Face, xarray applique une seule fois le décodage d’échelle CF. Les arrondis diffèrent entre miroirs : tenez compte de l’erreur de quantification documentée, notamment pour les décomptes de jours franchissant un seuil. Chaque requête renvoie les données d’une seule révision chez un seul fournisseur, sans assembler des jours de différents fournisseurs.

Pour CHIRPS v3, 543 valeurs quotidiennes par miroir ont été comparées à la grille native d’Earth Engine à Nairobi, Ouagadougou et Cusco, de décembre à février en 2019/20 et 2025/26. Les écarts journaliers maximaux, arrondis vers le haut, étaient de 0,041 mm pour Dynamical et de 0,050 mm pour Hugging Face. Au seuil strict de `>1 mm`, la classification des jours de pluie différait pour zéro et trois observations site-jour respectivement. Pour les comparaisons sensibles aux seuils, choisissez un seul fournisseur et consignez sa révision avec les résultats. Voir la [comparaison de référence et les instructions de reproduction](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirps-finalrnl-reference-comparison-2026-11-08).

Utilisez CHIRTS-ERA5 pour les nouvelles analyses de température. L’ancienne clé `chirts` (CHIRTS-daily, 1983–2016) est **obsolète** et déclenche un avertissement. Son adaptateur reste accessible explicitement pour reproduire des résultats anciens. Le recours automatique utilise désormais CHIRTS-ERA5. Les clés et caches existants gardent leur identité et ne sont jamais fusionnés. Le raccourci `chirps_v2+chirts` conserve son sens historique.

CHIRTS-ERA5 étend la couverture temporelle sans garantir une meilleure précision à chaque site. Le producteur publie ses données de suivi avec environ cinq jours de décalage ; le miroir peut les recevoir plus tard. CHIRTS-daily et CHIRTS-ERA5 utilisent tous deux des informations ERA5 mais sont construits différemment. La migration dépasse donc un simple changement d’hébergeur.

Le [miroir Hugging Face](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily) stocke Tmax et Tmin par pas de 0,1 °C. Le décompte des jours chauds utilise la température décodée et inclut les jours où Tmax atteint exactement 35 °C (NTx35) ou 40 °C (NTx40). Par exemple, une Tmax originale de 34,96 °C est arrondie à 35,0 °C et compte dans NTx35 sur le miroir. Les moyennes saisonnières utilisent aussi les valeurs décodées.

Avant d’appliquer des seuils absolus, vérifiez le biais par rapport à une station locale. Sur les dates communes de 1994–95 et 2023–24, les minima quotidiens de CHIRTS-ERA5 dépassaient en moyenne ceux de la station de Nairobi de 3,2 à 4,3 °C et ceux de Cusco de 3,3 à 3,8 °C. À Ouagadougou en 2023–24, la grille a manqué 30 des 349 jours où la station a atteint ou dépassé 35 °C et a compté six faux positifs. La couverture des observations dépend du site et de la variable.

Prévoyez la bande passante nécessaire pour les longues séries. À Nairobi, la première lecture de trente ans de Tmax et Tmin quotidiennes a pris 137 secondes et transféré 1,47 Go. La répétition depuis le cache a pris 0,07 seconde sans requête réseau. Sur la même période, 10 ou 100 sites dispersés dépassaient la limite par défaut de 4 Gio de données décodées. Regroupez les sites voisins ou demandez des périodes plus courtes pour les sites dispersés. Voir les [comparaisons avec les stations et les mesures de transfert](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_176_178_direct_cloud_access.md#chirts-era5-station-comparison-and-transport-benchmark-2026-11-10).

## Combiner deux sources et contrôler l’accès à GEE {#paired-workflows-and-gee-controls}

```python
with ct.backend_policy(allow_gee=False):
    result = ct.analyze_climate_statistics(
        location_coord=(-1.286, 36.817), start_year=2020, end_year=2020,
        source="paired", precip_source="chirps_v3_daily_rnl",
        temp_source="chirts_era5", fixed_season="03-01:05-31",
    )
```

```sh
climate-toolkit fetch --source chirps_v3_daily_rnl --no-gee \
  --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-12-31

climate-toolkit stats --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2020 --end-year 2020 \
  --fixed-season 03-01:05-31
```

L’interface unifiée accepte `--backend` et `--no-gee` pour toutes les commandes, tout comme la commande autonome de téléchargement. Les autres commandes autonomes peuvent utiliser les variables d’environnement `CLIMATE_TOOLKIT_ALLOW_GEE=false` et `CLIMATE_TOOLKIT_BACKEND=auto`. Les contextes Python peuvent être imbriqués ; les processus de calcul des modèles lancés par la bibliothèque héritent des règles d’accès. Tout fil d’exécution ou processus créé par l’utilisateur doit ouvrir son propre contexte.

En mode historique `auto`, CHIRPS v3 est associé à la source `era5_land` (**ERA5-Land**, distincte d’AgERA5) pour les variables complémentaires. CHIRTS-ERA5 sert désormais de dernier recours pour la température. Si GEE est interdit, `auto` sélectionne directement CHIRPS v3 et CHIRTS-ERA5. Cette association fournit uniquement les précipitations et Tmax/Tmin. Elle ne fournit ni humidité, ni vent, ni rayonnement, ni données de sol : les analyses qui les exigent en ont toujours besoin. Les métadonnées du stress thermique humain indiquent une valeur nulle pour les variables complémentaires absentes, sans les attribuer à CHIRTS-ERA5.

Le choix explicite du fournisseur s’applique aux sources accessibles directement dans le cloud. Les autres gardent leurs voies d’accès, sous réserve de l’interdiction générale de GEE. Choisir `dynamical` pour CHIRTS-ERA5 échoue car cet adaptateur n’existe pas. Utilisez `auto` pour les analyses associant des sources différentes. Le recours automatique à GEE exige une configuration préalable et n’ouvre jamais d’authentification interactive.

## Chaîne de traitement complète {#full-pipeline}

`run_pipeline` applique la même paire de sources et les mêmes règles d’accès au téléchargement quotidien, à la climatologie, à la comparaison des sources, aux statistiques saisonnières, aux aléas agricoles et à la comparaison des périodes. Cet essai utilise deux ans de climatologie. Pour des normales scientifiques, choisissez une période de référence plus longue et adaptée, en tenant compte des limites ci-dessous.

```python
result = ct.run_pipeline(
    name="Nairobi", location_coord=(-1.286, 36.817),
    source="paired", precip_source="chirps_v3_daily_rnl", temp_source="chirts_era5",
    allow_gee=False, workers=2,
    start_year=2020, end_year=2020,
    climatology_baseline=(2019, 2020),
    fixed_season="03-01:05-31", crop_name="maize",
    run_compare_sources=True,
    compare_sources_list=["paired", "chirps_v3_daily_rnl", "chirts_era5"],
    run_compare_periods=True,
    baseline_start=2019, baseline_end=2019, focal_year=2020,
    output_dir="outputs/nairobi_pipeline",
)
print(result.summary)
assert not result.errors, result.errors
```

`source="auto", allow_gee=False` sélectionne aussi cette paire. `backend="auto"` convient pour combiner des sources de précipitations et de température : Dynamical ne propose pas d’adaptateur de température. Si vous fournissez `ee_project_id` pour un accès GEE autorisé, il est transmis aux étapes concernées.

Le dossier de chaque site contient `daily.csv`, son fichier de métadonnées, les rapports JSON par étape et `status.json`. À la racine se trouvent `summary.csv` et `metadata.json`. Les exports quotidiens de comparaison des sources sont dans `source_comparison/` pour chaque site. Vérifiez le statut et `completed_steps` avant d’utiliser un rapport. Une erreur renvoyée ou une comparaison partielle fait échouer l’étape. Une nouvelle exécution en échec supprime les anciens rapports JSON devenus obsolètes. Des exports partiels peuvent subsister pour le diagnostic sans attester la réussite de l’étape.

La climatologie en accès direct exige toutes les années demandées et rejette les données qui échouent aux contrôles qualité. Elle ne raccourcit pas discrètement la période de référence. La ligne de commande permet également de calculer une climatologie à deux sources :

```sh
climate-toolkit climatology --no-gee --source paired \
  --precip-source chirps_v3_daily_rnl --temp-source chirts_era5 \
  --location=-1.286,36.817 --start-year 2019 --end-year 2020 \
  --format json --output outputs/climatology.json --output-dir ""
```

## Intégrité des données, caches et limites {#data-integrity-caches-and-limits}

- Les tableaux bruts contiennent les colonnes décodées avec leurs noms d’origine, les résultats des contrôles qualité et la provenance. Les tableaux transformés ou prétraités utilisent les noms normalisés. Les données directes conservent leur précision : le remplissage générique et les conversions heuristiques d’unités ne sont pas appliqués.
- Une valeur manquante ou infinie, des précipitations négatives, une température hors de l’intervalle −90 à 60 °C ou Tmin supérieure à Tmax empêchent l’analyse des données directes. Examinez `stage="raw"` pour en rechercher la cause. Ces contrôles grossiers ne garantissent pas l’exactitude scientifique. Une valeur physiquement invalide n’est pas traitée comme une panne.
- Une panne de transfert ou de fournisseur, une couverture obsolète, des dates ou variables manquantes ou des métadonnées incompatibles peuvent entraîner l’essai d’un autre miroir admissible. Une période partielle n’est jamais acceptée silencieusement. Un point en mer ou hors domaine n’est pas déplacé vers une maille terrestre voisine.
- Les blocs annuels sont stockés sous `outputs/cache/direct_cloud/v2/<source>/<backend>/` ou à la racine indiquée. Les fichiers JSON, munis d’une somme de contrôle, conservent la précision numérique, l’ordre des colonnes, les coordonnées demandées, les mailles retenues, les unités, la révision et les dates. Les écritures sont atomiques. Une réponse complète en cache évite tout appel de métadonnées ou d’authentification, même pour un fournisseur de secours. Une lecture interrompue peut reprendre avec les blocs de la même révision ; une nouvelle révision remplace les anciennes données sans les mélanger. `refresh_cache=True` demande les données amont actuelles. Les caches GEE existants restent séparés. Les années manquantes consécutives sont lues par lots de cinq ans au plus, en partageant les blocs sources entre années. Chaque lot terminé enregistre les résultats annuels séparément, ce qui permet une reprise à la même révision après une panne.
- Les exports CSV/JSON des téléchargements et comparaisons de sources écrivent un fichier annexe `.metadata.json`. Les statistiques, comparaisons de périodes, évaluations d’aléas et diagnostics de stations incluent des champs supplémentaires `data_provenance`. L’inventaire du cache inclut `direct_cloud`.
- Les appels HTTP de métadonnées ont des délais et un nombre de tentatives limités ; les transferts ont aussi un délai maximal par requête. La limite estimée par défaut est de 4 Gio de blocs sources décodés par requête et par fournisseur. Il s’agit de la taille décodée, **pas du trafic réseau mesuré**. Si la limite est dépassée, ce fournisseur est écarté. Réglez `CLIMATE_TOOLKIT_MAX_DECODED_BYTES` pour la modifier. Une requête longue ou géographiquement dispersée peut prendre plusieurs minutes.

Pour reproduire les mesures en ligne, utilisez `scripts/benchmark_direct_cloud.py`. Son délai de 90 secondes par cas est un critère de l’essai et ne limite pas la durée totale d’un traitement de la bibliothèque. Les tests ordinaires utilisent des données de test hors ligne ; les mesures en ligne sont facultatives.

CHIRTS-ERA5 dispose actuellement d’**un seul fournisseur direct intégré**. Les archives GeoTIFF/NetCDF du CHC sont des originaux indépendants. Les fichiers quotidiens et les échecs de lecture partielle observés exigent d’autres travaux avant d’en faire un recours automatique efficace. Le 2026-11-02, le NetCDF de Tmax de l’année en cours a été refusé, celui de Tmin s’arrêtait en septembre et le catalogue EWX ne proposait que des agrégats de cinq jours ou mensuels. Les lectures ponctuelles des NetCDF historiques dépassaient aussi le temps visé pour une requête courte. Le 10 novembre, les Tmin du 21 octobre différaient de 0,20 à 2,18 °C dans les mêmes mailles entre l’original CHC et la révision retenue du miroir Hugging Face. Ces écarts dépassent la tolérance de quantification du miroir (0,05 °C). L’équivalence des révisions doit être établie avant tout recours automatique à l’original. Reproduisez les essais de lecture par plages d’octets avec `scripts/probe_chc_backup.py` (dépendance `h5py` nécessaire uniquement pour l’enquête). Voir l’[étude de la source de secours](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_179_chc_backup_investigation.md) et le ticket [#179](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/179). L’accès sans identifiants aux variables complémentaires ERA5-Land est suivi dans [#180](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/issues/180). L’[audit de l’accès à ERA5-Land](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/analysis/issues/issue_180_era5_land_access.md) a identifié les archives CDS ARCO authentifiées, mais la consultation en ligne des métadonnées a rejeté la clé configurée. L’intégration CDS est suspendue puisqu’elle nécessite des identifiants. Aucun accès cloud direct à ERA5-Land n’est activé. Pour reproduire les résultats GEE, les flux horaires du CDS doivent aussi être agrégés en définissant explicitement les limites des journées.

## Références {#references}

- [Documentation du producteur de CHIRTS-ERA5](https://www.chc.ucsb.edu/data/chirts-era5)
- [CHIRTS-ERA5 sur Hugging Face](https://huggingface.co/datasets/aaguilar90/chirts-era5-daily)
- [CHIRPS v3 RNL sur Hugging Face](https://huggingface.co/datasets/aaguilar90/chirps-v3-daily-rnl)
- [Produit définitif/RNL de Dynamical](https://dynamical.org/catalog/ucsb-chc-chirps-analysis-final/)

Vérification intégrale en ligne : `python scripts/verify_direct_pipeline.py`. Le script contrôle les six étapes, la provenance exportée et une deuxième exécution depuis le cache où l’ouverture des fournisseurs et l’initialisation de GEE sont bloquées. Il utilise des périodes courtes de vérification, impropres au calcul de normales climatiques scientifiques.

<!-- source-sha256: c39cbc8080809be30231fbc7817ac7ac6ee9d3f9e68fef1a64b140458fde5e21 -->
