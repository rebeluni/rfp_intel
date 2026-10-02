"""
Unit tests for Search Engine Phase 2.
Tests cover:
  1. BM25 specialized tokenizer (compound preservation, sub-tokenization)
  2. Dense query prefixing and model dimensions
  3. RRF (Reciprocal Rank Fusion) ranking logic
  4. Metadata filtering on indices
  5. Search API endpoints (via FastAPI TestClient)
"""

import pytest
from fastapi.testclient import TestClient
from search.tokenizer import BM25Tokenizer, tokenize_bm25
from search.bm25_index import BM25Index
from ingestion.chunker import DocumentChunk, DocumentMetadata, DocType
from config.settings import settings
from api.server import app


# ---------------------------------------------------------
# 1. BM25 Tokenizer Tests
# ---------------------------------------------------------
def test_tokenizer_preserves_compound_identifiers():
    tok = BM25Tokenizer()
    text = "Dell SKU 210-BLYZ and RFP JA-207652 in Dallas ISD."
    tokens = tok.tokenize(text)

    # Whole tokens should be preserved in lower-case
    assert "210-blyz" in tokens
    assert "ja-207652" in tokens

    # Subparts should also be emitted for robust retrieval
    assert "210" in tokens
    assert "blyz" in tokens
    assert "ja" in tokens
    assert "207652" in tokens


def test_tokenizer_handles_emails_and_models():
    tok = BM25Tokenizer()
    text = "Contact thawkins@treasurer.state.md.us for BPM044557."
    tokens = tok.tokenize(text)

    assert "thawkins" in tokens
    assert "treasurer" in tokens
    assert "bpm044557" in tokens


# ---------------------------------------------------------
# 2. Dense Query Prefixing
# ---------------------------------------------------------
def test_dense_query_prefix():
    prefix = settings.EMBEDDING_QUERY_PREFIX
    assert prefix == "Represent this sentence for searching relevant passages: "
    assert settings.EMBEDDING_MAX_SEQ_LENGTH == 512


# ---------------------------------------------------------
# 3. RRF Rank Fusion Calculation Logic
# ---------------------------------------------------------
def test_rrf_formula_accuracy():
    rrf_k = 60
    # Simulate BM25 candidates: chunk_A at rank 0, chunk_B at rank 1
    bm25_ranks = {"chunk_A": 0, "chunk_B": 1}
    # Simulate Dense candidates: chunk_B at rank 0, chunk_C at rank 1
    dense_ranks = {"chunk_B": 0, "chunk_C": 1}

    rrf_scores = {}
    for cid, rank in bm25_ranks.items():
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank + 1))
    for cid, rank in dense_ranks.items():
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank + 1))

    # chunk_B is rank 1 in BM25 (1/62) and rank 0 in Dense (1/61)
    # total score for B = (1/62) + (1/61) = 0.032522
    assert rrf_scores["chunk_B"] > rrf_scores["chunk_A"]
    assert rrf_scores["chunk_B"] > rrf_scores["chunk_C"]
    assert pytest.approx(rrf_scores["chunk_B"], rel=1e-3) == (1 / 62 + 1 / 61)


# ---------------------------------------------------------
# 4. Metadata Filtering on BM25 Index
# ---------------------------------------------------------
def test_bm25_metadata_filtering(tmp_path):
    idx = BM25Index(index_file=tmp_path / "bm25.pkl")
    c1 = DocumentChunk(
        chunk_id="c1",
        text="Dell Latitude specifications and hardware requirements",
        metadata=DocumentMetadata(
            file_name="f1.pdf",
            file_path="f1.pdf",
            page_number=1,
            doc_type=DocType.SPECS,
            bid_id="Bid1",
            is_table=False
        )
    )
    c2 = DocumentChunk(
        chunk_id="c2",
        text="Dell Latitude pricing table and SKU quantities",
        metadata=DocumentMetadata(
            file_name="f2.pdf",
            file_path="f2.pdf",
            page_number=2,
            doc_type=DocType.SPECS,
            bid_id="Bid2",
            is_table=True
        )
    )
    c3 = DocumentChunk(
        chunk_id="c3",
        text="General legal terms and conditions for Maryland state contracts",
        metadata=DocumentMetadata(
            file_name="f3.pdf",
            file_path="f3.pdf",
            page_number=3,
            doc_type=DocType.AFFIDAVIT,
            bid_id="Bid2",
            is_table=False
        )
    )
    idx.add_chunks([c1, c2, c3])

    # Search with unique terms so IDF is positive (N=3, n=1 -> score > 0)
    res_bid1 = idx.search("specifications", bid_id="Bid1")
    assert len(res_bid1) == 1
    assert res_bid1[0][0].chunk_id == "c1"

    # Search with is_table filter
    res_table = idx.search("pricing", is_table=True)
    assert len(res_table) == 1
    assert res_table[0][0].chunk_id == "c2"


# ---------------------------------------------------------
# 5. FastAPI Endpoints
# ---------------------------------------------------------
def test_api_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_stats():
    client = TestClient(app)
    resp = client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "dense_vectors" in data
    assert "bm25_chunks" in data


def test_api_search_bm25_endpoint():
    client = TestClient(app)
    payload = {
        "query": "Dell Latitude 5550 210-BLYZ",
        "top_k": 3,
        "mode": "bm25_only"
    }
    resp = client.post("/search", json=payload)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    assert any("210-BLYZ" in r["text"] or "Dell" in r["text"] for r in results)
