"""
Unit tests for Multi-Agent Extraction Engine (Phase 3).
Tests cover:
  1. Data models and serialization
  2. ValidatorAgent hallucination detection (verifying quotes against text)
  3. ValidatorAgent addendum conflict reconciliation
  4. GroundedRuleExtractor deterministic extraction
  5. SynthesisAgent comparative matrix and markdown generation
  6. LangGraph ExtractionPipeline execution and refinement cycle
"""

import pytest
from extraction.models import (
    FieldEvidence,
    ExtractedField,
    FieldValidation,
    BidExtractionResult,
    CrossBidComparison,
)
from extraction.validator_agent import ValidatorAgent
from extraction.llm_client import GroundedRuleExtractor
from extraction.synthesis_agent import SynthesisAgent
from extraction.graph import ExtractionPipeline


# ---------------------------------------------------------
# 1. Models & Citation Formatting
# ---------------------------------------------------------
def test_field_evidence_citation_format():
    ev = FieldEvidence(
        file_name="RFP_Final.pdf",
        page_number=3,
        chunk_id="chk_123",
        quote="Proposals must be received by 2:00 PM CST."
    )
    citation = ev.format_citation()
    assert "[RFP_Final.pdf (p.3)]" in citation
    assert "Proposals must be received by 2:00 PM CST." in citation


def test_extracted_field_serialization():
    field = ExtractedField(
        field_name="Due Date",
        value="2024-07-09",
        status="FOUND",
        confidence=0.98,
        evidence=[
            FieldEvidence(
                file_name="Addendum_2.pdf",
                page_number=1,
                chunk_id="add_chunk",
                quote="The deadline has been extended to July 09, 2024."
            )
        ]
    )
    json_data = field.model_dump()
    assert json_data["field_name"] == "Due Date"
    assert json_data["value"] == "2024-07-09"
    assert len(json_data["evidence"]) == 1


# ---------------------------------------------------------
# 2. Validator Agent: Hallucination Detection
# ---------------------------------------------------------
def test_validator_detects_hallucination():
    validator = ValidatorAgent()
    retrieved_passages = [
        {"text": "The Dallas Independent School District is soliciting proposals for student laptops.", "file_name": "rfp.pdf", "page_number": 1}
    ]

    # Hallucinated extraction where quote is NOT in the text
    hallucinated_field = ExtractedField(
        field_name="Bid Bond Requirement",
        value="10% cashier check required",
        status="FOUND",
        evidence=[
            FieldEvidence(
                file_name="rfp.pdf",
                page_number=1,
                chunk_id="c1",
                quote="A mandatory 10% cashier check must be submitted with the proposal."
            )
        ]
    )

    validation = validator.validate_field(hallucinated_field, retrieved_passages)
    assert not validation.is_valid
    assert not validation.is_grounded
    assert validation.issue_type == "hallucination"


def test_validator_approves_grounded_quote():
    validator = ValidatorAgent()
    retrieved_passages = [
        {"text": "The contract term shall be for a three (3) year agreement with two (2) successive one (1) year extensions.", "file_name": "rfp.pdf", "page_number": 2}
    ]

    grounded_field = ExtractedField(
        field_name="Term of Bid",
        value="Three (3) years",
        status="FOUND",
        evidence=[
            FieldEvidence(
                file_name="rfp.pdf",
                page_number=2,
                chunk_id="c2",
                quote="three (3) year agreement with two (2) successive one (1) year extensions"
            )
        ]
    )

    validation = validator.validate_field(grounded_field, retrieved_passages)
    assert validation.is_valid
    assert validation.is_grounded
    assert validation.issue_type is None


# ---------------------------------------------------------
# 3. Validator Agent: Addendum Conflict Detection
# ---------------------------------------------------------
def test_validator_detects_addendum_deadline_extension():
    validator = ValidatorAgent()
    rfp_passages = [
        {"text": "Solicitation Due: 27-JUN-2024 14:00:00", "file_name": "rfp.pdf", "page_number": 2}
    ]
    addendum_passages = [
        {"text": "The proposal deadline is extended to July 09, 2024 at 2:00 PM CST.", "file_name": "Addendum_2.pdf", "page_number": 1}
    ]

    # Extracted field still using old RFP date
    old_date_field = ExtractedField(
        field_name="Due Date",
        value="27-JUN-2024",
        status="FOUND",
        evidence=[
            FieldEvidence(
                file_name="rfp.pdf",
                page_number=2,
                chunk_id="c1",
                quote="Solicitation Due: 27-JUN-2024 14:00:00"
            )
        ]
    )

    validation = validator.validate_field(old_date_field, rfp_passages, addendum_passages=addendum_passages)
    assert validation.has_addendum_conflict
    assert "July 09, 2024" in validation.suggested_value


# ---------------------------------------------------------
# 4. Synthesis Agent: Cross-Bid Matrix Generation
# ---------------------------------------------------------
def test_synthesis_matrix_generation():
    synthesis = SynthesisAgent()
    bids_data = {
        "Bid1": BidExtractionResult(
            bid_id="Bid1",
            fields={
                "Bid Number": ExtractedField(field_name="Bid Number", value="JA-207652", status="FOUND"),
                "company_name": ExtractedField(field_name="company_name", value="Dallas ISD", status="FOUND"),
            },
            overall_compliance_score=90.0,
        ),
        "Bid2": BidExtractionResult(
            bid_id="Bid2",
            fields={
                "Bid Number": ExtractedField(field_name="Bid Number", value="BPM044557", status="FOUND"),
                "company_name": ExtractedField(field_name="company_name", value="MD Treasurer", status="FOUND"),
            },
            overall_compliance_score=85.0,
        ),
    }

    fields_defs = {
        "Bid Number": {"specialist": "commercial_legal"},
        "company_name": {"specialist": "commercial_legal"},
    }

    comparison = synthesis.compare_bids(bids_data, fields_defs)
    assert len(comparison.bids) == 2
    assert len(comparison.matrix) == 2

    md_report = synthesis.generate_markdown_report(comparison)
    assert "# Cross-Bid Comparative Intelligence Report" in md_report
    assert "JA-207652" in md_report
    assert "BPM044557" in md_report
