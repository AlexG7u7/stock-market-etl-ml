#!/usr/bin/env python3
"""
Construye el índice RAG de literatura científica.

Flujo automático:
  1. PDFs en articles/inbox/ → se mueven a articles/papers/
  2. Actualiza corpus.yaml (metadatos)
  3. Indexa chunks TF-IDF en articles/knowledge/rag/

Uso:
    python scripts/build_literature_rag.py              # build incremental
    python scripts/build_literature_rag.py --force      # reindexar todo
    python scripts/build_literature_rag.py --query "LSTM intraday ranking"
    python scripts/build_literature_rag.py --watch      # vigila inbox/ cada 60s
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ml.literature_corpus import INBOX_DIR, ingest_inbox  # noqa: E402
from src.ml.literature_rag import LiteratureRAG, build_index, query_literature  # noqa: E402


def _update_corpus() -> None:
    from scripts.build_knowledge_base import update_corpus
    update_corpus(dry_run=False)


def _run_build(*, force: bool) -> dict:
    moved = ingest_inbox()
    if moved:
        print(f"✓ Inbox → papers: {len(moved)} PDF(s)")
        for p in moved:
            print(f"    {p.name}")

    print("Actualizando corpus.yaml...")
    _update_corpus()

    print("Indexando RAG...")
    stats = build_index(force=force)
    print(json.dumps(stats, indent=2))
    return stats


def _run_query(q: str, top_k: int) -> None:
    if not LiteratureRAG.is_built():
        print("Índice no existe — ejecuta build primero")
        sys.exit(1)
    rag = LiteratureRAG.load()
    hits = rag.search(q, top_k=top_k)
    if not hits:
        print("Sin resultados")
        return
    print(rag.format_for_prompt(hits, max_chars=8000))


def _watch(interval: int) -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Vigilando {INBOX_DIR} cada {interval}s (Ctrl+C para salir)")
    seen: set[str] = set()
    while True:
        pdfs = {p.name for p in INBOX_DIR.glob("*.pdf")}
        new = pdfs - seen
        if new:
            print(f"\n→ Nuevos PDFs: {', '.join(sorted(new))}")
            _run_build(force=False)
        seen = pdfs
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG de literatura — inbox → index")
    parser.add_argument("--force", action="store_true", help="Reindexar todos los PDFs")
    parser.add_argument("--query", "-q", help="Probar búsqueda")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--watch", action="store_true", help="Vigilar articles/inbox/")
    parser.add_argument("--watch-interval", type=int, default=60)
    args = parser.parse_args()

    if args.watch:
        _watch(args.watch_interval)
        return

    if args.query:
        if not LiteratureRAG.is_built():
            _run_build(force=False)
        _run_query(args.query, args.top_k)
        return

    _run_build(force=args.force)


if __name__ == "__main__":
    main()
