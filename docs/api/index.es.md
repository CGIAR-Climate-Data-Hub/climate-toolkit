# Descripción general de la API de Python

Importe el paquete para usar estas funciones públicas.

```python
import climate_toolkit as ct
```

| Nombre en Python | Guía |
|---|---|
| `ct.fetch_climate_data` | [Descargar datos](fetching.md) |
| `ct.analyze_climate_statistics` | [Analizar datos](analysis.md) |
| `ct.evaluate_hazards` | [Analizar datos](analysis.md) |
| `ct.compare_climate_periods` | [Analizar datos](analysis.md) |
| `ct.compare_climate_sources` | [Comparar y validar](comparison.md) |
| `ct.download_station_data` | [Comparar y validar](comparison.md) |
| `ct.compare_station_to_grids` | [Comparar y validar](comparison.md) |
| `ct.backend_policy` | [Elegir el método de acceso a los datos](../direct_cloud_access.md) |
| `ct.run_pipeline` | [Ejecutar el flujo de trabajo](../use-as-a-package.md#one-call-for-the-whole-workflow-run_pipeline) |

Los nombres de las funciones, los argumentos y las claves de los resultados son iguales en todos los idiomas. La ayuda de Python, los mensajes de la línea de comandos y la referencia generada a partir de las cadenas de documentación están en inglés. Para consultar los parámetros de una función, ejecute, por ejemplo, `help(ct.evaluate_hazards)`.

<!-- source-sha256: d862b8c76470dcad3da01c12450ef9275590f3d60983b2fd44ab440c14ee3272 -->
