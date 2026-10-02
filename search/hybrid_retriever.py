"""
Hybrid Search Retriever.
Combines Dense Embeddings (BAAI/bge-small-en-v1.5) and Sparse BM25
using Reciprocal Rank Fusion (RRF, k=60) and Cross-Encoder Re-ranking.
Produces rich citations with file name, physical page number/range, and section heading.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from config.settings import settings
from ingestion.models import DocumentChunk
from search.bm25_index import BM25Index
from search.dense_indexer import DenseIndexer
from search.query_expander import QueryExpander
from search.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    """A scored and cited retrieval result."""
    chunk_id: str
    text: str
    citation: str
    file_name: str
    page_number: int
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section: Optional[str] = None
    bid_id: str
    doc_type: str
    addendum_number: Optional[int] = None
    is_table: bool = False
    rrf_score: float = 0.0
    bm25_score: Optional[float] = None
    dense_score: Optional[float] = None
    rerank_score: Optional[float] = None

    def format_citation(self) -> str:
        """Standardized citation string: File, Page(s), Section."""
        p_str = f"p.{self.page_start}-{self.page_end}" if (self.page_end and self.page_end != self.page_number) else f"p.{self.page_number}"
        sec_str = f" | Section: {self.section}" if self.section else ""
        return f"{self.file_name} ({p_str}{sec_str})"


class HybridRetriever:
    """Orchestrates hybrid retrieval (BM25 + Dense + RRF + Cross-Encoder)."""

    def __init__(
        self,
        bm25_index: Optional[BM25Index] = None,
        dense_indexer: Optional[DenseIndexer] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        query_expander: Optional[QueryExpander] = None,
        rrf_k: int = settings.RRF_K,
        candidate_pool: int = settings.RETRIEVAL_CANDIDATE_POOL,
        default_top_k: int = settings.RERANKER_TOP_K,
    ):
        self.bm25_index = bm25_index or BM25Index()
        self.dense_indexer = dense_indexer or DenseIndexer()
        self.reranker = reranker or CrossEncoderReranker()
        self.query_expander = query_expander or QueryExpander()
        self.rrf_k = rrf_k
        self.candidate_pool = candidate_pool
        self.default_top_k = default_top_k

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        bid_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        addendum_number: Optional[int] = None,
        is_table: Optional[bool] = None,
        mode: str = "hybrid",  # "hybrid", "dense_only", "bm25_only", "hybrid_norerank"
        expand_query: bool = True,
    ) -> List[SearchResult]:
        """
        Execute search across configured retrieval modes with metadata filters.
        Modes:
          - 'hybrid': BM25 + Dense -> RRF -> CrossEncoder Rerank
          - 'hybrid_norerank': BM25 + Dense -> RRF (no reranker)
          - 'dense_only': Dense vector retrieval only
          - 'bm25_only': BM25 sparse retrieval only
        """
        top_k = top_k or self.default_top_k
        effective_query = self.query_expander.expand_query(query) if expand_query else query

        # 1. BM25 Only Mode
        if mode == "bm25_only":
            bm25_results = self.bm25_index.search(
                query=effective_query,
                top_k=top_k,
                bid_id=bid_id,
                doc_type=doc_type,
                addendum_number=addendum_number,
                is_table=is_table,
            )
            return [
                self._build_search_result(chunk, bm25_score=score, rrf_score=score)
                for chunk, score in bm25_results
            ]

        # 2. Dense Only Mode
        if mode == "dense_only":
            dense_results = self.dense_indexer.search(
                query=query,  # Dense uses original query + settings prefix
                top_k=top_k,
                bid_id=bid_id,
                doc_type=doc_type,
                addendum_number=addendum_number,
                is_table=is_table,
            )
            return [
                self._build_search_result(chunk, dense_score=score, rrf_score=score)
                for chunk, score in dense_results
            ]

        # 3. Hybrid Modes (RRF Fusion)
        pool_size = max(self.candidate_pool, top_k * 2)

        # Retrieve candidates from both systems
        bm25_candidates = self.bm25_index.search(
            query=effective_query,
            top_k=pool_size,
            bid_id=bid_id,
            doc_type=doc_type,
            addendum_number=addendum_number,
            is_table=is_table,
        )

        dense_candidates = self.dense_indexer.search(
            query=query,
            top_k=pool_size,
            bid_id=bid_id,
            doc_type=doc_type,
            addendum_number=addendum_number,
            is_table=is_table,
        )

        # Compute Reciprocal Rank Fusion (RRF) scores
        chunk_map: Dict[str, DocumentChunk] = {}
        bm25_score_map: Dict[str, float] = {}
        dense_score_map: Dict[str, float] = {}
        rrf_scores: Dict[str, float] = {}

        for rank, (chunk, score) in enumerate(bm25_candidates):
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            bm25_score_map[cid] = score
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        for rank, (chunk, score) in enumerate(dense_candidates):
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            dense_score_map[cid] = score
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        # Sort combined candidate pool by RRF score
        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        fused_candidates = [(chunk_map[cid], rrf) for cid, rrf in sorted_rrf[:pool_size]]

        # If hybrid_norerank requested, return top-k by RRF directly
        if mode == "hybrid_norerank":
            return [
                self._build_search_result(
                    chunk,
                    rrf_score=rrf,
                    bm25_score=bm25_score_map.get(chunk.chunk_id),
                    dense_score=dense_score_map.get(chunk.chunk_id),
                )
                for chunk, rrf in fused_candidates[:top_k]
            ]

        # 4. Hybrid + Cross-Encoder Rerank Mode
        if not fused_candidates:
            return []

        reranked = self.reranker.rerank(query=query, candidates=fused_candidates, top_k=top_k)

        results = []
        for chunk, rerank_score in reranked:
            cid = chunk.chunk_id
            results.append(
                self._build_search_result(
                    chunk,
                    rrf_score=rrf_scores.get(cid, 0.0),
                    bm25_score=bm25_score_map.get(cid),
                    dense_score=dense_score_map.get(cid),
                    rerank_score=rerank_score,
                )
            )

        return results

    def _build_search_result(
        self,
        chunk: DocumentChunk,
        rrf_score: float = 0.0,
        bm25_score: Optional[float] = None,
        dense_score: Optional[float] = None,
        rerank_score: Optional[float] = None,
    ) -> SearchResult:
        """Construct a SearchResult with citation formatting."""
        meta = chunk.metadata
        p_start = meta.page_start or meta.page_number
        p_end = meta.page_end or meta.page_number
        p_str = f"p.{p_start}-{p_end}" if (p_end != p_start) else f"p.{p_start}"
        sec_str = f" | Section: {meta.section}" if meta.section else ""
        citation = f"{meta.file_name} ({p_str}{sec_str})"

        return SearchResult(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            citation=citation,
            file_name=meta.file_name,
            page_number=meta.page_number,
            page_start=p_start,
            page_end=p_end,
            section=meta.section,
            bid_id=meta.bid_id,
            doc_type=meta.doc_type.value,
            addendum_number=meta.addendum_number,
            is_table=meta.is_table,
            rrf_score=round(rrf_score, 6),
            bm25_score=round(bm25_score, 4) if bm25_score is not None else None,
            dense_score=round(dense_score, 4) if dense_score is not None else None,
            rerank_score=round(rerank_score, 4) if rerank_score is not None else None,
        )
