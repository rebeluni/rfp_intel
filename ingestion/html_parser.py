"""
HTML Bid Page Parser.
Parses HTML procurement and portal pages using BeautifulSoup, converting tables to markdown
and capturing key-value lists (definition lists, label-value pairs).
"""

from pathlib import Path
from typing import List, Tuple
from bs4 import BeautifulSoup
from ingestion.cleaner import TextCleaner
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.models import DocType, ParsedDocument, ParsedPage, ParsedTable


class HTMLParser:
    """Parses HTML bid documents while preserving tabular and metadata structure."""

    @classmethod
    def parse(cls, file_path: Path, bid_id: str) -> ParsedDocument:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")

        # Strip scripts, styles, navigations, footers
        for tag in soup(["script", "style", "nav", "noscript"]):
            tag.decompose()

        # Extract structured tables
        parsed_tables = []
        for tbl in soup.find_all("table"):
            md_table = cls._table_to_markdown(tbl)
            if md_table:
                parsed_tables.append(ParsedTable(page_number=1, markdown=md_table))

        # Extract structured key-value pairs (common in BidNet Direct and similar portals)
        kv_pairs = cls._extract_key_value_pairs(soup)

        # Extract body text
        body_text_lines = []
        if kv_pairs:
            body_text_lines.append("### Bid Portal Metadata & Information")
            for k, v in kv_pairs:
                body_text_lines.append(f"- **{k}**: {v}")
            body_text_lines.append("\n")

        # Append markdown tables
        if parsed_tables:
            body_text_lines.append("### Tables")
            for t in parsed_tables:
                body_text_lines.append(t.markdown)
                body_text_lines.append("\n")

        # Get main text
        raw_text = soup.get_text(separator="\n")
        cleaned_main = TextCleaner.clean_text(raw_text)

        full_text = "\n".join(body_text_lines) + "\n\n" + cleaned_main
        cleaned_text = TextCleaner.normalize_whitespace(full_text)

        page = ParsedPage(
            page_number=1,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            tables=parsed_tables,
            is_scanned=False
        )

        doc_date = MetadataClassifier._extract_date(full_text)

        return ParsedDocument(
            file_name=file_path.name,
            file_path=str(file_path),
            bid_id=bid_id,
            doc_type=DocType.BID_PAGE,
            doc_type_confidence=0.98,
            addendum_number=None,
            document_date=doc_date,
            pages=[page],
            chunks=[]
        )

    @classmethod
    def _extract_key_value_pairs(cls, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract definition lists and label/value styled div structures."""
        kv = []

        # Definition lists
        for dl in soup.find_all("dl"):
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    k = TextCleaner.clean_text(dt.get_text())
                    v = TextCleaner.clean_text(dd.get_text())
                    if k and v:
                        kv.append((k, v))

        # Div-based label-value patterns (e.g. BidNet direct)
        labels = soup.find_all(class_=lambda c: c and any(sub in c.lower() for sub in ["label", "field-label", "bid-label"]))
        for lbl in labels:
            val_node = lbl.find_next_sibling()
            if val_node:
                k = TextCleaner.clean_text(lbl.get_text())
                v = TextCleaner.clean_text(val_node.get_text())
                if k and v and len(k) < 80:
                    kv.append((k, v))

        return kv

    @classmethod
    def _table_to_markdown(cls, table_tag) -> str:
        """Converts an HTML table element to a markdown table."""
        rows = []
        for tr in table_tag.find_all("tr"):
            cells = [TextCleaner.clean_text(c.get_text()) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)

        if not rows:
            return ""

        # Normalize column counts
        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return ""

        padded_rows = [r + [""] * (max_cols - len(r)) for r in rows]

        headers = padded_rows[0]
        # Replace empty header names with Col 1, Col 2, etc.
        headers = [h if h else f"Col {i+1}" for i, h in enumerate(headers)]

        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for r in padded_rows[1:]:
            # Escape pipe chars inside cells
            safe_cells = [c.replace("|", "\\|").replace("\n", " ") for c in r]
            md_lines.append("| " + " | ".join(safe_cells) + " |")

        return "\n".join(md_lines)
