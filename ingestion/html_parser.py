"""
HTML Bid Page Parser.
Parses HTML procurement and portal pages using BeautifulSoup, converting tables to markdown,
extracting key procurement fields (Published Date, Closing Date, Contact Info, Solicitation Number),
and ensuring portal metadata chunks are complete and untruncated.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from ingestion.cleaner import TextCleaner
from ingestion.metadata_classifier import MetadataClassifier
from ingestion.models import DocType, DocumentMetadata, ParsedDocument, ParsedPage, ParsedTable


class HTMLParser:
    """Parses HTML bid documents while preserving tabular, metadata, and contact structure."""

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
        kv_dict = cls._extract_key_value_dict(soup)

        # Extract contact information specifically (name, email, phone)
        contact_info = cls._extract_contact_info(soup, kv_dict)
        if contact_info:
            kv_dict["Contact Info"] = contact_info

        # Normalize specific date labels
        published_date = None
        for k in ["Publication", "Publication Date", "Date Issued", "Posted Date", "Published Date"]:
            if k in kv_dict and kv_dict[k]:
                published_date = kv_dict[k]
                break

        closing_date = None
        for k in ["Closing Date", "Due Date", "Submission Deadline", "Proposal Due Date"]:
            if k in kv_dict and kv_dict[k]:
                closing_date = kv_dict[k]
                break

        # Build clean labeled sections
        structured_sections: List[str] = []

        # 1. Procurement Metadata Section
        meta_lines = ["### Portal Bid Details & Schedule"]
        for label, val in kv_dict.items():
            if label not in ["Description", "Scope of Work"] and val:
                meta_lines.append(f"- **{label}**: {val}")
        structured_sections.append("\n".join(meta_lines))

        # 2. Scope & Description Section (if available)
        desc_val = kv_dict.get("Description") or kv_dict.get("Scope of Work")
        if not desc_val:
            # Fallback to main body paragraphs
            desc_div = soup.find(class_=lambda c: c and "description" in c.lower())
            if desc_div:
                desc_val = TextCleaner.clean_text(desc_div.get_text())

        if desc_val:
            structured_sections.append(f"### Scope & Description\n{desc_val}")

        # 3. Structured Tables
        if parsed_tables:
            table_lines = ["### Portal Specifications & Line Items"]
            for t in parsed_tables:
                table_lines.append(t.markdown)
            structured_sections.append("\n\n".join(table_lines))

        # 4. Any remaining text not in kv_dict
        raw_text = soup.get_text(separator="\n")
        cleaned_main = TextCleaner.clean_text(raw_text)

        full_cleaned_content = "\n\n".join(structured_sections)
        if not full_cleaned_content.strip():
            full_cleaned_content = cleaned_main

        # Extract published date fallback if not found in kv_dict
        if not published_date:
            published_date = MetadataClassifier._extract_date(full_cleaned_content)

        page = ParsedPage(
            page_number=1,
            raw_text=raw_text,
            cleaned_text=TextCleaner.normalize_whitespace(full_cleaned_content),
            tables=parsed_tables,
            is_scanned=False
        )

        return ParsedDocument(
            file_name=file_path.name,
            file_path=str(file_path),
            bid_id=bid_id,
            doc_type=DocType.BID_PAGE,
            doc_type_confidence=0.98,
            addendum_number=None,
            document_date=published_date,
            pages=[page],
            chunks=[]
        )

    @classmethod
    def _extract_key_value_dict(cls, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract definition lists and label/value styled structures into an ordered dictionary."""
        kv: Dict[str, str] = {}

        # 1. Definition lists
        for dl in soup.find_all("dl"):
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    k = TextCleaner.clean_text(dt.get_text())
                    v = TextCleaner.clean_text(dd.get_text())
                    if k and v and len(k) < 80:
                        kv[k] = v

        # 2. Div-based label-value patterns (e.g. BidNet direct)
        labels = soup.find_all(class_=lambda c: c and any(sub in c.lower() for sub in ["label", "field-label", "bid-label"]))
        for lbl in labels:
            val_node = lbl.find_next_sibling()
            if val_node:
                k = TextCleaner.clean_text(lbl.get_text())
                v = TextCleaner.clean_text(val_node.get_text())
                if k and v and len(k) < 80 and not k.startswith("-"):
                    # Standardize label
                    norm_k = re.sub(r"[:\s]+$", "", k)
                    if norm_k not in kv:
                        kv[norm_k] = v

        return kv

    @classmethod
    def _extract_contact_info(cls, soup: BeautifulSoup, kv_dict: Dict[str, str]) -> Optional[str]:
        """Generic detection of contact name, email address, and phone number."""
        text = soup.get_text()

        # Find emails
        email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
        email = email_match.group(0) if email_match else None

        # Find phone numbers
        phone_match = re.search(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b", text)
        phone = phone_match.group(0) if phone_match else None

        # Contact name / department: inspect kv keys or specific contact labels
        contact_name = None
        for k, v in kv_dict.items():
            if any(term in k.lower() for term in ["contact", "buyer", "procurement officer", "agent"]):
                contact_name = v
                break

        # Fallback if label itself was contact name (as seen in some portal html structures)
        if not contact_name:
            for k in kv_dict.keys():
                if phone and (phone in k or (k in kv_dict and kv_dict[k] == phone)):
                    # Previous sibling or related key
                    contact_name = k.replace(phone, "").strip()
                    break

        parts = []
        if contact_name:
            parts.append(contact_name)
        if phone:
            parts.append(phone)
        if email:
            parts.append(email)

        return " | ".join(parts) if parts else None

    @classmethod
    def _table_to_markdown(cls, table_tag) -> str:
        """Converts an HTML table element to a clean markdown table, dropping synthetic Col_N headers."""
        rows = []
        for tr in table_tag.find_all("tr"):
            cells = [TextCleaner.clean_text(c.get_text()) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)

        if not rows or len(rows) < 2:
            return ""

        # Check column population: real tables must have >= 2 populated columns
        max_cols = max(len(r) for r in rows)
        if max_cols < 2:
            return ""

        col_populated_count = 0
        for col_idx in range(max_cols):
            has_val = any(len(r) > col_idx and r[col_idx].strip() for r in rows)
            if has_val:
                col_populated_count += 1

        if col_populated_count < 2:
            return ""

        padded_rows = [r + [""] * (max_cols - len(r)) for r in rows]

        # Header handling: use first row, NEVER invent Col_N
        headers = padded_rows[0]
        if not any(h.strip() for h in headers):
            # If header is totally empty, check if rows are key-value
            if max_cols == 2:
                headers = ["Field", "Value"]
            else:
                return ""  # Skip formatting as table; render as prose

        md_lines = []
        md_lines.append("| " + " | ".join(h.replace("|", "\\|") for h in headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for r in padded_rows[1:]:
            safe_cells = [c.replace("|", "\\|").replace("\n", " ") for c in r]
            md_lines.append("| " + " | ".join(safe_cells) + " |")

        return "\n".join(md_lines)
