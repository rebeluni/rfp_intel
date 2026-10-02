"""
Index Manager for End-to-End Ingestion and Incremental Search Indexing.
Coordinates:
- Ingestion Pipeline
- Hash Manifest (SHA-256 change detection and eviction)
- BM25 Inverted Index
- Dense BGE Vector Index
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from config.settings import settings
from ingestion.models import DocumentChunk, ParsedDocument
from ingestion.pipeline import IngestionPipeline
from search.bm25_index import BM25Index
from search.dense_indexer import DenseIndexer
from search.manifest import HashManifest

logger = logging.getLogger(__name__)


class IndexManager:
    """Manages incremental search indexing for all bid documents."""

    def __init__(
        self,
        bm25_index: Optional[BM25Index] = None,
        dense_indexer: Optional[DenseIndexer] = None,
        manifest: Optional[HashManifest] = None,
        pipeline: Optional[IngestionPipeline] = None,
    ):
        self.bm25_index = bm25_index or BM25Index()
        self.dense_indexer = dense_indexer or DenseIndexer()
        self.manifest = manifest or HashManifest()
        self.pipeline = pipeline or IngestionPipeline()

    def index_folder(
        self,
        folder_path: Path,
        incremental: bool = True
    ) -> Tuple[int, int, int]:
        """
        Index a bid folder incrementally.
        Returns:
            (files_indexed, chunks_added, chunks_removed)
        """
        folder_path = Path(folder_path).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        supported_exts = {".pdf", ".html", ".htm"}
        files = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in supported_exts and not f.name.startswith("~")
        ]

        logger.info(f"Checking {len(files)} files in '{folder_path.name}' for incremental indexing...")

        files_to_process: List[Path] = []
        old_chunk_ids_to_evict: List[str] = []

        for f in files:
            status = self.manifest.get_file_status(f) if incremental else "new"
            if status == "unchanged":
                logger.debug(f"Skipping unchanged file: {f.name}")
                continue

            logger.info(f"File '{f.name}' status: {status}")
            files_to_process.append(f)

        if not files_to_process:
            logger.info(f"All files in '{folder_path.name}' are up-to-date. No indexing needed.")
            return 0, 0, 0

        # Ingest files that are new or modified
        new_chunks_to_add: List[DocumentChunk] = []

        for f in files_to_process:
            try:
                # Use pipeline parsing for the single file
                if f.suffix.lower() in [".html", ".htm"]:
                    from ingestion.html_parser import HTMLParser
                    doc = HTMLParser.parse(f, bid_id=folder_path.name)
                else:
                    from ingestion.pdf_parser import PDFParser
                    doc = PDFParser.parse(f, bid_id=folder_path.name)

                chunks = self.pipeline.chunker.chunk_document(doc)
                new_chunks_to_add.extend(chunks)

                # Record in manifest and collect old chunks to evict if modified
                chunk_ids = [c.chunk_id for c in chunks]
                old_ids = self.manifest.record_indexed_file(f, chunk_ids=chunk_ids)
                if old_ids:
                    old_chunk_ids_to_evict.extend(old_ids)

            except Exception as e:
                logger.error(f"Error processing '{f.name}' during indexing: {e}", exc_info=True)

        # Evict old chunks from indices if any
        if old_chunk_ids_to_evict:
            logger.info(f"Evicting {len(old_chunk_ids_to_evict)} stale chunks from search indices...")
            self.bm25_index.remove_chunks(old_chunk_ids_to_evict)
            self.dense_indexer.remove_chunks(old_chunk_ids_to_evict)

        # Add new chunks to BM25 and Dense indices
        if new_chunks_to_add:
            logger.info(f"Adding {len(new_chunks_to_add)} chunks to BM25 index...")
            self.bm25_index.add_chunks(new_chunks_to_add)

            logger.info(f"Adding {len(new_chunks_to_add)} chunks to Dense index...")
            self.dense_indexer.add_chunks(new_chunks_to_add)

        return len(files_to_process), len(new_chunks_to_add), len(old_chunk_ids_to_evict)

    def index_all(self, base_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Index all standard bid packages (Bid1, Bid2, etc.)."""
        base_dir = Path(base_dir or settings.PROJECT_ROOT).resolve()
        bid_dirs = [d for d in base_dir.iterdir() if d.is_dir() and d.name.lower().startswith("bid")]
        bid_dirs.sort(key=lambda d: d.name)

        summary = {}
        for bdir in bid_dirs:
            indexed, added, removed = self.index_folder(bdir, incremental=True)
            summary[bdir.name] = {
                "files_indexed": indexed,
                "chunks_added": added,
                "chunks_removed": removed,
            }

        return {
            "summary": summary,
            "total_bm25_chunks": len(self.bm25_index.chunks),
            "total_dense_vectors": len(self.dense_indexer.chunks),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return current index statistics."""
        return {
            "total_indexed_files": len(self.manifest.entries),
            "bm25_chunks": len(self.bm25_index.chunks),
            "dense_vectors": len(self.dense_indexer.chunks),
            "tracked_files": list(self.manifest.entries.keys()),
        }
