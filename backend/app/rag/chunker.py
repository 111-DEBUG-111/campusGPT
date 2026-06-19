"""
Semantic Chunking Engine for CampusGPT.

Architecture:
  Document pages → HeadingDetector (structural parse) → SectionNode tree
               → TableExtractor (atomic table blocks)
               → SemanticChunker (sentence-boundary packing)
               → list[ChunkDict]

Design goals:
  • Split on document structure, not word count
  • Sentence boundaries via nltk.sent_tokenize — no mid-sentence cuts
  • Tables preserved as atomic chunks (never split)
  • Section hierarchy (title, breadcrumb path) attached to every chunk
  • Token-budget based packing, configurable per embedding model:
      bge-m3 (8192 ctx)  → chunk_size=800, min=80
      bge-small (512 ctx) → chunk_size=400, min=40
  • 1-sentence look-back overlap at chunk boundaries for context continuity
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TypedDict

import nltk

logger = logging.getLogger(__name__)

# ─── Ensure NLTK punkt tokenizer is available ─────────────────────────────────
# punkt_tab is the newer resource name used by nltk >= 3.8; punkt is the legacy
# name. We attempt both so the module works across versions without crashing.
def _ensure_nltk_punkt() -> None:
    for resource in ("punkt_tab", "punkt"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
            return
        except LookupError:
            pass
    # Download once; subsequent calls hit cache
    try:
        nltk.download("punkt_tab", quiet=True)
    except Exception:
        nltk.download("punkt", quiet=True)


_ensure_nltk_punkt()


# ─── Token-count approximation ────────────────────────────────────────────────
# Avoids loading a full tokenizer at ingestion time.
# English academic text averages 1.25–1.35 tokens/word; we use 1.3.
_TOKENS_PER_WORD = 1.3


def approx_tokens(text: str) -> int:
    """Estimate BPE token count from whitespace-split word count."""
    return int(len(text.split()) * _TOKENS_PER_WORD)


# ─── Output schema ────────────────────────────────────────────────────────────

class ChunkDict(TypedDict, total=False):
    text: str
    document_id: int
    filename: str
    category: str
    page_number: int | None
    chunk_index: int
    # Semantic metadata (new fields)
    section_title: str | None      # immediate heading this chunk belongs to
    section_path: str | None       # "Introduction > 2.1 Methods > Results"
    chunk_type: str                # "text" | "table" | "heading_intro"
    heading_level: int | None      # 1 (H1) … 4 (H4); None for body text chunks


# ─── Heading Detection ────────────────────────────────────────────────────────

# Patterns ordered by specificity (most reliable first)
_HEADING_PATTERNS: list[tuple[int, re.Pattern]] = [
    # Markdown headings: ## Title
    (1, re.compile(r"^#{1}\s+(.+)$")),
    (2, re.compile(r"^#{2}\s+(.+)$")),
    (3, re.compile(r"^#{3}\s+(.+)$")),
    (4, re.compile(r"^#{4,}\s+(.+)$")),
    # Numbered section headings: 1. Title | 1.2 Title | 1.2.3 Title
    (1, re.compile(r"^(\d{1,2})\.\s{1,4}([A-Z].{2,60})$")),
    (2, re.compile(r"^(\d{1,2}\.\d{1,2})\s{1,4}([A-Z].{2,60})$")),
    (3, re.compile(r"^(\d{1,2}\.\d{1,2}\.\d{1,2})\s{1,4}([A-Z].{2,60})$")),
    # ALL CAPS short lines (≤ 8 words, ≥ 2 words)
    (2, re.compile(r"^([A-Z][A-Z\s\-:]{4,50})$")),
    # Title Case short lines with no period (≤ 7 words)
    (3, re.compile(r"^([A-Z][a-zA-Z\s\-:]{4,50})$")),
]

# Regex to detect if a line looks like a table row (pipe-delimited or
# dash-separated header)
_TABLE_ROW_RE = re.compile(r"(\|.+\|)|(-{3,}(\s*\|?\s*-{3,})+)")


@dataclass
class HeadingMatch:
    level: int       # 1 (highest) … 4 (lowest)
    title: str       # cleaned heading text
    line_index: int  # position in the page lines list


def detect_heading(line: str, line_index: int) -> HeadingMatch | None:
    """
    Try to classify a single line as a structural heading.

    Returns a HeadingMatch if the line is a heading, else None.
    Conservative: prefers false-negatives over false-positives to avoid
    splitting body paragraphs incorrectly.
    """
    stripped = line.strip()

    # Skip empty / very short / very long lines
    if not stripped or len(stripped) < 3 or len(stripped) > 120:
        return None

    # Skip lines that end in a sentence-terminating period (body text)
    # EXCEPT numbered section headings which can end with period
    if stripped.endswith(".") and not re.match(r"^\d+(\.\d+)*\.", stripped):
        return None

    # Skip lines that look like table rows
    if _TABLE_ROW_RE.search(stripped):
        return None

    word_count = len(stripped.split())

    for level, pattern in _HEADING_PATTERNS:
        m = pattern.match(stripped)
        if m:
            # For Title Case pattern (level 3), enforce word count ≤ 7 to avoid
            # accidentally catching the start of a body sentence
            if level == 3 and word_count > 7:
                continue
            # ALL CAPS pattern: must be ≥ 2 words and not look like an acronym
            if level == 2 and stripped == stripped.upper() and word_count < 2:
                continue
            title = m.group(len(m.groups())).strip() if m.lastindex else stripped
            return HeadingMatch(level=level, title=title, line_index=line_index)

    return None


# ─── Table Detection & Extraction ─────────────────────────────────────────────

def _is_table_line(line: str) -> bool:
    """True if a line looks like part of a markdown/grid table."""
    stripped = line.strip()
    if not stripped:
        return False
    # Pipe-delimited rows
    if stripped.startswith("|") and stripped.endswith("|"):
        return True
    # Separator rows: --- | --- | ---
    if re.match(r"^\|?[\s\-:]+(\|[\s\-:]+)+\|?$", stripped):
        return True
    return False


def extract_table_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """
    Identify contiguous table blocks in a list of text lines.

    Returns list of (start_idx, end_idx, table_text) tuples.
    A table block is 2+ consecutive table lines.
    """
    blocks: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        if _is_table_line(lines[i]):
            j = i
            while j < len(lines) and _is_table_line(lines[j]):
                j += 1
            if j - i >= 2:  # minimum 2 lines to be a real table
                table_text = "\n".join(lines[i:j]).strip()
                blocks.append((i, j - 1, table_text))
            i = j
        else:
            i += 1
    return blocks


# ─── Section Node (document parse tree) ───────────────────────────────────────

@dataclass
class SectionNode:
    """One logical section of a document."""
    level: int              # heading level; 0 = document root
    title: str              # section title (empty for root)
    lines: list[str] = field(default_factory=list)   # body text lines
    children: list["SectionNode"] = field(default_factory=list)
    page_start: int | None = None    # first page this section appears on

    @property
    def body_text(self) -> str:
        return "\n".join(self.lines).strip()


# ─── Semantic Chunker ─────────────────────────────────────────────────────────

class SemanticChunker:
    """
    Production-ready semantic chunker.

    Usage:
        chunker = SemanticChunker(chunk_size=800, chunk_min_tokens=80)
        chunks = chunker.chunk_document(
            pages=[{"page_number": 1, "text": "..."}],
            document_id=42,
            filename="handbook.pdf",
            category="academics",
        )
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_min_tokens: int = 80,
        sentence_overlap: int = 1,
    ) -> None:
        """
        Args:
            chunk_size: Target token budget per chunk.  Tables may exceed this
                        by up to 50% before being force-split.
            chunk_min_tokens: Discard chunks smaller than this (noise filter).
            sentence_overlap: Number of trailing sentences from previous chunk
                              to prepend to the next for context continuity.
        """
        self.chunk_size = chunk_size
        self.chunk_min_tokens = chunk_min_tokens
        self.sentence_overlap = sentence_overlap

    # ── Public API ────────────────────────────────────────────────────────────

    def chunk_document(
        self,
        pages: list[dict],      # [{"page_number": int, "text": str}]
        document_id: int,
        filename: str,
        category: str,
    ) -> list[ChunkDict]:
        """
        Main entry point.  Processes all pages as a unified document (not
        page-by-page) so sections that span page breaks are preserved.

        Returns a flat list of ChunkDicts ready for embedding + upsert.
        """
        if not pages:
            return []

        # 1. Merge all page text into annotated lines (track page number per line)
        annotated_lines = self._merge_pages(pages)

        # 2. Extract table blocks first (so they are never split by heading parser)
        table_regions = self._find_table_regions(annotated_lines)

        # 3. Parse structural hierarchy into SectionNode tree
        root = self._parse_sections(annotated_lines, table_regions)

        # 4. Walk tree → emit chunks
        all_chunks: list[ChunkDict] = []
        chunk_index = 0

        def _walk(node: SectionNode, ancestors: list[SectionNode]) -> None:
            nonlocal chunk_index
            breadcrumb = self._breadcrumb(ancestors + [node])

            # Emit table sub-blocks first (atomic)
            for tbl_text, tbl_page in self._extract_tables_from_node(node):
                tok = approx_tokens(tbl_text)
                if tok < self.chunk_min_tokens:
                    continue
                # Large tables: split at row boundaries
                table_chunks = self._split_table_if_needed(tbl_text)
                for tc in table_chunks:
                    if approx_tokens(tc) < self.chunk_min_tokens:
                        continue
                    all_chunks.append(ChunkDict(
                        text=self._prefix_section(tc, node, ancestors),
                        document_id=document_id,
                        filename=filename,
                        category=category,
                        page_number=tbl_page or node.page_start,
                        chunk_index=chunk_index,
                        section_title=node.title or None,
                        section_path=breadcrumb or None,
                        chunk_type="table",
                        heading_level=node.level if node.level > 0 else None,
                    ))
                    chunk_index += 1

            # Emit body text as sentence-packed chunks
            body = node.body_text
            if body:
                text_chunks = self._pack_sentences(body)
                for i, (chunk_text, overlap_prepend) in enumerate(text_chunks):
                    full_text = self._prefix_section(chunk_text, node, ancestors)
                    tok = approx_tokens(full_text)
                    if tok < self.chunk_min_tokens:
                        continue
                    chunk_type = "heading_intro" if (i == 0 and node.level > 0) else "text"
                    all_chunks.append(ChunkDict(
                        text=full_text,
                        document_id=document_id,
                        filename=filename,
                        category=category,
                        page_number=node.page_start,
                        chunk_index=chunk_index,
                        section_title=node.title or None,
                        section_path=breadcrumb or None,
                        chunk_type=chunk_type,
                        heading_level=node.level if node.level > 0 else None,
                    ))
                    chunk_index += 1

            # Recurse into children
            for child in node.children:
                _walk(child, ancestors + [node])

        _walk(root, [])

        logger.info(
            f"SemanticChunker: {filename} → {len(pages)} pages, "
            f"{len(all_chunks)} chunks "
            f"(target={self.chunk_size} tok, min={self.chunk_min_tokens} tok)"
        )
        return all_chunks

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _merge_pages(
        self, pages: list[dict]
    ) -> list[tuple[str, int]]:
        """
        Flatten pages into (line_text, page_number) tuples.
        Inserts a blank separator between pages to prevent cross-page merges.
        """
        annotated: list[tuple[str, int]] = []
        for page in pages:
            page_num = page["page_number"]
            for line in page["text"].splitlines():
                annotated.append((line, page_num))
            annotated.append(("", page_num))  # page boundary marker
        return annotated

    def _find_table_regions(
        self, annotated_lines: list[tuple[str, int]]
    ) -> set[int]:
        """
        Return the set of line indices that belong to table blocks.
        These lines are excluded from the section/body text parser.
        """
        lines = [l for l, _ in annotated_lines]
        regions: set[int] = set()
        for start, end, _ in extract_table_blocks(lines):
            for idx in range(start, end + 1):
                regions.add(idx)
        return regions

    def _parse_sections(
        self,
        annotated_lines: list[tuple[str, int]],
        table_regions: set[int],
    ) -> SectionNode:
        """
        Parse annotated lines into a SectionNode hierarchy.

        Strategy:
          • Maintain a stack of open sections at each heading level.
          • When a heading is found, close all lower-priority sections and
            open a new one.
          • Non-heading lines go into the body of the current open section.
        """
        root = SectionNode(level=0, title="", page_start=annotated_lines[0][1] if annotated_lines else None)
        # Stack: [root, ...open sections]
        stack: list[SectionNode] = [root]

        for idx, (line, page_num) in enumerate(annotated_lines):
            # Skip lines that are inside table blocks (handled separately)
            if idx in table_regions:
                stack[-1].lines.append(line)
                continue

            heading = detect_heading(line, idx)
            if heading:
                new_node = SectionNode(
                    level=heading.level,
                    title=heading.title,
                    page_start=page_num,
                )
                # Pop stack until we find a parent with lower level number
                while len(stack) > 1 and stack[-1].level >= heading.level:
                    stack.pop()
                stack[-1].children.append(new_node)
                stack.append(new_node)
            else:
                # Body text → belongs to current open section
                if stack[-1].page_start is None and line.strip():
                    stack[-1].page_start = page_num
                stack[-1].lines.append(line)

        return root

    def _extract_tables_from_node(
        self, node: SectionNode
    ) -> list[tuple[str, int | None]]:
        """
        Extract table blocks from a node's lines.
        Returns [(table_text, page_number), ...].
        The table lines are removed from node.lines in-place.
        """
        if not node.lines:
            return []

        table_blocks = extract_table_blocks(node.lines)
        if not table_blocks:
            return []

        results: list[tuple[str, int | None]] = []
        lines_to_remove: set[int] = set()

        for start, end, table_text in table_blocks:
            results.append((table_text, node.page_start))
            for i in range(start, end + 1):
                lines_to_remove.add(i)

        # Remove table lines from node body (keep non-table lines)
        node.lines = [
            line for idx, line in enumerate(node.lines)
            if idx not in lines_to_remove
        ]
        return results

    def _split_table_if_needed(self, table_text: str) -> list[str]:
        """
        Split an oversized table at row boundaries.
        Tables up to chunk_size * 1.5 tokens are kept whole.
        Larger tables are split at row boundaries, keeping the header
        row attached to each sub-table.
        """
        max_tokens = int(self.chunk_size * 1.5)
        if approx_tokens(table_text) <= max_tokens:
            return [table_text]

        rows = table_text.splitlines()
        # Detect header: first 1-2 rows (row + separator)
        header_rows: list[str] = []
        body_rows: list[str] = []
        for i, row in enumerate(rows):
            if i <= 1 and re.match(r"^\|?[\s\-:]+(\|[\s\-:]+)+\|?$", row):
                header_rows = rows[: i + 1]
                body_rows = rows[i + 1:]
                break
        if not header_rows:
            header_rows = rows[:1]
            body_rows = rows[1:]

        chunks: list[str] = []
        current: list[str] = list(header_rows)
        for row in body_rows:
            test = "\n".join(current + [row])
            if approx_tokens(test) > max_tokens and len(current) > len(header_rows):
                chunks.append("\n".join(current))
                current = list(header_rows) + [row]
            else:
                current.append(row)
        if current:
            chunks.append("\n".join(current))
        return chunks

    def _pack_sentences(self, text: str) -> list[tuple[str, bool]]:
        """
        Tokenize `text` into sentences and greedily pack them into
        token-budgeted chunks.

        Returns list of (chunk_text, had_overlap_prepend) tuples.
        • chunk_text: the packed sentences as a single string
        • had_overlap_prepend: True if sentence(s) from the previous chunk
          were prepended for context continuity
        """
        try:
            sentences = nltk.sent_tokenize(text)
        except Exception:
            # Graceful degradation: split on double-newline if nltk fails
            sentences = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not sentences:
            return []

        results: list[tuple[str, bool]] = []
        current_sents: list[str] = []
        current_tokens = 0
        overlap_buffer: list[str] = []   # trailing sentences from last chunk

        for sent in sentences:
            sent_tok = approx_tokens(sent)

            # Single sentence already exceeds budget — emit as its own chunk
            if sent_tok >= self.chunk_size:
                if current_sents:
                    results.append((" ".join(current_sents), bool(overlap_buffer and results)))
                    overlap_buffer = current_sents[-self.sentence_overlap:]
                    current_sents = []
                    current_tokens = 0
                results.append((sent, False))
                overlap_buffer = [sent][-self.sentence_overlap:]
                continue

            # Would exceed budget → flush current chunk, start new with overlap
            if current_tokens + sent_tok > self.chunk_size and current_sents:
                results.append((" ".join(current_sents), bool(overlap_buffer and results)))
                overlap_buffer = current_sents[-self.sentence_overlap:]
                # Start new chunk with overlap sentences
                current_sents = list(overlap_buffer)
                current_tokens = sum(approx_tokens(s) for s in current_sents)

            current_sents.append(sent)
            current_tokens += sent_tok

        # Flush last chunk
        if current_sents:
            results.append((" ".join(current_sents), bool(overlap_buffer and results)))

        return results

    def _breadcrumb(self, nodes: list[SectionNode]) -> str:
        """Build 'Title A > Title B > Title C' from a list of nodes."""
        titles = [n.title for n in nodes if n.title and n.level > 0]
        return " > ".join(titles)

    def _prefix_section(
        self,
        chunk_text: str,
        node: SectionNode,
        ancestors: list[SectionNode],
    ) -> str:
        """
        Optionally prefix chunk with its section heading for better
        embedding alignment.  Only prepended when the chunk text does
        not already start with the heading title.
        """
        if not node.title or node.level == 0:
            return chunk_text
        prefix = node.title + "\n"
        if chunk_text.startswith(node.title):
            return chunk_text
        return prefix + chunk_text
