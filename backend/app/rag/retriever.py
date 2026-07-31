"""
Hybrid Retriever — Combines BM25 + Vector Search via Reciprocal Rank Fusion (RRF).

RRF Score formula:  RRF(d) = Σ 1 / (k + rank(d))   where k=60 (standard)
"""
import logging
from app.config import get_settings
from app.rag.embedder import get_embedder
from app.rag.vectorstore import get_vectorstore
from app.rag.bm25_index import get_bm25_index
from app.rag.reranker import get_reranker

logger = logging.getLogger(__name__)
settings = get_settings()

RRF_K = 60  # Standard RRF constant


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    id_key: str = "id",
) -> list[dict]:
    """
    Merge multiple ranked result lists using Reciprocal Rank Fusion.

    Returns a combined list sorted by RRF score (descending).
    """
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for result_list in result_lists:
        for rank, chunk in enumerate(result_list, start=1):
            chunk_id = str(chunk.get(id_key, chunk.get("text", "")[:50]))
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (RRF_K + rank)
            chunk_map[chunk_id] = chunk

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)
    fused = []
    for cid in sorted_ids:
        chunk = dict(chunk_map[cid])
        chunk["rrf_score"] = rrf_scores[cid]
        fused.append(chunk)

    return fused


def _mode_to_source_filter(knowledge_mode: str) -> str | None:
    """Convert a knowledge mode string to a source_type filter value."""
    if knowledge_mode == "official":
        return "official"
    if knowledge_mode == "experience":
        return "experience"
    return None  # hybrid — no filter


from typing import Callable

def hybrid_retrieve(
    query: str,
    queries: list[str] | None = None,
    top_k_bm25: int | None = None,
    top_k_vector: int | None = None,
    top_k_rerank: int | None = None,
    knowledge_mode: str = "hybrid",
    on_rerank_start: Callable[[], None] | None = None,
    use_reranker: bool | None = None,
) -> list[dict]:
    """
    Full hybrid retrieval pipeline:
      1. BM25 search on original + rewritten queries
      2. Vector search on original + rewritten queries
      3. RRF fusion
      4. BGE Reranker → final top_k chunks

    Knowledge Source Mode filtering happens BEFORE fusion and reranking so
    only chunks from the selected source type enter the pipeline.

    Args:
        query: Original user query
        queries: Optional list of rewritten queries from query_rewriter
        top_k_bm25: BM25 candidates per query (default: settings.bm25_top_k)
        top_k_vector: Vector candidates per query (default: settings.vector_top_k)
        top_k_rerank: Final chunks after reranking (default: settings.reranker_top_k)
        knowledge_mode: "hybrid" | "official" | "experience"
        use_reranker: Per-call reranker override (default: settings.disable_reranker)

    Returns:
        Final ranked list of chunk dicts with relevance scores.
    """
    top_k_bm25 = top_k_bm25 or settings.bm25_top_k
    top_k_vector = top_k_vector or settings.vector_top_k
    top_k_rerank = top_k_rerank or settings.reranker_top_k

    source_filter = _mode_to_source_filter(knowledge_mode)
    if source_filter:
        logger.info(f"Retrieval filter: source_type='{source_filter}' (mode={knowledge_mode})")

    all_queries = [query] + (queries or [])
    embedder = get_embedder()
    vectorstore = get_vectorstore()
    bm25 = get_bm25_index()
    reranker = get_reranker()

    all_result_lists: list[list[dict]] = []

    for q in all_queries:
        # BM25 results — filtered by source_type when mode is not hybrid
        bm25_results = bm25.search(q, top_k=top_k_bm25, filter_source_type=source_filter)
        if bm25_results:
            all_result_lists.append(bm25_results)

        # Vector results — filtered by source_type when mode is not hybrid
        query_embedding = embedder.embed_query(q)
        vector_results = vectorstore.search(
            query_embedding,
            top_k=top_k_vector,
            filter_source_type=source_filter,
        )
        if vector_results:
            all_result_lists.append(vector_results)

    if not all_result_lists:
        logger.warning("No retrieval results — knowledge base may be empty")
        return []

    # RRF fusion — use text prefix as ID since Qdrant IDs differ from BM25 indices
    fused = reciprocal_rank_fusion(all_result_lists, id_key="text")

    # Deduplicate by text (keep highest-scored)
    seen_texts: set[str] = set()
    unique_fused = []
    for chunk in fused:
        text_key = chunk["text"][:100]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_fused.append(chunk)

    # Rerank the fused candidates
    rerank_enabled = (not settings.disable_reranker) if use_reranker is None else use_reranker
    if not rerank_enabled:
        logger.info(f"Reranking disabled. Selecting top {top_k_rerank} fused candidates directly.")
    else:
        logger.info(f"Reranking {len(unique_fused)} fused candidates → top {top_k_rerank}")
        if on_rerank_start is not None:
            try:
                on_rerank_start()
            except Exception as e:
                logger.error(f"Error in on_rerank_start callback: {e}")
    final_chunks = reranker.rerank(
        query, unique_fused, top_k=top_k_rerank, use_reranker=use_reranker
    )

    return final_chunks
