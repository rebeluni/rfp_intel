"""
Specialized Tokenizer for BM25 Retrieval.
Keeps hyphenated and alphanumeric tokens whole AND adds split parts.
Examples:
  - 'JA-207652' -> ['ja-207652', 'ja', '207652']
  - '210-BLYZ' -> ['210-blyz', '210', 'blyz']
  - 'thawkins@treasurer.state.md.us' -> ['thawkins@treasurer.state.md.us', 'thawkins', 'treasurer', 'state', 'md', 'us']
  - 'BPM044557' -> ['bpm044557', 'bpm', '044557']
"""

import re
from typing import List


def tokenize_bm25(text: str) -> List[str]:
    """
    Tokenize text for BM25 indexing and querying.
    Preserves whole compound tokens while also indexing their subcomponents.
    """
    if not text:
        return []

    # Extract all alphanumeric sequences with internal hyphens, dots, underscores, or @ signs
    raw_tokens = re.findall(r"[A-Za-z0-9]+(?:[-_.@][A-Za-z0-9]+)*", text.lower())
    result_tokens: List[str] = []

    for t in raw_tokens:
        result_tokens.append(t)
        sub_parts = set()

        # 1. Punctuation splits (hyphen, dot, underscore, @)
        if any(sep in t for sep in ["-", ".", "_", "@"]):
            parts = re.split(r"[-_.@]+", t)
            for p in parts:
                if p and p != t:
                    sub_parts.add(p)

        # 2. Alphanumeric transitions (e.g. 'bpm044557' -> 'bpm', '044557')
        alpha_num_parts = re.findall(r"[a-z]+|[0-9]+", t)
        if 1 < len(alpha_num_parts) <= 4:
            for an in alpha_num_parts:
                if an != t and len(an) >= 2:
                    sub_parts.add(an)

        result_tokens.extend(sub_parts)

    return result_tokens


class BM25Tokenizer:
    """Class wrapper around tokenize_bm25 for object-oriented interfaces."""
    def tokenize(self, text: str) -> List[str]:
        return tokenize_bm25(text)

    def __call__(self, text: str) -> List[str]:
        return tokenize_bm25(text)
