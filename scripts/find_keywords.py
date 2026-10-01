import sys
from pathlib import Path
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

for p in Path(".").rglob("*.pdf"):
    try:
        doc = pymupdf.open(p)
        for idx, page in enumerate(doc):
            text = page.get_text()
            for line in text.splitlines():
                if any(w in line.lower() for w in ["contractual", "financing", "provision"]):
                    print(f"[{p.name} p.{idx+1}] {line}")
    except Exception as e:
        pass
