# Évaluer le stress thermique du bétail avec le THI {#livestock-thi-workflow}

Statut : méthode actuellement utilisée<br>
Mise à jour : 2026-06-24

Ce guide explique comment le logiciel évalue le stress thermique du bétail à l’aide du `THI` quotidien (indice de température et d’humidité).

## Fonctionnalités actuelles {#what-toolkit-does-now}

Le logiciel fournit actuellement :

- le `THI` quotidien pour le bétail
- la classe de stress correspondant au THI de chaque jour
- des résumés par période comprenant :
  - THI moyen
  - THI maximal
  - nombre de jours par classe de stress
  - nombre total de jours de stress
- intégration à l’évaluation des aléas via `calculate_hazards`

La méthode THI **reste en cours de validation**. Cette mise en œuvre répond au ticket `#30`. La révision des seuils et les améliorations propres aux différents animaux restent ouvertes.

## Formule actuelle {#current-formula}

Le logiciel applique la formule suivante :

`THI = (1.8*T + 32) - ((0.55 - 0.0055*RH) * ((1.8*T) - 26))`

où :

- `T` est la température moyenne journalière de l’air au thermomètre sec, en degrés Celsius
- `RH` est l’humidité relative journalière en pourcentage

Choix par défaut :

- calcul du THI avec la température moyenne et l’humidité relative
- la température maximale n’est pas utilisée par défaut à ce stade

Raisons :

- dans la littérature sur les projections pour l’élevage, le THI fondé sur la température quotidienne et l’humidité relative est actuellement le mieux étayé
- cette méthode correspond le mieux aux données d’humidité disponibles dans les sources historiques et futures
- l’humidité disponible ne correspond pas forcément à l’heure de `Tmax`. Utiliser `Tmax` sans tenir compte de ce décalage peut exagérer ou fausser le stress estimé

## Choix de la température {#temperature-input-rule}

Le logiciel recherche la température dans cet ordre :

1. colonne de température moyenne si elle est présente
2. autres noms reconnus pour la moyenne : `mean_temperature`, `tavg`, `tmean`, `temperature`, `temp`
3. à défaut, moyenne quotidienne calculée par `(tmax + tmin) / 2`

Le logiciel **ne propose pas** de méthode par défaut distincte fondée sur la température maximale quotidienne. Cette possibilité reste à étudier.

## Humidité requise {#humidity-requirement}

Le THI nécessite l’humidité relative quotidienne en pourcentage.

Conditions actuelles :

- plage d’humidité valide : `0..100`
- l’absence d’humidité empêche le calcul du THI
- les projections sans source fiable d’humidité ne sont pas prises en charge

## Choix du profil climatique {#climate-profile-logic}

Profils disponibles :

- `auto`
- `temperate`
- `tropical`

Fonctionnement de `auto` :

- utiliser d’abord la latitude
- dans la bande tropicale (`|lat| <= 23.5`), à partir de `1500 m` d’altitude, utiliser le profil tempéré comme approximation des hauts plateaux
- les basses terres tropicales conservent le profil tropical

L’altitude peut provenir des sources suivantes :

- valeur indiquée par l’utilisateur
- modèle numérique de terrain (MNT), si sa consultation est activée

## Profils d’élevage {#livestock-profiles}

Profils intégrés actuellement :

- `cattle_dairy`
- `cattle_general`
- `cattle_beef`
- `goats`
- `sheep`
- `pigs`
- `poultry_broilers`
- `poultry_layers`
- `poultry_general`

Origine des seuils :

- Thornton et al. (2021), tableau 1, pour les seuils opérationnels de base
- Thornton et al. (2021), tableau 2, pour les ajustements du seuil extrême en milieu tropical, lorsqu’ils s’appliquent

À retenir :

- les valeurs par défaut servent à l’évaluation préliminaire et ne décrivent pas la physiologie de chaque race
- le logiciel combine des seuils par groupe d’animaux et une règle simple pour le contexte tropical ou d’altitude
- certains seuils et conseils d’interprétation pourront évoluer

## Limites liées aux races et aux systèmes de production {#breed-and-production-context-limits}

Ces résultats servent au repérage du stress thermique et ne constituent pas un diagnostic vétérinaire.

Limites actuelles :

- un même profil bovin **ne distingue pas** Bos indicus, Bos taurus, les Sanga et les bovins croisés
- le logiciel **ne déduit pas** l’adaptation d’une race à partir de sa génétique, du pelage, de la taille ou du système de conduite
- la règle `auto` est une approximation géographique fondée sur la latitude et l’altitude
- les seuils ne se transposent pas toujours aux races adaptées localement ni aux différents systèmes et conditions d’élevage

Conseils d’interprétation :

- utilisez les classes par défaut pour un premier repérage
- si le projet dispose de seuils propres à la race ou de recommandations vétérinaires, privilégiez ces seuils personnalisés
- consignez tout changement dans les résultats ou dans une note méthodologique

Situations exigeant davantage de prudence :

- élevages laitiers tropicaux de bovins croisés
- bovins africains adaptés localement et mal représentés par les profils généraux lait ou viande
- élevages d’altitude où exposition climatique et adaptation génétique peuvent diverger

Vérifier la méthode en Python :

```python
from climate_toolkit.climatology import describe_thi_method

method = describe_thi_method()
print(method["profiles"]["cattle_dairy"])
print(method["profiles"]["pigs"])
```

## Sources prises en charge {#source-support}

Sources prises en charge actuellement :

- `era5_land`
  - humidité calculée à partir du point de rosée et de la température de l’air pendant la récupération des données
- `nasa_power`
  - humidité disponible par l’accès actuel à POWER
- `ghcn_daily`
  - si la station choisie fournit l’humidité sur la période demandée
- `gsod`
  - si la station choisie fournit l’humidité sur la période demandée
- `custom_station`
  - si le fichier fourni comporte une colonne d’humidité relative
- `nex_gddp`
  - sous réserve que `hurs` soit disponible dans Earth Engine pour le modèle, le scénario et la période choisis

Disponibilité incertaine ou limitée :

- `era_5`
  - la configuration actuelle de téléchargement d’ERA5 ne définit pas de bande d’humidité pour le calcul opérationnel du THI
  - considérez cette voie comme incertaine jusqu’à son intégration et à sa vérification à l’exécution

Sources non prises en charge :

- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts_era5` (uniquement Tmax et Tmin) et l’ancien produit `chirts`

Vérifier la méthode en Python :

```python
from climate_toolkit.climatology import describe_thi_method, describe_thi_source_support

print(describe_thi_source_support())
print(describe_thi_method()["source_support"]["nex_gddp"])
```

## Interface en ligne de commande {#cli-surface}

Plusieurs analyses proposent des options pour le THI du bétail :

- `climate-toolkit-seasons`
- `climate-toolkit-stats`
- `climate-toolkit-periods`
- `climate-toolkit-periods-ensemble`
- `climate-toolkit-hazards`
- variantes d’ensemble correspondantes

Principaux arguments :

- `--livestock-type`
- `--livestock-climate-profile`
- `--livestock-elevation-override-m`

Exemple :

```bash
climate-toolkit-periods-ensemble \
  --location="-1.286,36.817" \
  --baseline-start=1995 \
  --baseline-end=2013 \
  --future-start=2041 \
  --future-end=2060 \
  --scenarios=ssp245 \
  --fixed-season="03-01:05-31" \
  --livestock-type cattle_dairy \
  --livestock-climate-profile auto
```

## Personnaliser les seuils {#threshold-override-path}

Les classes de THI par défaut dépendent du profil d’élevage et du contexte climatique.

L’analyse des aléas permet de remplacer ces seuils avec `--thresholds-file`.

Vous pouvez ainsi définir des classes de danger THI différentes de celles du profil par défaut de l’animal.

Extrait JSON :

```json
{
  "THI": {
    "none": [null, 70],
    "mild": [70, 76],
    "moderate": [76, 84],
    "severe": [84, null]
  }
}
```

Exemple d’utilisation :

```bash
climate-toolkit-hazards \
  --crop maize \
  --location="-1.286,36.817" \
  --date-from 2020-03-01 \
  --date-to 2020-05-31 \
  --source paired \
  --precip-source chirps_v3_daily_rnl \
  --temp-source era5_land \
  --livestock-type cattle_dairy \
  --thresholds-file custom_thresholds.json
```

À retenir :

- ce remplacement change les classes utilisées pour évaluer le risque
- il ne modifie pas la formule du THI
- consignez les seuils personnalisés puisqu’ils diffèrent des valeurs opérationnelles du paquet

## Questions ouvertes {#still-open}

Travaux restants pour `#30` :

1. confronter les seuils à davantage de publications et décider s’il convient de les conserver
2. décider s’il faut ajouter une variante de repérage par température maximale en complément du THI sur température moyenne
3. améliorer la prise en charge des projections d’humidité au-delà des limites documentées pour `hurs`
4. préciser l’interprétation des résultats selon l’espèce et la race

<!-- source-sha256: 10698da7de75290e8a438b7f861999bd878a5f7f78c7c1c0ac4636f80054af45 -->
