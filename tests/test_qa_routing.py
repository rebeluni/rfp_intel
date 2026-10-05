"""
Unit tests for Q&A Dynamic Metadata Routing & Semantics (Tasks C1, F7).
Tests cover:
  1. Routing from dynamic indexed metadata (solicitation numbers, agencies, titles)
  2. Multi-bid / comparison query detection
  3. Handling an unseen bid gracefully
  4. Handling an ambiguous question without crashing
  5. Mocking the LLM so unit tests execute offline
"""

import pytest
from unittest.mock import MagicMock
from search.qa_agent import QAAgent


@pytest.fixture
def mock_qa_agent():
    mock_retriever = MagicMock()
    mock_llm = MagicMock()

    # Setup mock chunks in BM25 index
    chunk1 = MagicMock()
    chunk1.text = "Dallas Independent School District Solicitation JA-207652 Student and Staff Computing"
    chunk1.metadata.bid_id = "Bid1"
    chunk1.metadata.file_name = "JA-207652.pdf"
    chunk1.metadata.page_number = 1
    chunk1.metadata.doc_type.value = "bid_page"

    chunk2 = MagicMock()
    chunk2.text = "State of Maryland Treasurer's Office PORFP #E20P4600040 BPM044557 Dell Laptops"
    chunk2.metadata.bid_id = "Bid2"
    chunk2.metadata.file_name = "PORFP_Dell.pdf"
    chunk2.metadata.page_number = 1
    chunk2.metadata.doc_type.value = "bid_page"

    chunk3 = MagicMock()
    chunk3.text = "Austin Independent School District Solicitation AISD-2025-9988 Laptops"
    chunk3.metadata.bid_id = "Bid3"
    chunk3.metadata.file_name = "PORFP_Austin.pdf"
    chunk3.metadata.page_number = 1
    chunk3.metadata.doc_type.value = "bid_page"

    mock_retriever.bm25_index.chunks = [chunk1, chunk2, chunk3]
    mock_retriever.bm25_index.search.return_value = [(chunk1, 2.5), (chunk2, 1.0)]

    qa = QAAgent(retriever=mock_retriever, llm_client=mock_llm)
    return qa


def test_routing_from_solicitation_number(mock_qa_agent):
    assert mock_qa_agent.route_bid("What is the due date for JA-207652?") == "Bid1"
    assert mock_qa_agent.route_bid("Tell me about BPM044557") == "Bid2"
    assert mock_qa_agent.route_bid("What model is in AISD-2025-9988?") == "Bid3"


def test_routing_from_agency_metadata(mock_qa_agent):
    assert mock_qa_agent.route_bid("Who is the contact at Dallas Independent School District?") == "Bid1"
    assert mock_qa_agent.route_bid("What does Maryland State Treasurer require?") == "Bid2"
    assert mock_qa_agent.route_bid("What are the evaluation criteria for Austin ISD?") == "Bid3"


def test_routing_multi_bid_comparison(mock_qa_agent):
    assert mock_qa_agent.route_bid("Compare the warranty terms across all three bids.") == "COMPARISON"
    assert mock_qa_agent.route_bid("What is the difference between Bid1 and Bid2?") == "COMPARISON"
    assert mock_qa_agent.route_bid("Summarise all three bids in one paragraph each.") == "COMPARISON"


def test_routing_unseen_bid_or_unknown_query(mock_qa_agent):
    # Query referencing an unseen entity not in metadata catalog
    mock_qa_agent.retriever.bm25_index.search.return_value = []
    routed = mock_qa_agent.route_bid("What is the protocol for Project XYZ-99999 from Seattle Metro?")
    assert routed is None


def test_ambiguous_question_handling(mock_qa_agent):
    # Ambiguous question without specific keywords
    mock_qa_agent.retriever.bm25_index.search.return_value = [
        (mock_qa_agent.retriever.bm25_index.chunks[0], 0.05)
    ]
    # Should not crash, returns best guess or None
    routed = mock_qa_agent.route_bid("Is there any document?")
    assert routed is None or routed in ["Bid1", "Bid2", "Bid3"]


def test_routing_with_four_indexed_bids_including_folder_not_named_bidn(mock_qa_agent):
    """Routing with four indexed bids including a folder not named 'BidN' (e.g. Acme_RFP_2025)."""
    chunk_acme = MagicMock()
    chunk_acme.text = "Acme Global Solutions Solicitation ACME-2025-009 Cloud Services Infrastructure"
    chunk_acme.metadata.bid_id = "Acme_RFP_2025"
    chunk_acme.metadata.file_name = "Acme_Proposal.pdf"
    chunk_acme.metadata.page_number = 1
    chunk_acme.metadata.doc_type.value = "bid_page"
    mock_qa_agent.retriever.bm25_index.chunks.append(chunk_acme)
    mock_qa_agent._bid_catalog = None  # Reset catalog cache

    # Verify 4 bids are indexed
    indexed_bids = mock_qa_agent._get_indexed_bids()
    assert "Acme_RFP_2025" in indexed_bids
    assert len(indexed_bids) >= 4

    # Route by bid ID
    assert mock_qa_agent.route_bid("What is the scope in Acme_RFP_2025?") == "Acme_RFP_2025"
    # Route by solicitation number
    assert mock_qa_agent.route_bid("What are the deliverables for ACME-2025-009?") == "Acme_RFP_2025"


def test_comparison_both_bids_with_three_indexed_bids(mock_qa_agent):
    """'both bids' with 3 bids indexed (expect all 3, with the note)."""
    mock_qa_agent.llm_client.answer_question.return_value = {
        "answer": "Mocked warranty comparison across bids.",
        "citations": []
    }
    # Ensure exactly 3 bids in index
    indexed_bids = mock_qa_agent._get_indexed_bids()
    assert len(indexed_bids) == 3

    resp = mock_qa_agent.ask("Compare the warranty terms of both bids.")
    assert resp["active_bids"] == indexed_bids
    assert "3 bids are indexed; comparing all of them" in resp["answer"]
    assert "Bids included in comparison: Bid1, Bid2, Bid3." in resp["answer"]


def test_comparison_two_bids_named_explicitly_by_agency_or_title(mock_qa_agent):
    """Two bids named explicitly by agency or title (expect exactly those)."""
    mock_qa_agent.llm_client.answer_question.return_value = {
        "answer": "Comparison between Dallas ISD and Austin ISD.",
        "citations": []
    }
    # Compare by agency names
    resp_agency = mock_qa_agent.ask(
        "Compare the evaluation criteria between Dallas Independent School District and Austin Independent School District"
    )
    assert resp_agency["active_bids"] == ["Bid1", "Bid3"]
    assert "Bids included in comparison: Bid1, Bid3." in resp_agency["answer"]

    # Compare by solicitation / title tokens
    resp_title = mock_qa_agent.ask(
        "Compare the computing device scope between JA-207652 and AISD-2025-9988"
    )
    assert resp_title["active_bids"] == ["Bid1", "Bid3"]

