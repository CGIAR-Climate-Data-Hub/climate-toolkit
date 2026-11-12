# Distribución del paquete {#distribution-workflow}

## Estado actual {#current-status}

El programa se instala como un paquete estándar de Python. Las pruebas de distribución comprueban las operaciones siguientes:

- instalación en modo editable: `python -m pip install -e .`
- instalación local no editable: `python -m pip install .`
- construcción de las distribuciones: `python -m build`
- validación de metadatos: `twine check dist/*`
- prueba automática de instalación desde el wheel y el archivo fuente (sdist)

## Publicación de versiones {#current-release-decision}

El paquete se **publica en PyPI** con el nombre [`climate-toolkit`](https://pypi.org/project/climate-toolkit/) y se instala con `pip install climate-toolkit`.

La publicación automática utiliza **Trusted Publishing** (OIDC, sin almacenar tokens). Al publicar una versión en GitHub se construye el paquete y se sube a PyPI. Si se marca como versión preliminar, se envía a TestPyPI como ensayo. Consulte el procedimiento completo en [`RELEASING.md`](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/RELEASING.md).

## Verificación local {#local-verification}

Procedimiento recomendado con versiones de dependencias fijadas:

```bash
uv sync --locked --group dev
rm -rf .tmp/dist-release
uv run python -m build --no-isolation --outdir .tmp/dist-release
uv run twine check .tmp/dist-release/*
uv run pytest -q tests/test_distribution_artifacts.py
```

Comprobaciones alternativas con `pip`:

```bash
python -m pip install -e .
python -m pip install .
```

## Comprobaciones antes de cada publicación {#per-release-checklist}

La primera versión pública (0.1.0) superó estos controles. Aplíquelos a cada nueva versión:

1. comprobar en integración continua la instalación del wheel y de la distribución fuente
2. mantener actualizadas las instrucciones de instalación del README
3. evitar valores provisionales ambiguos en las instrucciones de autenticación y configuración
4. documentar los requisitos de ejecución y autenticación para los usuarios del paquete distribuido
5. incrementar la versión (las versiones de PyPI son inmutables) y crear la etiqueta de publicación

<!-- source-sha256: 7ce632d6e7be3048c39c408fd69970b929298fa8f5db11f08cd9e72dde4bef7d -->
