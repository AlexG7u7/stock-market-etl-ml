# Gold: indicadores de noticias

Archivos generados:

- `daily_features.parquet`: resultados por fecha UTC, emisora y tema.
- `latest.json`: resultado de la última invocación.

Incluyen sentimiento, volumen ponderado, cambio de sentimiento, dispersión, relevancia y sentimiento ESG, además del corte temporal, ventana y referencias a los artículos y capturas utilizados.

El cálculo excluye información conocida después del corte y evita contar varias veces un artículo por capturas repetidas.

Los datos se generan localmente y están excluidos de Git; este README hace visible la capa en el repositorio.

Ver [arquitectura completa](../../../docs/NEWS_MEDALLION.md).
