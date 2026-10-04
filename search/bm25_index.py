"""
BM25 Sparse Inverted Index.
Uses rank_bm25.BM25Okapi with the specialized compound/subpart tokenizer.
Supports metadata filtering (bid_id, doc_type, addendum_number, is_table)
and incremental updates (add_chunks, remove_chunks).
"""

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rank_bm25 import BM25Okapi
from config.settings import settings
from ingestion.models import DocumentChunk
from search.tokenizer import tokenize_bm25

logger = logging.getLogger(__name__)


class BM25Index:
    """In-memory and persisted BM25 sparse search index."""

    def __init__(self, index_file: Optional[Path] = None):
        self.index_file = index_file or (settings.SEARCH_INDEX_DIR / "bm25_index.pkl")
        self.chunks: List[DocumentChunk] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: Optional[BM25Okapi] = None
        self.chunk_id_to_idx: Dict[str, int] = {}
        self.load()

    def add_chunks(self, new_chunks: List[DocumentChunk]) -> None:
        """Add new chunks to the BM25 index and rebuild."""
        if not new_chunks:
            return

        # Deduplicate or replace any existing chunks with same ID
        existing_ids = set(self.chunk_id_to_idx.keys())
        updated_chunks: List[DocumentChunk] = []

        new_chunk_ids = {c.chunk_id for c in new_chunks}
        for c in self.chunks:
            if c.chunk_id not in new_chunk_ids:
                updated_chunks.append(c)

        updated_chunks.extend(new_chunks)
        self._rebuild(updated_chunks)
        self.save()

    def remove_chunks(self, chunk_ids_to_remove: List[str]) -> None:
        """Remove specified chunk IDs from index and rebuild."""
        if not chunk_ids_to_remove:
            return
        remove_set = set(chunk_ids_to_remove)
        kept = [c for c in self.chunks if c.chunk_id not in remove_set]
        self._rebuild(kept)
        self.save()

    def _rebuild(self, chunks: List[DocumentChunk]) -> None:
        """Rebuild the BM25 index from a list of chunks."""
        self.chunks = chunks
        self.tokenized_corpus = [tokenize_bm25(c.text) for c in chunks]
        self.chunk_id_to_idx = {c.chunk_id: i for i, c in enumerate(chunks)}

        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

    def search(
        self,
        query: str,
        top_k: int = 20,
        bid_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        exclude_doc_type: Optional[str] = None,
        addendum_number: Optional[int] = None,
        is_table: Optional[bool] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Query the BM25 index with optional metadata filters.
        Returns top_k (DocumentChunk, score) tuples.
        """
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = tokenize_bm25(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)

        # Apply metadata filters and gather candidates
        candidates = []
        for idx, score in enumerate(scores):
            if score <= 0.0:
                continue
            chk = self.chunks[idx]
            meta = chk.metadata

            if bid_id and meta.bid_id.lower() != bid_id.lower():
                continue
            if doc_type and meta.doc_type.value != doc_type:
                continue
            if exclude_doc_type:
                dt_val = meta.doc_type.value if hasattr(meta.doc_type, "value") else str(meta.doc_type)
                if dt_val.lower() == exclude_doc_type.lower():
                    continue
            if addendum_number is not None and meta.addendum_number != addendum_number:
                continue
            if is_table is not None and meta.is_table != is_table:
                continue

            candidates.append((chk, float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def save(self) -> None:
        """Persist BM25 index and chunk objects to disk."""
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.index_file, "wb") as f:
                pickle.dump({
                    "chunks": self.chunks,
                    "tokenized_corpus": self.tokenized_corpus,
                    "chunk_id_to_idx": self.chunk_id_to_idx,
                }, f)
            logger.info(f"Saved BM25 index with {len(self.chunks)} chunks to {self.index_file}")
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")

    def load(self) -> None:
        """Load BM25 index from disk if available."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "rb") as f:
                    data = pickle.load(f)
                    self.chunks = data.get("chunks", [])
                    self.tokenized_corpus = data.get("tokenized_corpus", [])
                    self.chunk_id_to_idx = data.get("chunk_id_to_idx", {})
                    if self.tokenized_corpus:
                        self.bm25 = BM25Okapi(self.tokenized_corpus)
                logger.info(f"Loaded BM25 index with {len(self.chunks)} chunks from {self.index_file}")
            except Exception as e:
                logger.warning(f"Could not load BM25 index from {self.index_file}: {e}")
                self.chunks = []
                self.tokenized_corpus = []
                self.chunk_id_to_idx = {}
                self.bm25 = None
