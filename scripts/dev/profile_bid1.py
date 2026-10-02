import sys
import time
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
import pymupdf

doc = pymupdf.open("Bid1/JA-207652 Student and Staff Computing Devices FINAL.pdf")
print(f"Total pages: {len(doc)}")
for i in range(min(10, len(doc))):
    t0 = time.time()
    page = doc[i]
    tables = list(page.find_tables())
    extracted = [t.extract() for t in tables]
    print(f"Page {i+1}: {len(tables)} tables ({time.time() - t0:.3f}s)")
