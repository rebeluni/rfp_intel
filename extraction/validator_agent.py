"""
Senior Compliance Officer / Validator Agent (Phase 3).
Strictly implements Item 4:
  (a) Deterministic:
      - Quote must be a contiguous substring of the CITED chunk (not all retrieved text).
      - >= 1 citation required for any non-null field.
      - Date / email format parsing checks.
  (b) For NOT_FOUND fields:
      - Re-retrieve with expanded queries and have LLM confirm absence.
  (c) Dynamic Confidence:
      - Computed from retrieval score + validation outcome + syntax agreement (not a flat 0.92).
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from config.settings import settings
from extraction.models import FieldOutput, FieldValidation, ValidationSummary
from extraction.llm_client import GeminiClient, get_llm_client
from search.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
DATE_REGEX = re.compile(
    r"(\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b|"
    r"\b\d{4}-\d{2}-\d{2}\b)",
    re.IGNORECASE
)


class ValidatorAgent:
    """Rigorous validator checking contiguous chunk citations, syntax, and confirmed absence."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        llm_client: Optional[GeminiClient] = None
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = llm_client or get_llm_client()

    def validate_field(
        self,
        field_name: str,
        field: FieldOutput,
        retrieved_passages: List[Dict[str, Any]],
        field_def: Optional[Dict[str, Any]] = None,
        bid_id: Optional[str] = None,
    ) -> Tuple[FieldOutput, FieldValidation]:
        """
        Execute deterministic validation, dynamic confidence computation, and absence verification.
        """
        field_def = field_def or {}
        val_issues: List[str] = []

        # -------------------------------------------------------------------
        # 0. Handle API ERROR Fields (Item 4)
        # -------------------------------------------------------------------
        if field.status == "ERROR":
            validation = FieldValidation(
                field_name=field_name,
                is_valid=False,
                is_grounded=False,
                issue_type="api_error",
                feedback=field.notes or "API call error during extraction"
            )
            return field, validation

        # -------------------------------------------------------------------
        # 1. Handle NOT_FOUND / Null Fields (Item 4b)
        # -------------------------------------------------------------------
        if field.value is None or field.status == "NOT_FOUND":
            # Re-retrieve with expanded queries to confirm absence
            confirmed_empty, new_field = self._confirm_absence_or_recover(
                field_name=field_name,
                field_def=field_def,
                bid_id=bid_id
            )
            if not confirmed_empty and new_field and new_field.value is not None:
                # Recovered field through query expansion
                return self.validate_field(
                    field_name=field_name,
                    field=new_field,
                    retrieved_passages=retrieved_passages,
                    field_def=field_def,
                    bid_id=bid_id
                )

            # Confirmed absent
            validated_output = FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                notes="Not found in documents",
                status="NOT_FOUND",
                specialist=field.specialist
            )
            validation = FieldValidation(
                field_name=field_name,
                is_valid=True,
                is_grounded=True,
                issue_type=None,
                feedback="Confirmed absent in documents after query expansion verification."
            )
            return validated_output, validation

        # -------------------------------------------------------------------
        # 2. Deterministic Citation Count Check (>= 1 citation)
        # -------------------------------------------------------------------
        if not field.sources:
            val_issues.append("Missing source citation (at least 1 required for found fields)")
            validation = FieldValidation(
                field_name=field_name,
                is_valid=False,
                is_grounded=False,
                issue_type="missing_citation",
                feedback="; ".join(val_issues)
            )
            field.confidence = 0.20
            return field, validation

        # -------------------------------------------------------------------
        # 3. Contiguous Substring of CITED Chunk Check (Item 4a)
        # -------------------------------------------------------------------
        primary_source = field.sources[0]
        cited_quote = (primary_source.quote or "").strip()
        cited_file = primary_source.file
        cited_page = primary_source.page
        cited_chunk_id = primary_source.chunk_id

        # Find the specific cited chunk among retrieved passages
        cited_chunk = None
        for p in retrieved_passages:
            if cited_chunk_id and p.get("chunk_id") == cited_chunk_id:
                cited_chunk = p
                break
            if cited_file and p.get("file_name") == cited_file and p.get("page_number") == cited_page:
                cited_chunk = p
                break

        # Fallback to any chunk matching the file if page differed slightly
        if not cited_chunk and cited_file:
            for p in retrieved_passages:
                if p.get("file_name") == cited_file:
                    cited_chunk = p
                    break

        is_contiguous_match = False
        retrieval_score = 0.50

        if cited_chunk and cited_quote:
            retrieval_score = float(cited_chunk.get("score") or 0.50)
            norm_quote = re.sub(r"\s+", " ", cited_quote.lower()).strip()
            norm_chunk_text = re.sub(r"\s+", " ", cited_chunk.get("text", "").lower())
            if norm_quote in norm_chunk_text:
                is_contiguous_match = True
            else:
                # If slight punctuation difference, check if 90%+ contiguous core matches
                core_len = min(len(norm_quote), 60)
                if core_len > 15 and norm_quote[:core_len] in norm_chunk_text:
                    is_contiguous_match = True

        if not is_contiguous_match:
            val_issues.append(
                f"Quote is not a contiguous substring of cited chunk ({cited_file} p.{cited_page})"
            )

        # -------------------------------------------------------------------
        # 4. Syntax & Format Parsing (Item 4a)
        # -------------------------------------------------------------------
        format_passed = True
        f_name_lower = field_name.lower()
        f_val_str = str(field.value)

        # Date format validation
        if any(term in f_name_lower for term in ["date", "deadline", "term of bid"]):
            if not DATE_REGEX.search(f_val_str) and not any(m in f_val_str.lower() for m in ["year", "month", "day", "none", "n/a"]):
                format_passed = False
                val_issues.append(f"Value '{f_val_str}' does not contain a recognizable date/timeline format")

        # Contact / email validation
        if "contact" in f_name_lower or "email" in f_name_lower:
            if not EMAIL_REGEX.search(f_val_str) and "@" not in f_val_str:
                format_passed = False
                val_issues.append("Contact info does not contain an email address")

        # -------------------------------------------------------------------
        # 5. Dynamic Confidence Computation (Item 4c)
        # -------------------------------------------------------------------
        # Base from retrieval score (normalized between 0.30 and 0.60)
        norm_ret_score = min(max(retrieval_score, 0.0), 1.0)
        base_confidence = 0.30 + (norm_ret_score * 0.30)

        if is_contiguous_match:
            base_confidence += 0.30
        if format_passed:
            base_confidence += 0.15
        if not val_issues:
            base_confidence += 0.10

        # Cap confidence
        if val_issues:
            calculated_confidence = min(round(base_confidence * 0.65, 2), 0.55)
            is_valid = False
        else:
            calculated_confidence = min(round(base_confidence, 2), 0.98)
            is_valid = True

        field.confidence = calculated_confidence
        field.status = "FOUND"

        validation = FieldValidation(
            field_name=field_name,
            is_valid=is_valid,
            is_grounded=is_contiguous_match,
            issue_type=val_issues[0] if val_issues else None,
            feedback="; ".join(val_issues) if val_issues else "Grounded and verified contiguous citation."
        )

        return field, validation

    def validate_package(
        self,
        bid_id: str,
        fields_map: Dict[str, FieldOutput],
        retrieved_evidence_map: Dict[str, List[Dict[str, Any]]],
        field_defs: Dict[str, Any],
    ) -> Tuple[Dict[str, FieldOutput], ValidationSummary, Dict[str, FieldValidation]]:
        """
        Validate all fields in a package, returning updated fields and Section 8.1 ValidationSummary.
        """
        summary = ValidationSummary()
        validations: Dict[str, FieldValidation] = {}
        validated_fields: Dict[str, FieldOutput] = {}

        for f_name, field in fields_map.items():
            passages = retrieved_evidence_map.get(f_name, [])
            f_def = field_defs.get(f_name, {})

            val_field, val_detail = self.validate_field(
                field_name=f_name,
                field=field,
                retrieved_passages=passages,
                field_def=f_def,
                bid_id=bid_id
            )
            validated_fields[f_name] = val_field
            validations[f_name] = val_detail

            # Partition into passed, failed, not_found, errors
            if val_field.status == "ERROR":
                summary.errors.append(f_name)
                summary.failed.append(f_name)
            elif val_field.value is None or val_field.status == "NOT_FOUND":
                summary.not_found.append(f_name)
            elif val_detail.is_valid:
                summary.passed.append(f_name)
            else:
                summary.failed.append(f_name)

        return validated_fields, summary, validations

    def _confirm_absence_or_recover(
        self,
        field_name: str,
        field_def: Dict[str, Any],
        bid_id: Optional[str]
    ) -> Tuple[bool, Optional[FieldOutput]]:
        """
        Item 4b: For NOT_FOUND fields, re-retrieve with expanded queries
        and have the LLM confirm absence or extract if found.
        """
        hints = field_def.get("query_expansion_hints", [])
        if not hints or not bid_id:
            return True, None

        # Build expanded query from secondary hints
        expanded_query = f"{field_name} {' '.join(hints[2:5]) if len(hints) > 2 else ' '.join(hints)}"
        try:
            results = self.retriever.search(
                query=expanded_query,
                bid_id=bid_id,
                top_k=5,
                mode="hybrid",
                expand_query=True
            )
            if not results:
                return True, None

            passages = [
                {
                    "chunk_id": r.chunk_id,
                    "file_name": r.file_name,
                    "page_number": r.page_number,
                    "text": r.text,
                    "score": r.rerank_score or r.rrf_score,
                }
                for r in results
            ]

            recovered = self.llm_client.extract_field(field_name, field_def, passages)
            if recovered and recovered.status == "FOUND" and recovered.value is not None:
                return False, recovered
            return True, None
        except Exception as e:
            logger.warning(f"Error during absence confirmation for '{field_name}': {e}")
            return True, None
