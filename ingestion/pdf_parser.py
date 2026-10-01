"""
PDF Document Parser.
Uses PyMuPDF (fitz) with find_tables() to extract true structured specification tables,
filters out false-positive layout boxes (converting them to clean prose),
skips table extraction for affidavits/forms,
preserves 1-indexed page numbers, normalizes running headers/footers,
and handles scanned, empty, or corrupt files gracefully.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple
import pymupdf
from ingestion.cleaner import TextCleaner
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.models import DocType, ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger(__name__)


class PDFParser:
    """Extracts text and structured markdown tables from RFP PDF documents."""

    @classmethod
    def parse(cls, file_path: Path, bid_id: str) -> ParsedDocument:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            doc = pymupdf.open(file_path)
        except Exception as e:
            logger.error(f"Failed to open/parse corrupt file '{file_path.name}': {e}. Gracefully skipping.")
            # Return an empty document rather than crashing
            return ParsedDocument(
                file_name=file_path.name,
                file_path=str(file_path),
                bid_id=bid_id,
                doc_type=DocType.OTHER,
                doc_type_confidence=0.0,
                pages=[],
                chunks=[]
            )

        raw_pages_text: List[str] = []
        parsed_pages: List[ParsedPage] = []

        # Preliminary metadata inference from file name to check if it's an affidavit or form
        prelim_doc_type, prelim_conf, prelim_add_num, prelim_date = MetadataClassifier.infer_metadata(
            file_path=file_path,
            content_preview=""
        )

        skip_tables = prelim_doc_type in [DocType.AFFIDAVIT, DocType.FORM]

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Extract raw page text
            page_text = page.get_text("text")
            char_count = len(page_text.strip())

            # 2. Check for empty or scanned page
            is_scanned = False
            if char_count == 0:
                logger.warning(f"Page {page_num} of '{file_path.name}' is empty (0 characters).")
            elif char_count < 30:
                is_scanned = True
                logger.warning(
                    f"Page {page_num} of '{file_path.name}' appears scanned "
                    f"({char_count} chars < 30 threshold); triggering OCR fallback."
                )
                ocr_text = cls._ocr_page(page)
                if ocr_text:
                    logger.info(f"OCR extracted {len(ocr_text)} characters on page {page_num}.")
                    page_text = ocr_text

            page_tables: List[ParsedTable] = []
            layout_prose_additions: List[str] = []

            # 3. Extract tables only if document is not an affidavit or form
            if not skip_tables:
                try:
                    table_finder = page.find_tables()
                    for tbl in table_finder:
                        extracted_rows = tbl.extract()
                        is_table, formatted_content = cls._classify_and_format_table(extracted_rows)

                        if is_table:
                            headers = [str(c or "").strip() for c in extracted_rows[0]] if extracted_rows else []
                            row_data = [[str(c or "").strip() for c in r] for r in extracted_rows[1:]] if len(extracted_rows) > 1 else []
                            page_tables.append(ParsedTable(
                                page_number=page_num,
                                headers=headers,
                                rows=row_data,
                                markdown=formatted_content
                            ))
                        elif formatted_content:
                            # Converted layout box (e.g. LENGTH OF CONTRACT) -> append to prose
                            layout_prose_additions.append(formatted_content)
                except Exception as e:
                    logger.warning(f"Table finder failed on '{file_path.name}' page {page_num}: {e}")

            # Merge layout box prose into page text if present
            if layout_prose_additions:
                combined_text = "\n\n".join(layout_prose_additions) + "\n\n" + page_text
            else:
                combined_text = page_text

            raw_pages_text.append(combined_text)
            parsed_pages.append(ParsedPage(
                page_number=page_num,
                raw_text=combined_text,
                cleaned_text="",  # populated in second pass
                tables=page_tables,
                is_scanned=is_scanned
            ))

        doc.close()

        # Second pass: strip repetitive running headers and footers across the document
        cleaned_page_texts = TextCleaner.strip_running_headers_footers(raw_pages_text)

        # Assemble final cleaned page content (combining prose + markdown tables)
        for idx, p_text in enumerate(cleaned_page_texts):
            p = parsed_pages[idx]
            page_components = []

            clean_prose = TextCleaner.clean_text(p_text)
            if clean_prose:
                page_components.append(clean_prose)

            # Append real markdown tables formatted clearly
            if p.tables:
                page_components.append("\n### Specification / Bid Tables:")
                for t in p.tables:
                    page_components.append(t.markdown)

            p.cleaned_text = TextCleaner.normalize_whitespace("\n\n".join(page_components))

        # Re-infer metadata with actual page content for full accuracy
        first_page_preview = parsed_pages[0].cleaned_text if parsed_pages else ""
        doc_type, confidence, addendum_num, doc_date = MetadataClassifier.infer_metadata(
            file_path=file_path,
            content_preview=first_page_preview
        )

        return ParsedDocument(
            file_name=file_path.name,
            file_path=str(file_path),
            bid_id=bid_id,
            doc_type=doc_type,
            doc_type_confidence=confidence,
            addendum_number=addendum_num,
            document_date=doc_date,
            pages=parsed_pages,
            chunks=[]
        )

    @classmethod
    def _classify_and_format_table(cls, rows: List[List[Optional[str]]]) -> Tuple[bool, str]:
        """
        Differentiates real tabular data from layout boxes.
        Returns:
            (True, markdown_table_string) if valid real table
            (False, prose_string) if layout box
            (False, "") if empty/noise
        """
        if not rows or len(rows) < 2:
            return False, ""

        # Filter empty rows
        filtered_rows = []
        for r in rows:
            cells = [str(c or "").strip() for c in r]
            if any(cells):
                filtered_rows.append(cells)

        if len(filtered_rows) < 2:
            return False, ""

        max_cols = max(len(r) for r in filtered_rows)
        if max_cols < 2:
            return False, cls._rows_to_prose(filtered_rows)

        # 1. Check column population: count how many columns have non-empty values
        col_counts = [0] * max_cols
        total_len = 0
        cell_count = 0
        has_huge_narrative = False

        for r in filtered_rows:
            for c_idx, cell in enumerate(r):
                if cell:
                    col_counts[c_idx] += 1
                    text_len = len(cell)
                    total_len += text_len
                    cell_count += 1
                    # A single cell with > 250 characters indicates narrative prose paragraph
                    if text_len > 250:
                        has_huge_narrative = True

        # Columns that have values in at least 25% of rows
        populated_cols = sum(1 for cnt in col_counts if cnt >= max(1, len(filtered_rows) * 0.25))

        # If only 1 column is populated, it's a boxed single-column layout
        if populated_cols < 2:
            return False, cls._rows_to_prose(filtered_rows)

        avg_cell_len = total_len / max(1, cell_count)
        # If cells contain long multi-sentence prose paragraphs, treat as layout box
        if avg_cell_len > 120 or has_huge_narrative:
            return False, cls._rows_to_prose(filtered_rows)

        # 2. Format real table: Drop synthetic Col_N headers
        padded = [r + [""] * (max_cols - len(r)) for r in filtered_rows]

        headers = padded[0]
        # If header row is entirely empty or has missing names, use meaningful labels
        if not any(h for h in headers):
            if max_cols == 2:
                headers = ["Item / Specification", "Requirement / Detail"]
            else:
                headers = [f"Field {i+1}" for i in range(max_cols)]
        else:
            # Replace empty header cells with fallback without Col_N
            headers = [h if h else f"Field {i+1}" for i, h in enumerate(headers)]

        md_lines = []
        md_lines.append("| " + " | ".join(h.replace("|", "\\|").replace("\n", " ") for h in headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for r in padded[1:]:
            safe_cells = [c.replace("|", "\\|").replace("\n", " ") for c in r]
            md_lines.append("| " + " | ".join(safe_cells) + " |")

        return True, "\n".join(md_lines)

    @staticmethod
    def _rows_to_prose(rows: List[List[str]]) -> str:
        """Convert a layout box (table false positive) into clean natural prose paragraphs."""
        prose_blocks = []
        for r in rows:
            non_empty = [c.replace("\n", " ").strip() for c in r if c.strip()]
            if not non_empty:
                continue
            if len(non_empty) == 1:
                prose_blocks.append(non_empty[0])
            elif len(non_empty) == 2:
                # Key: Value pattern
                prose_blocks.append(f"{non_empty[0]}: {non_empty[1]}")
            else:
                prose_blocks.append(" - ".join(non_empty))
        return "\n\n".join(prose_blocks)

    @staticmethod
    def _ocr_page(page: pymupdf.Page) -> str:
        """Optional OCR fallback using pytesseract if available."""
        try:
            import pytesseract
            from PIL import Image
            import io

            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            return text.strip()
        except ImportError:
            logger.debug("pytesseract or PIL not installed; skipping OCR fallback.")
            return ""
        except Exception as e:
            logger.warning(f"OCR execution failed: {e}")
            return ""
