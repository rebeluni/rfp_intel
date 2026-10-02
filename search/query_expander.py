"""
Query Expander driven by config/fields.yaml.
Dynamically injects field definitions, expansion hints, and procurement synonyms
into search queries to maximize retrieval recall without modifying user intent.
"""

import logging
import re
from typing import Dict, List, Set
from config.settings import load_fields_config

logger = logging.getLogger(__name__)


class QueryExpander:
    """Expands queries using field definitions and expansion hints from fields.yaml."""

    def __init__(self):
        self.fields_config: Dict[str, dict] = load_fields_config()
        self._build_expansion_index()

    def _build_expansion_index(self) -> None:
        """Map keywords and phrases to their field expansion hints."""
        self.term_to_hints: Dict[str, List[str]] = {}

        for field_name, field_def in self.fields_config.items():
            hints = field_def.get("query_expansion_hints", [])
            desc = field_def.get("description", "")

            # Index field name (e.g. "Bid Number" -> "bid number", "bid", "number")
            norm_name = field_name.lower().strip()
            self.term_to_hints[norm_name] = hints

            # Index each hint back to all other sibling hints
            for h in hints:
                norm_h = h.lower().strip()
                if norm_h not in self.term_to_hints:
                    self.term_to_hints[norm_h] = [field_name] + [other for other in hints if other != h]

    def expand_query(self, query: str) -> str:
        """
        Generate an expanded query string incorporating relevant field hints.
        Preserves original query as the primary focus and appends top expansion terms.
        """
        if not query:
            return ""

        query_lower = query.lower()
        matched_hints: Set[str] = set()

        for key, hints in self.term_to_hints.items():
            # Check for exact term or word boundary match
            if re.search(r"\b" + re.escape(key) + r"\b", query_lower):
                matched_hints.update(hints[:3])  # top 3 hints per matched term

        # Avoid redundant expansion if already present in query
        filtered_hints = [
            h for h in matched_hints
            if h.lower() not in query_lower
        ]

        if filtered_hints:
            expanded = f"{query} {' '.join(filtered_hints[:4])}"
            return expanded

        return query
