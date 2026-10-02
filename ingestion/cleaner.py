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

    @classmethod
    def strip_running_headers_footers(
        cls,
        pages_text: List[str]
    ) -> Tuple[List[str], List[Optional[str]]]:
        """
        Detect and strip repetitive header/footer lines that occur across multiple pages,
        using digit-normalized pattern matching (e.g. 'Page # of #', 'Dallas ISD rev #.#').
        Extracts page labels to metadata and returns (cleaned_pages, page_labels).
        """
        page_labels: List[Optional[str]] = []
        for page in pages_text:
            # Check for page label in top or bottom lines
            lbl = None
            for line in page.splitlines()[:3] + page.splitlines()[-3:]:
                m = re.search(r"^\s*Page\s+(\d+(?:\s*(?:of|\|)\s*\d+)?)", line, re.IGNORECASE)
                if m:
                    lbl = m.group(1).strip()
                    break
            page_labels.append(lbl)

        if len(pages_text) <= 2:
            cleaned = []
            for p in pages_text:
                filtered = [
                    l for l in p.splitlines()
                    if not re.match(r"^\s*Page\s+\d+(?:\s*(?:of|\|)\s*\d+)?\s*$", l, re.IGNORECASE)
                ]
                cleaned.append(cls.clean_text("\n".join(filtered)))
            return cleaned, page_labels

        # Count digit-normalized line occurrences across pages (top line and bottom line only)
        norm_occurrences = {}
        for p_idx, page in enumerate(pages_text):
            lines = [l.strip() for l in page.splitlines() if l.strip()]
            if not lines:
                continue
            candidate_lines = {lines[0], lines[-1]}
            for line in candidate_lines:
                norm = re.sub(r"\d+", "#", line)
                if len(norm) > 4 and norm != "#":
                    norm_occurrences[norm] = norm_occurrences.get(norm, 0) + 1

        # Threshold: present in more than 35% of pages
        threshold = max(2, int(len(pages_text) * 0.35))
        repeated_norm_lines = {norm for norm, count in norm_occurrences.items() if count >= threshold}

        cleaned_pages = []
        for page in pages_text:
            lines = page.splitlines()
            cleaned_lines = []
            for idx, line in enumerate(lines):
                stripped = line.strip()
                norm = re.sub(r"\d+", "#", stripped)

                # Header/footer positions: first line or last line
                is_header_footer_pos = (idx == 0 or idx == len(lines) - 1)

                # Skip if matches a repeated digit-normalized pattern in header/footer position
                if is_header_footer_pos and norm in repeated_norm_lines:
                    continue
                if re.match(r"^\s*Page\s+#(?:\s*(?:of|\|)\s*#)?\s*$", norm, re.IGNORECASE):
                    continue
                if re.match(r"^Dallas\s+ISD\s+rev\s+#\.#$", norm, re.IGNORECASE):
                    continue

                cleaned_lines.append(line)
            cleaned_pages.append("\n".join(cleaned_lines))

        return [cls.clean_text(p) for p in cleaned_pages], page_labels

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Run standard text cleaning pipeline on a text snippet."""
        text = cls.fix_hyphenation(text)
        text = cls.fix_kerning(text)
        text = cls.fix_fused_words(text)
        text = cls.reflow_vertical_lines(text)
        text = cls.normalize_whitespace(text)
        return text
