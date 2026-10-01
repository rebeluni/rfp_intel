"""
Generates the specific verification outputs requested by the reviewer:
1. Full output of Dell_Laptop_Specs.pdf chunks.
2. Before/after cleaning example on 2 pages of Bid1 RFP.
3. Log output for empty page, scanned page, and corrupt file.
4. LLM doc_type fallback trigger report and threshold location.
5. Full untruncated chunks for both HTML portal pages.
"""

import io
import logging
import sys
from pathlib import Path
import pymupdf

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import settings
from ingestion.cleaner import TextCleaner
from ingestion.html_parser import HTMLParser
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.pdf_parser import PDFParser
from ingestion.chunker import DocumentChunker

sys.stdout.reconfigure(encoding="utf-8")


def generate_verifications():
    print("=" * 80)
    print("1. FULL OUTPUT OF Dell_Laptop_Specs.pdf CHUNKS")
    print("=" * 80)
    specs_path = project_root / "Bid2" / "Dell_Laptop_Specs.pdf"
    specs_doc = PDFParser.parse(specs_path, bid_id="Bid2")
    chunker = DocumentChunker()
    specs_chunks = chunker.chunk_document(specs_doc)

    print(f"Total Chunks Generated for Dell_Laptop_Specs.pdf: {len(specs_chunks)}\n")
    for idx, c in enumerate(specs_chunks):
        print(f"--- Chunk {idx + 1} of {len(specs_chunks)} [ID: {c.chunk_id}] ---")
        print(f"Context Header: {c.context_header}")
        print(f"Metadata: Page {c.metadata.page_number} | DocType: {c.metadata.doc_type.value} | Section: {c.metadata.section}")
        print("Text Content:")
        print(c.text)
        print("\n" + "-" * 60 + "\n")

    print("\n" + "=" * 80)
    print("2. BEFORE / AFTER CLEANING ON 2 PAGES OF Bid1 RFP")
    print("=" * 80)
    rfp_path = project_root / "Bid1" / "JA-207652 Student and Staff Computing Devices FINAL.pdf"
    rfp_pdf = pymupdf.open(rfp_path)

    for pno in [1, 2]:  # Page 1 (cover) and Page 2
        raw_p = rfp_pdf[pno - 1].get_text("text")
        cleaned_p = TextCleaner.clean_text(raw_p)

        print(f"\n>>> [PAGE {pno} - RAW EXTRACTED TEXT (First 350 chars)] <<<")
        print(repr(raw_p[:350]))
        print(f"\n>>> [PAGE {pno} - AFTER CLEANING & NORMALIZATION (First 350 chars)] <<<")
        print(cleaned_p[:350])
        print("\n" + "-" * 50)
    rfp_pdf.close()

    print("\n" + "=" * 80)
    print("3. LOG OUTPUT FOR EMPTY PAGE, SCANNED PAGE, AND CORRUPT FILE")
    print("=" * 80)
    # Configure logger to capture output
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger = logging.getLogger("ingestion.pdf_parser")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    # 3a. Empty Page
    empty_doc = pymupdf.open()
    empty_doc.new_page()
    empty_path = project_root / ".storage" / "temp_empty.pdf"
    empty_doc.save(str(empty_path))
    empty_doc.close()
    PDFParser.parse(empty_path, "TestBid")

    # 3b. Scanned Page (< 30 chars)
    scanned_doc = pymupdf.open()
    scanned_p = scanned_doc.new_page()
    scanned_p.insert_text((50, 50), "Minimal text")  # 12 chars
    scanned_path = project_root / ".storage" / "temp_scanned.pdf"
    scanned_doc.save(str(scanned_path))
    scanned_doc.close()
    PDFParser.parse(scanned_path, "TestBid")

    # 3c. Corrupt File
    corrupt_path = project_root / ".storage" / "temp_corrupt.pdf"
    corrupt_path.write_bytes(b"%PDF-CORRUPTED_NON_VALID_FILE_STREAM")
    PDFParser.parse(corrupt_path, "TestBid")

    # Cleanup temp files
    empty_path.unlink(missing_ok=True)
    scanned_path.unlink(missing_ok=True)
    corrupt_path.unlink(missing_ok=True)

    print("Captured Log Messages:")
    print(log_capture.getvalue())

    print("=" * 80)
    print("4. LLM DOC_TYPE FALLBACK TRIGGER & THRESHOLD REPORT")
    print("=" * 80)
    print(f"Configured Threshold: settings.DOC_TYPE_CONFIDENCE_THRESHOLD = {settings.DOC_TYPE_CONFIDENCE_THRESHOLD}")
    print(f"Location in Code: config/settings.py (Line 74) & ingestion/metadata_classifier.py (Line 79)")

    # Test odd filename
    odd_file = Path("vendor_packet_archive_991823.pdf")
    odd_text = "Standard submission terms without direct solicitation keywords or identifiers."
    doc_t, conf, add_n, doc_d = MetadataClassifier.infer_metadata(odd_file, odd_text, allow_llm_fallback=True)
    print(f"\nTested Odd File: '{odd_file.name}'")
    print(f"Calculated Keyword Confidence: {conf}")
    print(f"Did it trigger LLM Fallback? {'YES (Confidence < ' + str(settings.DOC_TYPE_CONFIDENCE_THRESHOLD) + ')' if conf < settings.DOC_TYPE_CONFIDENCE_THRESHOLD else 'NO'}")
    print(f"Resulting DocType: {doc_t.value}")

    print("\n" + "=" * 80)
    print("5. FULL UNTRUNCATED CHUNKS FOR BOTH HTML PAGES")
    print("=" * 80)
    for bid_name in ["Bid1", "Bid2"]:
        html_file = list((project_root / bid_name).glob("*.html"))[0]
        parsed_html = HTMLParser.parse(html_file, bid_id=bid_name)
        html_chunks = chunker.chunk_document(parsed_html)

        print(f"\n######################################################################")
        print(f"  {bid_name.upper()} HTML: {html_file.name}")
        print(f"  Total Chunks: {len(html_chunks)}")
        print(f"######################################################################\n")

        for idx, c in enumerate(html_chunks):
            print(f"*** {bid_name} HTML Chunk {idx + 1} of {len(html_chunks)} [ID: {c.chunk_id}] ***")
            print(f"Context Header: {c.context_header}")
            print(f"Published Date: {c.metadata.published_date} | Section: {c.metadata.section}")
            print("Full Text Content:")
            print(c.text)
            print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    generate_verifications()
