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


# ---------------------------------------------------------
# 4. Strict Contiguous Chunk Grounding & Dynamic Confidence (B1-B6)
# ---------------------------------------------------------
def test_validator_rejects_deviating_quote_no_shortcut():
    validator = ValidatorAgent()
    retrieved_passages = [
        {
            "text": "The proposals must be delivered in person by 2:00 PM CST on the designated date.",
            "file_name": "rfp.pdf",
            "page_number": 1,
            "chunk_id": "c1",
            "score": 0.90
        }
    ]

    # Quote starts identical for 25 chars, but changes at the end
    altered_field = FieldOutput(
        value="2:00 PM CST via email",
        status="FOUND",
        sources=[
            FieldSource(
                file="rfp.pdf",
                page=1,
                chunk_id="c1",
                quote="The proposals must be delivered electronically by 2:00 PM CST"
            )
        ]
    )

    updated_field, validation = validator.validate_field("Due Date", altered_field, retrieved_passages)
    assert not validation.is_valid
    assert not validation.is_grounded
    assert "Quote is not a contiguous substring" in validation.feedback
    assert updated_field.confidence < 0.50


def test_validator_dynamic_confidence_variance():
    validator = ValidatorAgent()
    high_score_chunk = [
        {
            "text": "Invoicing instructions: Invoices must be submitted within 10 days of delivery.",
            "file_name": "rfp.pdf",
            "page_number": 2,
            "chunk_id": "c_high",
            "score": 0.95
        }
    ]
    low_score_chunk = [
        {
            "text": "Invoicing instructions: Invoices must be submitted within 10 days of delivery.",
            "file_name": "rfp.pdf",
            "page_number": 2,
            "chunk_id": "c_low",
            "score": 0.15
        }
    ]

    field_high = FieldOutput(
        value="Invoices within 10 days",
        status="FOUND",
        sources=[
            FieldSource(file="rfp.pdf", page=2, chunk_id="c_high", quote="Invoices must be submitted within 10 days of delivery.")
        ]
    )
    field_low = FieldOutput(
        value="Invoices within 10 days",
        status="FOUND",
        sources=[
            FieldSource(file="rfp.pdf", page=2, chunk_id="c_low", quote="Invoices must be submitted within 10 days of delivery.")
        ]
    )

    _, val_high = validator.validate_field("Payment Terms", field_high, high_score_chunk)
    _, val_low = validator.validate_field("Payment Terms", field_low, low_score_chunk)

    assert val_high.is_valid and val_low.is_valid
    assert field_high.confidence > field_low.confidence
    assert field_high.confidence >= 0.70


def test_validation_mutually_exclusive_buckets_and_completeness():
    validator = ValidatorAgent()
    fields_map = {
        "field_passed": FieldOutput(
            value="Dallas ISD",
            status="FOUND",
            sources=[FieldSource(file="doc.pdf", page=1, quote="Dallas ISD")]
        ),
        "field_failed": FieldOutput(
            value="Invalid",
            status="FOUND",
            sources=[FieldSource(file="doc.pdf", page=1, quote="Nonexistent hallucination")]
        ),
        "field_not_found": FieldOutput(
            value=None,
            status="NOT_FOUND"
        ),
        "field_error": FieldOutput(
            value=None,
            status="ERROR",
            notes="API Rate Limited"
        )
    }

    passages = {"field_passed": [{"file_name": "doc.pdf", "page_number": 1, "text": "Welcome to Dallas ISD RFP."}]}

    _, summary, _ = validator.validate_package(
        bid_id="TestBid",
        fields_map=fields_map,
        retrieved_evidence_map=passages,
        field_defs={}
    )

    # Check that each field belongs to exactly one bucket
    all_categorized = summary.passed + summary.failed + summary.not_found + summary.errors
    assert len(all_categorized) == 4
    assert len(set(all_categorized)) == 4
    assert "field_passed" in summary.passed
    assert "field_failed" in summary.failed
    assert "field_not_found" in summary.not_found
    assert "field_error" in summary.errors


def test_trace_step_token_tracking(tmp_path):
    from extraction.tracer import StructuredTracer
    trace_file = tmp_path / "test_trace.json"
    tracer = StructuredTracer(trace_path=trace_file)

    with tracer.start_step("extractor", {"task": "test"}) as ctx:
        ctx.add_tokens(count=150, prompt_count=100, completion_count=50)
        ctx.complete({"result": "ok"}, tokens=150, prompt_tokens=100, completion_tokens=50)

    saved_path = tracer.save()
    assert saved_path.exists()
    assert len(tracer.steps) == 1
    step = tracer.steps[0]
    assert step.tokens == 150
    assert step.prompt_tokens == 100
    assert step.completion_tokens == 50
    assert step.agent == "extractor"


def test_transient_retry_logic(monkeypatch):
    """Offline unit test: transient network errors (Timeout, ConnectionError) are retried and recover."""
    from unittest.mock import MagicMock
    import json
    import httpx
    from extraction.llm_client import GeminiClient

    client = GeminiClient(api_key="mock_key")
    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("Read timed out")
        elif call_count == 2:
            raise ConnectionError("Connection reset by peer")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "value": "JA-207652",
                            "status": "FOUND",
                            "quote": "Solicitation JA-207652",
                            "file_name": "rfp.pdf",
                            "page_number": 1,
                            "reason": "Found solicitation number"
                        })
                    }]
                }
            }],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70}
        }
        return mock_resp

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)

    res = client.extract_field("Bid Number", {"description": "Bid number"}, [{"file_name": "rfp.pdf", "page_number": 1, "text": "Solicitation JA-207652"}])
    assert call_count == 3
    assert res.value == "JA-207652"
    assert res.status == "FOUND"


def test_bid_summary_generation_from_scope(monkeypatch):
    """Offline unit test: Bid Summary synthesizes purpose, scope, and equipment from scope chunks."""
    from unittest.mock import MagicMock
    import json
    import httpx
    from extraction.llm_client import GeminiClient

    client = GeminiClient(api_key="mock_key")

    mock_summary_json = {
        "value": "Dallas Independent School District is soliciting offers for student and staff computing devices across high school campuses.",
        "status": "FOUND",
        "quote": "Dallas Independent School District is soliciting offers for student and staff computing devices",
        "file_name": "scope.pdf",
        "page_number": 1,
        "reason": "Generated from district scope and objectives."
    }

    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps(mock_summary_json)}]
                }
            }],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 40, "totalTokenCount": 140}
        }
        return mock_resp

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    scope_passages = [{
        "file_name": "scope.pdf",
        "page_number": 1,
        "text": "Dallas Independent School District is soliciting offers for student and staff computing devices to support high school campus programs.",
        "score": 0.92
    }]

    res = client.extract_field("Bid Summary", {"description": "1-2 paragraph executive summary"}, scope_passages)
    assert res.value is not None
    assert "Dallas Independent School District" in res.value
    assert "student and staff computing devices" in res.value
    assert len(res.sources) == 1
    assert res.sources[0].file == "scope.pdf"


def test_null_none_semantics_for_absent_fields():
    """Offline unit test: Absent fields yield value=None, confidence=0.0, status=NOT_FOUND, sources=[]."""
    from extraction.validator_agent import ValidatorAgent
    from extraction.models import FieldOutput

    validator = ValidatorAgent(retriever=None, llm_client=None)

    absent_field = FieldOutput(
        value=None,
        status="NOT_FOUND",
        confidence=0.0,
        sources=[]
    )

    validated_field, val_detail = validator.validate_field(
        field_name="Payment Terms",
        field=absent_field,
        retrieved_passages=[]
    )

    assert validated_field.value is None
    assert validated_field.confidence == 0.0
    assert validated_field.status == "NOT_FOUND"
    assert validated_field.sources == []
    assert val_detail.is_valid is True
    assert val_detail.issue_type is None
    assert "absent" in val_detail.feedback.lower() or "not found" in val_detail.feedback.lower()


def test_buyer_payment_terms_distinction():
    """Offline unit test: Distinguishes contractor invoicing timing from buyer payment terms."""
    from extraction.validator_agent import ValidatorAgent
    from extraction.models import FieldOutput, FieldSource

    validator = ValidatorAgent(retriever=None, llm_client=None)

    buyer_terms_field = FieldOutput(
        value="Net 30 days from invoice approval",
        status="FOUND",
        confidence=0.90,
        sources=[
            FieldSource(
                file="contract.pdf",
                page=5,
                chunk_id="c_pay",
                quote="Payment terms are Net 30 days from invoice approval by the District."
            )
        ]
    )

    passages = [{
        "chunk_id": "c_pay",
        "file_name": "contract.pdf",
        "page_number": 5,
        "text": "Payment terms are Net 30 days from invoice approval by the District. Invoices must be submitted within 10 days.",
        "score": 0.85
    }]

    val_field, val_detail = validator.validate_field(
        field_name="Payment Terms",
        field=buyer_terms_field,
        retrieved_passages=passages
    )

    assert val_detail.is_valid is True
    assert val_field.confidence >= 0.70
    assert "Net 30" in str(val_field.value)


