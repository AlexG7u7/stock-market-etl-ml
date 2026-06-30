#!/usr/bin/env python3
"""
Construye y mantiene la base de conocimiento desde PDFs en articles/scopus/ y articles/web-of-science/.

Uso:
    python scripts/build_knowledge_base.py              # escanea PDFs, actualiza corpus
    python scripts/build_knowledge_base.py --list       # lista corpus curado por relevancia
    python scripts/build_knowledge_base.py --gaps       # muestra gap analysis
    python scripts/build_knowledge_base.py --roadmap    # muestra roadmap priorizado
    python scripts/build_knowledge_base.py --extract ID # extrae texto de un paper por id
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ml.literature_corpus import (  # noqa: E402
    ARTICLE_DIRS,
    classify_relevance,
    discover_pdfs,
    extract_doi,
    extract_pdf_text,
    extract_year,
    file_id,
    guess_title,
    pdf_page_count,
    source_label,
)

KNOWLEDGE_DIR = ROOT / "articles" / "knowledge"
CORPUS_PATH = KNOWLEDGE_DIR / "corpus.yaml"
STACK_PATH = KNOWLEDGE_DIR / "stack_mapping.yaml"
ROADMAP_PATH = KNOWLEDGE_DIR / "research_roadmap.yaml"

# Keywords para clasificación automática de relevancia (en literature_corpus.py)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _pdf_text_first_pages(pdf_path: Path, max_pages: int = 3) -> str:
    return extract_pdf_text(pdf_path, max_pages=max_pages)


def scan_pdfs() -> list[dict]:
    """Escanea todas las carpetas de artículos."""
    entries = []
    for pdf in discover_pdfs():
        rel = pdf.relative_to(ROOT)
        text = _pdf_text_first_pages(pdf)
        relevance, score = classify_relevance(text, pdf.name)
        entry = {
            "id": file_id(pdf),
            "file": str(rel),
            "source": source_label(pdf),
            "title": guess_title(text),
            "year": extract_year(text),
            "doi": extract_doi(text),
            "relevance": relevance,
            "relevance_score": score,
            "pages": pdf_page_count(pdf),
            "auto_scanned": str(date.today()),
        }
        entries.append(entry)
    return entries


def update_corpus(dry_run: bool = False) -> None:
    """Fusiona scan automático con corpus existente (preserva fichas manuales)."""
    existing = _load_yaml(CORPUS_PATH)
    manual_by_file = {p.get("file"): p for p in existing.get("papers", []) if p.get("ficha")}
    manual_by_doi = {p.get("doi"): p for p in existing.get("papers", []) if p.get("ficha") and p.get("doi")}
    scanned = scan_pdfs()

    merged: list[dict] = []
    seen_files: set[str] = set()
    for s in scanned:
        seen_files.add(s["file"])
        if s["file"] in manual_by_file:
            merged.append(manual_by_file[s["file"]])
        elif s.get("doi") and s["doi"] in manual_by_doi:
            merged.append(manual_by_doi[s["doi"]])
        else:
            merged.append(s)

    # Preservar entradas manuales cuyo PDF fue deduplicado en el scan
    for p in existing.get("papers", []):
        if p.get("ficha") and p.get("file") not in seen_files:
            merged.append(p)

    relevant = sum(1 for p in merged if p.get("relevance") == "high")
    partial = sum(1 for p in merged if p.get("relevance") == "partial")

    corpus = {
        "meta": {
            "source_dirs": [str(d.relative_to(ROOT)) for d in ARTICLE_DIRS if d.exists()],
            "last_updated": str(date.today()),
            "total_pdfs": len(merged),
            "relevant": relevant,
            "partial": partial,
            "not_relevant": len(merged) - relevant - partial,
            "curated_fichas": sum(1 for p in merged if p.get("ficha")),
            "note": "Entradas con ficha= son curadas manualmente; resto auto-escaneadas",
        },
        "papers": merged,
        "watchlist": existing.get("watchlist", []),
    }

    if dry_run:
        print(json.dumps(corpus["meta"], indent=2))
        for p in merged:
            flag = "★" if p.get("relevance") == "high" else "○" if p.get("relevance") == "partial" else "·"
            print(f"  {flag} [{p.get('relevance', '?'):>7}] {p.get('title', '')[:70]}")
    else:
        _save_yaml(CORPUS_PATH, corpus)
        print(f"✓ corpus.yaml actualizado — {len(merged)} PDFs ({relevant} relevantes, {partial} parciales)")


def show_list() -> None:
    corpus = _load_yaml(CORPUS_PATH)
    papers = corpus.get("papers", [])
    meta = corpus.get("meta", {})
    print(f"\n═══ CORPUS — {meta.get('total_pdfs', len(papers))} PDFs "
          f"({meta.get('curated_fichas', 0)} fichas) ═══\n")
    for tier, label in [("high", "RELEVANTES ★"), ("partial", "PARCIALES ○"), ("none", "RUIDO ·")]:
        group = [p for p in papers if p.get("relevance") == tier]
        if not group:
            continue
        print(f"── {label} ({len(group)}) ──")
        for p in sorted(group, key=lambda x: -(x.get("relevance_score") or 0)):
            ficha = "📄" if p.get("ficha") else "  "
            src = p.get("source", "?")[:8]
            print(f"  {ficha} [{src:>8}] {p.get('id', '?')[:35]:35} | {p.get('title', '')[:55]}")
        print()


def show_gaps() -> None:
    data = _load_yaml(STACK_PATH)
    if not data:
        print("stack_mapping.yaml no encontrado")
        return
    print("\n═══ GAP ANALYSIS — Literatura vs Stack BMV ═══\n")
    print(f"Cobertura general: {data.get('overall_coverage', {}).get('coverage_pct', '?')}%\n")

    matrix = data.get("coverage_matrix", {})
    for name, info in sorted(matrix.items(), key=lambda x: x[1].get("score", 0)):
        score = info.get("score", 0)
        bar = "█" * score + "░" * (3 - score)
        mod = info.get("module") or "—"
        print(f"  [{bar}] {score}/3  {name}")
        print(f"         {info.get('notes', '')[:80]}")
        print(f"         → {mod}\n")

    print("Gaps críticos:")
    for g in data.get("critical_gaps_vs_sota", []):
        print(f"  #{g.get('rank')} [{g.get('effort')} effort] {g.get('gap')} → {g.get('ticket')}")


def show_roadmap() -> None:
    data = _load_yaml(ROADMAP_PATH)
    if not data:
        print("research_roadmap.yaml no encontrado")
        return
    print("\n═══ RESEARCH ROADMAP ═══\n")
    for phase in data.get("phases", []):
        print(f"▸ {phase.get('name')} ({phase.get('timeline')})")
        for item in phase.get("items", []):
            print(f"    [{item.get('ticket')}] {item.get('title')}")
        print()


def extract_paper(paper_id: str) -> None:
    corpus = _load_yaml(CORPUS_PATH)
    papers = corpus.get("papers", [])
    match = next((p for p in papers if p.get("id", "").startswith(paper_id) or paper_id in p.get("file", "")), None)
    if not match:
        print(f"Paper '{paper_id}' no encontrado en corpus")
        sys.exit(1)
    pdf = ROOT / match["file"]
    text = _pdf_text_first_pages(pdf, max_pages=5)
    print(f"\n{'='*60}\n{match.get('title')}\n{'='*60}\n")
    print(text[:8000])


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge base builder — Scopus → BMV modeling")
    parser.add_argument("--gaps", action="store_true", help="Mostrar gap analysis")
    parser.add_argument("--roadmap", action="store_true", help="Mostrar roadmap")
    parser.add_argument("--extract", metavar="ID", help="Extraer texto de un paper")
    parser.add_argument("--list", action="store_true", help="Listar corpus por relevancia")
    parser.add_argument("--dry-run", action="store_true", help="Scan sin escribir corpus")
    args = parser.parse_args()

    if args.gaps:
        show_gaps()
    elif args.roadmap:
        show_roadmap()
    elif args.list:
        show_list()
    elif args.extract:
        extract_paper(args.extract)
    else:
        update_corpus(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
