import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
from ingestion.pdf_parser import PDFParser
from ingestion.chunker import DocumentChunker

fpath = Path("Bid2/Dell_Laptop_Specs.pdf")
doc = PDFParser.parse(fpath, bid_id="Bid2")

print(f"DocType: {doc.doc_type}")
print(f"Pages: {len(doc.pages)}")
for idx, p in enumerate(doc.pages):
    print(f"  Page {p.page_number}: {len(p.tables)} tables, is_scanned={p.is_scanned}, is_blank={p.is_blank}, label={p.page_label}")
    if p.tables:
        print(f"    Table rows: {len(p.tables[0].rows)}")

chunker = DocumentChunker()
chunks = chunker.chunk_document(doc)
print(f"\nTotal chunks: {len(chunks)}")
for c in chunks:
    print(f"\n--- CHUNK {c.chunk_id} ---")
    print(c.text[:400])
