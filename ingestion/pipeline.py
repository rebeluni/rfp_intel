"""
Ingestion Pipeline Coordinator.
Iterates over all files in a bid folder, parses HTML and PDF documents,
runs text cleaning and table formatting, and produces chunked documents.
Zero hardcoding: processes any folder dynamically.
"""

import logging
from pathlib import Path
from typing import List, Tuple
from ingestion.chunker import DocumentChunker
from ingestion.html_parser import HTMLParser
from ingestion.models import DocumentChunk, ParsedDocument
from ingestion.pdf_parser import PDFParser

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end ingestion pipeline for any RFP bid folder."""

    def __init__(self, chunker: DocumentChunker = None):
        self.chunker = chunker or DocumentChunker()

    def ingest_folder(self, folder_path: Path) -> Tuple[List[ParsedDocument], List[DocumentChunk]]:
        """
        Ingest an entire bid folder.
        Infers bid_id from folder name (e.g. 'Bid1', 'Bid2', 'Custom_RFP').
        """
        folder_path = Path(folder_path).resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            raise FileNotFoundError(f"Bid folder does not exist: {folder_path}")

        bid_id = folder_path.name
        parsed_documents: List[ParsedDocument] = []
        all_chunks: List[DocumentChunk] = []

        # Find all supported files (HTML and PDF)
        supported_extensions = {".pdf", ".html", ".htm"}
        files = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in supported_extensions and not f.name.startswith("~")
        ]

        logger.info(f"Ingesting bid '{bid_id}' with {len(files)} files found in {folder_path.name}...")

        # Sort files so HTML portals or base RFPs are processed consistently
        files.sort(key=lambda x: (x.suffix != ".html", x.name))

        for file_path in files:
            try:
                if file_path.suffix.lower() in [".html", ".htm"]:
                    doc = HTMLParser.parse(file_path=file_path, bid_id=bid_id)
                elif file_path.suffix.lower() == ".pdf":
                    doc = PDFParser.parse(file_path=file_path, bid_id=bid_id)
                else:
                    continue

                # Generate chunks
                chunks = self.chunker.chunk_document(doc)
                parsed_documents.append(doc)
                all_chunks.extend(chunks)

                logger.info(
                    f"Parsed '{file_path.name}': doc_type={doc.doc_type.value}, "
                    f"pages={doc.total_pages}, chunks={len(chunks)}"
                )

            except Exception as e:
                logger.error(f"Error parsing file '{file_path.name}': {e}", exc_info=True)

        return parsed_documents, all_chunks
