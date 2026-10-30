# Silver: artículos normalizados

Archivo generado: `articles.parquet`.

Cada fila representa un artículo asociado a una emisora o tema en una captura. Incluye identificadores, titular, texto disponible, URL, fuente, fechas UTC y referencia al archivo bronce.

Se eliminan duplicados dentro de cada captura y se conservan observaciones de capturas diferentes para auditoría. Las noticias de Trump se clasifican con tema `trump`, sin asignarlas automáticamente a emisoras.

Los datos se generan localmente y se versionan en Git junto con este README.

Ver [arquitectura completa](../../../docs/NEWS_MEDALLION.md).
