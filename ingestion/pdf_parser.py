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

            # 2. Check for empty, blank, or scanned page
            is_scanned = False
            is_blank = False
            images = page.get_images()

            if char_count == 0:
                logger.warning(f"Page {page_num} of '{file_path.name}' is empty (0 characters).")
                if len(images) > 0:
                    is_scanned = True
                    logger.warning(
                        f"Page {page_num} of '{file_path.name}' has 0 text chars but {len(images)} images; triggering OCR."
                    )
                    ocr_text = cls._ocr_page(page)
                    if ocr_text:
                        page_text = ocr_text
                else:
                    is_blank = True
            elif char_count < 30:
                is_scanned = True
                logger.warning(
                    f"Page {page_num} of '{file_path.name}' appears scanned "
                    f"({char_count} chars < 30 threshold); triggering OCR fallback."
                )
                if len(images) > 0:
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
                        is_table, formatted_content = cls._classify_and_format_table(
                            extracted_rows, doc_type=prelim_doc_type
                        )

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

                # 4. If table_finder found no tables and doc is SPECS, check if page has coordinate-based specs table (SKU | Description)
                if not page_tables and not is_blank and prelim_doc_type == DocType.SPECS:
                    spec_tbl, remaining_prose = cls._extract_specs_coordinate_table(page, page_num)
                    if spec_tbl:
                        page_tables.append(spec_tbl)
                        page_text = remaining_prose

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
                is_scanned=is_scanned,
                is_blank=is_blank
            ))

        doc.close()

        # Second pass: strip repetitive running headers and footers across the document
        cleaned_page_texts, page_labels = TextCleaner.strip_running_headers_footers(raw_pages_text)

        # Assemble final cleaned page content (combining prose + markdown tables)
        for idx, p_text in enumerate(cleaned_page_texts):
            p = parsed_pages[idx]
            p.page_label = page_labels[idx] if idx < len(page_labels) else None
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
    def _extract_specs_coordinate_table(
        cls,
        page: pymupdf.Page,
        page_num: int
    ) -> Tuple[Optional[ParsedTable], str]:
        """
        Reconstruct specification table from word coordinates when grid lines are absent.
        Detects left description column and right SKU column, pairing rows by y-coordinate.
        Returns:
            (ParsedTable or None, remaining_prose_text)
        """
        words = page.get_text("words")
        if not words:
            return None, ""

        # Find SKU candidates in right region (x >= 280, 95 <= y <= 750)
        sku_words = [w for w in words if w[0] >= 280 and 95 <= w[1] <= 750]
        # Keep words that look like part numbers / SKUs
        sku_tokens = [w for w in sku_words if any(c.isdigit() for c in w[4]) and ("-" in w[4] or len(w[4]) >= 6)]

        if len(sku_tokens) < 4:
            return None, page.get_text("text")

        sku_tokens.sort(key=lambda w: w[1])

        # Description words in left region (x < 280, 95 <= y <= 750)
        desc_words = [w for w in words if w[0] < 280 and 95 <= w[1] <= 750]

        rows = []
        for i, sku in enumerate(sku_tokens):
            y_start = sku[1] - 8
            y_end = sku_tokens[i + 1][1] - 8 if i + 1 < len(sku_tokens) else 9999

            d_words = [w for w in desc_words if y_start <= w[1] < y_end]
            # Sort words in description by line then x
            d_words.sort(key=lambda w: (round(w[1] / 6), w[0]))
            desc_text = " ".join(w[4] for w in d_words).strip()
            desc_text = TextCleaner.clean_text(desc_text)
            sku_code = sku[4].strip()
            if sku_code and desc_text:
                rows.append([sku_code, desc_text])

        if not rows:
            return None, page.get_text("text")

        headers = ["SKU", "Description"]
        md_lines = [
            "| SKU | Description |",
            "| --- | --- |"
        ]
        for r in rows:
            safe_desc = r[1].replace("|", "\\|")
            md_lines.append(f"| {r[0]} | {safe_desc} |")

        # Collect prose outside the table area (e.g. top heading like 'SI# CC7802 Dell Latitude 5550')
        top_words = [w for w in words if w[1] < 95 and not w[4].lower().startswith("page")]
        top_words.sort(key=lambda w: (round(w[1] / 6), w[0]))
        remaining_prose = " ".join(w[4] for w in top_words).strip()

        table = ParsedTable(
            page_number=page_num,
            headers=headers,
            rows=rows,
            markdown="\n".join(md_lines)
        )
        return table, remaining_prose

    @classmethod
    def _classify_and_format_table(
        cls,
        rows: List[List[Optional[str]]],
        doc_type: Optional[DocType] = None
    ) -> Tuple[bool, str]:
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
        # Exempt doc_type == DocType.SPECS from the short-cell rule
        is_specs = (doc_type == DocType.SPECS)
        if not is_specs and (avg_cell_len > 120 or has_huge_narrative):
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
        import shutil
        if not shutil.which("tesseract"):
            logger.debug("tesseract binary not installed on system; skipping OCR fallback.")
            return ""

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
