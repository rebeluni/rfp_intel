"""
Section-aware and table-aware document chunker.
Splits text along semantic section boundaries, preserves complete tables where possible,
and attaches rich metadata to every chunk for precise citations.
"""

import re
from typing import List
from config.settings import settings
from ingestion.cleaner import TextCleaner
from ingestion.models import (
    DocType,
    DocumentChunk,
    DocumentMetadata,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


class DocumentChunker:
    """Chunks parsed documents into searchable units with grounded citations."""

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
        table_max_chunk_size: int = settings.TABLE_MAX_CHUNK_SIZE,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.table_max_chunk_size = table_max_chunk_size

    def chunk_document(self, doc: ParsedDocument) -> List[DocumentChunk]:
        """Generate chunks for all pages of a parsed document."""
        chunks: List[DocumentChunk] = []

        for page in doc.pages:
            page_chunks = self._chunk_page(doc, page)
            chunks.extend(page_chunks)

        doc.chunks = chunks
        return chunks

    def _chunk_page(self, doc: ParsedDocument, page: ParsedPage) -> List[DocumentChunk]:
        """Chunk a single page, treating tables as cohesive chunks."""
        page_chunks: List[DocumentChunk] = []
        chunk_idx = 0

        # 1. Chunk structured tables first if present
        for tbl_idx, tbl in enumerate(page.tables):
            table_chunks = self._chunk_table(doc, page, tbl, f"tbl_{tbl_idx}")
            page_chunks.extend(table_chunks)

        # 2. Chunk prose / non-table text
        # If there are tables, we keep the page's cleaned prose
        prose_text = page.cleaned_text
        if "### Structured Specification / Bid Tables:" in prose_text:
            prose_text = prose_text.split("### Structured Specification / Bid Tables:")[0].strip()

        if prose_text:
            prose_chunks = self._chunk_text(
                text=prose_text,
                doc=doc,
                page_number=page.page_number,
                prefix="p"
            )
            page_chunks.extend(prose_chunks)

        return page_chunks

    def _chunk_table(
        self,
        doc: ParsedDocument,
        page: ParsedPage,
        table: ParsedTable,
        suffix: str
    ) -> List[DocumentChunk]:
        """Keep table intact or split row-wise while repeating headers."""
        md = table.markdown.strip()
        if not md:
            return []

        chunks: List[DocumentChunk] = []
        lines = md.splitlines()

        # If table fits within maximum allowed table chunk size, keep it intact
        if len(md) <= self.table_max_chunk_size:
            chunk_id = f"{doc.bid_id}_{self._safe_name(doc.file_name)}_p{page.page_number}_{suffix}"
            meta = DocumentMetadata(
                bid_id=doc.bid_id,
                file_name=doc.file_name,
                file_path=doc.file_path,
                doc_type=doc.doc_type,
                addendum_number=doc.addendum_number,
                page_number=page.page_number,
                document_date=doc.document_date,
                is_table=True,
                table_caption=f"Table on page {page.page_number}"
            )
            chunks.append(DocumentChunk(chunk_id=chunk_id, text=md, metadata=meta))
            return chunks

        # Otherwise, split large table into row blocks repeating header and separator
        if len(lines) >= 2:
            header_block = "\n".join(lines[:2])
            data_rows = lines[2:]

            current_rows = []
            sub_idx = 0
            for r in data_rows:
                current_rows.append(r)
                current_block = header_block + "\n" + "\n".join(current_rows)
                if len(current_block) >= self.chunk_size:
                    chunk_id = f"{doc.bid_id}_{self._safe_name(doc.file_name)}_p{page.page_number}_{suffix}_part{sub_idx}"
                    meta = DocumentMetadata(
                        bid_id=doc.bid_id,
                        file_name=doc.file_name,
                        file_path=doc.file_path,
                        doc_type=doc.doc_type,
                        addendum_number=doc.addendum_number,
                        page_number=page.page_number,
                        document_date=doc.document_date,
                        is_table=True,
                        table_caption=f"Table on page {page.page_number} (part {sub_idx+1})"
                    )
                    chunks.append(DocumentChunk(chunk_id=chunk_id, text=current_block, metadata=meta))
                    sub_idx += 1
                    current_rows = []

            if current_rows:
                current_block = header_block + "\n" + "\n".join(current_rows)
                chunk_id = f"{doc.bid_id}_{self._safe_name(doc.file_name)}_p{page.page_number}_{suffix}_part{sub_idx}"
                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page.page_number,
                    document_date=doc.document_date,
                    is_table=True,
                    table_caption=f"Table on page {page.page_number} (part {sub_idx+1})"
                )
                chunks.append(DocumentChunk(chunk_id=chunk_id, text=current_block, metadata=meta))

        return chunks

    def _chunk_text(
        self,
        text: str,
        doc: ParsedDocument,
        page_number: int,
        prefix: str
    ) -> List[DocumentChunk]:
        """Split text along section headers or sliding window with paragraph/sentence breaks."""
        chunks: List[DocumentChunk] = []

        # Break text into paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        current_chunk_parts = []
        current_len = 0
        seq = 0

        for para in paragraphs:
            para_len = len(para)

            # If adding paragraph exceeds chunk_size and we already have content
            if current_len + para_len > self.chunk_size and current_chunk_parts:
                chunk_text = "\n\n".join(current_chunk_parts)
                chunk_id = f"{doc.bid_id}_{self._safe_name(doc.file_name)}_p{page_number}_{prefix}{seq}"
                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    document_date=doc.document_date,
                    is_table=False
                )
                chunks.append(DocumentChunk(chunk_id=chunk_id, text=chunk_text, metadata=meta))
                seq += 1

                # Retain overlap from previous chunk
                overlap_text = chunk_text[-self.chunk_overlap:] if len(chunk_text) > self.chunk_overlap else ""
                current_chunk_parts = [overlap_text, para] if overlap_text else [para]
                current_len = len(overlap_text) + para_len
            else:
                current_chunk_parts.append(para)
                current_len += para_len

        if current_chunk_parts:
            chunk_text = "\n\n".join(p for p in current_chunk_parts if p.strip())
            if chunk_text.strip():
                chunk_id = f"{doc.bid_id}_{self._safe_name(doc.file_name)}_p{page_number}_{prefix}{seq}"
                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    document_date=doc.document_date,
                    is_table=False
                )
                chunks.append(DocumentChunk(chunk_id=chunk_id, text=chunk_text, metadata=meta))

        return chunks

    @staticmethod
    def _safe_name(name: str) -> str:
        """Create a short, filesystem/identifier-safe token from filename."""
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        return clean[:24].strip("_")
