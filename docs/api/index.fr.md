# Vue d’ensemble de l’API Python

Importez le paquet pour utiliser ces fonctions publiques.

```python
import climate_toolkit as ct
```

| Nom dans Python | Guide |
|---|---|
| `ct.fetch_climate_data` | [Télécharger des données](fetching.md) |
| `ct.analyze_climate_statistics` | [Analyser les données](analysis.md) |
| `ct.evaluate_hazards` | [Analyser les données](analysis.md) |
| `ct.compare_climate_periods` | [Analyser les données](analysis.md) |
| `ct.compare_climate_sources` | [Comparer et valider](comparison.md) |
| `ct.download_station_data` | [Comparer et valider](comparison.md) |
| `ct.compare_station_to_grids` | [Comparer et valider](comparison.md) |
| `ct.backend_policy` | [Choisir le mode d’accès aux données](../direct_cloud_access.md) |
| `ct.run_pipeline` | [Exécuter la chaîne de traitement](../use-as-a-package.md#one-call-for-the-whole-workflow-run_pipeline) |

Les noms des fonctions, les arguments et les clés des résultats sont identiques dans toutes les langues. L’aide de Python, les messages de la ligne de commande et les guides techniques ci-dessus sont en anglais. Pour consulter les paramètres d’une fonction, utilisez par exemple `help(ct.evaluate_hazards)`.

<!-- source-sha256: d862b8c76470dcad3da01c12450ef9275590f3d60983b2fd44ab440c14ee3272 -->
