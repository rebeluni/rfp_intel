"""
Text cleaning and normalization utilities for parsed RFP documents.
Handles whitespace normalization, hyphenation repair, and header/footer stripping.
"""

import re
from typing import List


class TextCleaner:
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Replace non-breaking spaces, zero-width spaces, and excess whitespace."""
        if not text:
            return ""
        # Remove zero-width spaces and soft hyphens
        text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xad", "")
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
    def strip_running_headers_footers(pages_text: List[str]) -> List[str]:
        """
        Detect and strip repetitive header/footer lines that occur across multiple pages.
        Identifies exact or near-identical single lines that appear on > 50% of multi-page docs.
        """
        if len(pages_text) <= 2:
            return [TextCleaner.normalize_whitespace(p) for p in pages_text]

        # Count line frequencies across pages
        line_occurrences = {}
        for p_idx, page in enumerate(pages_text):
            lines = [l.strip() for l in page.splitlines() if l.strip()]
            # Look only at top 3 lines (headers) and bottom 3 lines (footers)
            candidate_lines = set(lines[:3] + lines[-3:])
            for line in candidate_lines:
                # Ignore very short lines (like numbers or empty)
                if len(line) > 5 and not line.isdigit():
                    line_occurrences[line] = line_occurrences.get(line, 0) + 1

        # Threshold: present in more than 40% of pages
        threshold = max(2, int(len(pages_text) * 0.40))
        repeated_lines = {line for line, count in line_occurrences.items() if count >= threshold}

        cleaned_pages = []
        for page in pages_text:
            cleaned_lines = []
            for line in page.splitlines():
                stripped = line.strip()
                # Skip if it is a repeated header/footer or standalone page counter like 'Page 1 of 5'
                if stripped in repeated_lines:
                    continue
                if re.match(r"^Page\s+\d+(\s+of\s+\d+|\s*\|\s*\d+)?$", stripped, re.IGNORECASE):
                    continue
                cleaned_lines.append(line)
            cleaned_pages.append("\n".join(cleaned_lines))

        return [TextCleaner.normalize_whitespace(p) for p in cleaned_pages]

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Run standard text cleaning pipeline on a text snippet."""
        text = cls.fix_hyphenation(text)
        text = cls.normalize_whitespace(text)
        return text
