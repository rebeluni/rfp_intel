import sys
import re
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
import pymupdf
sys.stdout.reconfigure(encoding="utf-8")
from ingestion.cleaner import TextCleaner

doc = pymupdf.open("Bid2/Dell_Laptop_Specs.pdf")

def extract_sku_description_table(page):
    """
    Extract SKU and Description columns by word coordinates.
    Left column (x < 300) = Description
    Right column (x >= 300) = SKU
    """
    words = page.get_text("words")
    # Filter out header/footer lines (e.g. y < 80 or y > 750)
    # Also find if there is an explicit SKU column
    # Header words: Description at ~22, SKU at ~334
    
    # Let's find all SKU tokens: typically alphanumeric with hyphen (e.g. 210-BLYZ, 362-7806)
    sku_words = [w for w in words if w[0] >= 290 and w[1] > 100 and w[3] < 720]
    # Sort skus by y0
    sku_words.sort(key=lambda w: w[1])
    
    if not sku_words:
        return []
    
    # Description words: x < 290, y > 100, y < 720
    desc_words = [w for w in words if w[0] < 290 and w[1] > 100 and w[3] < 720]
    
    # We pair each SKU with the description words that fall within its vertical span
    # Each SKU i has a y0. The description for SKU i begins around SKU i's y0 (or slightly before)
    # and ends before SKU i+1's y0.
    rows = []
    for i, sku in enumerate(sku_words):
        y_start = sku[1] - 8
        if i + 1 < len(sku_words):
            y_end = sku_words[i+1][1] - 8
        else:
            y_end = 9999
        
        # Words for this description
        d_words = [w for w in desc_words if y_start <= w[1] < y_end]
        # Sort words in description by y0 then x0
        d_words.sort(key=lambda w: (round(w[1] / 5), w[0]))
        desc_text = " ".join(w[4] for w in d_words).strip()
        # Clean kerning in description
        desc_text = TextCleaner.clean_text(desc_text)
        sku_code = sku[4].strip()
        
        # In case a SKU was on p.2 where the block had both description and SKU together
        rows.append((sku_code, desc_text))
    
    return rows

for p_idx in [0, 1]:
    p = doc[p_idx]
    rows = extract_sku_description_table(p)
    print(f"=== PAGE {p_idx+1}: {len(rows)} ROWS ===")
    for sku, desc in rows:
        print(f"| {sku} | {desc} |")
