# Arquitectura medallion de noticias

El proyecto mantiene un lago local en `data/news/bronze`, `silver` y `gold`. Su implementación está en `src/data/news_medallion.py`. Los JSON, CSV y Parquet anteriores se conservan para los consumidores existentes. Este cambio no ejecuta cargas en PostgreSQL ni altera las tablas `lab`.

## Estructura física

```text
data/news/
├── bronze/
│   ├── databursatil/YYYY-MM-DD/<batch_id>.json
│   ├── trump/YYYY-MM-DD/<batch_id>.json
│   ├── google_news/YYYY-MM-DD/<batch_id>.json
│   ├── gdelt/YYYY-MM-DD/<batch_id>.json
│   ├── <otra_fuente>/YYYY-MM-DD/<batch_id>.json
│   └── _imports/<hash>.json
├── silver/
│   └── articles.parquet
├── gold/
│   ├── daily_features.parquet
│   └── latest.json
├── history/                       # Datos anteriores, conservados
├── noticias_trump.csv              # Exportación compatible de la ingesta Trump
└── latest.json                     # Indicadores del flujo anterior
```

Los JSON, CSV y Parquet de las tres capas, el CSV temático de Trump y los registros de importación se versionan en Git. El bloqueo de escritura permanece excluido. No se incluyen credenciales en los sobres de captura. La fecha de partición bronce es la fecha UTC de captura, no la fecha de publicación.

## Bronce: capturas inmutables

Cada ingesta escribe un archivo nuevo con identificador aleatorio. Repetir una descarga conserva ambas capturas, incluso si son iguales. No se sobrescribe una captura anterior.

| Campo del sobre | Contenido |
|---|---|
| `schema_version` | Versión del sobre: `1`. |
| `batch_id` | Identificador único de captura. |
| `source` | Fuente o conector. |
| `fetched_at` | Fecha y hora UTC de captura o de importación. |
| `representation` | Naturaleza del contenido preservado. |
| `origin` | Ruta de un archivo anterior, si es una importación; de otro modo null. |
| `payload` | Datos capturados. |

Las representaciones distinguen `api_payload` (snapshot de noticias/cables de DataBursátil), `rss_extract` (campos seleccionados del RSS Trump), `normalized_extract` (salida de los conectores existentes, antes de deduplicar en `news.py`) y `legacy_import` (archivo anterior). **No todas las capturas son respuestas HTTP completas**: los conectores existentes ya seleccionan campos. Bronce conserva exactamente el contenido recibido en esta frontera, sin presentarlo como XML o JSON HTTP original cuando no lo es.

## Silver: observaciones normalizadas

`silver/articles.parquet` contiene una fila por artículo, asociación y captura. Conserva observaciones repetidas entre capturas para auditar qué datos se conocían en cada momento. Dentro de la misma captura elimina duplicados exactos de la clave `(article_id, ticker, topic, batch_id)`.

| Columna | Tipo lógico | Significado |
|---|---|---|
| `article_id` | texto | SHA-256 de fuente y URL; sin URL, usa el titular normalizado. |
| `batch_id` | texto | Captura de origen. |
| `bronze_path` | texto | Ruta relativa al JSON bronce. |
| `source` | texto | Fuente del artículo. |
| `ticker` | texto | Emisora asociada; vacío si no existe asociación. |
| `topic` | texto | Tema, como `trump` o `market`; puede estar vacío. |
| `title` | texto | Titular sin espacios exteriores. |
| `text` | texto | Extracto disponible o titular. |
| `text_kind` | texto | `headline` o `excerpt`; no implica cuerpo completo. |
| `url` | texto | Enlace disponible, incluido el enlace intermediario de Google News. |
| `published_at` | timestamp UTC nullable | Publicación, si está disponible y es interpretable. |
| `fetched_at` | timestamp UTC | Momento de observación o importación. |
| `available_at` | timestamp UTC | Máximo entre publicación y captura; sin publicación, usa captura. |
| `sentiment` | decimal | Valor recibido del conector, si existe; de otro modo cero. |
| `relevance_score` | decimal | Relevancia recibida; por defecto uno. |

Las filas sin titular se descartan. Una misma noticia puede tener asociaciones con varias emisoras. La coincidencia por URL no intenta resolver redirecciones ni identificar que dos medios describen el mismo evento.

### DataBursátil

Los snapshots completos se vinculan a emisoras mediante coincidencias de alias con límites de palabra. Las noticias sin coincidencias se conservan con tema `market`. Esta asociación es léxica; no demuestra exposición económica.

`published_at` se mantiene nulo para DataBursátil, incluso si su conector anterior había sintetizado una hora. No se presenta la captura como una publicación real.

### Trump

`scripts/ingesta_trump.py` conserva la exportación CSV y añade capturas bronce y filas silver. La correspondencia es `titulo → title`, `fecha → published_at`, `texto → text`; la fuente es `trump` y el tema `trump`. Como el CSV usa el titular como texto, `text_kind` queda en `headline`.

Las noticias temáticas no se asignan automáticamente a emisoras. Sus indicadores gold se calculan para `ticker=""`, `topic="trump"`.

## Gold: indicadores con evidencia

`gold/daily_features.parquet` conserva resultados diarios con clave lógica `(date, ticker, topic)`. Cada cálculo reemplaza las filas de su fecha UTC y conserva las de otras fechas. `gold/latest.json` contiene el resultado de la última invocación, aunque se haya solicitado un corte histórico.

Antes de calcular, se excluyen observaciones con `available_at` posterior al corte y se toma la última observación disponible de cada artículo/asociación. Se consideran hasta dos ventanas para comparar sentimiento reciente y anterior. Así, las capturas repetidas no multiplican el número de noticias.

| Campo | Significado |
|---|---|
| `date`, `as_of` | Fecha UTC de la fila y corte exacto utilizado. |
| `ticker`, `topic` | Asociación empresarial o temática. |
| `window_days` | Tamaño de la ventana reciente; siete por defecto. |
| `scoring_method` | `keywords`: sentimiento ES/EN reproducible, sin llamadas a Gemini. |
| `article_ids`, `batch_ids` | Listas JSON de identificadores de los artículos y observaciones empleados, incluidas ambas ventanas. |
| `publication_date_missing` | Cantidad de artículos considerados sin publicación conocida. |
| `sources` | Fuentes de los artículos de la ventana reciente. |
| `n_articles` | Número de artículos de la ventana reciente. |
| `news_sent_score` | Sentimiento reciente ponderado. |
| `news_count_7d` | Logaritmo `log(1 + suma de pesos)`; no es el conteo bruto. El nombre se conserva aunque `window_days` sea distinto de siete. |
| `news_sent_delta` | Sentimiento reciente menos sentimiento de la ventana previa. |
| `news_sent_vol` | Desviación ponderada del sentimiento. |
| `news_relevance_avg` | Relevancia media ponderada. |
| `news_esg_score` | Sentimiento de titulares identificados como ESG. |

Cuando falta publicación, la ventana usa el momento de captura y se registra la ausencia. No se reconstruyen fechas de publicación inexistentes. Los grupos sin observaciones en ambas ventanas no generan filas; un resultado vacío no implica que la descarga haya sido exitosa ni que todo el mercado sea neutral.

Gold se reconstruye desde silver y aplica el cálculo común de `news.py` con ponderación temporal y de similitud. Puede diferir del JSON anterior cuando este utiliza Gemini, sentimiento de Alpha Vantage o una cobertura distinta. No reemplaza silenciosamente el histórico anterior de backtesting.

## Integración y ejecución

Se conectaron los siguientes puntos:

- `news.py`: conserva los artículos de todas las fuentes antes de su deduplicación local. Al guardar un lote con caché, también construye gold.
- `scripts/fetch_news.py`: al guardar resultados, construye gold desde silver.
- `databursatil_news.save_daily_snapshot`: conserva el snapshot en bronce y normaliza silver. El script `databursatil_news_snapshot.py` también construye gold.
- `news_history.py`: conserva los nuevos resultados de consultas históricas GDELT. `build_news_history.py` construye gold al terminar, con corte actual; no inventa disponibilidad histórica.
- `scripts/ingesta_trump.py`: conserva la extracción temática, normaliza silver y construye gold cuando hay noticias.

Desde la raíz del proyecto:

```bash
# Importar datos locales anteriores y construir gold, sin descargar noticias.
venv/bin/python scripts/build_news_medallion.py --migrate

# Reconstruir silver desde bronce y recalcular gold.
venv/bin/python scripts/build_news_medallion.py --replay

# Consultar un corte reproducible con una ventana explícita.
venv/bin/python scripts/build_news_medallion.py --as-of 2026-10-29T23:59:59Z --days 7

# Ingestas habituales: generan las nuevas capas y las salidas anteriores.
venv/bin/python scripts/fetch_news.py --universe bmv
venv/bin/python scripts/databursatil_news_snapshot.py
venv/bin/python scripts/ingesta_trump.py
```

`--replay` vuelve a materializar cada captura mediante un upsert por lote. Permite recuperar silver después de perder su Parquet. No elimina observaciones de lotes que hayan sido borrados manualmente de bronce.

### Migración conservadora

`--migrate` importa snapshots fechados de DataBursátil, `history/articles.parquet` y el CSV Trump si existe. Usa un registro de hashes para no duplicar importaciones iguales. Conserva los archivos originales. Si cambia un archivo, crea una nueva captura.

Los snapshots con `fetched_at` conservan ese momento. Cuando un archivo anterior no registra su fecha de captura, se utiliza la fecha de importación, sin afirmar que el sistema ya lo conocía en su fecha de publicación. Por ello un corte antiguo puede no tener resultados para artículos importados después.

Los indicadores agregados anteriores no se convierten en artículos ni se mezclan automáticamente con gold: no permiten reconstruir su evidencia. Si los artículos disponibles son antiguos, gold reciente puede estar vacío hasta ejecutar nuevas ingestas.

## Consistencia y alcance

Silver y gold usan escritura temporal y reemplazo atómico; un bloqueo local serializa sus modificaciones concurrentes. Bronce es la evidencia persistida y permite repetir la normalización tras una interrupción. No hay transacción única entre capas.

Esta versión usa Parquet local completo: cada actualización de silver lee y escribe su conjunto. Es adecuada para el volumen actual; volúmenes mayores requerirán particiones y un catálogo o motor transaccional. No incorpora un servidor MCP, una programación de tareas ni cambios en las tablas SQL.
