"""
Cross-Encoder Reranker using cross-encoder/ms-marco-MiniLM-L-6-v2.
Applies deep bidirectional cross-attention scoring on top retrieval candidates
to optimize precision and ranking fidelity.
"""

import logging
from typing import List, Optional, Tuple
from sentence_transformers import CrossEncoder
from config.settings import settings
from ingestion.models import DocumentChunk

import threading

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranker using a pretrained Cross-Encoder model."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_name = model_name or settings.RERANKER_MODEL_NAME
        self.device = device or settings.EMBEDDING_DEVICE
        self._model: Optional[CrossEncoder] = None
        self._lock = threading.RLock()

    @property
    def model(self) -> CrossEncoder:
        """Lazy load CrossEncoder model with thread lock."""
        with self._lock:
            if self._model is None:
                try:
                    self._model = CrossEncoder(self.model_name, device=self.device)
                except Exception:
                    logger.warning(f"Network error loading '{self.model_name}', falling back to local cached files...")
                    self._model = CrossEncoder(self.model_name, device=self.device, local_files_only=True)
            return self._model

    def rerank(
        self,
        query: str,
        candidates: List[Tuple[DocumentChunk, float]],
        top_k: int = 5,
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Rerank a pool of candidate chunks for a query.
        Returns top_k (DocumentChunk, rerank_score) sorted in descending order.
        """
        if not candidates or not query:
            return []

        chunks = [c[0] for c in candidates]
        pairs = [(query, c.text) for c in chunks]

        # Score all pairs with cross-encoder with lock
        with self._lock:
            scores = self.model.predict(pairs, show_progress_bar=False)

        scored_candidates: List[Tuple[DocumentChunk, float]] = []
        for chunk, score in zip(chunks, scores):
            scored_candidates.append((chunk, float(score)))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:top_k]
