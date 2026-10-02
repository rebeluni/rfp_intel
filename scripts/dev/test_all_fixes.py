import sys
import re
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")
import pymupdf
from ingestion.cleaner import TextCleaner

# 1. Test Kerning Fixes
print("--- TEST 1: Kerning Fixes ---")
samples = [
    "CFI,Information,MIAS, Post Bur n,Factory Install",
    "CFI,Information, Validation,Se lect Any Microsoft OS",
    "CFI,Information,CSRouting,Elig ible,Factory Install",
    "CFI,LBL,POLY,SML,CC7801,FACTOR Y INSTALL"
]
for s in samples:
    fixed = TextCleaner.fix_kerning(s)
    print(f"Original: {s}")
    print(f"Fixed:    {fixed}")
assert "Post Burn" in TextCleaner.fix_kerning(samples[0])
assert "Select" in TextCleaner.fix_kerning(samples[1])
assert "Eligible" in TextCleaner.fix_kerning(samples[2])
assert "FACTORY" in TextCleaner.fix_kerning(samples[3])

# 2. Test Heading Detection
print("\n--- TEST 2: Heading Detection ---")
def detect_heading(line: str):
    line = line.strip()
    if not line or len(line) < 3 or len(line) > 60:
        return None
    # Reject table rows
    if line.startswith("|") or line.endswith("|"):
        return None
    # Reject SKUs, part numbers, codes (e.g. 210-BLYZ, CC7802, 410-260-7533)
    if re.match(r"^[\w\d]+[-_][\w\d]+$", line):
        return None
    # Reject lines where digits make up > 20% or have no vowels
    digits = sum(c.isdigit() for c in line)
    if digits > 0 and digits / len(line) > 0.15:
        return None
    # Standard section patterns
    sec_match = re.match(
        r"^(?:Section|SECTION|Article|ARTICLE|Part|PART)\s+([0-9A-Za-z.-]+(?:\s*[-:–]\s*[^\n]+)?)",
        line
    )
    if sec_match:
        return sec_match.group(0).strip()
    if re.match(r"^#{1,4}\s+([^\n]+)", line):
        return re.match(r"^#{1,4}\s+([^\n]+)", line).group(1).strip()
    # All caps heading must have real words with >= 3 letters, no codes
    words = re.findall(r"\b[A-Za-z]{3,}\b", line)
    if line.isupper() and len(words) >= 2 and not line.endswith("."):
        return line.title()
    return None

test_lines = [
    "210-BLYZ",
    "SI# CC7802",
    "410-260-7533",
    "LENGTH OF CONTRACT",
    "SCOPE OF WORK",
    "Section 1 - General Requirements",
    "Dell Latitude 5550 XCTO Base"
]
for tl in test_lines:
    dh = detect_heading(tl)
    print(f"'{tl}' -> Heading: {dh}")
assert detect_heading("210-BLYZ") is None
assert detect_heading("LENGTH OF CONTRACT") == "Length Of Contract"
assert detect_heading("Section 1 - General Requirements") == "Section 1 - General Requirements"

# 3. Test Bid2 Scope Deduplication
print("\n--- TEST 3: Bid2 Scope Deduplication ---")
raw_scope = "1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 Dock – WD22TB4 WD22TB4 30 06/10/2024\nSee more"

def dedupe_scope_text(text: str) -> str:
    # Strip See more / See less
    text = re.sub(r"\b(?:See\s+more|See\s+less|Read\s+more)\b", "", text, flags=re.IGNORECASE)
    # Split by item numbers
    item_chunks = re.split(r"(?=\b\d+\.\s+)", text.strip())
    cleaned_items = []
    for chunk in item_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Extract item number
        num_m = re.match(r"^(\d+)\.\s*(.*)", chunk)
        if not num_m:
            cleaned_items.append(chunk)
            continue
        num, rest = num_m.group(1), num_m.group(2)
        # Tail pattern: <qty> <due_date> e.g. '30 06/10/2024'
        tail_m = re.search(r"\b(\d{1,4})\s+(\d{2}/\d{2}/\d{4})\b", rest)
        qty = None
        due_date = None
        if tail_m:
            qty = tail_m.group(1)
            due_date = tail_m.group(2)
            rest = rest[:tail_m.start()] + rest[tail_m.end():]
        else:
            date_m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", rest)
            if date_m:
                due_date = date_m.group(1)
                rest = rest.replace(due_date, "")
        # Extract note if any
        note_m = re.search(r"(\*[^*]+\*)", rest)
        note = note_m.group(1) if note_m else ""
        if note:
            rest = rest.replace(note, "")
        # Deduplicate repeated phrases in the rest
        # Split tokens/words and remove consecutive duplicates
        words = rest.split()
        deduped_words = []
        i = 0
        while i < len(words):
            # check for phrase repetition (1, 2, 3, 4 words)
            matched = False
            max_span = min(15, len(words) - i)
            for span in range(max_span // 2, 0, -1):
                if i + 2 * span <= len(words):
                    p1 = words[i:i+span]
                    p2 = words[i+span:i+2*span]
                    if p1 == p2:
                        deduped_words.extend(p1)
                        i += 2 * span
                        matched = True
                        break
            if not matched:
                deduped_words.append(words[i])
                i += 1
        item_title = " ".join(deduped_words).strip()
        # Clean double tokens if any
        item_title = re.sub(r"\b(\w+)\s+\1\b", r"\1", item_title)
        row = f"{num}. {item_title}"
        if note:
            row += f" {note}"
        if qty:
            row += f" | Quantity: {qty}"
        if due_date:
            row += f" | Due Date: {due_date}"
        cleaned_items.append(row)
    return "\n".join(cleaned_items)

deduped = dedupe_scope_text(raw_scope)
print("Deduped Scope:\n" + deduped)
assert "1. SI# CC7802 Dell Latitude 5550" in deduped
assert "Quantity: 30" in deduped
assert "Due Date: 06/10/2024" in deduped
assert "2. Dell Thunderbolt 4 Dock – WD22TB4" in deduped
print("\nALL 3 TESTS PASSED!")
