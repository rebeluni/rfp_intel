"""
PDF Document Parser.
Uses PyMuPDF (fitz) with find_tables() to extract structured tables as markdown,
preserves 1-indexed page numbers, normalizes running headers/footers,
and handles scanned/unreadable pages gracefully with OCR fallback.
"""

import logging
from pathlib import Path
from typing import List, Optional
import pymupdf
from ingestion.cleaner import TextCleaner
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.models import ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger(__name__)


class PDFParser:
    """Extracts text and structured markdown tables from RFP PDF documents."""

    @classmethod
    def parse(cls, file_path: Path, bid_id: str) -> ParsedDocument:
        doc = pymupdf.open(file_path)
        raw_pages_text: List[str] = []
        parsed_pages: List[ParsedPage] = []

        # First pass: extract raw text and tables per page
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Extract structured tables using PyMuPDF find_tables()
            page_tables: List[ParsedTable] = []
            try:
                table_finder = page.find_tables()
                for tbl in table_finder:
                    extracted_rows = tbl.extract()
                    md_table = cls._format_table_markdown(extracted_rows)
                    if md_table:
                        headers = [str(c or "") for c in extracted_rows[0]] if extracted_rows else []
                        row_data = [[str(c or "") for c in r] for r in extracted_rows[1:]] if len(extracted_rows) > 1 else []
                        page_tables.append(ParsedTable(
                            page_number=page_num,
                            headers=headers,
                            rows=row_data,
                            markdown=md_table
                        ))
            except Exception as e:
                logger.warning(f"Table extraction failed on {file_path.name} page {page_num}: {e}")

            # 2. Extract standard page text
            page_text = page.get_text("text")

            # 3. Check for empty or scanned page
            is_scanned = False
            if len(page_text.strip()) < 30 and not page_tables:
                is_scanned = True
                logger.info(f"Page {page_num} of {file_path.name} has minimal text; attempting OCR fallback.")
                ocr_text = cls._ocr_page(page)
                if ocr_text:
                    page_text = ocr_text

            raw_pages_text.append(page_text)
            parsed_pages.append(ParsedPage(
                page_number=page_num,
                raw_text=page_text,
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

            # If page text exists, add cleaned version
            clean_prose = TextCleaner.clean_text(p_text)
            if clean_prose:
                page_components.append(clean_prose)

            # Append markdown tables formatted clearly
            if p.tables:
                page_components.append("\n### Structured Specification / Bid Tables:")
                for t in p.tables:
                    page_components.append(t.markdown)

            p.cleaned_text = TextCleaner.normalize_whitespace("\n\n".join(page_components))

        # Infer metadata (doc_type, confidence, addendum_number, document_date)
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

    @staticmethod
    def _format_table_markdown(rows: List[List[Optional[str]]]) -> str:
        """Converts raw list-of-lists table rows into a clean Github-flavored Markdown table."""
        if not rows:
            return ""

        # Filter out completely empty rows
        filtered_rows = []
        for r in rows:
            cells = [str(c or "").strip().replace("\n", " ") for c in r]
            if any(cells):
                filtered_rows.append(cells)

        if not filtered_rows:
            return ""

        max_cols = max(len(r) for r in filtered_rows)
        padded = [r + [""] * (max_cols - len(r)) for r in filtered_rows]

        headers = padded[0]
        # Ensure header cells are not blank
        headers = [h if h else f"Col_{i+1}" for i, h in enumerate(headers)]

        md_lines = []
        # Header row
        md_lines.append("| " + " | ".join(h.replace("|", "\\|") for h in headers) + " |")
        # Separator row
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        # Data rows
        for r in padded[1:]:
            safe_cells = [c.replace("|", "\\|") for c in r]
            md_lines.append("| " + " | ".join(safe_cells) + " |")

        return "\n".join(md_lines)

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
