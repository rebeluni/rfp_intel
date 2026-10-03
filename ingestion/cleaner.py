"""
Text cleaning and normalization utilities for parsed RFP documents.
Handles whitespace normalization, hyphenation repair, kerning artifact repair,
and digit-normalized running header/footer stripping.
"""

import re
from typing import List, Optional, Tuple


class TextCleaner:
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Replace non-breaking spaces, zero-width spaces, and excess whitespace."""
        if not text:
            return ""
        # Remove zero-width spaces and soft hyphens
        text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xad", "")
        # Replace private-use area characters (bullets, boxes, symbols)
        text = re.sub(r"[\uf000-\uf8ff]", "* ", text)
        # Replace non-breaking spaces with standard space
        text = text.replace("\xa0", " ")
        # Replace multiple horizontal spaces/tabs with single space
        text = re.sub(r"[ \t]+", " ", text)
        # Strip trailing spaces before newlines
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        # Normalize 3+ newlines down to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def fix_hyphenation(text: str) -> str:
        """
        Fix hyphenated line breaks (e.g. 'com-\nputing' -> 'computing').
        Preserves intentional hyphenated words (e.g. 'state-of-the-art').
        """
        if not text:
            return ""
        # Match lowercase letters followed by hyphen, newline, and lowercase letter
        return re.sub(r"([a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,})", r"\1\2", text)

    @staticmethod
    def fix_kerning(text: str) -> str:
        """
        Fix specific kerning/font artifacts where letters are split by small whitespace gaps,
        only when the merged token is a dictionary word and fragments are not.
        Examples: 'Post Bur n' -> 'Post Burn', 'Se lect' -> 'Select', 'FACTOR Y' -> 'FACTORY', 'Elig ible' -> 'Eligible'.
        Does NOT touch valid English words like 'provide a', 'consider a', 'data', 'extra', 'REMAIN', 'CERTAIN'.
        """
        if not text:
            return ""
        # Specific non-word fragment joins
        text = re.sub(r"\bBur\s+n\b", "Burn", text, flags=re.IGNORECASE)
        text = re.sub(r"\b([Ss]e)\s+(lect(?:ion|ed|ing|s)?)\b", r"\1\2", text, flags=re.IGNORECASE)
        text = re.sub(r"\b([Ee]lig)\s+(ible|ibility)\b", r"\1\2", text, flags=re.IGNORECASE)
        text = re.sub(r"\bFACTOR\s+Y\b", "FACTORY", text)
        # Fused trailing Roman numeral/pronoun I on uppercase heading words (e.g. AFFIRMATIONI -> AFFIRMATION I)
        text = re.sub(r"\b([A-Z]{4,})I\b(?=\s+FURTHER|\s*$)", r"\1 I", text)
        return text

    @staticmethod
    def fix_fused_words(text: str) -> str:
        """
        Safe word fusion repair. Only acts on verified non-words; never splits valid words
        like REMAIN, CERTAIN, data, extra.
        """
        if not text:
            return ""
        # Fused uppercase pronoun in affidavits
        text = re.sub(r"\b(AUTHORITY|TAXATION|AFFIRMATION|VALID)I\b", r"\1 I", text)
        return text

    @staticmethod
    def reflow_vertical_lines(text: str) -> str:
        """
        Reflow one-word-per-line text extracted from narrow table/form columns
        into coherent sentences and paragraphs.
        """
        if not text:
            return ""
        lines = text.splitlines()
        reflowed = []
        buf = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if buf:
                    reflowed.append(" ".join(buf))
                    buf = []
                reflowed.append("")
                continue

            # Skip markdown table rows and headers
            if stripped.startswith("|") or stripped.endswith("|"):
                if buf:
                    reflowed.append(" ".join(buf))
                    buf = []
                reflowed.append(stripped)
                continue

            # Check if line is a single short word or fragment (< 22 chars, <= 2 words, no colon at end, not a list item)
            words = stripped.split()
            is_fragment = (
                len(words) <= 2
                and len(stripped) < 22
                and not stripped.endswith(":")
                and not stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "*", "-", "•", "(", "#"))
                and not stripped.isupper()
            )

            if is_fragment:
                buf.append(stripped)
            else:
                if buf:
                    buf.append(stripped)
                    reflowed.append(" ".join(buf))
                    buf = []
                else:
                    reflowed.append(stripped)

        if buf:
            reflowed.append(" ".join(buf))

        # Collapse excess empty lines
        return re.sub(r"\n{3,}", "\n\n", "\n".join(reflowed))

    @staticmethod
    def fix_split_urls_and_emails(text: str) -> str:
        """
        Rejoin emails and URLs split across lines by PDF layout / line wrapping.
        Example: 'thawkins@treasurer.state.md\\n.us' -> 'thawkins@treasurer.state.md.us'
        'https://procurement.maryland.gov/emma-\\nqrgs/' -> 'https://procurement.maryland.gov/emma-qrgs/'
        """
        if not text:
            return ""
        # Split email domain: name@domain\n.us or user@treasurer.state.md\n.us
        text = re.sub(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)\n\s*(\.[a-zA-Z]{2,}\b)", r"\1\2", text)
        # Split email domain where dot precedes newline: state.\nmd.us or treasurer.state.\nmd.us
        text = re.sub(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]*\.)\n\s*([a-zA-Z0-9.-]+\b)", r"\1\2", text)
        # Split email before @: name\n@domain.com
        text = re.sub(r"([A-Za-z0-9._%+-]+)\n\s*(@[A-Za-z0-9.-]+\.[a-zA-Z]{2,}\b)", r"\1\2", text)
        # Split URL with trailing hyphen: https://...foo-\nbar
        text = re.sub(r"(https?://[^\s]+)-\n\s*([a-zA-Z0-9_\-./?=&%#]+)", r"\1-\2", text)
        # Split URL at slash: https://...foo/\nbar
        text = re.sub(r"(https?://[^\s]+/\b)\n\s*([a-zA-Z0-9_\-./?=&%#]+)", r"\1\2", text)
        return text

    @classmethod
    def strip_running_headers_footers(
        cls,
        pages_text: List[str]
    ) -> Tuple[List[str], List[Optional[str]]]:
        """
        Detect and strip repetitive header/footer lines that occur across multiple pages,
        using digit-normalized pattern matching (e.g. 'Page # of #', 'Dallas ISD rev #.#',
        'Purchase Order Request for Proposals (PORFP)').
        Also strips bare page numbers (solitary digits) in the top/bottom header-footer zones.
        Extracts page labels to metadata and returns (cleaned_pages, page_labels).
        """
        page_labels: List[Optional[str]] = []
        for page in pages_text:
            lbl = None
            for line in page.splitlines()[:5] + page.splitlines()[-5:]:
                m = re.search(r"^\s*Page\s+(\d+(?:\s*(?:of|\|)\s*\d+)?)", line, re.IGNORECASE)
                if m:
                    lbl = m.group(1).strip()
                    break
            page_labels.append(lbl)

        # Count digit-normalized line occurrences across pages in candidate header/footer positions
        norm_occurrences: dict = {}
        for page in pages_text:
            lines = [l.strip() for l in page.splitlines() if l.strip()]
            if not lines:
                continue
            if len(lines) <= 4:
                candidates = [lines[0]] + ([lines[-1]] if len(lines) > 1 else [])
            else:
                candidates = lines[:3] + lines[-2:]
            for line in set(candidates):
                norm = re.sub(r"\d+", "#", line)
                if len(norm) > 4 and norm != "#":
                    norm_occurrences[norm] = norm_occurrences.get(norm, 0) + 1

        # Threshold: present in 35% or more of pages (min 2 occurrences)
        threshold = max(2, int(len(pages_text) * 0.35))
        repeated_norm_lines = {norm for norm, count in norm_occurrences.items() if count >= threshold}

        cleaned_pages = []
        for page in pages_text:
            lines = page.splitlines()
            non_empty_indices = [i for i, l in enumerate(lines) if l.strip()]
            if len(non_empty_indices) <= 4:
                top_indices = {non_empty_indices[0]} if non_empty_indices else set()
                bottom_indices = {non_empty_indices[-1]} if len(non_empty_indices) > 1 else set()
            else:
                top_indices = set(non_empty_indices[:3])
                bottom_indices = set(non_empty_indices[-2:])
            hdr_ftr_indices = top_indices | bottom_indices

            cleaned_lines = []
            for idx, line in enumerate(lines):
                stripped = line.strip()
                norm = re.sub(r"\d+", "#", stripped)

                is_hdr_ftr = idx in hdr_ftr_indices

                # Strip bare page numbers in top/bottom header/footer zones
                if is_hdr_ftr and re.match(r"^\d{1,3}$", stripped):
                    continue

                # Skip if matches a repeated digit-normalized pattern in header/footer position
                if is_hdr_ftr and norm in repeated_norm_lines:
                    continue
                if is_hdr_ftr and re.match(r"^\s*Page\s+#(?:\s*(?:of|\|)\s*#)?\s*$", norm, re.IGNORECASE):
                    continue
                if is_hdr_ftr and re.match(r"^Dallas\s+ISD\s+rev\s+#\.#$", norm, re.IGNORECASE):
                    continue

                cleaned_lines.append(line)
            cleaned_pages.append("\n".join(cleaned_lines))

        return [cls.clean_text(p) for p in cleaned_pages], page_labels

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Run standard text cleaning pipeline on a text snippet."""
        text = cls.fix_hyphenation(text)
        text = cls.fix_split_urls_and_emails(text)
        text = cls.fix_kerning(text)
        text = cls.fix_fused_words(text)
        text = cls.reflow_vertical_lines(text)
        text = cls.normalize_whitespace(text)
        return text
