# Climate Toolkit

[English](README.md) · [Français](README.fr.md)

Climate Toolkit permite analizar el clima de un sitio agrícola a partir de sus coordenadas. Puede descargar series diarias, comparar períodos y estaciones meteorológicas y evaluar riesgos para los cultivos y el ganado.

[Escriba a Pete para suscribirse](mailto:p.steward@cgiar.org?subject=Subscribe%20to%20Climate%20Toolkit%20release%20updates) y recibir un correo con cada versión estable sobre los cambios que puedan afectar a su código o sus resultados. Para darse de baja, responda «unsubscribe».

```bash
pip install climate-toolkit
```

Para obtener precipitaciones de CHIRPS v3 y temperaturas diarias de CHIRTS-ERA5 sin credenciales de Google, use Python 3.12 o posterior e instale las dependencias opcionales con `pip install "climate-toolkit[cloud]"`.

[Primeros pasos](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/es/getting_started/) · [Documentación](https://CGIAR-Climate-Data-Hub.github.io/climate-toolkit/es/) · [Probar en Colab](https://colab.research.google.com/github/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/examples/climate_toolkit_colab.ipynb)

Para visualizar los valores de estación y de malla por mes y por estación del año, añada `--diagnostics-html ARCHIVO` al comando de comparación de estaciones.

<!-- source-sha256: 286af8674047232596371906773e1ca5b9bfb5b4dd8e6fb0c9b3e59ec767ac96 -->
