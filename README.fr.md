# Climate Toolkit

[English](README.md) · [Español](README.es.md)

Climate Toolkit permet d’analyser le climat d’un site agricole à partir de ses coordonnées. Vous pouvez télécharger des séries quotidiennes, comparer des périodes et des stations météorologiques et évaluer les risques pour les cultures et le bétail.

```bash
pip install climate-toolkit
```

Pour obtenir les précipitations CHIRPS v3 et les températures quotidiennes CHIRTS-ERA5 sans identifiants Google, utilisez Python 3.12 ou une version ultérieure et installez les dépendances facultatives avec `pip install "climate-toolkit[cloud]"`.

[Premiers pas](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/fr/getting_started/) · [Documentation](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/fr/) · [Essayer dans Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)

Pour visualiser les observations et les données sur grille par mois et par saison, ajoutez `--diagnostics-html FICHIER` à la commande de comparaison des stations.

Ajoutez `--uncertainty-html ensemble.html` à `climate-toolkit periods-ensemble` pour visualiser la dispersion annuelle et saisonnière, les changements par modèle et le nombre de modèles contributeurs.

<!-- source-sha256: 8527afca25b4942318b82124a2bc47590df6960b94d3eaac382f37fb209adf57 -->
