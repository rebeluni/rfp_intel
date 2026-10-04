"""
Extractor Agent (Phase 3).
Coordinates field retrieval and extraction across all target fields in config/fields.yaml.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml
from config.settings import settings
from search.hybrid_retriever import HybridRetriever, SearchResult
from extraction.models import FieldOutput, ExtractedField, FieldSource, FieldEvidence
from extraction.llm_client import BaseLLMClient, get_llm_client

logger = logging.getLogger(__name__)


class ExtractorAgent:
    """Agent responsible for gathering evidence and extracting structured fields."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        llm_client: Optional[BaseLLMClient] = None,
        fields_path: Optional[Path] = None,
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = llm_client or get_llm_client()
        self.fields_path = fields_path or (settings.PROJECT_ROOT / "config" / "fields.yaml")
        self.field_definitions = self._load_fields()

    def _load_fields(self) -> Dict[str, Any]:
        """Load field schemas dynamically from fields.yaml."""
        if not self.fields_path.exists():
            logger.error(f"Fields configuration not found at {self.fields_path}")
            return {}
        try:
            with open(self.fields_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("fields", {})
        except Exception as e:
            logger.error(f"Failed to parse fields.yaml: {e}")
            return {}

    def retrieve_evidence_for_field(
        self,
        field_name: str,
        field_def: Dict[str, Any],
        bid_id: str,
        top_k: int = 5,
        exclude_doc_type: Optional[str] = "addendum",
    ) -> List[Dict[str, Any]]:
        """Retrieve top candidate chunks for a specific field filtered by bid_id."""
        import re

        # Task A7: contact_info searches across all chunks of the bid for name, email, and phone
        if field_name == "contact_info" and hasattr(self.retriever, "bm25_index") and self.retriever.bm25_index.chunks:
            contact_chunks = []
            for chk in self.retriever.bm25_index.chunks:
                meta = chk.metadata
                if meta.bid_id != bid_id:
                    continue
                if exclude_doc_type:
                    dt_val = meta.doc_type.value if hasattr(meta.doc_type, "value") else str(meta.doc_type)
                    if dt_val.lower() == exclude_doc_type.lower():
                        continue
                t = chk.text
                has_email = "@" in t
                has_phone = bool(re.search(r"\b(?:\d{3}[-.\s]??\d{3}[-.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-.\s]??\d{4})\b", t))
                has_contact_kw = any(k in t.lower() for k in ["poc", "buyer", "contact", "procurement officer", "phone", "email"])
                if has_email or has_phone or (has_contact_kw and ("name" in t.lower() or "address" in t.lower())):
                    score = 2.0 if (has_email and has_phone) else (1.5 if (has_email or has_phone) else 1.0)
                    contact_chunks.append((chk, score))

            if contact_chunks:
                contact_chunks.sort(key=lambda x: x[1], reverse=True)
                passages = []
                for chk, score in contact_chunks[:top_k]:
                    passages.append({
                        "chunk_id": chk.chunk_id,
                        "file_name": chk.metadata.file_name,
                        "page_number": chk.metadata.page_number,
                        "text": chk.text,
                        "score": score,
                        "section": chk.metadata.section,
                        "doc_type": chk.metadata.doc_type.value if hasattr(chk.metadata.doc_type, "value") else str(chk.metadata.doc_type),
                    })
                return passages

        hints = field_def.get("query_expansion_hints", [field_name])
        # Formulate query from field name and top 2 hints
        query = f"{field_name} {' '.join(hints[:2])}"

        results: List[SearchResult] = self.retriever.search(
            query=query,
            bid_id=bid_id,
            top_k=top_k,
            exclude_doc_type=exclude_doc_type,
            mode="hybrid",
        )

        passages = []
        for r in results:
            passages.append({
                "chunk_id": r.chunk_id,
                "file_name": r.file_name,
                "page_number": r.page_number,
                "text": r.text,
                "score": r.rerank_score or r.rrf_score,
                "section": r.section,
                "doc_type": r.doc_type,
            })
        return passages

    def extract_field(
        self,
        field_name: str,
        bid_id: str,
        top_k: int = 5
    ) -> Tuple[ExtractedField, List[Dict[str, Any]]]:
        """Retrieve evidence and extract a single field."""
        field_def = self.field_definitions.get(field_name, {})
        evidence = self.retrieve_evidence_for_field(field_name, field_def, bid_id, top_k=top_k)
        extracted = self.llm_client.extract_field(field_name, field_def, evidence)
        extracted.specialist = field_def.get("specialist")
        return extracted, evidence

    def extract_all_fields(
        self,
        bid_id: str,
        top_k: int = 5
    ) -> Tuple[Dict[str, ExtractedField], Dict[str, List[Dict[str, Any]]]]:
        """Extract all configured fields for a bid package."""
        logger.info(f"Extracting {len(self.field_definitions)} fields for bid '{bid_id}'...")
        extracted_map: Dict[str, ExtractedField] = {}
        evidence_map: Dict[str, List[Dict[str, Any]]] = {}

        for f_name, f_def in self.field_definitions.items():
            ext, ev = self.extract_field(f_name, bid_id, top_k=top_k)
            extracted_map[f_name] = ext
            evidence_map[f_name] = ev

        return extracted_map, evidence_map
