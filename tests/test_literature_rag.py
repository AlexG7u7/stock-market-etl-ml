"""Tests for literature RAG."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import save_npz
from sklearn.feature_extraction.text import TfidfVectorizer

from src.ml.literature_corpus import classify_relevance, ingest_inbox
from src.ml.literature_rag import (
    LiteratureRAG,
    RAG_DIR,
    CHUNKS_PATH,
    MATRIX_PATH,
    VECTORIZER_PATH,
    _chunk_text,
    build_index,
    query_literature,
)


def test_chunk_text_overlap():
    text = "word " * 500
    chunks = _chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_classify_finance_text():
    text = "Stock market prediction using LSTM and random forest for trading"
    rel, score = classify_relevance(text, "paper.pdf")
    assert rel in ("high", "partial")
    assert score >= 2


def test_rag_search_in_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("src.ml.literature_rag.RAG_DIR", tmp_path)
    monkeypatch.setattr("src.ml.literature_rag.CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr("src.ml.literature_rag.MATRIX_PATH", tmp_path / "matrix.npz")
    monkeypatch.setattr("src.ml.literature_rag.VECTORIZER_PATH", tmp_path / "vectorizer.joblib")
    monkeypatch.setattr("src.ml.literature_rag.MANIFEST_PATH", tmp_path / "manifest.json")

    chunks = [
        {
            "chunk_id": "a_0000",
            "paper_id": "ghosh2022",
            "file": "articles/test/a.pdf",
            "title": "LSTM intraday ranking",
            "relevance": "high",
            "page_start": 1,
            "text": "LSTM and random forests for intraday cross-sectional stock ranking",
        },
        {
            "chunk_id": "b_0000",
            "paper_id": "other",
            "file": "articles/test/b.pdf",
            "title": "Solar chimney optimization",
            "relevance": "none",
            "page_start": 1,
            "text": "Solar chimney performance in sustainable buildings",
        },
    ]
    texts = [c["text"] for c in chunks]
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(texts)

    chunks_path = tmp_path / "chunks.jsonl"
    matrix_path = tmp_path / "matrix.npz"
    vectorizer_path = tmp_path / "vectorizer.joblib"

    chunks_path.write_text("\n".join(json.dumps(c) for c in chunks) + "\n")
    save_npz(matrix_path, matrix)
    joblib.dump(vectorizer, vectorizer_path)

    rag = LiteratureRAG(chunks, matrix, vectorizer)
    hits = rag.search("LSTM intraday cross-sectional", top_k=3, relevance_only=True)
    assert hits
    assert hits[0].paper_id == "ghosh2022"


def test_query_literature_empty_when_not_built(monkeypatch, tmp_path):
    monkeypatch.setattr("src.ml.literature_rag.RAG_DIR", tmp_path)
    monkeypatch.setattr("src.ml.literature_rag.CHUNKS_PATH", tmp_path / "missing.jsonl")
    assert query_literature("test") == ""


def test_ingest_inbox_moves_pdf(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    papers = tmp_path / "papers"
    inbox.mkdir()
    papers.mkdir()
    pdf = inbox / "new_paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    monkeypatch.setattr("src.ml.literature_corpus.INBOX_DIR", inbox)
    monkeypatch.setattr("src.ml.literature_corpus.PAPERS_DIR", papers)

    moved = ingest_inbox()
    assert len(moved) == 1
    assert not pdf.exists()
    assert (papers / "new_paper.pdf").exists()
