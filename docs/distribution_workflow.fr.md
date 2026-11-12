# Distribution du paquet {#distribution-workflow}

## État actuel {#current-status}

Le logiciel s’installe comme un paquet Python standard. Les tests de distribution vérifient les opérations suivantes :

- installation en mode modifiable : `python -m pip install -e .`
- installation locale non modifiable : `python -m pip install .`
- construction des distributions : `python -m build`
- validation des métadonnées : `twine check dist/*`
- test automatique d’installation à partir du wheel et de l’archive source (sdist)

## Publication des versions {#current-release-decision}

Le paquet est **publié sur PyPI** sous le nom [`climate-toolkit`](https://pypi.org/project/climate-toolkit/) et s’installe avec `pip install climate-toolkit`.

La publication automatique utilise **Trusted Publishing** (OIDC, sans jeton enregistré). La publication d’une version sur GitHub déclenche la construction du paquet et son envoi vers PyPI. Une version marquée comme préversion est envoyée vers TestPyPI pour un essai. Consultez la procédure complète dans [`RELEASING.md`](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/RELEASING.md).

## Vérification locale {#local-verification}

Procédure recommandée avec versions de dépendances verrouillées :

```bash
uv sync --locked --group dev
rm -rf .tmp/dist-release
uv run python -m build --no-isolation --outdir .tmp/dist-release
uv run twine check .tmp/dist-release/*
uv run pytest -q tests/test_distribution_artifacts.py
```

Autres vérifications avec `pip` :

```bash
python -m pip install -e .
python -m pip install .
```

## Vérifications avant chaque publication {#per-release-checklist}

La première version publique (0.1.0) a satisfait à ces contrôles. Appliquez-les à chaque nouvelle version :

1. vérifier en intégration continue l’installation du wheel et de la distribution source
2. actualiser les instructions d’installation du README
3. éviter les valeurs d’exemple ambiguës dans les instructions d’authentification et de configuration
4. documenter les prérequis d’exécution et d’authentification pour les utilisateurs du paquet distribué
5. incrémenter la version (les versions PyPI sont immuables) et créer l’étiquette de publication

<!-- source-sha256: 7ce632d6e7be3048c39c408fd69970b929298fa8f5db11f08cd9e72dde4bef7d -->
