"""
Section-aware and table-aware document chunker.
Splits text along semantic section boundaries, preserves complete tables where possible,
adds contextual RAG headers to every chunk, merges tiny chunks (< 40 tokens) into neighbours,
and generates collision-free IDs using full file slugs and short hashes.
"""

import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple
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
        active_section: Optional[str] = None

        for page in doc.pages:
            page_chunks, active_section = self._chunk_page(doc, page, active_section)
            raw_chunks.extend(page_chunks)

        # Merge chunks under ~40 tokens into their neighbours on the same page
        merged_chunks = self._merge_small_chunks(raw_chunks, doc)

        # Filter out blank form widget chunks (Task E1)
        valid_chunks = []
        for chk in merged_chunks:
            unfilled_count = len(re.findall(r"\[unfilled/blank\]", chk.text, re.IGNORECASE))
            if unfilled_count >= 5:
                continue
            valid_chunks.append(chk)

        doc.chunks = valid_chunks
        return valid_chunks

    def _chunk_page(
        self,
        doc: ParsedDocument,
        page: ParsedPage,
        active_section: Optional[str] = None
    ) -> Tuple[List[DocumentChunk], Optional[str]]:
        """Chunk a single page, treating tables as cohesive chunks."""
        page_chunks: List[DocumentChunk] = []

        # 1. Chunk structured tables first if present
        for tbl_idx, tbl in enumerate(page.tables):
            table_chunks = self._chunk_table(doc, page, tbl, f"tbl_{tbl_idx}", active_section)
            page_chunks.extend(table_chunks)

        # 2. Chunk prose / non-table text
        prose_text = page.cleaned_text
        if "### Specification / Bid Tables:" in prose_text:
            prose_text = prose_text.split("### Specification / Bid Tables:")[0].strip()

        if prose_text:
            prose_chunks, active_section = self._chunk_text(
                text=prose_text,
                doc=doc,
                page_number=page.page_number,
                page_label=page.page_label,
                active_section=active_section
            )
            page_chunks.extend(prose_chunks)

        # Deduplicate near-identical chunks on the same page
        unique_chunks: List[DocumentChunk] = []
        for chk in page_chunks:
            is_dup = False
            chk_words = set(re.findall(r"\w{3,}", chk.text.lower()))
            for u in unique_chunks:
                u_words = set(re.findall(r"\w{3,}", u.text.lower()))
                if chk_words and u_words:
                    intersection = len(chk_words & u_words)
                    similarity = intersection / min(len(chk_words), len(u_words))
                    if similarity > 0.85:
                        is_dup = True
                        break
            if not is_dup:
                unique_chunks.append(chk)

        return unique_chunks, active_section

    def _chunk_table(
        self,
        doc: ParsedDocument,
        page: ParsedPage,
        table: ParsedTable,
        suffix: str,
        active_section: Optional[str] = None
    ) -> List[DocumentChunk]:
        """Keep table intact or split row-wise while repeating headers."""
        md = table.markdown.strip()
        if not md:
            return []

        chunks: List[DocumentChunk] = []
        lines = md.splitlines()

        section_name = self._detect_heading(page.cleaned_text) or active_section
        if not section_name:
            if doc.doc_type == DocType.SPECS:
                section_name = "Specifications"
            else:
                section_name = f"Table (p.{page.page_number})"

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
                page_start=page.page_number,
                page_end=page.page_number,
                page_label=page.page_label,
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
                if len(current_block) >= self.chunk_size * 4:
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
                        page_start=page.page_number,
                        page_end=page.page_number,
                        page_label=page.page_label,
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
                    page_start=page.page_number,
                    page_end=page.page_number,
                    page_label=page.page_label,
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

    @staticmethod
    def _count_tokens(text: str) -> int:
        """Count approximate tokens using word and punctuation boundaries."""
        return len(re.findall(r"\w+|[^\w\s]", text))

    def _chunk_text(
        self,
        text: str,
        doc: ParsedDocument,
        page_number: int,
        page_label: Optional[str] = None,
        active_section: Optional[str] = None
    ) -> Tuple[List[DocumentChunk], Optional[str]]:
        """
        Split text using word- and sentence-aligned boundaries.
        Target chunk size: ~500 tokens. Overlap: ~75 tokens.
        Guarantees zero mid-word or mid-sentence cuts.
        Section label = heading in effect at the START of the chunk.
        """
        chunks: List[DocumentChunk] = []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return [], active_section

        # Break overly long paragraphs into full sentences
        segments: List[str] = []
        for p in paragraphs:
            if self._count_tokens(p) > 220:
                sents = re.split(r"(?<=[.!?])\s+", p)
                segments.extend(s.strip() for s in sents if s.strip())
            else:
                segments.append(p)

        current_segments: List[str] = []
        current_token_count = 0
        seq = 0

        # Section in effect at start of this first chunk:
        # Check if the very first line of the chunk is a heading
        first_line = ""
        if segments:
            seg_lines = [l.strip() for l in segments[0].splitlines() if l.strip()]
            first_line = seg_lines[0] if seg_lines else ""
        first_heading = self._detect_heading_line(first_line) if first_line else None
        if first_heading:
            active_section = first_heading
        chunk_start_section = active_section or self._detect_heading(text) or "General"

        for seg in segments:
            for l in seg.splitlines():
                dh = self._detect_heading_line(l)
                if dh:
                    active_section = dh

            seg_tokens = self._count_tokens(seg)

            if current_token_count + seg_tokens > self.chunk_size and current_segments:
                body_text = "\n\n".join(current_segments)
                context_hdr = self._build_context_header(doc, page_number, chunk_start_section)
                full_text = f"{context_hdr}\n{body_text}"
                chunk_id = self._generate_chunk_id(doc.bid_id, doc.file_name, page_number, f"c{seq}", full_text)

                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    page_start=page_number,
                    page_end=page_number,
                    page_label=page_label,
                    document_date=doc.document_date,
                    published_date=doc.document_date,
                    section=chunk_start_section,
                    is_table=False
                )
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=full_text,
                    context_header=context_hdr,
                    metadata=meta
                ))
                seq += 1

                # Word/sentence-aligned sliding window overlap (~75 tokens)
                overlap_segments = []
                overlap_tokens = 0
                for s in reversed(current_segments):
                    s_tok = self._count_tokens(s)
                    if overlap_tokens + s_tok <= self.chunk_overlap or not overlap_segments:
                        overlap_segments.insert(0, s)
                        overlap_tokens += s_tok
                    else:
                        break

                current_segments = overlap_segments + [seg]
                current_token_count = overlap_tokens + seg_tokens
                # Next chunk's section is the heading active at its start
                chunk_start_section = active_section
            else:
                current_segments.append(seg)
                current_token_count += seg_tokens

        if current_segments:
            body_text = "\n\n".join(s for s in current_segments if s.strip())
            if body_text.strip():
                context_hdr = self._build_context_header(doc, page_number, chunk_start_section)
                full_text = f"{context_hdr}\n{body_text}"
                chunk_id = self._generate_chunk_id(doc.bid_id, doc.file_name, page_number, f"c{seq}", full_text)

                meta = DocumentMetadata(
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_path=doc.file_path,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    page_number=page_number,
                    page_start=page_number,
                    page_end=page_number,
                    page_label=page_label,
                    document_date=doc.document_date,
                    published_date=doc.document_date,
                    section=chunk_start_section,
                    is_table=False
                )
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=full_text,
                    context_header=context_hdr,
                    metadata=meta
                ))

        return chunks, active_section

    def _merge_small_chunks(
        self,
        chunks: List[DocumentChunk],
        doc: ParsedDocument
    ) -> List[DocumentChunk]:
        """
        Merge tiny chunks (< 40 tokens / ~40 words) into neighbouring chunks on the SAME page.
        Never merges chunks across pages. If merging across pages were ever needed,
        page_start and page_end would be cited.
        """
        if len(chunks) <= 1:
            return chunks

        merged: List[DocumentChunk] = []

        for chk in chunks:
            # Count words in the body (excluding the first context header line)
            lines = chk.text.splitlines()
            body_text = "\n".join(lines[1:]) if len(lines) > 1 else chk.text
            word_count = len(body_text.split())

            # If small chunk and not a table, merge into preceding chunk ON THE SAME PAGE ONLY
            if word_count < self.min_chunk_words and not chk.metadata.is_table and merged:
                prev = merged[-1]
                if (
                    prev.metadata.file_name == chk.metadata.file_name
                    and prev.metadata.page_number == chk.metadata.page_number
                ):
                    prev.text = prev.text + "\n\n" + body_text
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

    def _build_context_header(
        self,
        doc: ParsedDocument,
        page_number: int,
        section: str,
        page_end: Optional[int] = None
    ) -> str:
        """
        Build contextual breadcrumb header.
        Format: [Bid1 | Addendum 1 | Clean Title Cut At Word Boundary | p.1 | Section: <heading>]
        No underscores, cut at word boundary, no literal '...'.
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

        # Short clean title without underscores or portal noise
        stem = Path(doc.file_name).stem
        clean_title = re.sub(r"[_\-]+", " ", stem).strip()
        clean_title = re.sub(r"\b(?:SOURCING\s*\d+|Bid\s+Information|\{\d+\}|BidNet\s+Direct)\b", "", clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r"\s+", " ", clean_title).strip()

        # Cut at a word boundary (max 42 chars) without literal '...'
        if len(clean_title) > 42:
            truncated = clean_title[:42]
            last_space = truncated.rfind(" ")
            if last_space > 20:
                clean_title = truncated[:last_space].strip()
            else:
                clean_title = truncated.strip()

        clean_section = section.strip() if section else "General"
        if len(clean_section) > 35:
            truncated_sec = clean_section[:35]
            last_space = truncated_sec.rfind(" ")
            if last_space > 15:
                clean_section = truncated_sec[:last_space].strip()
            else:
                clean_section = truncated_sec.strip()

        page_str = f"p.{page_number}-{page_end}" if (page_end and page_end != page_number) else f"p.{page_number}"
        return f"[{doc.bid_id} | {doc_label} | {clean_title} | {page_str} | Section: {clean_section}]"

    def _detect_heading_line(self, line: str) -> Optional[str]:
        """Detect if a single line is a section header, rejecting codes, SKUs, and table rows."""
        line = line.strip()
        if not line:
            return None

        # Reject table rows
        if line.startswith("|") or line.endswith("|"):
            return None

        # Reject termination markers (e.g. END OF ADDENDUM, END OF SOLICITATION)
        if re.search(r"\bEND\s+OF\s+(?:ADDENDUM|SOLICITATION|DOCUMENT|SECTION|FILE|PROPOSAL)\b", line, re.IGNORECASE):
            return None

        # Reject person names (e.g. Alzate, Jasmine or ALZATE, JASMINE)
        if re.match(r"^[A-Z][a-zA-Z]+,\s+[A-Z][a-zA-Z]+(?:\s+[A-Z]\.?)?$", line):
            return None
        if any(line.upper().startswith(p) for p in ["BUYER", "CONTACT", "OFFICER", "NAME:", "AFFIANT", "REPRESENTATIVE"]):
            return None

        # Reject SKUs, part numbers, codes (e.g. 210-BLYZ, 362-7806, CC7802, SOL-1234)
        if re.match(r"^[\w\d]+[-_][\w\d]+$", line):
            return None

        # Reject lines with high digit concentration or phone numbers
        digits = sum(c.isdigit() for c in line)
        if digits > 0 and (digits / len(line) > 0.18 or digits >= 5):
            return None

        # Pattern 1: Section 1 - General Information
        sec_match = re.match(
            r"^(?:Section|SECTION|Article|ARTICLE|Part|PART)\s+([0-9A-Za-z.-]+(?:\s*[-:–]\s*[^\n]+)?)",
            line
        )
        if sec_match:
            return sec_match.group(0).strip()

        # Pattern 2: Addendum heading (e.g. ADDENDUM No. 2, Addendum 1)
        add_match = re.match(r"^(?:ADDENDUM|Addendum)\s*(?:No\.?|NUMBER)?\s*([0-9A-Za-z.-]+)?", line, re.IGNORECASE)
        if add_match and not re.search(r"\bEND\s+OF\b", line, re.IGNORECASE):
            return line.strip().title()

        # Pattern 3: Markdown headers # Section Title
        h_match = re.match(r"^#{1,4}\s+([^\n]+)", line)
        if h_match:
            candidate = h_match.group(1).strip()
            if not re.match(r"^[\w\d]+[-_][\w\d]+$", candidate):
                return candidate

        # Pattern 4: Short all-caps headings (e.g. LENGTH OF CONTRACT, SCOPE OF WORK, FINANCIAL DISCLOSURE AFFIRMATION)
        clean_l = re.sub(r"\b([A-Z]{4,})I\b", r"\1", line)  # strip fused Roman numeral I
        words = re.findall(r"\b[A-Za-z]{3,}\b", clean_l)
        known_headers = {
            "OVERVIEW", "INTRODUCTION", "SCOPE", "SPECIFICATIONS", "REQUIREMENTS",
            "SUMMARY", "BACKGROUND", "DELIVERABLES", "TIMELINE", "SCHEDULE",
            "PRICING", "EVALUATION", "ATTACHMENTS", "EXHIBITS", "INSTRUCTIONS",
            "CONTRACT", "GENERAL", "PURPOSE", "ELIGIBILITY", "SUBMISSION",
            "AFFIRMATION", "AFFIDAVIT", "DISCLOSURE", "WORKPLACE", "AUTHORITY"
        }
        if len(clean_l) < 55 and clean_l.isupper() and not clean_l.endswith(".") and len(clean_l) > 4:
            # Must not be a person name (LASTNAME, FIRSTNAME)
            if "," in clean_l:
                return None
            # Must have at least 2 words or contain a known header keyword
            if len(words) >= 2 or any(w in known_headers for w in words):
                title_candidate = clean_l.title()
                # Strip fused trailing i (e.g. Affirmationi -> Affirmation)
                title_candidate = re.sub(r"(?<=[a-zA-Z]{4})[iI]$", "", title_candidate)
                return title_candidate

        return None

    def _detect_heading(self, text: str) -> Optional[str]:
        """Detect section headers in text snippet, rejecting codes, SKUs, and table rows."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines[:5]:
            h = self._detect_heading_line(line)
            if h:
                return h
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
