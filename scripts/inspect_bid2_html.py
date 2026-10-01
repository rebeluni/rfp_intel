import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.stdout.reconfigure(encoding="utf-8")

p = list(Path("Bid2").glob("*.html"))[0]
print(f"File: {p.name}, size: {p.stat().st_size / 1024:.1f} KB")

t0 = time.time()
with open(p, "r", encoding="utf-8", errors="ignore") as f:
    html_content = f.read()
print(f"Read file: {time.time() - t0:.2f}s")

t0 = time.time()
from bs4 import BeautifulSoup
soup = BeautifulSoup(html_content, "html.parser")
print(f"BS4 parsed: {time.time() - t0:.2f}s")

t0 = time.time()
for tag in soup(["script", "style", "nav", "noscript"]):
    tag.decompose()
print(f"Decompose: {time.time() - t0:.2f}s")

from ingestion.cleaner import TextCleaner
from ingestion.html_parser import HTMLParser
t0 = time.time()
kv = HTMLParser._extract_key_value_dict(soup)
print(f"KV extracted ({len(kv)} keys): {time.time() - t0:.2f}s")
for k, v in kv.items():
    print(f"  {k}: {v[:60]}")
