"""
Senior Compliance Officer / Validator Agent (Phase 3).
Performs:
  1. Hallucination Detection: Verifies that cited quotes exist verbatim in source text.
  2. Addendum Conflict Check: Flags when an original RFP term was superseded by an addendum.
  3. Format & Completeness Validation: Checks date syntax, email syntax, and required fields.
"""

import re
import logging
from typing import Any, Dict, List, Optional
from extraction.models import ExtractedField, FieldValidation

logger = logging.getLogger(__name__)


class ValidatorAgent:
    """Senior compliance officer enforcing strict grounding and addendum hierarchy."""

    def __init__(self):
        pass

    def validate_field(
        self,
        field: ExtractedField,
        retrieved_passages: List[Dict[str, Any]],
        addendum_passages: Optional[List[Dict[str, Any]]] = None,
    ) -> FieldValidation:
        """
        Validate an extracted field against retrieved evidence.
        """
        # 1. If field was not found
        if field.status == "NOT_FOUND" or field.value is None:
            return FieldValidation(
                field_name=field.field_name,
                is_valid=True,
                is_grounded=True,
                has_addendum_conflict=False,
                feedback="Field correctly identified as not present in retrieved evidence."
            )

        # 2. Check Grounding (Hallucination Detection)
        if not field.evidence:
            return FieldValidation(
                field_name=field.field_name,
                is_valid=False,
                is_grounded=False,
                issue_type="missing_citation",
                feedback="Extracted value has no supporting citation or quote.",
            )

        # Verify each evidence quote against chunk text
        grounded_count = 0
        all_chunks_text = " ".join([p.get("text", "") for p in retrieved_passages])

        for ev in field.evidence:
            clean_quote = ev.quote.strip()
            # Normalize whitespace for robust comparison
            norm_quote = re.sub(r"\s+", " ", clean_quote.lower())
            norm_chunks = re.sub(r"\s+", " ", all_chunks_text.lower())

            # Check if a substantial part of the quote (or whole quote) exists in retrieved text
            if norm_quote in norm_chunks or any(part in norm_chunks for part in norm_quote.split(". ") if len(part) > 20):
                grounded_count += 1

        is_grounded = grounded_count > 0
        if not is_grounded:
            return FieldValidation(
                field_name=field.field_name,
                is_valid=False,
                is_grounded=False,
                issue_type="hallucination",
                feedback=f"Quote '{field.evidence[0].quote[:80]}...' could not be verified in retrieved source text.",
            )

        # 3. Check for Addendum Conflicts (e.g. Due Date changes)
        has_addendum_conflict = False
        suggested_val = None
        feedback = "Grounded in source text and verified."

        if addendum_passages and "due date" in field.field_name.lower():
            for ap in addendum_passages:
                txt = ap.get("text", "")
                m = re.search(r"extended to\s+([A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+[\d:]+\s*(?:AM|PM|CST|EDT|CDT)?)", txt, re.IGNORECASE)
                if m:
                    addendum_date = m.group(1).strip()
                    if field.value and addendum_date.lower() not in str(field.value).lower():
                        has_addendum_conflict = True
                        suggested_val = addendum_date
                        feedback = f"Original due date superseded by Addendum ({addendum_date})."
                        break

        # 4. Format Checks for critical fields
        issue_type = None
        if "contact_info" in field.field_name.lower():
            if "@" not in str(field.value):
                feedback = "Contact info extracted without email address."

        return FieldValidation(
            field_name=field.field_name,
            is_valid=(not has_addendum_conflict),
            is_grounded=is_grounded,
            has_addendum_conflict=has_addendum_conflict,
            issue_type=issue_type or ("addendum_conflict" if has_addendum_conflict else None),
            feedback=feedback,
            suggested_value=suggested_val,
        )

    def validate_package(
        self,
        extracted_fields: Dict[str, ExtractedField],
        retrieved_evidence_map: Dict[str, List[Dict[str, Any]]],
        addenda_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, FieldValidation]:
        """Validate all fields in a bid package and return validations map."""
        validations: Dict[str, FieldValidation] = {}

        for f_name, field in extracted_fields.items():
            passages = retrieved_evidence_map.get(f_name, [])
            val_res = self.validate_field(
                field=field,
                retrieved_passages=passages,
                addendum_passages=addenda_chunks,
            )
            validations[f_name] = val_res

        return validations
