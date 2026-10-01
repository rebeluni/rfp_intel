"""
Section-aware and table-aware document chunker.
Splits text along semantic section boundaries, preserves complete tables where possible,
adds contextual RAG headers to every chunk, merges tiny chunks (< 40 tokens) into neighbours,
and generates collision-free IDs using full file slugs and short hashes.
"""

import hashlib
import re
from pathlib import Path
from typing import List, Optional
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
    """Chunks parsed documents into searchable units with rich contextual headers."""

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
        table_max_chunk_size: int = settings.TABLE_MAX_CHUNK_SIZE,
        min_chunk_words: int = 40,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.table_max_chunk_size = table_max_chunk_size
        self.min_chunk_words = min_chunk_words

    def chunk_document(self, doc: ParsedDocument) -> List[DocumentChunk]:
        """Generate chunks for all pages of a parsed document and merge tiny fragments."""
        raw_chunks: List[DocumentChunk] = []

        for page in doc.pages:
            page_chunks = self._chunk_page(doc, page)
            raw_chunks.extend(page_chunks)

        # Merge chunks under ~40 tokens into their neighbours
        merged_chunks = self._merge_small_chunks(raw_chunks, doc)
        doc.chunks = merged_chunks
        return merged_chunks

    def _chunk_page(self, doc: ParsedDocument, page: ParsedPage) -> List[DocumentChunk]:
        """Chunk a single page, treating tables as cohesive chunks."""
        page_chunks: List[DocumentChunk] = []

        # 1. Chunk structured tables first if present
        for tbl_idx, tbl in enumerate(page.tables):
            table_chunks = self._chunk_table(doc, page, tbl, f"tbl_{tbl_idx}")
            page_chunks.extend(table_chunks)

        # 2. Chunk prose / non-table text
        prose_text = page.cleaned_text
        if "### Specification / Bid Tables:" in prose_text:
            prose_text = prose_text.split("### Specification / Bid Tables:")[0].strip()

        if prose_text:
            prose_chunks = self._chunk_text(
                text=prose_text,
                doc=doc,
                page_number=page.page_number
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

        section_name = self._detect_heading(md) or "Specification Table"
        context_hdr = self._build_context_header(doc, page.page_number, section_name)

        # If table fits within maximum allowed table chunk size, keep it intact
        if len(md) <= self.table_max_chunk_size:
            chunk_body = f"{context_hdr}\n{md}"
            chunk_id = self._generate_chunk_id(doc.bid_id, doc.file_name, page.page_number, suffix, chunk_body)
            meta = DocumentMetadata(
                bid_id=doc.bid_id,
                file_name=doc.file_name,
                file_path=doc.file_path,
                doc_type=doc.doc_type,
                addendum_number=doc.addendum_number,
                page_number=page.page_number,
                document_date=doc.document_date,
                published_date=doc.document_date,
                section=section_name,
                is_table=True,
                table_caption=f"Table on page {page.page_number}"
            )
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                text=chunk_body,
                context_header=context_hdr,
                metadata=meta
            ))
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
                    chunk_body = f"{context_hdr}\n{current_block}"
                    chunk_id = self._generate_chunk_id(
                        doc.bid_id, doc.file_name, page.page_number, f"{suffix}_part{sub_idx}", chunk_body
                    )
                    meta = DocumentMetadata(
                        bid_id=doc.bid_id,
                        file_name=doc.file_name,
                        file_path=doc.file_path,
                        doc_type=doc.doc_type,
                        addendum_number=doc.addendum_number,
                        page_number=page.page_number,
                        document_date=doc.document_date,
                        published_date=doc.document_date,
                        section=section_name,
                        is_table=True,
                        table_caption=f"Table on page {page.page_number} (part {sub_idx+1})"
                    )
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        text=chunk_body,
                        context_header=context_hdr,
                        metadata=meta
                    ))
                    sub_idx += 1
                    current_rows = []

            if current_rows:
                current_block = header_block + "\n" + "\n".join(current_rows)
                chunk_body = f"{context_hdr}\n{current_block}"
                chunk_id = self._generate_chunk_id(
                    doc.bid_id, doc.file_name, page.page_number, f"{suffix}_part{sub_idx}", chunk_body
                )
                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page.page_number,
                    document_date=doc.document_date,
                    published_date=doc.document_date,
                    section=section_name,
                    is_table=True,
                    table_caption=f"Table on page {page.page_number} (part {sub_idx+1})"
                )
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=chunk_body,
                    context_header=context_hdr,
                    metadata=meta
                ))

        return chunks

    def _chunk_text(
        self,
        text: str,
        doc: ParsedDocument,
        page_number: int
    ) -> List[DocumentChunk]:
        """Split text along section headers or sliding window with paragraph/sentence breaks."""
        chunks: List[DocumentChunk] = []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        current_chunk_parts = []
        current_len = 0
        seq = 0
        current_section = self._detect_heading(text) or "General"

        for para in paragraphs:
            # Check if this paragraph introduces a new section heading
            detected_h = self._detect_heading(para)
            if detected_h:
                current_section = detected_h

            para_len = len(para)

            # If adding paragraph exceeds chunk_size and we already have content
            if current_len + para_len > self.chunk_size and current_chunk_parts:
                body_text = "\n\n".join(current_chunk_parts)
                context_hdr = self._build_context_header(doc, page_number, current_section)
                full_text = f"{context_hdr}\n{body_text}"
                chunk_id = self._generate_chunk_id(doc.bid_id, doc.file_name, page_number, f"c{seq}", full_text)

                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    document_date=doc.document_date,
                    published_date=doc.document_date,
                    section=current_section,
                    is_table=False
                )
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=full_text,
                    context_header=context_hdr,
                    metadata=meta
                ))
                seq += 1

                # Retain overlap from previous chunk
                overlap_text = body_text[-self.chunk_overlap:] if len(body_text) > self.chunk_overlap else ""
                current_chunk_parts = [overlap_text, para] if overlap_text else [para]
                current_len = len(overlap_text) + para_len
            else:
                current_chunk_parts.append(para)
                current_len += para_len

        if current_chunk_parts:
            body_text = "\n\n".join(p for p in current_chunk_parts if p.strip())
            if body_text.strip():
                context_hdr = self._build_context_header(doc, page_number, current_section)
                full_text = f"{context_hdr}\n{body_text}"
                chunk_id = self._generate_chunk_id(doc.bid_id, doc.file_name, page_number, f"c{seq}", full_text)

                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    document_date=doc.document_date,
                    published_date=doc.document_date,
                    section=current_section,
                    is_table=False
                )
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=full_text,
                    context_header=context_hdr,
                    metadata=meta
                ))

        return chunks

    def _merge_small_chunks(
        self,
        chunks: List[DocumentChunk],
        doc: ParsedDocument
    ) -> List[DocumentChunk]:
        """Merge tiny chunks (< 40 tokens / ~40 words) into neighbouring chunks."""
        if len(chunks) <= 1:
            return chunks

        merged: List[DocumentChunk] = []

        for chk in chunks:
            # Count words in the body (excluding the first context header line)
            lines = chk.text.splitlines()
            body_text = "\n".join(lines[1:]) if len(lines) > 1 else chk.text
            word_count = len(body_text.split())

            # If small chunk and not a table, merge into preceding chunk
            if word_count < self.min_chunk_words and not chk.metadata.is_table and merged:
                prev = merged[-1]
                # Check if same page or adjacent page
                if prev.metadata.file_name == chk.metadata.file_name:
                    # Append body without duplicating header
                    prev.text = prev.text + "\n\n" + body_text
                    # Update ID hash
                    prev.chunk_id = self._generate_chunk_id(
                        prev.metadata.bid_id,
                        prev.metadata.file_name,
                        prev.metadata.page_number,
                        "merged",
                        prev.text
                    )
                    continue

            merged.append(chk)

        return merged

    def _build_context_header(self, doc: ParsedDocument, page_number: int, section: str) -> str:
        """
        Build contextual breadcrumb header.
        Format: [Bid1 | Addendum 1 | RFP JA-207652 | p.1 | Section: <heading>]
        """
        # Document type label
        if doc.doc_type == DocType.ADDENDUM:
            doc_label = f"Addendum {doc.addendum_number}" if doc.addendum_number else "Addendum"
        elif doc.doc_type == DocType.AFFIDAVIT:
            doc_label = "Affidavit"
        elif doc.doc_type == DocType.FORM:
            doc_label = "Form"
        elif doc.doc_type == DocType.SPECS:
            doc_label = "Specifications"
        elif doc.doc_type == DocType.BID_PAGE:
            doc_label = "Portal Summary"
        else:
            doc_label = "RFP"

        # Short clean title (strip long hashes or extensions)
        clean_title = Path(doc.file_name).stem
        clean_title = re.sub(r"__+", " ", clean_title).strip()
        if len(clean_title) > 35:
            clean_title = clean_title[:32] + "..."

        clean_section = section[:35] if section else "General"

        return f"[{doc.bid_id} | {doc_label} | {clean_title} | p.{page_number} | Section: {clean_section}]"

    def _detect_heading(self, text: str) -> Optional[str]:
        """Detect section headers in text snippet."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines[:5]:
            # Pattern 1: Section 1 - General Information
            sec_match = re.match(
                r"^(?:Section|SECTION|Article|ARTICLE|Part|PART)\s+([0-9A-Za-z.-]+(?:\s*[-:–]\s*[^\n]+)?)",
                line
            )
            if sec_match:
                return sec_match.group(0).strip()

            # Pattern 2: Markdown headers # Section Title
            h_match = re.match(r"^#{1,4}\s+([^\n]+)", line)
            if h_match:
                return h_match.group(1).strip()

            # Pattern 3: Short all-caps headings
            if len(line) < 55 and line.isupper() and not line.endswith(".") and len(line) > 4:
                return line.title()

        return None

    @staticmethod
    def _generate_chunk_id(
        bid_id: str,
        file_name: str,
        page_number: int,
        suffix: str,
        content: str
    ) -> str:
        """
        Generates full file slug + short hash chunk ID.
        Example: Bid1_JA_207652_Student_and_Staff_Computing_Devices_FINAL_p2_tbl_0_a3f89e12
        """
        # Full file slug without truncation
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", Path(file_name).stem).strip("_")
        # Short 8-character content-based hash
        short_hash = hashlib.md5(f"{bid_id}_{file_name}_{page_number}_{suffix}_{content[:100]}".encode()).hexdigest()[:8]
        return f"{bid_id}_{slug}_p{page_number}_{suffix}_{short_hash}"
