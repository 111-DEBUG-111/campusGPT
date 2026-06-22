"""
BM25 Keyword Index — In-Memory, rebuilt from pgvector on startup.

The index is also persisted to disk via pickle so that warm restarts can
skip the full rebuild.  The pickle file stores the current KB version as
a header; if the on-disk version doesn't match Redis, the file is
ignored and the index is rebuilt from pgvector (then re-saved).

Cache path: BM25_CACHE_DIR env var (default /tmp) / bm25_index.pkl
"""
import logging
import os
import pickle
import re
import string
import threading
from pathlib import Path

import nltk
from nltk.stem import PorterStemmer
from nltk.corpus import stopwords
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Disk-cache path
# Override BM25_CACHE_DIR to point at a Render persistent disk (e.g. /data)
# so the index survives cold starts.  Falls back to /tmp (ephemeral).
# ──────────────────────────────────────────────────────────────────────────────
_CACHE_DIR = Path(os.getenv("BM25_CACHE_DIR", "/tmp"))
_CACHE_PATH = _CACHE_DIR / "bm25_index.pkl"

# ──────────────────────────────────────────────────────────────────────────────
# NLTK resource bootstrap (runs once, thread-safe)
# ──────────────────────────────────────────────────────────────────────────────
_nltk_ready = False
_nltk_lock = threading.Lock()


def _ensure_nltk_resources() -> None:
    global _nltk_ready
    if _nltk_ready:
        return
    with _nltk_lock:
        if _nltk_ready:
            return
        for resource in ("punkt_tab", "stopwords"):
            try:
                nltk.data.find(f"tokenizers/{resource}" if resource.startswith("punkt") else f"corpora/{resource}")
            except LookupError:
                logger.info(f"Downloading NLTK resource: {resource}")
                nltk.download(resource, quiet=True)
        _nltk_ready = True


# ──────────────────────────────────────────────────────────────────────────────
# University-specific synonym map
# Each canonical form maps to a list of aliases (all lowercase, no punctuation).
# During tokenization, any alias is *replaced* with the canonical term so that
# the index and the query share the same token regardless of how the user wrote it.
# ──────────────────────────────────────────────────────────────────────────────
_SYNONYM_MAP: dict[str, str] = {
    # CGPA / GPA
    "cumulative grade point average": "cgpa",
    "grade point average": "gpa",
    "gpa": "gpa",
    # Degrees & programmes
    "bachelor of technology": "btech",
    "b.tech": "btech",
    "b tech": "btech",
    "master of technology": "mtech",
    "m.tech": "mtech",
    "m tech": "mtech",
    "master of business administration": "mba",
    # Academic administration
    "head of department": "hod",
    "h.o.d": "hod",
    "dean of academics": "doa",
    "vice chancellor": "vc",
    # Leave & attendance
    "on duty": "od",
    "on-duty": "od",
    "medical leave": "ml",
    "casual leave": "cl",
    "earned leave": "el",
    "attendance waiver": "attendance waiver",
    "attendance exemption": "attendance waiver",
    # Exams
    "examination": "exam",
    "examinations": "exam",
    "end semester examination": "ese",
    "end-semester": "ese",
    "end sem": "ese",
    "cat": "cat",          # continuous assessment test
    "internal assessment": "ia",
    # Fees
    "tuition fee": "tuition",
    "hostel fee": "hostel",
    # Misc university terms
    "machine learning": "ml",    # context-dependent but common in CS curricula
    "artificial intelligence": "ai",
    "natural language processing": "nlp",
    "research and development": "rd",
    "r&d": "rd",
}

# Pre-compile phrase → canonical mapping (longest phrases first to avoid partial replacements)
_PHRASE_SYNONYMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE), canonical)
    for phrase, canonical in sorted(_SYNONYM_MAP.items(), key=lambda x: -len(x[0]))
]

# ──────────────────────────────────────────────────────────────────────────────
# Singleton NLP objects
# ──────────────────────────────────────────────────────────────────────────────
_stemmer = PorterStemmer()
_ENGLISH_STOPWORDS: frozenset[str] | None = None


def _get_stopwords() -> frozenset[str]:
    global _ENGLISH_STOPWORDS
    if _ENGLISH_STOPWORDS is None:
        _ensure_nltk_resources()
        # Keep a few semantically important words even though NLTK marks them
        # as stop-words (e.g., "no", "not", "which", "how", "when", "where")
        keep = {"no", "not", "how", "when", "where", "which", "who", "whom"}
        _ENGLISH_STOPWORDS = frozenset(stopwords.words("english")) - keep
    return _ENGLISH_STOPWORDS


# ──────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ──────────────────────────────────────────────────────────────────────────────

def _apply_synonyms(text: str) -> str:
    """Replace known multi-word phrases with their canonical forms."""
    for pattern, canonical in _PHRASE_SYNONYMS:
        text = pattern.sub(canonical, text)
    return text


def _tokenize(text: str) -> list[str]:
    """
    Full NLP tokenization pipeline:
    1. Synonym / acronym expansion  (phrase-level)
    2. Lowercase
    3. Punctuation stripping (preserves intra-word hyphens — e.g. "on-duty")
    4. Whitespace split
    5. Stop-word removal
    6. Porter stemming  (skip tokens that look like acronyms so "CGPA" stays "cgpa")
    """
    _ensure_nltk_resources()
    stop_words = _get_stopwords()

    # 1. Replace known synonyms/phrases before splitting
    text = _apply_synonyms(text)

    # 2. Lowercase
    text = text.lower()

    # 3. Remove punctuation except hyphens inside words
    #    e.g. "on-duty" → kept; "hello," → "hello"
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"(?<!\w)-|-(?!\w)", " ", text)  # strip isolated hyphens

    # 4. Split on whitespace
    raw_tokens = text.split()

    tokens: list[str] = []
    for tok in raw_tokens:
        # 5. Stop-word removal
        if tok in stop_words:
            continue
        # 6. Stem — but not for short all-alpha tokens that look like acronyms
        #    (2-5 chars, no vowels) so that "od", "hod", "cgpa", "ml" are kept as-is
        if len(tok) <= 5 and tok.isalpha() and not any(c in "aeiou" for c in tok):
            tokens.append(tok)  # acronym — keep verbatim
        else:
            tokens.append(_stemmer.stem(tok))

    return tokens


# ──────────────────────────────────────────────────────────────────────────────
_bm25_index: "BM25Index | None" = None


class BM25Index:
    """
    Wraps rank_bm25.BM25Okapi with metadata tracking.
    Supports search and incremental rebuild.
    """

    def __init__(self):
        self._chunks: list[dict] = []
        self._corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def _tokenize(self, text: str) -> list[str]:
        """Delegate to the module-level NLP tokenizer."""
        return _tokenize(text)

    def build_from_chunks(self, chunks: list[dict]) -> None:
        """
        Build the BM25 index from a list of chunk dicts.
        Each dict must have at least {"text": str, ...metadata...}
        """
        self._chunks = chunks
        self._corpus = [self._tokenize(c["text"]) for c in chunks]
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
            logger.info(f"BM25 index built with {len(self._corpus)} chunks")
        else:
            self._bm25 = None
            logger.info("BM25 index empty (no documents indexed yet)")

    def add_chunks(self, new_chunks: list[dict]) -> None:
        """Add new chunks and rebuild the index."""
        self._chunks.extend(new_chunks)
        self._corpus = [self._tokenize(c["text"]) for c in self._chunks]
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)

    def remove_by_document_id(self, document_id: int) -> None:
        """Remove chunks belonging to a document and rebuild."""
        self._chunks = [c for c in self._chunks if c.get("document_id") != document_id]
        self._corpus = [self._tokenize(c["text"]) for c in self._chunks]
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int = 20, filter_source_type: str | None = None) -> list[dict]:
        """BM25 retrieval — returns top_k chunks with BM25 scores.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.
            filter_source_type: If set, only chunks with this source_type
                are considered (pre-reranking filter for mode isolation).
        """
        if self._bm25 is None or not self._chunks:
            return []

        tokenized_query = self._tokenize(query)

        # Apply source_type filter before scoring so only eligible chunks enter
        if filter_source_type:
            eligible_indices = [
                i for i, c in enumerate(self._chunks)
                if c.get("source_type", "official") == filter_source_type
            ]
            if not eligible_indices:
                return []
            # Score only eligible chunks using their original corpus tokens
            import numpy as np  # noqa: PLC0415
            scores_all = self._bm25.get_scores(tokenized_query)
            scored = sorted(
                [(i, scores_all[i]) for i in eligible_indices],
                key=lambda x: x[1],
                reverse=True,
            )[:top_k]
        else:
            scores_all = self._bm25.get_scores(tokenized_query)
            scored = sorted(
                enumerate(scores_all),
                key=lambda x: x[1],
                reverse=True,
            )[:top_k]

        results = []
        for idx, score in scored:
            if score > 0:  # Only include non-zero scores
                chunk = dict(self._chunks[idx])
                chunk["bm25_score"] = float(score)
                results.append(chunk)

        return results

    # ── Disk persistence ──────────────────────────────────────────────────────

    def save_to_disk(self, kb_version: int) -> None:
        """
        Pickle the index to disk with the current KB version as a header.

        The file is written atomically (temp file → rename) so a crash mid-write
        never leaves a corrupted cache file.
        """
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "kb_version": kb_version,
                "chunks": self._chunks,
                "corpus": self._corpus,
                "bm25": self._bm25,
            }
            tmp_path = _CACHE_PATH.with_suffix(".tmp")
            with open(tmp_path, "wb") as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_path.rename(_CACHE_PATH)
            logger.info(
                f"BM25 index persisted to disk "
                f"({len(self._chunks)} chunks, kb_version={kb_version})"
            )
        except Exception as exc:
            logger.warning(f"BM25 disk save failed (non-fatal): {exc}")

    def load_from_disk(self, expected_kb_version: int) -> bool:
        """
        Try to restore the index from the on-disk pickle.

        Returns True  → index loaded, skip pgvector rebuild.
        Returns False → cache miss / stale / corrupt, caller must rebuild.
        """
        if not _CACHE_PATH.exists():
            logger.info("BM25 disk cache not found — will rebuild from pgvector")
            return False
        try:
            with open(_CACHE_PATH, "rb") as f:
                payload = pickle.load(f)
            cached_version = payload.get("kb_version", -1)
            if cached_version != expected_kb_version:
                logger.info(
                    f"BM25 disk cache stale "
                    f"(disk={cached_version}, expected={expected_kb_version}) "
                    f"— rebuilding from pgvector"
                )
                return False
            self._chunks = payload["chunks"]
            self._corpus = payload["corpus"]
            self._bm25 = payload["bm25"]
            logger.info(
                f"✅ BM25 index loaded from disk cache "
                f"({len(self._chunks)} chunks, kb_version={expected_kb_version})"
            )
            return True
        except Exception as exc:
            logger.warning(f"BM25 disk cache load failed: {exc} — will rebuild from pgvector")
            return False

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


def get_bm25_index() -> BM25Index:
    """Return the singleton BM25 index."""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index
