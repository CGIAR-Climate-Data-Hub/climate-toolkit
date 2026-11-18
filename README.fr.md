# Climate Toolkit

[English](README.md) · [Español](README.es.md)

Climate Toolkit permet d’analyser le climat d’un site agricole à partir de ses coordonnées. Vous pouvez télécharger des séries quotidiennes, comparer des périodes et des stations météorologiques et évaluer les risques pour les cultures et le bétail.

[Écrivez à Pete pour vous abonner](mailto:p.steward@cgiar.org?subject=Subscribe%20to%20Climate%20Toolkit%20release%20updates) et recevoir à chaque version stable un courriel sur les changements susceptibles d’affecter votre code ou vos résultats. Pour vous désabonner, répondez «unsubscribe».

```bash
pip install climate-toolkit
```

Pour obtenir les précipitations CHIRPS v3 et les températures quotidiennes CHIRTS-ERA5 sans identifiants Google, utilisez Python 3.12 ou une version ultérieure et installez les dépendances facultatives avec `pip install "climate-toolkit[cloud]"`.

[Premiers pas](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/fr/getting_started/) · [Documentation](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/fr/) · [Essayer dans Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)

Pour visualiser les observations et les données sur grille par mois et par saison, ajoutez `--diagnostics-html FICHIER` à la commande de comparaison des stations.

Ajoutez `--uncertainty-html ensemble.html` à `climate-toolkit periods-ensemble` pour visualiser la dispersion annuelle et saisonnière, les changements par modèle et le nombre de modèles contributeurs.

<!-- source-sha256: ed0f5eb0297a9a643fb90218831b8a92800b566ee67f3e0e3cc2436ccd6d47ab -->
