# Bronce: capturas de noticias

Aquí se guardan las capturas inmutables de las ingestas. Cada descarga crea un JSON nuevo:

```text
<fuente>/YYYY-MM-DD/<batch_id>.json
```

Fuentes: DataBursátil, Trump, Google News, GDELT y los demás conectores. Cada captura incluye fuente, fecha UTC, identificador de lote, representación y contenido. Dependiendo del conector, el contenido es la respuesta de la API o una extracción de campos, no necesariamente la respuesta HTTP completa.

Los datos se generan localmente y están excluidos de Git; este README hace visible la capa en el repositorio.

Ver [arquitectura completa](../../../docs/NEWS_MEDALLION.md).
