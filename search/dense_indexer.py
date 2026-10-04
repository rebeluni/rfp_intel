"""
Dense Embedding Indexer using BAAI/bge-small-en-v1.5.
Features:
- Configurable query prefix for asymmetric search.
- Explicit verification that max_seq_length >= chunk size (512 tokens) so nothing is truncated.
- Cosine similarity vector search with metadata filtering.
- Incremental indexing and vector persistence.
"""

import logging
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from config.settings import settings
from ingestion.models import DocumentChunk

logger = logging.getLogger(__name__)


class DenseIndexer:
    """Dense vector retriever using sentence-transformers (BGE)."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        query_prefix: Optional[str] = None,
        device: Optional[str] = None,
        storage_dir: Optional[Path] = None,
    ):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.query_prefix = query_prefix if query_prefix is not None else settings.EMBEDDING_QUERY_PREFIX
        self.device = device or settings.EMBEDDING_DEVICE
        self.storage_dir = storage_dir or settings.SEARCH_INDEX_DIR

        self.vector_file = self.storage_dir / "dense_vectors.npy"
        self.meta_file = self.storage_dir / "dense_meta.pkl"

        self.chunks: List[DocumentChunk] = []
        self.vectors: Optional[np.ndarray] = None
        self.chunk_id_to_idx: Dict[str, int] = {}

        self._model: Optional[SentenceTransformer] = None
        self._lock = threading.RLock()
        self.load()

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-loaded SentenceTransformer model with max_seq_length validation and thread lock."""
        with self._lock:
            if self._model is None:
                try:
                    self._model = SentenceTransformer(self.model_name, device=self.device)
                except Exception:
                    logger.warning(f"Network error loading '{self.model_name}', falling back to local cached files...")
                    self._model = SentenceTransformer(self.model_name, device=self.device, local_files_only=True)

                # Verify max_seq_length >= chunk size (512 tokens)
                target_seq_len = max(settings.EMBEDDING_MAX_SEQ_LENGTH, settings.CHUNK_SIZE)
                if self._model.max_seq_length < target_seq_len:
                    logger.info(
                        f"Setting {self.model_name} max_seq_length from {self._model.max_seq_length} to {target_seq_len}"
                    )
                    self._model.max_seq_length = target_seq_len
            return self._model

    def add_chunks(self, new_chunks: List[DocumentChunk], batch_size: int = 32) -> None:
        """Add new chunks to the dense index, compute embeddings, and persist."""
        if not new_chunks:
            return

        new_chunk_ids = {c.chunk_id for c in new_chunks}

        # Filter out existing chunks with same ID to avoid duplicates
        kept_chunks: List[DocumentChunk] = []
        kept_indices: List[int] = []
        for idx, c in enumerate(self.chunks):
            if c.chunk_id not in new_chunk_ids:
                kept_chunks.append(c)
                kept_indices.append(idx)

        if self.vectors is not None and len(kept_indices) > 0 and len(kept_indices) < len(self.chunks):
            existing_vectors = self.vectors[kept_indices]
        elif self.vectors is not None and len(kept_indices) == len(self.chunks):
            existing_vectors = self.vectors
        else:
            existing_vectors = None

        # Compute embeddings for new chunks (passages do NOT have query prefix)
        texts_to_embed = [c.text for c in new_chunks]
        logger.info(f"Computing dense embeddings for {len(texts_to_embed)} chunks...")
        new_vectors = self.model.encode(
            texts_to_embed,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True
        )

        # Merge vectors
        if existing_vectors is not None and len(existing_vectors) > 0:
            merged_vectors = np.vstack([existing_vectors, new_vectors])
            merged_chunks = kept_chunks + new_chunks
        else:
            merged_vectors = new_vectors
            merged_chunks = new_chunks

        self.chunks = merged_chunks
        self.vectors = merged_vectors
        self.chunk_id_to_idx = {c.chunk_id: i for i, c in enumerate(merged_chunks)}
        self.save()

    def remove_chunks(self, chunk_ids_to_remove: List[str]) -> None:
        """Remove chunks by ID and update vector matrix."""
        if not chunk_ids_to_remove or self.vectors is None:
            return

        remove_set = set(chunk_ids_to_remove)
        kept_indices = [i for i, c in enumerate(self.chunks) if c.chunk_id not in remove_set]
        self.chunks = [self.chunks[i] for i in kept_indices]
        self.vectors = self.vectors[kept_indices] if kept_indices else None
        self.chunk_id_to_idx = {c.chunk_id: i for i, c in enumerate(self.chunks)}
        self.save()

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
        Embed the query with query_prefix and perform cosine similarity search.
        Applies metadata filters.
        """
        if self.vectors is None or len(self.chunks) == 0:
            return []

        # Prepend query prefix if configured (BGE asymmetric search requirement)
        formatted_query = f"{self.query_prefix}{query}" if self.query_prefix else query
        with self._lock:
            query_vec = self.model.encode(
                [formatted_query],
                normalize_embeddings=True,
                convert_to_numpy=True
            )[0]

        # Cosine similarity (vectors are normalized so dot product = cosine sim)
        sim_scores = np.dot(self.vectors, query_vec)

        # Apply metadata filters
        candidates = []
        for idx, score in enumerate(sim_scores):
            chk = self.chunks[idx]
            meta = chk.metadata

            if bid_id and meta.bid_id != bid_id:
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
        """Persist vectors and metadata to disk."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self.vectors is not None:
                np.save(self.vector_file, self.vectors)
            with open(self.meta_file, "wb") as f:
                pickle.dump({
                    "chunks": self.chunks,
                    "chunk_id_to_idx": self.chunk_id_to_idx,
                }, f)
            logger.info(f"Saved dense index with {len(self.chunks)} vectors to {self.storage_dir}")
        except Exception as e:
            logger.error(f"Failed to save dense index: {e}")

    def load(self) -> None:
        """Load persisted vectors and metadata from disk if available."""
        if self.vector_file.exists() and self.meta_file.exists():
            try:
                self.vectors = np.load(self.vector_file)
                with open(self.meta_file, "rb") as f:
                    data = pickle.load(f)
                    self.chunks = data.get("chunks", [])
                    self.chunk_id_to_idx = data.get("chunk_id_to_idx", {})
                logger.info(f"Loaded dense index with {len(self.chunks)} vectors from {self.storage_dir}")
            except Exception as e:
                logger.warning(f"Could not load dense index: {e}")
                self.chunks = []
                self.vectors = None
                self.chunk_id_to_idx = {}
