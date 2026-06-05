"""
PDF Ingestion + Chunking Pipeline for CampusGPT.

Parsing strategy:
  1. PyMuPDF for fast text extraction + page numbers
  2. pdfplumber as fallback for complex layouts / tables
  3. Sentence-aware chunking with configurable size + overlap
"""
import logging
import re
from pathlib import Path
from typing import Generator
import fitz  # PyMuPDF
import pdfplumber
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Text Extraction ──────────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str | Path) -> list[dict]:
    """
    Extract text per page from a PDF.

    Returns:
        List of {"page_number": int, "text": str} dicts.
    """
    file_path = Path(file_path)
    pages = []

    try:
        # Primary: PyMuPDF (fast, good for most PDFs)
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
        # Fallback: pdfplumber (better for tables/columns)
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()
                if text:
                    pages.append({"page_number": page_num, "text": text})

        logger.info(f"Extracted {len(pages)} pages via pdfplumber from {file_path.name}")

    except Exception as e:
        logger.error(f"Both PDF extractors failed for {file_path.name}: {e}")

    return pages


# ─── Text Cleaning ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Basic text cleaning for PDFs."""
    # Collapse multiple whitespace/newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    # Remove form feed characters
    text = text.replace('\x0c', '\n')
    return text.strip()


# ─── Chunking ─────────────────────────────────────────────────────────────────

def word_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> Generator[str, None, None]:
    """
    Word-count based chunking with overlap.
    Respects paragraph boundaries where possible.
    """
    # Split into paragraphs first
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    words_buffer: list[str] = []

    for paragraph in paragraphs:
        para_words = paragraph.split()

        # If single paragraph already exceeds chunk size, sub-chunk it
        if len(para_words) > chunk_size:
            for i in range(0, len(para_words), chunk_size - chunk_overlap):
                sub = para_words[i:i + chunk_size]
                yield " ".join(sub)
            continue

        # Accumulate paragraphs until we hit chunk size
        words_buffer.extend(para_words)
        words_buffer.append('')  # Paragraph separator

        while len(words_buffer) >= chunk_size:
            chunk_words = words_buffer[:chunk_size]
            yield " ".join(w for w in chunk_words if w)
            # Slide window with overlap
            words_buffer = words_buffer[chunk_size - chunk_overlap:]

    # Flush remainder
    if words_buffer:
        remaining = " ".join(w for w in words_buffer if w)
        if len(remaining.split()) >= 20:  # Minimum chunk size
            yield remaining


# ─── Full Ingestion Pipeline ──────────────────────────────────────────────────

def ingest_pdf(
    file_path: str | Path,
    document_id: int,
    filename: str,
    category: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """
    Full ingestion pipeline: extract → clean → chunk → prepare for embedding.

    Returns:
        List of chunk dicts ready for embedding + upsert:
        {
            "text": str,
            "document_id": int,
            "filename": str,
            "category": str,
            "page_number": int | None,
            "chunk_index": int,
        }
    """
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    pages = extract_text_from_pdf(file_path)

    if not pages:
        logger.error(f"No text extracted from {filename}")
        return []

    all_chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        cleaned = clean_text(page["text"])
        for chunk_text in word_chunks(cleaned, chunk_size, chunk_overlap):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            all_chunks.append({
                "text": chunk_text,
                "document_id": document_id,
                "filename": filename,
                "category": category,
                "page_number": page["page_number"],
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    logger.info(f"Ingested {filename}: {len(pages)} pages → {len(all_chunks)} chunks")
    return all_chunks


def ingest_text_file(
    file_path: str | Path,
    document_id: int,
    filename: str,
    category: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """Ingest a plain text or markdown file."""
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    try:
        text = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read text file {filename}: {e}")
        return []

    cleaned = clean_text(text)
    all_chunks = []
    chunk_index = 0

    for chunk_text in word_chunks(cleaned, chunk_size, chunk_overlap):
        chunk_text = chunk_text.strip()
        if chunk_text:
            all_chunks.append({
                "text": chunk_text,
                "document_id": document_id,
                "filename": filename,
                "category": category,
                "page_number": None,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    return all_chunks
