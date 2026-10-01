import sys
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
doc = pymupdf.open("Bid2/Dell_Laptop_Specs.pdf")

for p_num in [0, 1]:
    page = doc[p_num]
    print(f"==================== PAGE {p_num + 1} BLOCKS ====================")
    blocks = page.get_text("blocks")
    for b in blocks:
        print(f"Block ({b[0]:.1f}, {b[1]:.1f}, {b[2]:.1f}, {b[3]:.1f}):\n{b[4][:120]}...")
