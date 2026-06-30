# Base de Conocimiento — Predicción BMV / Quantitative Finance

Repositorio estructurado de literatura científica (Scopus / ScienceDirect) para guiar el modelado de señales en el proyecto **stock-market**. El objetivo es traducir la vanguardia (SOTA) en decisiones concretas sobre arquitectura, features, validación y despliegue.

## Problema que modelamos

Predicción direccional y ranking cross-seccional de tickers BMV (5 universos, ~87 símbolos) con horizonte 5d, modulado por régimen de mercado, sentimiento de noticias y gestión de riesgo (Kelly, ATR, correlación).

**Stack actual** (ver `src/ml/super_model.py`):

| Capa | Componente | Estado |
|------|-----------|--------|
| L1 | Ensemble WoE+LR+LGBM, xs_lgbm, heurístico técnico | Producción |
| L2 | Fusión por edge histórico (AUC−0.5) | Producción |
| L3 | HMM régimen + sentimiento Gemini | Producción |
| L4 | Gemini validator (narrativa, no decisión) | Producción |
| — | LSTM + GA (framework legacy) | Parcial |
| — | Ising market (econofísica) | Experimental |
| — | DRL / FinRL | No implementado |

## Estructura

```
articles/
├── inbox/                     # ← DROP ZONE: PDFs nuevos aquí
├── papers/                    # archivo permanente post-inbox
├── scopus/
├── web-of-science/
└── knowledge/
    ├── rag/                   # índice TF-IDF (chunks.jsonl + matrix.npz)
    ├── README.md
    ├── corpus.yaml            # Índice maestro (ambas fuentes)
    ├── stack_mapping.yaml
    ├── research_roadmap.yaml
    ├── taxonomy.yaml
    ├── agent/                 # ← Playbook operativo para agente de apuestas
    │   ├── decision_protocol.yaml
    │   ├── bmv_market_rules.yaml
    │   ├── calibration.yaml
    │   ├── risk_limits.yaml
    │   ├── literature_rules.yaml
    │   └── failure_modes.yaml
    └── papers/                # Fichas académicas
```

## Uso

### 0. RAG — búsqueda sobre PDFs para agentes

```bash
# Drop PDF en articles/inbox/ y luego:
python scripts/build_literature_rag.py

# Vigilar inbox automáticamente:
python scripts/build_literature_rag.py --watch
```

### 1. Reconstruir el corpus desde PDFs

```bash
python scripts/build_knowledge_base.py
```

Escanea `articles/scopus/`, extrae metadatos (título, DOI, abstract) y actualiza `corpus.yaml`.

### 2. Consultar gap analysis

```bash
python scripts/build_knowledge_base.py --gaps
```

Muestra qué técnicas SOTA faltan en nuestro stack y su prioridad.

### 3. Añadir un paper nuevo

1. Colocar el PDF en `articles/inbox/` (o directamente en `scopus/`)
2. Ejecutar `python scripts/build_literature_rag.py`
3. Crear ficha en `papers/<id>.yaml` si es relevante (plantilla `_template.yaml`)

## Artículos clave (relevantes al proyecto)

| ID | Título | Relevancia | Tema |
|----|--------|------------|------|
| `ghosh2022_intraday_lstm_rf` | LSTM+RF intraday, ranking cross-seccional S&P500 | ★★★★★ | **Más cercano a nuestro pipeline** |
| `kumbure2022_ml_data_review` | ML + taxonomía de 2173 variables (138 papers) | ★★★★★ | Datos & features |
| `sahu2023_qf_survey` | ML/DL/RL en Quantitative Finance (survey 70+ papers) | ★★★★★ | Panorama general |
| `ashtiani2023_news_slr` | SLR noticias + ML para mercados (61 estudios) | ★★★★★ | Pipeline noticias |
| `leone2025_roberta_nhits` | RoBERTa + N-HiTS + ESG sentiment → DJIA | ★★★★★ | Noticias SOTA 2025 |
| `quadir2023_mls_lstm` | MLS-LSTM multi-capa para forecasting | ★★★★☆ | LSTM integración |
| `zhao2023_sa_dlstm` | SA-DLSTM: ECNN + DAE + LSTM + sentiment | ★★★★☆ | Híbrido sentiment |
| `mukherjee2021_cnn_ann` | CNN/ANN sobre histogramas NIFTY | ★★★☆☆ | Input visual |
| `dudukcu2023_tcn_rnn` | TCN+RNN series caóticas (sin benchmark finanzas) | ★★☆☆☆ | Arquitectura |

## Fuentes de datos recomendadas (literatura)

- **Yahoo Finance** — ya usamos vía `yfinance` / `store`
- Noticias / sentimiento — ya usamos RSS + Gemini (`src/ml/news.py`)
- Tick data intraday — futuro (`src/ml/intraday_features.py` existe como base)
- Fundamentales — gap identificado en roadmap

## Próximos pasos sugeridos (de la literatura)

Ver `research_roadmap.yaml` para la lista priorizada. Resumen ejecutivo:

1. **Híbrido LSTM + ensemble tabular** (MLS-LSTM + LGBM fusion)
2. **Purged CV / walk-forward** estricto (ya tenemos `purged_cv.py` — formalizar en pipeline)
3. **Multi-modal**: OHLCV + noticias + macro (parcialmente implementado)
4. **DRL para sizing/execution** (largo plazo; FinRL como referencia)
5. **Auto-ML** para hiperparámetros (extender GA existente)
