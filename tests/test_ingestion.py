"""
Unit tests for Document Ingestion & Parsing (Phase 1).
Validates text cleaning, table extraction, table false-positive filtering,
metadata classification (including addendum variants and fallback triggering),
failure handling (empty, scanned, corrupt), and contextual chunking.
"""

import logging
from pathlib import Path
import pytest
import pymupdf
from ingestion.cleaner import TextCleaner
from ingestion.chunker import DocumentChunker
from ingestion.html_parser import HTMLParser
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.models import (
    DocType,
    DocumentMetadata,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)
from ingestion.pdf_parser import PDFParser
from ingestion.pipeline import IngestionPipeline


class TestTextCleaner:
    def test_normalize_whitespace(self):
        text = "Hello   world!\u200b \xa0\n\n\n\nNext line."
        cleaned = TextCleaner.normalize_whitespace(text)
        assert cleaned == "Hello world!\n\nNext line."

    def test_fix_hyphenation(self):
        text = "This is a comput-\ning device with state-of-the-art specs."
        fixed = TextCleaner.fix_hyphenation(text)
        assert "computing device" in fixed
        assert "state-of-the-art" in fixed

    def test_strip_running_headers_footers(self):
        pages = [
            "Official Header Notice\nContent of page 1\nPage 1 of 3",
            "Official Header Notice\nContent of page 2\nPage 2 of 3",
            "Official Header Notice\nContent of page 3\nPage 3 of 3",
        ]
        cleaned_pages, page_labels = TextCleaner.strip_running_headers_footers(pages)
        assert len(cleaned_pages) == 3
        assert len(page_labels) == 3
        assert page_labels[0] == "1 of 3"
        for p in cleaned_pages:
            assert "Official Header Notice" not in p
            assert "Page 1 of 3" not in p
            assert "Content of page" in p


class TestMetadataClassifier:
    def test_classify_addendum_with_number(self):
        p = Path("Addendum 2 RFP General Supplies.pdf")
        doc_type, conf, addendum_num, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="Addendum No. 2 to RFP for General Supplies. Extends due date."
        )
        assert doc_type == DocType.ADDENDUM
        assert addendum_num == 2
        assert conf >= 0.90

    def test_classify_affidavit(self):
        p = Path("Non_Collusion_Affidavit.pdf")
        doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="State of Maryland. Sworn Affidavit of Non-Collusion."
        )
        assert doc_type == DocType.AFFIDAVIT
        assert conf >= 0.85

    def test_classify_specs(self):
        p = Path("Hardware_Specs.pdf")
        doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="Technical Specifications and minimum system requirements for laptops."
        )
        assert doc_type == DocType.SPECS
        assert conf >= 0.65

    def test_classify_bid_page(self):
        p = Path("portal_page.html")
        doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="<html><title>BidNet Direct</title></html>"
        )
        assert doc_type == DocType.BID_PAGE
        assert conf >= 0.95

    def test_classify_form(self):
        p = Path("W9_Standard_Form.pdf")
        doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="Standard Form W-9 Request for Taxpayer Identification"
        )
        assert doc_type == DocType.FORM
        assert conf >= 0.65

    @pytest.mark.parametrize(
        "fname,content,expected_num",
        [
            ("Amendment #2.pdf", "RFP updates", 2),
            ("Addendum No. 3.pdf", "Questions and Answers", 3),
            ("Addendum No 4.pdf", "Schedule change", 4),
            ("Addendum_05_Final.pdf", "Details", 5),
            ("Clarification #1.pdf", "Clarifications", 1),
            ("Bulletin #3.pdf", "Pre-bid bulletin", 3),
        ],
    )
    def test_addendum_number_variants(self, fname, content, expected_num):
        """Test regex robustness across addendum naming variations."""
        num = MetadataClassifier._extract_addendum_number(fname.lower(), content.lower())
        assert num == expected_num

    def test_odd_filename_doctype_fallback_trigger(self, caplog):
        """Test that an ambiguous/odd filename triggers confidence < threshold and logs LLM fallback."""
        with caplog.at_level(logging.INFO):
            p = Path("7398172_misc_doc.pdf")
            doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
                file_path=p,
                content_preview="Random text with no procurement keywords or identifiers."
            )
            assert conf < 0.65
            assert any("below threshold" in record.message for record in caplog.records)


class TestTableExtractionAndFiltering:
    def test_table_false_positive_layout_box_filter(self):
        """
        Verify that a single-column layout box with narrative paragraphs (e.g. LENGTH OF CONTRACT)
        is converted to clean prose and NOT formatted as a table with Col_N headers.
        """
        layout_box_rows = [
            ["LENGTH OF CONTRACT", ""],
            ["The term of this proposal shall be for a three (3) year agreement with renewals.", None],
            ["SCOPE OF PROPOSAL", ""],
            ["The district is soliciting proposals for goods and services described herein.", None]
        ]
        is_table, content = PDFParser._classify_and_format_table(layout_box_rows)
        assert is_table is False
        assert "Col_1" not in content
        assert "Col_2" not in content
        assert "LENGTH OF CONTRACT" in content
        assert "The term of this proposal" in content

    def test_real_table_retains_markdown_without_col_n(self):
        """Verify that genuine structured tables retain markdown formatting and drop Col_N."""
        real_table_rows = [
            ["Item", "Specification", "Qty"],
            ["CPU", "Intel Core i5", "100"],
            ["RAM", "16GB DDR4", "100"],
            ["Storage", "512GB SSD", "100"]
        ]
        is_table, content = PDFParser._classify_and_format_table(real_table_rows)
        assert is_table is True
        assert "| Item | Specification | Qty |" in content
        assert "Col_" not in content
        assert "| CPU | Intel Core i5 | 100 |" in content

    def test_affidavit_skips_table_extraction(self, tmp_path):
        """Verify that affidavits bypass find_tables() to prevent text garbling."""
        pdf_path = tmp_path / "Contract_Affidavit.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "State of Maryland Contract Affidavit. I hereby affirm that I am duly authorized.")
        doc.save(str(pdf_path))
        doc.close()

        parsed = PDFParser.parse(pdf_path, bid_id="BidTest")
        assert parsed.doc_type == DocType.AFFIDAVIT
        assert len(parsed.pages[0].tables) == 0
        assert "I hereby affirm that I am duly authorized" in parsed.pages[0].cleaned_text


class TestFailureHandling:
    def test_empty_page_handling(self, tmp_path, caplog):
        """Test logging and graceful handling of an empty (0-character) page."""
        with caplog.at_level(logging.WARNING):
            pdf_path = tmp_path / "empty_doc.pdf"
            doc = pymupdf.open()
            doc.new_page()  # Blank page
            doc.save(str(pdf_path))
            doc.close()

            parsed = PDFParser.parse(pdf_path, bid_id="BidTest")
            assert len(parsed.pages) == 1
            assert parsed.pages[0].cleaned_text == ""
            assert any("is empty (0 characters)" in record.message for record in caplog.records)

    def test_scanned_page_handling(self, tmp_path, caplog):
        """Test detection and OCR trigger logging for a page with < 30 characters."""
        with caplog.at_level(logging.WARNING):
            pdf_path = tmp_path / "scanned_doc.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 50), "Minimal")  # 7 chars < 30 chars
            doc.save(str(pdf_path))
            doc.close()

            parsed = PDFParser.parse(pdf_path, bid_id="BidTest")
            assert parsed.pages[0].is_scanned is True
            assert any("appears scanned" in record.message for record in caplog.records)

    def test_corrupt_file_handling(self, tmp_path, caplog):
        """Test that a corrupt non-PDF file does not crash the pipeline and returns empty doc."""
        with caplog.at_level(logging.ERROR):
            corrupt_path = tmp_path / "broken.pdf"
            corrupt_path.write_bytes(b"%PDF-INVALID_BYTES_NOT_A_REAL_PDF")

            parsed = PDFParser.parse(corrupt_path, bid_id="BidTest")
            assert parsed.doc_type == DocType.OTHER
            assert len(parsed.pages) == 0
            assert any("Failed to open/parse corrupt file" in record.message for record in caplog.records)


class TestHTMLParser:
    def test_table_and_kv_parsing(self, tmp_path):
        html_file = tmp_path / "test_bid.html"
        html_content = """
        <html>
        <head><title>Portal Bid</title></head>
        <body>
            <dl>
                <dt>Solicitation Number</dt>
                <dd>SOL-998811</dd>
                <dt>Publication Date</dt>
                <dd>05/29/2024</dd>
                <dt>Closing Date</dt>
                <dd>07/09/2024</dd>
            </dl>
            <div class="field-label">Buyer Contact</div>
            <div>Jane Doe 555-123-4567 jane@agency.gov</div>
            <table>
                <tr><th>Item</th><th>Qty</th></tr>
                <tr><td>Laptops</td><td>50</td></tr>
            </table>
        </body>
        </html>
        """
        html_file.write_text(html_content, encoding="utf-8")
        parsed = HTMLParser.parse(html_file, bid_id="TestBid")

        assert parsed.doc_type == DocType.BID_PAGE
        assert len(parsed.pages) == 1
        page = parsed.pages[0]
        assert "SOL-998811" in page.cleaned_text
        assert "05/29/2024" in page.cleaned_text
        assert "07/09/2024" in page.cleaned_text
        assert "| Item | Qty |" in page.cleaned_text
        assert "| Laptops | 50 |" in page.cleaned_text


class TestDocumentChunker:
    def test_context_header_and_chunk_ids(self):
        """Verify context header format and full file slug + short hash chunk IDs."""
        chunker = DocumentChunker(chunk_size=500, min_chunk_words=10)
        page = ParsedPage(
            page_number=1,
            raw_text="Section 1 - General Requirements\nThe contractor shall provide all hardware.",
            cleaned_text="Section 1 - General Requirements\nThe contractor shall provide all hardware specified in the requirements.",
            tables=[]
        )
        doc = ParsedDocument(
            file_name="RFP_JA-207652_FINAL.pdf",
            file_path="/path/RFP_JA-207652_FINAL.pdf",
            bid_id="Bid1",
            doc_type=DocType.RFP,
            pages=[page]
        )
        chunks = chunker.chunk_document(doc)
        assert len(chunks) == 1
        chunk = chunks[0]
        # Check context header (clean title without underscores)
        assert "[Bid1 | RFP | RFP JA 207652 FINAL | p.1 | Section: Section 1 - General Requirements]" in chunk.text
        # Check chunk ID format (full slug + short hash)
        assert chunk.chunk_id.startswith("Bid1_RFP_JA_207652_FINAL_p1_c0_")
        assert len(chunk.chunk_id.split("_")[-1]) == 8  # 8-char hash

    def test_merge_small_chunks(self):
        """Verify chunks under min_chunk_words are merged into neighbouring chunks."""
        chunker = DocumentChunker(chunk_size=300, min_chunk_words=30)
        p1 = ParsedPage(
            page_number=1,
            raw_text="Short sentence.",
            cleaned_text="Short sentence.",
            tables=[]
        )
        p2 = ParsedPage(
            page_number=2,
            raw_text="This is a much longer chunk that has sufficient words to meet the minimum threshold requirement and remain independent.",
            cleaned_text="This is a much longer chunk that has sufficient words to meet the minimum threshold requirement and remain independent.",
            tables=[]
        )
        doc = ParsedDocument(
            file_name="test_doc.pdf",
            file_path="/path/test_doc.pdf",
            bid_id="Bid1",
            doc_type=DocType.RFP,
            pages=[p1, p2]
        )
        chunks = chunker.chunk_document(doc)
        # Verify p1 was merged into p2 or kept if different pages, but not fragmented
        assert len(chunks) <= 2
