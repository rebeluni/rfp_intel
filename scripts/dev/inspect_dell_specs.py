import sys
from pathlib import Path
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
doc = pymupdf.open("Bid2/Dell_Laptop_Specs.pdf")

for page_idx in range(len(doc)):
    page = doc[page_idx]
    print(f"=== PAGE {page_idx + 1} ===")
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    print(f"Total words: {len(words)}")
    # Find words with SKU or Dell patterns
    skus = [w for w in words if any(c.isdigit() for c in w[4]) and "-" in w[4]]
    print(f"Sample SKU words: {[w[4] for w in skus[:10]]}")
    # Inspect x coordinate ranges
    x0s = [w[0] for w in words]
    print(f"Min x0: {min(x0s):.1f}, Max x0: {max(x0s):.1f}")
    
    # Check if there are any prices ($) or quantities
    prices = [w for w in words if "$" in w[4] or "qty" in w[4].lower() or "price" in w[4].lower() or "quantity" in w[4].lower()]
    print(f"Price/Qty matches: {[w[4] for w in prices]}")
