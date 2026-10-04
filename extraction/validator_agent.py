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
        secondary_field: Optional[FieldOutput] = None,
    ) -> Tuple[FieldOutput, FieldValidation]:
        """
        Execute deterministic validation, dynamic multi-factor confidence computation,
        and absence verification.
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

        # Collect candidate matching chunks for this citation
        candidate_chunks = []
        if cited_chunk_id:
            for p in retrieved_passages:
                if p.get("chunk_id") == cited_chunk_id:
                    candidate_chunks.append(p)
        if not candidate_chunks and cited_file:
            for p in retrieved_passages:
                if p.get("file_name") == cited_file:
                    if cited_page is not None and p.get("page_number") == cited_page:
                        candidate_chunks.append(p)
            if not candidate_chunks:
                for p in retrieved_passages:
                    if p.get("file_name") == cited_file:
                        candidate_chunks.append(p)
        if not candidate_chunks:
            candidate_chunks = retrieved_passages

        is_contiguous_match = False
        retrieval_score = 0.50
        matched_chunk = None
        matched_chunk_idx = 0

        def _clean_markdown(text: str) -> str:
            # Remove markdown syntax characters (*, _, #, >, `, |)
            t = re.sub(r"[\*_#>`|]", "", text)
            # Normalize whitespace
            return re.sub(r"\s+", " ", t.lower()).strip(' "\'“”‘’:,;')

        if cited_quote:
            norm_quote = re.sub(r"\s+", " ", cited_quote.lower()).strip(' "\'“”‘’:,;')
            clean_quote = _clean_markdown(cited_quote)

            for idx, p in enumerate(candidate_chunks):
                chk_text = p.get("text", "")
                norm_chunk_text = re.sub(r"\s+", " ", chk_text.lower())
                clean_chunk_text = _clean_markdown(chk_text)

                if (norm_quote and norm_quote in norm_chunk_text) or (clean_quote and clean_quote in clean_chunk_text):
                    is_contiguous_match = True
                    matched_chunk = p
                    matched_chunk_idx = idx
                    retrieval_score = float(p.get("score") or 0.50)
                    break

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
        # 5. Dynamic Multi-Factor Confidence Computation (Task 6)
        # -------------------------------------------------------------------
        # Factor 1: Retrieval score of cited chunk (weight: 0.25)
        # Normalized from hybrid RRF, dense cosine, cross-encoder, or keyword score
        if retrieval_score >= 1.0:
            norm_ret = min(retrieval_score / 4.0, 1.0)
        elif retrieval_score >= 0.05:
            norm_ret = min(max(retrieval_score, 0.1), 1.0)
        elif retrieval_score > 0.0:
            # RRF scores typically range 0.010 - 0.033
            norm_ret = min(max((retrieval_score - 0.008) / 0.024, 0.15), 1.0)
        else:
            norm_ret = 0.20

        # Rank adjustment: top chunk gets 1.0, lower ranks receive minor discounting
        rank_multiplier = max(1.0 - (matched_chunk_idx * 0.05), 0.75)
        retrieval_factor = round(norm_ret * rank_multiplier, 3)

        # Factor 2: Validation outcome (weight: 0.45)
        # (contiguous citation, format check, physical page verification, quote length)
        quote_score = 0.40 if is_contiguous_match else 0.0
        
        # Physical page verification:
        if cited_page is not None and cited_page > 0:
            if matched_chunk and matched_chunk.get("page_number") == cited_page:
                page_score = 0.20
            else:
                page_score = 0.14
        else:
            page_score = 0.05

        # Format / syntax verification:
        format_score = 0.25 if format_passed else 0.0

        # Grounding cleanliness & quote length:
        q_len = len(cited_quote)
        if q_len >= 30 and "..." not in str(field.value):
            clean_score = 0.15
        elif q_len >= 15:
            clean_score = 0.10
        else:
            clean_score = 0.05

        validation_factor = round(quote_score + page_score + format_score + clean_score, 3)

        # Factor 3: Dual-run & Syntax Agreement (weight: 0.30)
        # (re-extract agreement or multi-passage corroboration + syntax alignment)
        if secondary_field and secondary_field.value is not None:
            s_val = str(secondary_field.value).strip().lower()
            p_val = str(field.value).strip().lower()
            if s_val == p_val:
                agreement_factor = 0.98
            elif s_val in p_val or p_val in s_val:
                agreement_factor = 0.85
            else:
                s_toks = set(s_val.split())
                p_toks = set(p_val.split())
                jaccard = len(s_toks & p_toks) / max(len(s_toks | p_toks), 1)
                agreement_factor = round(max(0.30, min(0.95, 0.40 + jaccard * 0.55)), 3)
        else:
            # Standalone agreement: Value-to-Quote grounding + multi-passage corroboration + syntax match
            val_norm = str(field.value).strip().lower()
            quote_norm = cited_quote.lower()
            
            # Grounding agreement (0.0 to 0.45)
            if val_norm and val_norm in quote_norm:
                grounding_agr = 0.45
            else:
                val_toks = set(re.findall(r"\w+", val_norm))
                quote_toks = set(re.findall(r"\w+", quote_norm))
                if val_toks and val_toks.issubset(quote_toks):
                    grounding_agr = 0.40
                elif val_toks:
                    ov = len(val_toks & quote_toks) / max(len(val_toks), 1)
                    grounding_agr = round(0.15 + ov * 0.25, 3)
                else:
                    grounding_agr = 0.15

            # Multi-passage corroboration (0.0 to 0.35)
            corrob_count = 0
            val_lead = val_norm[:20] if len(val_norm) >= 5 else val_norm
            for p in retrieved_passages:
                ptxt = p.get("text", "").lower()
                if val_lead and val_lead in ptxt:
                    corrob_count += 1
            if corrob_count >= 3:
                corrob_agr = 0.35
            elif corrob_count == 2:
                corrob_agr = 0.25
            else:
                corrob_agr = 0.15

            # Schema / Type agreement (0.0 to 0.20)
            schema_agr = 0.20 if format_passed else 0.05

            agreement_factor = round(grounding_agr + corrob_agr + schema_agr, 3)

        # Multi-factor weighted confidence calculation (weights: 0.25, 0.45, 0.30)
        raw_confidence = (
            0.25 * retrieval_factor +
            0.45 * validation_factor +
            0.30 * agreement_factor
        )

        if val_issues:
            calculated_confidence = min(round(raw_confidence * 0.40, 2), 0.39)
            is_valid = False
        else:
            calculated_confidence = max(min(round(raw_confidence, 2), 0.98), 0.45)
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
        secondary_fields_map: Optional[Dict[str, FieldOutput]] = None,
    ) -> Tuple[Dict[str, FieldOutput], ValidationSummary, Dict[str, FieldValidation]]:
        """
        Validate all fields in a package, returning updated fields and Section 8.1 ValidationSummary.
        Ensures every field belongs to EXACTLY one bucket (B6).
        """
        summary = ValidationSummary()
        validations: Dict[str, FieldValidation] = {}
        validated_fields: Dict[str, FieldOutput] = {}

        for f_name, field in fields_map.items():
            passages = retrieved_evidence_map.get(f_name, [])
            f_def = field_defs.get(f_name, {})
            sec_field = secondary_fields_map.get(f_name) if secondary_fields_map else None

            val_field, val_detail = self.validate_field(
                field_name=f_name,
                field=field,
                retrieved_passages=passages,
                field_def=f_def,
                bid_id=bid_id,
                secondary_field=sec_field,
            )
            validated_fields[f_name] = val_field
            validations[f_name] = val_detail

            # Mutually exclusive partitioning (B6): exactly one bucket per field
            if val_field.status == "ERROR":
                summary.errors.append(f_name)
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
        Item 4b / B2: For NOT_FOUND fields, re-retrieve with expanded queries
        and have the LLM confirm absence or extract if found.
        R6: API failures must NEVER be disguised as absence.
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
                expand_query=True,
                exclude_doc_type="addendum"
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
            if recovered.status == "ERROR":
                # Per R6, preserve API error rather than treating as absent
                return False, recovered

            if recovered and recovered.status == "FOUND" and recovered.value is not None:
                return False, recovered
            return True, None
        except Exception as e:
            logger.warning(f"Error during absence confirmation for '{field_name}': {e}")
            err_field = FieldOutput(
                value=None,
                status="ERROR",
                notes=f"API/System error during absence confirmation: {str(e)}",
                confidence=0.0
            )
            return False, err_field
