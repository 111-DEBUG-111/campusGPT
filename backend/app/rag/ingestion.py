"""
PDF & Text File Ingestion Pipeline for CampusGPT.

Pipeline:
  1. Extract text per-page (PyMuPDF primary, pdfplumber fallback)
  2. Extract structured tables from PDF via pdfplumber (atomic blocks)
  3. Clean text
  4. SemanticChunker: structure-aware, sentence-boundary chunking
     → SectionNode hierarchy → sentence-packed chunks with metadata

All pages are passed together (not per-page) so cross-page sections
are preserved intact.
"""
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from app.config import get_settings
from app.rag.chunker import SemanticChunker, ChunkDict

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Text Extraction ──────────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str | Path) -> list[dict]:
    """
    Extract text per-page from a PDF.

    Returns:
        List of {"page_number": int, "text": str} dicts.
        Uses PyMuPDF as the primary extractor (fast, accurate for most PDFs).
        Falls back to pdfplumber for complex layouts and scanned documents.
    """
    file_path = Path(file_path)
    pages: list[dict] = []

    try:
        doc = fitz.open(str(file_path))
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page_number": page_num, "text": text})
        doc.close()

        if pages:
            logger.info(f"Extracted {len(pages)} pages via PyMuPDF from {file_path.name}")
            return pages

    except Exception as e:
        logger.warning(f"PyMuPDF failed ({e}), falling back to pdfplumber")

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append({"page_number": page_num, "text": text})

        logger.info(f"Extracted {len(pages)} pages via pdfplumber from {file_path.name}")

    except Exception as e:
        logger.error(f"Both PDF extractors failed for {file_path.name}: {e}")

    return pages


def extract_tables_from_pdf(file_path: str | Path) -> list[dict]:
    """
    Extract structured tables from a PDF via pdfplumber.

    Returns a list of {"page_number": int, "text": str} dicts where
    the text is a markdown-style pipe-table representation.  These
    are injected into the page text so the SemanticChunker can detect
    and preserve them as atomic chunks.
    """
    file_path = Path(file_path)
    table_pages: list[dict] = []

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or not table[0]:
                        continue
                    # Format as pipe-delimited markdown table
                    rows = []
                    for i, row in enumerate(table):
                        cells = [str(c or "").replace("\n", " ").strip() for c in row]
                        rows.append("| " + " | ".join(cells) + " |")
                        if i == 0:
                            # Insert separator after header row
                            rows.append("| " + " | ".join(["---"] * len(row)) + " |")
                    if len(rows) >= 3:  # header + separator + ≥1 data row
                        table_pages.append({
                            "page_number": page_num,
                            "text": "\n".join(rows),
                        })

    except Exception as e:
        logger.warning(f"Table extraction failed for {file_path.name}: {e}")

    return table_pages


# ─── Text Cleaning ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Normalise extracted PDF/text content.

    • Collapses 3+ consecutive newlines → 2 (preserves paragraph breaks)
    • Normalises horizontal whitespace (tabs → single space)
    • Removes form-feed / page-separator characters
    • Does NOT strip single newlines — they may carry structural meaning
      (e.g. list items, table rows)
    """
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.replace("\x0c", "\n")
    return text.strip()


# ─── Full Ingestion Pipeline ──────────────────────────────────────────────────

def _make_chunker() -> SemanticChunker:
    """
    Instantiate a SemanticChunker from current settings.

    Tuning guide (matches config.py comments):
      bge-m3  (8192 token ctx) → chunk_size=800, chunk_min_tokens=80
      bge-small (512 token ctx) → chunk_size=400, chunk_min_tokens=40
    """
    return SemanticChunker(
        chunk_size=settings.chunk_size,
        chunk_min_tokens=settings.chunk_min_tokens,
        sentence_overlap=1,
    )


def ingest_pdf(
    file_path: str | Path,
    document_id: int,
    filename: str,
    category: str,
    chunk_size: int | None = None,       # kept for API compat; use config instead
    chunk_overlap: int | None = None,    # legacy; ignored by SemanticChunker
    source_type: str = "official",       # "official" | "experience"
    author: str | None = None,           # populated for experience documents
) -> list[ChunkDict]:
    """
    Full PDF ingestion pipeline:
      extract → inject tables → clean → semantic chunk → return chunks.

    Args:
        file_path: Path to the uploaded PDF file.
        document_id: Postgres Document row ID.
        filename: Original display filename.
        category: Document category (academics, placements, …).
        chunk_size: Override settings.chunk_size (optional).
        chunk_overlap: Ignored — semantic chunker uses sentence overlap.

    Returns:
        List of ChunkDicts ready for embedding + Qdrant upsert.
    """
    file_path = Path(file_path)

    # 1. Extract text pages
    pages = extract_text_from_pdf(file_path)
    if not pages:
        logger.error(f"No text extracted from {filename}")
        return []

    # 2. Extract structured tables and inject as additional "pages"
    #    Injecting at the end ensures table content is visible to the chunker
    #    without disrupting the original page order used for section parsing.
    table_pages = extract_tables_from_pdf(file_path)
    if table_pages:
        logger.info(f"Injecting {len(table_pages)} table block(s) from {filename}")
        pages = pages + table_pages

    # 3. Clean each page's text
    cleaned_pages = [
        {"page_number": p["page_number"], "text": clean_text(p["text"])}
        for p in pages
        if p["text"].strip()
    ]

    if not cleaned_pages:
        logger.error(f"No usable text after cleaning for {filename}")
        return []

    # 4. Semantic chunking (whole document, not per-page)
    chunker = _make_chunker()
    if chunk_size:
        chunker.chunk_size = chunk_size

    chunks = chunker.chunk_document(
        pages=cleaned_pages,
        document_id=document_id,
        filename=filename,
        category=category,
    )

    # Propagate Knowledge Source metadata to every chunk
    for chunk in chunks:
        chunk["source_type"] = source_type
        chunk["author"] = author

    logger.info(
        f"Ingested {filename}: {len(pages)} pages → {len(chunks)} semantic chunks "
        f"(source_type={source_type})"
    )
    return chunks


def ingest_text_file(
    file_path: str | Path,
    document_id: int,
    filename: str,
    category: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    source_type: str = "official",       # "official" | "experience"
    author: str | None = None,           # populated for experience documents
) -> list[ChunkDict]:
    """
    Ingest a plain text (.txt) or Markdown (.md) file.

    Markdown headings (# / ## / ###) are detected by HeadingDetector inside
    SemanticChunker, so .md files get full hierarchy-aware chunking for free.
    """
    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Failed to read text file {filename}: {e}")
        return []

    cleaned = clean_text(raw)
    if not cleaned:
        logger.error(f"Empty text file: {filename}")
        return []

    # Treat the whole file as a single "page" (page_number=None)
    pages = [{"page_number": None, "text": cleaned}]

    chunker = _make_chunker()
    if chunk_size:
        chunker.chunk_size = chunk_size

    chunks = chunker.chunk_document(
        pages=pages,
        document_id=document_id,
        filename=filename,
        category=category,
    )

    # Propagate Knowledge Source metadata to every chunk
    for chunk in chunks:
        chunk["source_type"] = source_type
        chunk["author"] = author

    logger.info(
        f"Ingested text file {filename}: {len(chunks)} semantic chunks "
        f"(source_type={source_type})"
    )
    return chunks
