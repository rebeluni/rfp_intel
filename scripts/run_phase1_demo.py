"""
Phase 1 Ingestion Verification Script.
Ingests Bid1 and Bid2, prints summary statistics, metadata classification,
and previews parsed chunks including structured tables.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ingestion.pipeline import IngestionPipeline

# Ensure UTF-8 output encoding for Windows terminal
sys.stdout.reconfigure(encoding="utf-8")

def run_verification():
    pipeline = IngestionPipeline()
    base_dir = Path(__file__).resolve().parent.parent

    for bid_name in ["Bid1", "Bid2"]:
        bid_folder = base_dir / bid_name
        print(f"\n{'='*70}")
        print(f"  INGESTING {bid_name.upper()} (Path: {bid_folder.name})")
        print(f"{'='*70}")

        parsed_docs, all_chunks = pipeline.ingest_folder(bid_folder)

        print(f"\n[Summary for {bid_name}]")
        print(f"- Total Files Ingested: {len(parsed_docs)}")
        print(f"- Total Search Chunks Generated: {len(all_chunks)}")

        print("\n[Per-File Breakdown & Inferred Metadata]")
        for doc in parsed_docs:
            print(f"  * {doc.file_name}")
            print(f"      doc_type:        {doc.doc_type.value} (confidence: {doc.doc_type_confidence})")
            print(f"      addendum_number: {doc.addendum_number}")
            print(f"      document_date:   {doc.document_date}")
            print(f"      total_pages:     {doc.total_pages}")
            print(f"      chunks_count:    {len(doc.chunks)}")

        print(f"\n[Sample Parsed Chunks from {bid_name}]")
        # 1. Sample text chunk
        text_chunks = [c for c in all_chunks if not c.metadata.is_table]
        if text_chunks:
            sample_text = text_chunks[0]
            print(f"\n--- Sample Text Chunk ({sample_text.chunk_id}) ---")
            print(f"Source: {sample_text.metadata.file_name} (Page {sample_text.metadata.page_number})")
            preview = sample_text.text[:350].replace("\n", " ")
            print(f"Preview: {preview}...\n")

        # 2. Sample table chunk
        table_chunks = [c for c in all_chunks if c.metadata.is_table]
        if table_chunks:
            sample_tbl = table_chunks[0]
            print(f"--- Sample Table Chunk ({sample_tbl.chunk_id}) ---")
            print(f"Source: {sample_tbl.metadata.file_name} (Page {sample_tbl.metadata.page_number})")
            tbl_lines = sample_tbl.text.splitlines()[:6]
            print("\n".join(tbl_lines))
            print("...\n")

        # 3. Addendum chunk if present
        addendum_chunks = [c for c in all_chunks if c.metadata.doc_type.value == "addendum"]
        if addendum_chunks:
            sample_add = addendum_chunks[0]
            print(f"--- Sample Addendum Chunk ({sample_add.chunk_id}) ---")
            print(f"Source: {sample_add.metadata.file_name} (Page {sample_add.metadata.page_number})")
            preview_add = sample_add.text[:300].replace("\n", " ")
            print(f"Preview: {preview_add}...\n")

if __name__ == "__main__":
    run_verification()
