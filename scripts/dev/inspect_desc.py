import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
sys.stdout.reconfigure(encoding="utf-8")

from bs4 import BeautifulSoup
from ingestion.html_parser import HTMLParser

p = list(Path("Bid2").glob("*.html"))[0]
with open(p, "r", encoding="utf-8", errors="ignore") as f:
    html_content = f.read()
soup = BeautifulSoup(html_content, "html.parser")
for tag in soup(["script", "style", "nav", "noscript"]):
    tag.decompose()
kv = HTMLParser._extract_key_value_dict(soup)
print("=== RAW DESCRIPTION ===")
print(repr(kv.get("Description")))
print("=== FORMATTED DESCRIPTION ===")
print(kv.get("Description"))
