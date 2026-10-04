"""
Unit tests for Addendum Reconciliation Agent (Phase 3).
Tests cover:
  1. Ordering addendum chunks chronologically by addendum number, then page.
  2. Exact contiguous substring verification (rejecting non-contiguous hallucinated quotes).
  3. Change-log entries schema ({field, old_value, new_value, quote, file, page, reason}).
  4. Dynamic confidence computation (not a flat 0.95).
  5. Re-validation gate (amendment must pass validator before acceptance).
"""

import pytest
from unittest.mock import MagicMock
from extraction.models import FieldOutput, FieldSource, ValidationSummary, AddendumChange
from extraction.reconciliation_agent import ReconciliationAgent
from extraction.models import FieldValidation


def test_addendum_chunks_ordering():
    agent = ReconciliationAgent(retriever=MagicMock(), llm_client=MagicMock())
    # Mock chunks with different addendum numbers and pages
    mock_chunks = [
        MagicMock(chunk_id="c3", text="Addendum 2 page 1", metadata=MagicMock(bid_id="Bid1", file_name="Addendum 2.pdf", doc_type="addendum", addendum_number=2, page_number=1)),
        MagicMock(chunk_id="c1", text="Addendum 1 page 2", metadata=MagicMock(bid_id="Bid1", file_name="Addendum 1.pdf", doc_type="addendum", addendum_number=1, page_number=2)),
        MagicMock(chunk_id="c2", text="Addendum 1 page 1", metadata=MagicMock(bid_id="Bid1", file_name="Addendum 1.pdf", doc_type="addendum", addendum_number=1, page_number=1)),
    ]
    agent.retriever.bm25_index.chunks = mock_chunks

    ordered = agent.get_addendum_chunks("Bid1")
    assert len(ordered) == 3
    assert ordered[0]["addendum_number"] == 1 and ordered[0]["page_number"] == 1
    assert ordered[1]["addendum_number"] == 1 and ordered[1]["page_number"] == 2
    assert ordered[2]["addendum_number"] == 2 and ordered[2]["page_number"] == 1


def test_reconciliation_contiguous_substring_check():
    mock_llm = MagicMock()
    # LLM proposes an amendment with a quote that is NOT in the chunk
    mock_llm.reconcile_all_addenda.return_value = [
        {
            "field": "Due Date",
            "old_value": "27-JUN-2024 14:00:00",
            "new_value": "July 9, 2024 at 2:00 PM CST",
            "quote": "This quote is completely fabricated and does not exist in any chunk.",
            "file_name": "Addendum 2.pdf",
            "page_number": 1,
            "reason": "Deadline extended"
        }
    ]

    agent = ReconciliationAgent(retriever=MagicMock(), llm_client=mock_llm)
    addendum_chunks = [{
        "chunk_id": "chk_add2",
        "file_name": "Addendum 2.pdf",
        "page_number": 1,
        "addendum_number": 2,
        "text": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."
    }]

    fields_map = {
        "Due Date": FieldOutput(value="27-JUN-2024 14:00:00", sources=[FieldSource(file="RFP.pdf", page=2, quote="27-JUN-2024 14:00:00")])
    }

    updated, changes = agent.reconcile_fields("Bid1", fields_map, addendum_chunks=addendum_chunks)
    # Amendment should be rejected because quote is not a contiguous substring
    assert len(changes) == 0
    assert updated["Due Date"].value == "27-JUN-2024 14:00:00"


def test_reconciliation_valid_amendment_and_changelog_entry():
    mock_llm = MagicMock()
    mock_llm.reconcile_all_addenda.return_value = [
        {
            "field": "Due Date",
            "old_value": "27-JUN-2024 14:00:00",
            "new_value": "July 9, 2024 at 2:00 PM CST",
            "quote": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.",
            "file_name": "Addendum 2.pdf",
            "page_number": 1,
            "reason": "Deadline extension"
        }
    ]

    mock_validator = MagicMock()
    # Validator approves
    mock_validator.validate_field.side_effect = lambda field_name, field, retrieved_passages, bid_id=None, field_def=None: (
        field,
        FieldValidation(field_name=field_name, is_valid=True, is_grounded=True)
    )

    agent = ReconciliationAgent(retriever=MagicMock(), llm_client=mock_llm, validator=mock_validator)
    addendum_chunks = [{
        "chunk_id": "chk_add2",
        "file_name": "Addendum 2.pdf",
        "page_number": 1,
        "addendum_number": 2,
        "text": "Please note: The new due date for this RFP will be July 9, 2024 at 2:00 PM CST. All submissions must be received on time."
    }]

    fields_map = {
        "Due Date": FieldOutput(value="27-JUN-2024 14:00:00", sources=[FieldSource(file="RFP.pdf", page=2, quote="27-JUN-2024 14:00:00")])
    }
    summary = ValidationSummary(passed=["Due Date"], failed=[], not_found=[])

    updated, changes = agent.reconcile_fields("Bid1", fields_map, addendum_chunks=addendum_chunks, summary=summary)

    # Verified amendment accepted
    assert len(changes) == 1
    chg = changes[0]
    assert chg.field == "Due Date"
    assert chg.old_value == "27-JUN-2024 14:00:00"
    assert chg.new_value == "July 9, 2024 at 2:00 PM CST"
    assert chg.quote == "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."
    assert chg.file == "Addendum 2.pdf"
    assert chg.page == 1
    assert chg.reason == "Deadline extension"

    # Updated field
    assert updated["Due Date"].value == "July 9, 2024 at 2:00 PM CST"
    assert updated["Due Date"].confidence > 0.85
    assert updated["Due Date"].confidence != 0.95  # Computed, not flat 0.95


def test_reconciliation_validator_rejection():
    mock_llm = MagicMock()
    mock_llm.reconcile_all_addenda.return_value = [
        {
            "field": "Due Date",
            "old_value": "27-JUN-2024 14:00:00",
            "new_value": "Invalid Date Format",
            "quote": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.",
            "file_name": "Addendum 2.pdf",
            "page_number": 1,
            "reason": "Deadline extension"
        }
    ]

    mock_validator = MagicMock()
    # Validator rejects
    mock_validator.validate_field.side_effect = lambda field_name, field, retrieved_passages, bid_id=None, field_def=None: (
        field,
        FieldValidation(field_name=field_name, is_valid=False, is_grounded=True, issue_type="syntax_invalid", feedback="Invalid date syntax")
    )

    agent = ReconciliationAgent(retriever=MagicMock(), llm_client=mock_llm, validator=mock_validator)
    addendum_chunks = [{
        "chunk_id": "chk_add2",
        "file_name": "Addendum 2.pdf",
        "page_number": 1,
        "addendum_number": 2,
        "text": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."
    }]

    fields_map = {
        "Due Date": FieldOutput(value="27-JUN-2024 14:00:00", sources=[FieldSource(file="RFP.pdf", page=2, quote="27-JUN-2024 14:00:00")])
    }
    summary = ValidationSummary(passed=[], failed=[], not_found=[])

    updated, changes = agent.reconcile_fields("Bid1", fields_map, addendum_chunks=addendum_chunks, summary=summary)

    # Amendment must not be accepted because validator rejected it
    assert len(changes) == 0
    assert "Due Date" not in summary.passed
