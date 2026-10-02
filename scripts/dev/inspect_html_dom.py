import sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding="utf-8")

p = list(Path("Bid2").glob("*.html"))[0]
with open(p, "r", encoding="utf-8", errors="ignore") as f:
    html_content = f.read()
soup = BeautifulSoup(html_content, "html.parser")
desc_el = soup.find(text=lambda t: t and "CC7802" in t)
if desc_el:
    parent = desc_el.parent
    for _ in range(4):
        if parent.name in ['div', 'table', 'dl', 'section']:
            print(f"Parent <{parent.name}> class={parent.get('class')}:")
            print(parent.prettify()[:1000])
            break
        parent = parent.parent
