"""
RAG de literatura científica — búsqueda semántica (TF-IDF) sobre PDFs indexados.

Uso agentes:
    from src.ml.literature_rag import LiteratureRAG

    rag = LiteratureRAG.load()
    hits = rag.search("LSTM intraday cross-sectional ranking", top_k=5)
    context = rag.format_for_prompt(hits)
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.sparse import load_npz, save_npz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.ml.literature_corpus import (
    PROJECT_ROOT,
    discover_pdfs,
    extract_pdf_text,
    file_sha256,
    scan_pdf_entry,
)

RAG_DIR = PROJECT_ROOT / "articles" / "knowledge" / "rag"
CHUNKS_PATH = RAG_DIR / "chunks.jsonl"
MANIFEST_PATH = RAG_DIR / "manifest.json"
VECTORIZER_PATH = RAG_DIR / "vectorizer.joblib"
MATRIX_PATH = RAG_DIR / "matrix.npz"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
MIN_RELEVANCE = {"high", "partial"}


@dataclass
class ChunkHit:
    chunk_id: str
    paper_id: str
    title: str
    file: str
    page_start: int
    text: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _chunk_text(text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        piece = cleaned[start:end].strip()
        if len(piece) > 80:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _page_offsets(pdf_path: Path) -> list[tuple[int, int, int]]:
    """(page_num, char_start, char_end) por página."""
    try:
        import pypdf
    except ImportError:
        return []

    reader = pypdf.PdfReader(str(pdf_path))
    offsets: list[tuple[int, int, int]] = []
    pos = 0
    for i, page in enumerate(reader.pages, start=1):
        txt = page.extract_text() or ""
        start = pos
        pos += len(txt) + 1
        offsets.append((i, start, pos))
    return offsets


def _page_for_char(offsets: list[tuple[int, int, int]], char_idx: int) -> int:
    for page, start, end in offsets:
        if start <= char_idx < end:
            return page
    return offsets[-1][0] if offsets else 1


class LiteratureRAG:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        matrix: Any,
        vectorizer: TfidfVectorizer,
    ) -> None:
        self.chunks = chunks
        self.matrix = matrix
        self.vectorizer = vectorizer

    @classmethod
    def load(cls) -> LiteratureRAG:
        if not CHUNKS_PATH.exists() or not MATRIX_PATH.exists():
            raise FileNotFoundError(
                "Índice RAG no encontrado — ejecuta: python scripts/build_literature_rag.py"
            )
        chunks = [
            json.loads(line)
            for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        matrix = load_npz(MATRIX_PATH)
        if not VECTORIZER_PATH.exists():
            raise FileNotFoundError("vectorizer.joblib no encontrado — reindexa el RAG")
        vectorizer = joblib.load(VECTORIZER_PATH)
        return cls(chunks, matrix, vectorizer)

    @classmethod
    def is_built(cls) -> bool:
        return CHUNKS_PATH.exists() and MATRIX_PATH.exists()

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.08,
        relevance_only: bool = True,
    ) -> list[ChunkHit]:
        if not query.strip() or not self.chunks:
            return []

        q_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self.matrix).flatten()

        ranked = np.argsort(scores)[::-1]
        hits: list[ChunkHit] = []
        for idx in ranked:
            if len(hits) >= top_k:
                break
            score = float(scores[idx])
            if score < min_score:
                break
            ch = self.chunks[idx]
            if relevance_only and ch.get("relevance") not in MIN_RELEVANCE:
                continue
            hits.append(
                ChunkHit(
                    chunk_id=ch["chunk_id"],
                    paper_id=ch["paper_id"],
                    title=ch.get("title", ""),
                    file=ch.get("file", ""),
                    page_start=int(ch.get("page_start", 1)),
                    text=ch["text"],
                    score=round(score, 4),
                )
            )
        return hits

    def format_for_prompt(self, hits: list[ChunkHit], *, max_chars: int = 4000) -> str:
        if not hits:
            return ""
        lines = ["LITERATURE RAG (citar paper_id en evidencia):"]
        used = 0
        for h in hits:
            block = (
                f"\n[{h.paper_id}] {h.title} (p.{h.page_start}, score={h.score})\n"
                f"{h.text[:600]}"
            )
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n".join(lines)


def build_index(*, force: bool = False) -> dict[str, Any]:
    """
    Indexa todos los PDFs descubiertos. Incremental por sha256 en manifest.
    """
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    if MANIFEST_PATH.exists() and not force:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    existing_chunks: list[dict] = []
    if CHUNKS_PATH.exists() and not force:
        existing_chunks = [
            json.loads(line)
            for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    chunks_by_file: dict[str, list[dict]] = {}
    for ch in existing_chunks:
        chunks_by_file.setdefault(ch["file"], []).append(ch)

    pdfs = discover_pdfs()
    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "missing": 0}

    for pdf in pdfs:
        rel = str(pdf.relative_to(PROJECT_ROOT))
        if not pdf.exists():
            stats["missing"] += 1
            continue

        digest = file_sha256(pdf)
        if not force and manifest.get(rel) == digest and rel in chunks_by_file:
            stats["skipped"] += 1
            continue

        try:
            meta = scan_pdf_entry(pdf)
        except Exception:
            stats["missing"] += 1
            continue

        if meta.get("relevance") not in MIN_RELEVANCE:
            manifest[rel] = digest
            chunks_by_file[rel] = []
            stats["skipped"] += 1
            continue

        full_text = extract_pdf_text(pdf)
        offsets = _page_offsets(pdf)
        text_chunks = _chunk_text(full_text)
        file_chunks: list[dict] = []

        for i, txt in enumerate(text_chunks):
            char_pos = full_text.find(txt[:80]) if len(txt) >= 80 else 0
            page = _page_for_char(offsets, max(char_pos, 0))
            file_chunks.append({
                "chunk_id": f"{meta['id']}_{i:04d}",
                "paper_id": meta["id"],
                "file": rel,
                "title": meta.get("title", ""),
                "year": meta.get("year"),
                "doi": meta.get("doi"),
                "relevance": meta.get("relevance"),
                "page_start": page,
                "text": txt,
            })

        chunks_by_file[rel] = file_chunks
        manifest[rel] = digest
        stats["indexed"] += 1
        stats["chunks"] += len(file_chunks)

    all_chunks: list[dict] = []
    for pdf in pdfs:
        rel = str(pdf.relative_to(PROJECT_ROOT))
        all_chunks.extend(chunks_by_file.get(rel, []))

    if not all_chunks:
        CHUNKS_PATH.write_text("", encoding="utf-8")
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {**stats, "total_chunks": 0}

    texts = [c["text"] for c in all_chunks]
    vectorizer = TfidfVectorizer(
        max_features=8000,
        ngram_range=(1, 2),
        stop_words="english",
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(texts)

    CHUNKS_PATH.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in all_chunks) + "\n",
        encoding="utf-8",
    )
    save_npz(MATRIX_PATH, matrix)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {**stats, "total_chunks": len(all_chunks), "papers": len(manifest)}


def query_literature(query: str, *, top_k: int = 5) -> str:
    """Atajo para agentes — retorna texto listo para prompt o vacío si no hay índice."""
    if not LiteratureRAG.is_built():
        return ""
    try:
        rag = LiteratureRAG.load()
        hits = rag.search(query, top_k=top_k)
        return rag.format_for_prompt(hits)
    except Exception:
        return ""
