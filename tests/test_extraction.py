"""
Unit tests for Multi-Agent Extraction Engine (Phase 3).
Tests cover:
  1. Data models and serialization matching Section 8.1
  2. ValidatorAgent hallucination detection (verifying quotes against cited text)
  3. ValidatorAgent quote grounding & dynamic confidence
  4. SynthesisAgent cross-bid matrix and markdown generation
"""

import pytest
from extraction.models import (
    FieldSource,
    FieldEvidence,
    FieldOutput,
    ExtractedField,
    FieldValidation,
    BidExtractionResult,
    CrossBidComparison,
)
from extraction.validator_agent import ValidatorAgent
from extraction.synthesis_agent import SynthesisAgent


# ---------------------------------------------------------
# 1. Models & Citation Formatting
# ---------------------------------------------------------
def test_field_evidence_citation_format():
    ev = FieldSource(
        file="RFP_Final.pdf",
        page=3,
        chunk_id="chk_123",
        quote="Proposals must be received by 2:00 PM CST."
    )
    citation = ev.format_citation()
    assert "[RFP_Final.pdf (p.3)]" in citation
    assert "Proposals must be received by 2:00 PM CST." in citation


def test_extracted_field_serialization():
    field = FieldOutput(
        value="2024-07-09",
        status="FOUND",
        confidence=0.98,
        sources=[
            FieldSource(
                file="Addendum_2.pdf",
                page=1,
                chunk_id="add_chunk",
                quote="The deadline has been extended to July 09, 2024."
            )
        ]
    )
    json_data = field.model_dump()
    assert json_data["value"] == "2024-07-09"
    assert len(json_data["sources"]) == 1
    assert json_data["sources"][0]["file"] == "Addendum_2.pdf"


# ---------------------------------------------------------
# 2. Validator Agent: Hallucination Detection
# ---------------------------------------------------------
def test_validator_detects_hallucination():
    validator = ValidatorAgent()
    retrieved_passages = [
        {"text": "The Dallas Independent School District is soliciting proposals for student laptops.", "file_name": "rfp.pdf", "page_number": 1, "chunk_id": "c1"}
    ]

    # Hallucinated extraction where quote is NOT in the text
    hallucinated_field = FieldOutput(
        value="10% cashier check required",
        status="FOUND",
        sources=[
            FieldSource(
                file="rfp.pdf",
                page=1,
                chunk_id="c1",
                quote="A mandatory 10% cashier check must be submitted with the proposal."
            )
        ]
    )

    updated_field, validation = validator.validate_field("Bid Bond Requirement", hallucinated_field, retrieved_passages)
    assert not validation.is_valid
    assert not validation.is_grounded
    assert "not a contiguous substring" in validation.issue_type


def test_validator_approves_grounded_quote():
    validator = ValidatorAgent()
    retrieved_passages = [
        {"text": "The contract term shall be for a three (3) year agreement with two (2) successive one (1) year extensions.", "file_name": "rfp.pdf", "page_number": 2, "chunk_id": "c2"}
    ]

    grounded_field = FieldOutput(
        value="Three (3) years",
        status="FOUND",
        sources=[
            FieldSource(
                file="rfp.pdf",
                page=2,
                chunk_id="c2",
                quote="three (3) year agreement with two (2) successive one (1) year extensions"
            )
        ]
    )

    updated_field, validation = validator.validate_field("Term of Bid", grounded_field, retrieved_passages)
    assert validation.is_valid
    assert validation.is_grounded
    assert validation.issue_type is None


# ---------------------------------------------------------
# 3. Synthesis Agent: Cross-Bid Matrix Generation
# ---------------------------------------------------------
def test_synthesis_matrix_generation():
    synthesis = SynthesisAgent()
    bids_data = {
        "Bid1": BidExtractionResult(
            bid_id="Bid1",
            fields={
                "Bid Number": FieldOutput(value="JA-207652", status="FOUND"),
                "company_name": FieldOutput(value="Dallas ISD", status="FOUND"),
            },
            overall_compliance_score=90.0,
        ),
        "Bid2": BidExtractionResult(
            bid_id="Bid2",
            fields={
                "Bid Number": FieldOutput(value="BPM044557", status="FOUND"),
                "company_name": FieldOutput(value="MD Treasurer", status="FOUND"),
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
