# Golden Diario de Noticias Segmentadas (`lab.news_feature_daily`)

## 1. Propósito

El producto **Golden diario de noticias segmentadas** (`lab.news_feature_daily`) almacena en la base de datos `mercado` (esquema `lab` de PostgreSQL 16) las características cuantitativas (*features*) agregadas del flujo noticioso para todos los universos de inversión disponibles en GBM (BMV, USA SIC, ETFs, Cripto proxies y FIBRAs).

Este dataset sintetiza el análisis de procesamiento de lenguaje natural (NLP), deduplicación léxica y descuento temporal sobre noticias financieras, proporcionando una fotografía estandarizada y normalizada de cada activo por día de operación bursátil.

---

## 2. Grano y Llave

- **Grano:** Exactamente **una fila por ticker × fecha hábil** (`ticker × trade_date`).
- **Llave Primaria:** `PRIMARY KEY (ticker, trade_date)`.
- **Estrategia de Carga:** Inserción y actualización idempotente (*UPSERT*) mediante:
  ```sql
  ON CONFLICT (ticker, trade_date) DO UPDATE
  ```
  Ejecutar el pipeline de ingesta múltiples veces para una misma fecha actualiza los registros existentes sin duplicar filas ni corromper series de tiempo.

---

## 3. Diccionario de Columnas

| Columna | Tipo SQL | Descripción y Reglas de Negocio |
| :--- | :--- | :--- |
| `ticker` | `text NOT NULL` | Símbolo identificador del activo en el universo (ej. `"WALMEX"`, `"AAPL"`, `"SPY"`). |
| `trade_date` | `date NOT NULL` | Fecha de la sesión de mercado correspondiente a la ventana de noticias. |
| `universe` | `text` | Slug del universo al que pertenece el activo (`"bmv"`, `"usa"`, `"etfs"`, `"cripto"`, `"fibras"`). |
| `news_sent_score` | `double precision` | Puntuación agregada de sentimiento ponderado en escala $[-1.0, +1.0]$. Descuenta artículos repetidos y noticias antiguas. |
| `news_count_7d` | `double precision` | Volumen mediático efectivo en la ventana móvil de 7 días, comprimido logarítmicamente: $\ln(1 + \sum w_i)$. Evita distorsiones por coberturas sindicadas masivas. |
| `news_sent_delta` | `double precision` | Cambio del sentimiento respecto a la ventana de 7 días previa ($\text{sent}_{t} - \text{sent}_{t-7d}$). Detecta giros o quiebres repentinos de narrativa. |
| `news_sent_vol` | `double precision` | Desviación estándar ponderada del sentimiento de los artículos recientes. Mide incertidumbre o desacuerdo entre medios de prensa. |
| `news_relevance_avg` | `double precision` | Puntuación media ponderada de relevancia léxica de los titulares frente a los alias corporativos de la empresa $[0.0, 1.0]$. |
| `news_esg_score` | `double precision` | Puntuación de sentimiento restringida a artículos con temática ambiental, social o de gobernanza corporativa (ASG / ESG). |
| `n_articles` | `integer` | Conteo entero bruto de artículos recopilados dentro de la ventana de 7 días. |
| `sources` | `text` | Lista de proveedores que aportaron artículos en la ventana, separada por comas (ej. `"expansion,google_news"`). |
| `loaded_at` | `timestamptz NOT NULL` | Marca de tiempo UTC de inserción o última actualización (`DEFAULT now()`). |

---

## 4. Diferencia entre `lab.news_daily` y `lab.news_feature_daily`

El esquema `lab` mantiene una separación rigurosa entre datos no estructurados en crudo y métricas analíticas agregadas:

| Criterio | `lab.news_daily` | `lab.news_feature_daily` |
| :--- | :--- | :--- |
| **Grano** | **1 fila por artículo individual** | **1 fila por ticker × trade_date** |
| **Llave** | `id serial PRIMARY KEY` | `PRIMARY KEY (ticker, trade_date)` |
| **Contenido** | Titular (`title`), URL, fuente y sentimiento de cada noticia en crudo. | Las 6 features cuantitativas (`NEWS_FEATURE_COLS`), volumen comprimido y metadatos agregados. |
| **Cardinalidad** | 0 a $N$ artículos por ticker y día. | Máximo 1 registro por ticker en cada fecha. |
| **Comportamiento** | Inserción acumulativa de notas de prensa. | *UPSERT* idempotente. |
| **Objetivo** | Trazabilidad documental y lectura directa de titulares. | Alimentación cuantitativa de modelos de Machine Learning y semáforos de agentes. |

---

## 5. Consumidores del Golden

1. **Capa Semántica y Agentes de Consulta (`ver_noticias`):**
   Permite al agente consultar de forma instantánea el sentimiento numérico, volumen y alertas de un activo sin necesidad de recalcular scraping o procesar texto en tiempo de ejecución.
2. **Modelos Cuantitativos y SuperModel:**
   Inyección directa de `NEWS_FEATURE_COLS` en el ensamble de Machine Learning (LightGBM, WoE y Regresión Logística) para generar señales multi-horizonte.
3. **Agentes de Validación y Riesgo (`Gemini Validator`):**
   Detección de condiciones de veto (ej. regla `LR-003: noticias contradicen momentum técnico` cuando `news_sent_score < -0.25` o `news_alerta = True`).
