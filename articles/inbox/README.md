# Drop zone — agrega PDFs aquí

Coloca cualquier PDF nuevo en esta carpeta. El pipeline RAG lo detecta automáticamente.

## Opción A — una vez

```bash
python scripts/build_literature_rag.py
```

1. Mueve PDFs de `inbox/` → `articles/papers/`
2. Actualiza `knowledge/corpus.yaml`
3. Indexa chunks en `knowledge/rag/` para búsqueda por agentes

## Opción B — vigilancia continua

```bash
python scripts/build_literature_rag.py --watch
```

Cada 60 segundos revisa si hay PDFs nuevos y los indexa.

## Probar búsqueda

```bash
python scripts/build_literature_rag.py --query "LSTM intraday cross-sectional"
```

## Uso en agentes (Python)

```python
from src.ml.literature_rag import query_literature

context = query_literature("news sentiment transformers stock prediction", top_k=5)
```

Los agentes Gemini ya consumen contexto RAG vía `get_knowledge_prompt(literature_query=...)`.
