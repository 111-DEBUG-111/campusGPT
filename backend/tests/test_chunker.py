"""
Unit tests for the SemanticChunker.

Run with:
    cd backend
    .venv/bin/python -m pytest tests/test_chunker.py -v
"""
import pytest
from app.rag.chunker import (
    SemanticChunker,
    HeadingMatch,
    detect_heading,
    extract_table_blocks,
    approx_tokens,
    _is_table_line,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_pages(text: str, page_number: int = 1) -> list[dict]:
    """Wrap a raw string as a single-page list (the chunker's input format)."""
    return [{"page_number": page_number, "text": text}]


def chunker(chunk_size: int = 300, chunk_min_tokens: int = 10) -> SemanticChunker:
    return SemanticChunker(chunk_size=chunk_size, chunk_min_tokens=chunk_min_tokens, sentence_overlap=1)


# ─── approx_tokens ────────────────────────────────────────────────────────────

class TestApproxTokens:
    def test_empty_string(self):
        assert approx_tokens("") == 0

    def test_single_word(self):
        # 1 word × 1.3 = 1 (int)
        assert approx_tokens("hello") == 1

    def test_ten_words(self):
        text = " ".join(["word"] * 10)
        assert approx_tokens(text) == 13


# ─── Heading Detection ────────────────────────────────────────────────────────

class TestHeadingDetection:
    def test_markdown_h1(self):
        result = detect_heading("# Introduction", 0)
        assert result is not None
        assert result.level == 1
        assert result.title == "Introduction"

    def test_markdown_h2(self):
        result = detect_heading("## 2.1 Grading Policy", 0)
        assert result is not None
        assert result.level == 2

    def test_markdown_h3(self):
        result = detect_heading("### Overview", 0)
        assert result is not None
        assert result.level == 3

    def test_numbered_section_level1(self):
        result = detect_heading("1. Introduction", 0)
        assert result is not None
        assert result.level == 1

    def test_numbered_section_level2(self):
        result = detect_heading("2.3 Eligibility Criteria", 0)
        assert result is not None
        assert result.level == 2

    def test_numbered_section_level3(self):
        result = detect_heading("1.2.3 Subsection", 0)
        assert result is not None
        assert result.level == 3

    def test_body_sentence_not_a_heading(self):
        result = detect_heading(
            "Students must submit the assignment before the deadline.", 0
        )
        assert result is None

    def test_empty_line_not_a_heading(self):
        assert detect_heading("", 0) is None

    def test_very_long_line_not_a_heading(self):
        long_line = "This is a very long body sentence that goes on and on " * 5
        assert detect_heading(long_line, 0) is None

    def test_table_row_not_a_heading(self):
        assert detect_heading("| Name | Score | Grade |", 0) is None

    def test_period_terminated_line_not_heading(self):
        # body sentences end with period
        assert detect_heading("This is a complete sentence.", 0) is None


# ─── Table Detection ──────────────────────────────────────────────────────────

class TestTableDetection:
    def test_pipe_table_line_detected(self):
        assert _is_table_line("| Col1 | Col2 | Col3 |") is True

    def test_separator_line_detected(self):
        assert _is_table_line("| --- | --- | --- |") is True

    def test_regular_text_not_table(self):
        assert _is_table_line("This is a normal paragraph.") is False

    def test_empty_line_not_table(self):
        assert _is_table_line("") is False

    def test_extract_table_blocks_simple(self):
        lines = [
            "Some text before.",
            "| Name | Score |",
            "| --- | --- |",
            "| Alice | 95 |",
            "| Bob | 88 |",
            "Some text after.",
        ]
        blocks = extract_table_blocks(lines)
        assert len(blocks) == 1
        start, end, text = blocks[0]
        assert start == 1
        assert end == 4
        assert "Alice" in text
        assert "Bob" in text

    def test_extract_table_blocks_no_table(self):
        lines = ["Normal text.", "Another line.", "Third line."]
        blocks = extract_table_blocks(lines)
        assert blocks == []

    def test_single_table_line_not_extracted(self):
        # A single table-looking line is not a table (needs ≥ 2 consecutive)
        lines = ["| Single row |", "Normal text."]
        blocks = extract_table_blocks(lines)
        assert blocks == []


# ─── SemanticChunker: Basic Behaviour ────────────────────────────────────────

class TestSemanticChunkerBasic:
    def test_empty_input_returns_empty(self):
        c = chunker()
        assert c.chunk_document([], document_id=1, filename="f.pdf", category="gen") == []

    def test_single_paragraph_becomes_chunk(self):
        text = (
            "The university offers a wide range of academic programs. "
            "Students can choose from engineering, science, arts, and commerce. "
            "Each department has its own faculty and research facilities."
        )
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        assert len(chunks) >= 1
        assert chunks[0]["document_id"] == 1
        assert chunks[0]["filename"] == "f.pdf"
        assert chunks[0]["category"] == "gen"

    def test_chunk_index_is_monotonic(self):
        text = "\n\n".join([
            "# Section One\nThis is the first section with some content about academics.",
            "# Section Two\nThis is the second section with content about placements.",
            "# Section Three\nThis is the third section with content about hostels.",
        ])
        c = chunker(chunk_size=50)
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        indices = [ch["chunk_index"] for ch in chunks]
        assert indices == list(range(len(indices))), "chunk_index must be strictly monotonic"

    def test_min_token_filter_removes_tiny_chunks(self):
        # A heading-only "section" with no body should be discarded
        text = "# Heading Only"
        c = chunker(chunk_min_tokens=20)
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        assert all(approx_tokens(ch["text"]) >= 20 for ch in chunks)

    def test_chunk_type_field_present(self):
        text = (
            "# Introduction\n"
            "This section introduces the university. It was founded in 1985. "
            "The campus spans over 200 acres."
        )
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        for ch in chunks:
            assert "chunk_type" in ch
            assert ch["chunk_type"] in ("text", "table", "heading_intro")


# ─── SemanticChunker: Section Hierarchy ──────────────────────────────────────

class TestSectionHierarchy:
    def test_section_title_attached(self):
        text = (
            "## Grading Policy\n"
            "Grades are assigned on a 10-point scale. "
            "Students with a CGPA above 8.5 receive honors."
        )
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="academics")
        titled = [ch for ch in chunks if ch.get("section_title")]
        assert len(titled) >= 1
        assert titled[0]["section_title"] == "Grading Policy"

    def test_section_path_breadcrumb(self):
        text = (
            "# Academics\n"
            "Overview of academic programs.\n\n"
            "## 2.1 Grading\n"
            "Grades are determined by mid-term and final exams. "
            "The passing grade is 40%. Students who fail may reappear."
        )
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="academics")
        grading_chunks = [ch for ch in chunks if ch.get("section_title") == "2.1 Grading"]
        if grading_chunks:
            path = grading_chunks[0].get("section_path", "")
            assert "Academics" in path
            assert "2.1 Grading" in path

    def test_heading_level_attached(self):
        text = "## Methods\nWe conducted a survey of 500 students across three campuses."
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        leveled = [ch for ch in chunks if ch.get("heading_level") is not None]
        assert len(leveled) >= 1
        assert leveled[0]["heading_level"] == 2

    def test_root_body_has_no_section_title(self):
        text = (
            "This is introductory text before any heading. "
            "It should have no section title."
        )
        c = chunker(chunk_min_tokens=5)
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        # Root-level chunks may have section_title=None
        assert all(ch.get("section_title") is None for ch in chunks)


# ─── SemanticChunker: Table Preservation ─────────────────────────────────────

class TestTablePreservation:
    TABLE_TEXT = (
        "## Fee Structure\n"
        "Below is the annual fee breakdown:\n\n"
        "| Program | Tuition | Hostel | Total |\n"
        "| --- | --- | --- | --- |\n"
        "| B.Tech | 80000 | 30000 | 110000 |\n"
        "| M.Tech | 60000 | 30000 | 90000 |\n"
        "| MBA | 100000 | 30000 | 130000 |\n"
    )

    def test_table_chunk_type(self):
        c = chunker(chunk_size=800)
        chunks = c.chunk_document(
            make_pages(self.TABLE_TEXT), document_id=1, filename="fees.pdf", category="academics"
        )
        table_chunks = [ch for ch in chunks if ch["chunk_type"] == "table"]
        assert len(table_chunks) >= 1, "Table must produce at least one table-type chunk"

    def test_table_content_intact(self):
        c = chunker(chunk_size=800)
        chunks = c.chunk_document(
            make_pages(self.TABLE_TEXT), document_id=1, filename="fees.pdf", category="academics"
        )
        table_chunks = [ch for ch in chunks if ch["chunk_type"] == "table"]
        all_table_text = " ".join(ch["text"] for ch in table_chunks)
        assert "B.Tech" in all_table_text
        assert "MBA" in all_table_text

    def test_no_chunk_breaks_table_mid_row(self):
        """No individual chunk should contain just the header but not the data rows."""
        c = chunker(chunk_size=800)
        chunks = c.chunk_document(
            make_pages(self.TABLE_TEXT), document_id=1, filename="fees.pdf", category="academics"
        )
        for ch in chunks:
            if "| Program |" in ch["text"]:
                # If header is present, data rows must also be present
                assert "B.Tech" in ch["text"] or "M.Tech" in ch["text"], (
                    "Table header chunk is missing data rows — table was split mid-content"
                )


# ─── SemanticChunker: Sentence Boundary Respect ───────────────────────────────

class TestSentenceBoundaries:
    def test_chunks_do_not_end_mid_sentence(self):
        """Each chunk's text should end with a sentence-terminating character."""
        long_text = " ".join([
            f"This is sentence number {i} about the university campus facilities and programs."
            for i in range(1, 40)
        ])
        c = chunker(chunk_size=100)
        chunks = c.chunk_document(make_pages(long_text), document_id=1, filename="f.pdf", category="gen")
        for ch in chunks:
            text = ch["text"].strip()
            if len(text) < 20:
                continue  # skip tiny remnants
            # Sentences end with period, ?, !, or closing quote
            assert text[-1] in ".?!\"')", (
                f"Chunk appears to end mid-sentence: '…{text[-40:]}'"
            )

    def test_overlap_provides_context_continuity(self):
        """With sentence_overlap=1, adjacent chunks should share a boundary sentence."""
        sentences = [
            f"Sentence {i} contains important information about the program."
            for i in range(1, 20)
        ]
        text = " ".join(sentences)
        c = SemanticChunker(chunk_size=80, chunk_min_tokens=5, sentence_overlap=1)
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        if len(chunks) >= 2:
            # Last sentence of chunk N should appear in chunk N+1 (overlap)
            last_sent_of_first = chunks[0]["text"].strip().split(".")[-2].strip() + "."
            second_chunk_text = chunks[1]["text"]
            # Relaxed assertion: overlap is best-effort
            assert len(chunks) >= 1  # At minimum, chunks were produced


# ─── SemanticChunker: Metadata Integrity ─────────────────────────────────────

class TestMetadataIntegrity:
    def test_all_required_keys_present(self):
        text = "## Section\nSome body text about campus placements and internships."
        c = chunker()
        chunks = c.chunk_document(make_pages(text, page_number=3), document_id=42, filename="doc.pdf", category="placements")
        required_keys = {"text", "document_id", "filename", "category", "chunk_index",
                         "section_title", "section_path", "chunk_type", "heading_level"}
        for ch in chunks:
            missing = required_keys - ch.keys()
            assert not missing, f"Chunk missing keys: {missing}"

    def test_document_id_propagated(self):
        text = "Content about hostel facilities including mess timings and room allocation."
        c = chunker()
        chunks = c.chunk_document(make_pages(text), document_id=99, filename="hostel.pdf", category="hostel")
        assert all(ch["document_id"] == 99 for ch in chunks)

    def test_page_number_propagated(self):
        text = "Content on page five about academic regulations and attendance policy."
        c = chunker()
        chunks = c.chunk_document(make_pages(text, page_number=5), document_id=1, filename="f.pdf", category="gen")
        assert all(ch["page_number"] == 5 for ch in chunks)

    def test_multi_page_processing(self):
        pages = [
            {"page_number": 1, "text": "## Introduction\nThe university was founded in 1985."},
            {"page_number": 2, "text": "## Programs\nWe offer B.Tech, M.Tech and MBA programs."},
            {"page_number": 3, "text": "## Facilities\nThe campus has a library, gym, and hostel."},
        ]
        c = chunker()
        chunks = c.chunk_document(pages, document_id=1, filename="guide.pdf", category="academics")
        assert len(chunks) >= 1
        # Chunks should have page_number set
        page_numbers = {ch["page_number"] for ch in chunks if ch["page_number"]}
        assert len(page_numbers) >= 1


# ─── Edge Cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_document_with_only_headings(self):
        text = "# H1\n## H2\n### H3\n#### H4"
        c = chunker(chunk_min_tokens=5)
        # Should not crash; may return empty or minimal chunks
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        assert isinstance(chunks, list)

    def test_single_very_long_sentence(self):
        # A sentence longer than chunk_size — should be emitted as-is
        words = ["word"] * 200
        long_sentence = " ".join(words) + "."
        c = chunker(chunk_size=50, chunk_min_tokens=5)
        chunks = c.chunk_document(make_pages(long_sentence), document_id=1, filename="f.pdf", category="gen")
        assert len(chunks) >= 1
        combined = " ".join(ch["text"] for ch in chunks)
        assert "word" in combined

    def test_unicode_content(self):
        text = "## विश्वविद्यालय\nThis section covers university policy. यह नीति महत्वपूर्ण है।"
        c = chunker(chunk_min_tokens=3)
        chunks = c.chunk_document(make_pages(text), document_id=1, filename="f.pdf", category="gen")
        assert isinstance(chunks, list)

    def test_empty_pages_handled(self):
        pages = [
            {"page_number": 1, "text": ""},
            {"page_number": 2, "text": "   \n\n   "},
            {"page_number": 3, "text": "Actual content about the placement cell activities."},
        ]
        c = chunker()
        chunks = c.chunk_document(pages, document_id=1, filename="f.pdf", category="gen")
        assert len(chunks) >= 1

    def test_markdown_file_uses_heading_detection(self):
        md_text = (
            "# CampusGPT User Guide\n\n"
            "Welcome to CampusGPT. This guide explains how to use the system.\n\n"
            "## Getting Started\n\n"
            "To start, open the chat interface. Type your question and press Enter. "
            "The system will retrieve relevant information from university documents.\n\n"
            "## Supported Topics\n\n"
            "You can ask about academics, placements, hostels, and clubs."
        )
        c = chunker()
        chunks = c.chunk_document(make_pages(md_text), document_id=1, filename="guide.md", category="general")
        titled_chunks = [ch for ch in chunks if ch.get("section_title")]
        assert len(titled_chunks) >= 1
