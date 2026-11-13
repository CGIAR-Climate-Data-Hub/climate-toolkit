# Climate Toolkit

[English](README.md) · [Français](README.fr.md)

Climate Toolkit permite analizar el clima de un sitio agrícola a partir de sus coordenadas. Puede descargar series diarias, comparar períodos y estaciones meteorológicas y evaluar riesgos para los cultivos y el ganado.

```bash
pip install climate-toolkit
```

Para obtener precipitaciones de CHIRPS v3 y temperaturas diarias de CHIRTS-ERA5 sin credenciales de Google, use Python 3.12 o posterior e instale las dependencias opcionales con `pip install "climate-toolkit[cloud]"`.

[Primeros pasos](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/es/getting_started/) · [Documentación](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/es/) · [Probar en Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)

Para visualizar los valores de estación y de malla por mes y por estación del año, añada `--diagnostics-html ARCHIVO` al comando de comparación de estaciones.

<!-- source-sha256: fd62b4c5b8a29dba6217c349918620c3b89a6e8937e988a9e084ac06fca747a8 -->
