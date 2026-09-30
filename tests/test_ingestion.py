"""
Unit tests for Document Ingestion & Parsing (Phase 1).
Validates text cleaning, table extraction, metadata classification, chunking, and end-to-end pipeline.
"""

from pathlib import Path
import pytest
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
        cleaned_pages = TextCleaner.strip_running_headers_footers(pages)
        assert len(cleaned_pages) == 3
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
        assert conf >= 0.80

    def test_classify_bid_page(self):
        p = Path("portal_page.html")
        doc_type, conf, _, _ = MetadataClassifier.infer_metadata(
            file_path=p,
            content_preview="<html><title>BidNet Direct</title></html>"
        )
        assert doc_type == DocType.BID_PAGE
        assert conf >= 0.95


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
            </dl>
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
        assert "| Item | Qty |" in page.cleaned_text
        assert "| Laptops | 50 |" in page.cleaned_text


class TestDocumentChunker:
    def test_table_preservation_in_chunk(self):
        chunker = DocumentChunker(chunk_size=1000, table_max_chunk_size=2000)
        table = ParsedTable(
            page_number=1,
            headers=["Part", "Description"],
            rows=[["A1", "Device 1"], ["B2", "Device 2"]],
            markdown="| Part | Description |\n| --- | --- |\n| A1 | Device 1 |\n| B2 | Device 2 |"
        )
        page = ParsedPage(
            page_number=1,
            raw_text="Sample text",
            cleaned_text="Sample text",
            tables=[table]
        )
        doc = ParsedDocument(
            file_name="specs.pdf",
            file_path="/path/specs.pdf",
            bid_id="Bid123",
            doc_type=DocType.SPECS,
            pages=[page]
        )
        chunks = chunker.chunk_document(doc)
        table_chunks = [c for c in chunks if c.metadata.is_table]
        assert len(table_chunks) >= 1
        assert "| A1 | Device 1 |" in table_chunks[0].text
        assert table_chunks[0].metadata.page_number == 1
        assert table_chunks[0].metadata.doc_type == DocType.SPECS
