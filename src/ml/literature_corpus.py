"""
Corpus de literatura — extracción de PDFs y metadatos.

Carpetas escaneadas (en orden):
  articles/inbox/       → drop zone (se mueve a papers/ al indexar)
  articles/papers/      → archivo permanente
  articles/scopus/
  articles/web-of-science/
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

ARTICLE_DIRS: tuple[Path, ...] = (
    PROJECT_ROOT / "articles" / "papers",
    PROJECT_ROOT / "articles" / "scopus",
    PROJECT_ROOT / "articles" / "web-of-science",
)
INBOX_DIR = PROJECT_ROOT / "articles" / "inbox"
PAPERS_DIR = PROJECT_ROOT / "articles" / "papers"

FINANCE_KW = re.compile(
    r"stock|market|financ|trading|lstm|quantitative|portfolio|forecast|"
    r"algorithmic|reinforcement learning|ohlcv|price prediction|bmv|equity",
    re.I,
)
IRRELEVANT_KW = re.compile(
    r"cancer|parkinson|solar chimney|organoid|drug discover|gliobla|"
    r"spatial information|infrastructure optimization|electrocardiogram|arrhythmia|"
    r"lorenz|rossler|chaotic time series prediction",
    re.I,
)
FINANCE_PARTIAL_KW = re.compile(
    r"stock market|financial market|quantitative|portfolio|trading|ohlcv|equity",
    re.I,
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def extract_pdf_text(pdf_path: Path, *, max_pages: int | None = None) -> str:
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError("pypdf no instalado — pip install pypdf") from exc

    reader = pypdf.PdfReader(str(pdf_path))
    pages = reader.pages if max_pages is None else reader.pages[:max_pages]
    chunks: list[str] = []
    for page in pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def pdf_page_count(pdf_path: Path) -> int | None:
    try:
        import pypdf
        return len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        return None


def extract_doi(text: str) -> str | None:
    m = re.search(r"doi\.org/([\d./a-zA-Z-]+)", text, re.I)
    if m:
        return m.group(1).rstrip(".")
    m = re.search(r"doi:\s*([\d./a-zA-Z-]+)", text, re.I)
    return m.group(1).rstrip(".") if m else None


def extract_year(text: str) -> int | None:
    m = re.search(r"(?:Received|Published|Accepted).*?(\d{4})", text, re.I | re.DOTALL)
    if m:
        y = int(m.group(1))
        if 1990 <= y <= 2030:
            return y
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else None


def guess_title(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines[:30]:
        if len(ln) > 20 and not re.match(
            r"^(Contents|Applied|Citation|Article|Review|Abstract)", ln, re.I
        ):
            if not re.match(r"^[A-Z]{2,}\s+\d", ln):
                return ln[:200]
    return lines[0][:200] if lines else "Unknown"


def classify_relevance(text: str, filename: str) -> tuple[str, int]:
    combined = f"{filename} {text}"
    if IRRELEVANT_KW.search(combined) and not FINANCE_PARTIAL_KW.search(combined):
        return "none", 0
    if FINANCE_KW.search(combined):
        hits = len(FINANCE_KW.findall(combined))
        if hits >= 5:
            return "high", min(5, 3 + hits // 10)
        return "partial", 2
    if FINANCE_PARTIAL_KW.search(combined):
        return "partial", 2
    return "none", 0


def file_id(pdf_path: Path) -> str:
    stem = pdf_path.stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem)[:40].strip("_")
    h = hashlib.md5(pdf_path.name.encode()).hexdigest()[:6]
    return f"{stem}_{h}" if stem else h


def source_label(pdf_path: Path) -> str:
    parts = pdf_path.relative_to(PROJECT_ROOT).parts
    return parts[1] if len(parts) > 1 else "unknown"


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\- ]+", "_", base)
    return base.replace(" ", "_")


def ingest_inbox(*, dry_run: bool = False) -> list[Path]:
    """
    Mueve PDFs de articles/inbox/ → articles/papers/.
    Retorna lista de PDFs movidos (paths destino).
    """
    if not INBOX_DIR.exists():
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        return []

    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []

    for pdf in sorted(INBOX_DIR.glob("*.pdf")):
        dest = PAPERS_DIR / _sanitize_filename(pdf.name)
        if dest.exists() and file_sha256(dest) == file_sha256(pdf):
            if not dry_run:
                pdf.unlink()
            moved.append(dest)
            continue
        if dest.exists():
            dest = PAPERS_DIR / f"{dest.stem}_{file_sha256(pdf)[:8]}{dest.suffix}"
        if not dry_run:
            pdf.rename(dest)
        moved.append(dest)

    return moved


def discover_pdfs(*, include_inbox: bool = False) -> list[Path]:
    """Lista PDFs únicos en carpetas de artículos."""
    pdfs: list[Path] = []
    dirs = list(ARTICLE_DIRS)
    if include_inbox and INBOX_DIR.exists():
        dirs = [INBOX_DIR, *dirs]

    for src_dir in dirs:
        if src_dir.exists():
            pdfs.extend(src_dir.rglob("*.pdf"))

    pdfs = [p for p in pdfs if "ScienceDirect_articles_" not in str(p)]

    seen_sizes: dict[int, Path] = {}
    unique: list[Path] = []
    for p in sorted(set(pdfs)):
        size = p.stat().st_size
        if size in seen_sizes:
            continue
        seen_sizes[size] = p
        unique.append(p)
    return unique


def scan_pdf_entry(pdf: Path) -> dict:
    rel = pdf.relative_to(PROJECT_ROOT)
    preview = extract_pdf_text(pdf, max_pages=3)
    relevance, score = classify_relevance(preview, pdf.name)
    return {
        "id": file_id(pdf),
        "file": str(rel),
        "source": source_label(pdf),
        "title": guess_title(preview),
        "year": extract_year(preview),
        "doi": extract_doi(preview),
        "relevance": relevance,
        "relevance_score": score,
        "pages": pdf_page_count(pdf),
        "sha256": file_sha256(pdf),
        "auto_scanned": str(date.today()),
    }
