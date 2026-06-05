"""
BM25 Keyword Index — In-Memory, rebuilt from Qdrant on startup.

Since we use Qdrant Cloud (no local disk for vectors), the BM25 index
is built by fetching all chunk texts from Qdrant at startup.
This means no separate file storage needed — the Qdrant collection is
the single source of truth.
"""
import logging
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

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
        """Simple whitespace + lowercase tokenizer."""
        return text.lower().split()

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

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """BM25 retrieval — returns top_k chunks with BM25 scores."""
        if self._bm25 is None or not self._chunks:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Pair scores with chunk metadata
        scored = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        results = []
        for idx, score in scored:
            if score > 0:  # Only include non-zero scores
                chunk = dict(self._chunks[idx])
                chunk["bm25_score"] = float(score)
                results.append(chunk)

        return results

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


def get_bm25_index() -> BM25Index:
    """Return the singleton BM25 index."""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index
