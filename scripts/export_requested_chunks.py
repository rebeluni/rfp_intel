import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
import pymupdf
from ingestion.pdf_parser import PDFParser
from ingestion.chunker import DocumentChunker

chunker = DocumentChunker()
out_file = project_root / "outputs" / "requested_chunks.txt"
lines = []

def log(s=""):
    lines.append(s)

# 1. Addendum 1 & Addendum 2
add1_path = project_root / "Bid1" / "Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf"
doc_add1 = PDFParser.parse(add1_path, bid_id="Bid1")
chunks_add1 = chunker.chunk_document(doc_add1)

log(f"================================================================================")
log(f"1. ADDENDUM 1 FULL CHUNKS ({len(chunks_add1)} chunks)")
log(f"================================================================================")
for i, c in enumerate(chunks_add1):
    log(f"\n--- [Addendum 1 | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number}] ---")
    log(c.text)

add2_path = project_root / "Bid1" / "Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf"
doc_add2 = PDFParser.parse(add2_path, bid_id="Bid1")
chunks_add2 = chunker.chunk_document(doc_add2)

log(f"\n================================================================================")
log(f"2. ADDENDUM 2 FULL CHUNKS ({len(chunks_add2)} chunks)")
log(f"================================================================================")
for i, c in enumerate(chunks_add2):
    log(f"\n--- [Addendum 2 | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number}] ---")
    log(c.text)

# 3. PORFP_-_Dell_Laptop_Final.pdf (Bid2 RFP)
porfp_path = project_root / "Bid2" / "PORFP_-_Dell_Laptop_Final.pdf"
doc_porfp = PDFParser.parse(porfp_path, bid_id="Bid2")
chunks_porfp = chunker.chunk_document(doc_porfp)

log(f"\n================================================================================")
log(f"3. PORFP_-_Dell_Laptop_Final.pdf FULL CHUNKS ({len(chunks_porfp)} chunks)")
log(f"================================================================================")
for i, c in enumerate(chunks_porfp):
    log(f"\n--- [PORFP | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number} | Table: {c.metadata.is_table}] ---")
    log(c.text)

# 4. Bid1 "LENGTH OF CONTRACT" chunk
# In JA-207652 Student and Staff Computing Devices FINAL.pdf, LENGTH OF CONTRACT is on page 2
bid1_rfp_path = project_root / "Bid1" / "JA-207652 Student and Staff Computing Devices FINAL.pdf"
# Open doc with PyMuPDF and parse first 5 pages for fast extraction
doc_full = pymupdf.open(bid1_rfp_path)
doc_sample = pymupdf.open()
doc_sample.insert_pdf(doc_full, from_page=0, to_page=4)
tmp_sample_path = project_root / "outputs" / "temp_rfp_p1_5.pdf"
doc_sample.save(tmp_sample_path)
doc_full.close()
doc_sample.close()

doc_bid1_rfp = PDFParser.parse(tmp_sample_path, bid_id="Bid1")
# Reset file_name to original
doc_bid1_rfp.file_name = bid1_rfp_path.name
chunks_bid1_rfp = chunker.chunk_document(doc_bid1_rfp)

loc_chunks = [c for c in chunks_bid1_rfp if "LENGTH OF CONTRACT" in c.text or "Length Of Contract" in c.text or "CONTRACT" in c.text]
log(f"\n================================================================================")
log(f"4. Bid1 'LENGTH OF CONTRACT' CHUNK AFTER LAYOUT-BOX FIX ({len(loc_chunks)} chunks)")
log(f"================================================================================")
for i, c in enumerate(loc_chunks):
    log(f"\n--- [LENGTH OF CONTRACT | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number} | Table: {c.metadata.is_table}] ---")
    log(c.text)

# 5. Fixed Contract_Affidavit chunk
aff_path = project_root / "Bid2" / "Contract_Affidavit.pdf"
doc_aff = PDFParser.parse(aff_path, bid_id="Bid2")
chunks_aff = chunker.chunk_document(doc_aff)

log(f"\n================================================================================")
log(f"5. FIXED CONTRACT_AFFIDAVIT CHUNKS ({len(chunks_aff)} chunks)")
log(f"================================================================================")
for i, c in enumerate(chunks_aff):
    log(f"\n--- [Contract Affidavit | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number}] ---")
    log(c.text)

# 6. Corrected Dell specs chunks
specs_path = project_root / "Bid2" / "Dell_Laptop_Specs.pdf"
doc_specs = PDFParser.parse(specs_path, bid_id="Bid2")
chunks_specs = chunker.chunk_document(doc_specs)

log(f"\n================================================================================")
log(f"6. CORRECTED DELL SPECS CHUNKS ({len(chunks_specs)} chunks)")
log(f"================================================================================")
for i, c in enumerate(chunks_specs):
    log(f"\n--- [Dell Specs | Chunk {i+1} | ID: {c.chunk_id} | Page {c.metadata.page_number} | Table: {c.metadata.is_table}] ---")
    log(c.text)

out_text = "\n".join(lines)
out_file.write_text(out_text, encoding="utf-8")
print(f"Exported successfully to {out_file}, size: {len(out_text)} characters.")
