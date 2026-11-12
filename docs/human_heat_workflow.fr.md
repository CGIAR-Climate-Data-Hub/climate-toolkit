# Évaluer le stress thermique chez l’être humain {#human-heat-workflow}

Pour cette première évaluation, le logiciel calcule l’indice `Humidex` avec `xclim`.

Le périmètre est plus restreint que celui d’une évaluation complète de l’exposition à la chaleur au travail ou en plein air.

## Choix de la première phase {#phase-1-choice}

Indicateur retenu :
- `humidex`

Travaux différés :
- `WBGT`
- `UTCI`
- évaluations plus détaillées de la chaleur au travail

## Pourquoi commencer par `humidex` ? {#why-humidex-first}

- ne nécessite que la température et l’humidité ou le point de rosée
- déjà disponible via `xclim` dans le logiciel
- mieux adapté aux variables disponibles que `WBGT` ou `UTCI`
- utilisable pour certaines projections `nex_gddp` si `hurs` est disponible

## Pourquoi différer `WBGT` ? {#why-not-wbgt-first}

L’indice `WBGT` est important, mais le logiciel ne dispose pas encore d’un traitement cohérent du vent et du rayonnement pour l’ensemble des analyses historiques et futures visées.

## Pourquoi différer `UTCI` ? {#why-not-utci-first}

L’indice `UTCI` tient compte de davantage de mécanismes physiques. Sa mise en œuvre exige les données suivantes :
- température
- humidité
- vent
- température moyenne de rayonnement ou composantes du rayonnement

Ces données existent pour certaines sources historiques, mais leur disponibilité n’est pas uniforme pour les projections visées.

## Sources prises en charge {#source-support}

Sources adaptées à cette première évaluation :
- `era5_land`
- `nasa_power`
- `ghcn_daily` si l’humidité est disponible
- `gsod` si l’humidité est disponible
- `custom_station` si l’humidité ou le point de rosée est disponible
- `paired`
  - si la source de température fournit aussi l’humidité ou le point de rosée
- `auto`
  - si la source de température retenue fournit l’humidité ou le point de rosée

Prise en charge conditionnelle :
- `nex_gddp`
  - uniquement si la variable `hurs` est disponible dans Earth Engine pour le modèle, le scénario et la période choisis

Sources actuellement inadaptées :
- `era_5`
  - la méthode d’accès actuelle ne garantit pas la disponibilité de l’humidité
- `chirps_v2`
- `chirps_v3_daily_rnl`
- `imerg`
- `tamsat`
- `chirts_era5` (uniquement Tmax et Tmin) et l’ancien produit `chirts`

## Fonctions auxiliaires disponibles {#current-helper-surface}

Fonctions Python :
- `climate_toolkit.climatology.build_human_heat_source_bundle`
- `climate_toolkit.climatology.compute_daily_humidex`
- `climate_toolkit.climatology.summarize_humidex_period`
- `climate_toolkit.climatology.describe_human_heat_method`
- `climate_toolkit.climatology.describe_human_heat_source_support`

Utilisation dans les modules :
- `climate_statistics`
  - ajoute un bloc facultatif `human_heat_stress` si l’humidité ou le point de rosée est disponible
- `compare_periods`
  - calcule les écarts des indicateurs `human_heat_stress` si l’humidex peut être calculé pour la période de référence et la période étudiée
- `calculate_hazards`
  - produit une évaluation indicative de l’humidex et un décompte des jours si des données d’humidité sont disponibles

## Limites actuelles {#current-limits}

- les classes d’humidex servent au repérage général et ne constituent pas des recommandations médicales ou de santé au travail
- rien ne permet de considérer `humidex` comme le meilleur indicateur du stress thermique humain dans tous les contextes

## Prochaines étapes envisagées {#likely-next-steps}

1. déterminer l’approche pour la deuxième phase :
   - `WBGT`
   - `UTCI`
   - une combinaison selon les capacités de chaque source
2. préciser les méthodes et les conditions d’utilisation des sources pour distinguer le dépistage général par humidex d’une évaluation complète de l’exposition par WBGT

<!-- source-sha256: 9fc411b38a405dfd4741a712be7681216a27aff6f7c2f99665651cf4a145e76b -->
