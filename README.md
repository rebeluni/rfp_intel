# RFP Intelligence Platform

An enterprise-grade RFP Intelligence Platform combining a hybrid RAG search engine (BM25 + BAAI/bge-small-en-v1.5 dense embeddings + cross-encoder re-ranking) with a multi-agent system (LangGraph) to parse, index, extract, and reconcile structured data from complex procurement solicitations and addenda.

---

## Architecture Overview

```
                        ┌──────────────────────────────┐
                        │   RFP Package Ingestion      │
                        │   (PDF, HTML, Forms, Specs)  │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │  Ingestion & Normalization   │
                        │  - Word coordinate tables    │
                        │  - Dynamic column clustering │
                        │  - Header/footer stripping   │
                        │  - Sentence-aligned chunking │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │   Hybrid Search Engine       │
                        │   - BM25 Sparse Index        │
                        │   - Dense BGE Embeddings     │
                        │   - Reciprocal Rank Fusion   │
                        │   - Cross-Encoder Re-ranker  │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │    Multi-Agent Extraction    │
                        │   - Orchestrator / Planner   │
                        │   - 3 Parallel Specialists   │
                        │   - Deterministic Validator  │
                        │   - Addendum Reconciler      │
                        │   - Q&A Agent + Bid Router   │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │     CLI & FastAPI Engine     │
                        │  - main.py extract / ask     │
                        │  - Section 8.1 JSON Schema   │
                        └──────────────────────────────┘
```

---

## Directory Structure

```
├── Bid1/                         # Sample RFP solicitation 1 (Dallas ISD)
├── Bid2/                         # Sample RFP solicitation 2 (Maryland STO)
├── config/
│   ├── fields.yaml               # Standardized target extraction fields with query hints
│   └── settings.py               # Pydantic environment configuration (.env loader)
├── ingestion/                    # Document ingestion and parsing engine
│   ├── cleaner.py                # Kerning, whitespace, running header/footer stripping, email rejoin
│   ├── pdf_parser.py             # PyMuPDF parser, coordinate tables, vector outlines, form filters
│   ├── html_parser.py            # Portal page parsing and scope deduplication
│   ├── chunker.py                # Sentence/paragraph-aligned token chunking (~500/75 tokens)
│   ├── metadata_classifier.py    # Document type inference (heuristics + fallback)
│   ├── models.py                 # Core domain models (DocumentChunk, ParsedDocument, etc.)
│   └── pipeline.py               # Package-level ingestion orchestrator
├── search/                       # Hybrid search, BM25, embeddings, RRF, re-ranker, Q&A agent, eval
│   ├── bm25_index.py             # Okapi BM25 index with alphanumeric compound tokenizer
│   ├── dense_indexer.py          # BAAI/bge-small-en-v1.5 dense vector index
│   ├── reranker.py               # Cross-Encoder (ms-marco-MiniLM-L-6-v2) re-ranking
│   ├── hybrid_retriever.py       # RRF fusion engine & metadata filters
│   ├── qa_agent.py               # Natural language bid routing & LLM citations
│   └── eval.py                   # Rigorous IR evaluation benchmark with expected_page
├── extraction/                   # Multi-agent extraction pipeline
│   ├── graph.py                  # LangGraph cyclic state machine with retry loop
│   ├── extractor_agent.py        # Specialist field extractor (parallel fan-out)
│   ├── validator_agent.py        # Deterministic contiguous quote validation & dynamic confidence
│   ├── reconciliation_agent.py   # Chronological addendum supersession & change logging
│   ├── tracer.py                 # Execution tracer (latency, tokens, agent steps)
│   ├── llm_client.py             # Real LLM client (Gemini 2.5 Flash, temp 0, JSON mode)
│   └── models.py                 # Section 8.1 data models (FieldOutput, AddendumChange, etc.)
├── api/                          # FastAPI backend endpoints (/search, /ask, /extract, /compare)
├── outputs/                      # Generated Section 8.1 JSON extractions and execution traces
├── tests/                        # Comprehensive pytest suite
├── ui/                           # Streamlit interactive user interface
│   └── app.py                    # 3-tab UI: Search Passages, Ask Q&A, Extract & Reconcile
├── main.py                       # Unified CLI interface (extract, ask, serve, ui)
└── requirements.txt              # Production and development dependencies
```

---

## Quick Start & CLI Usage

### 1. Installation
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Set GEMINI_API_KEY in .env
```

### 2. Interactive Web UI (Streamlit)
```bash
# Launch interactive 3-tab web interface (Search, Ask, Extract & Reconcile)
python main.py ui --port 8501
```

### 3. Run Extraction via CLI
```bash
# Extract Bid1 with full Addendum reconciliation & save to outputs/bid1.json
python main.py extract --bid ./Bid1

# Extract Bid2
python main.py extract --bid ./Bid2

# Extract Bid3
python main.py extract --bid ./Bid3
```

### 4. Ask Natural Language Questions
```bash
# Natural language bid routing automatically routes to Bid2
python main.py ask "What is the due date for the Dell laptop bid?"

# Questions routed to Bid1
python main.py ask "When are proposals due for Dallas ISD?"

# Cross-bid comparisons
python main.py ask "Compare warranties across all bids."
```

### 5. Start API Server
```bash
python main.py serve --port 8000
```

### 6. Run Search Engine Evaluation Benchmark
```bash
python -m scripts.run_search_eval
```

### 7. Run Test Suite
```bash
pytest
```

---

## Search Retrieval Evaluation Benchmark

Evaluation performed across **22 ground-truth target queries** with strict citation matching (`expected_file` and `expected_page`).

> **Note on Evaluation Granularity:** With 22 evaluation queries, exactly **one query represents 4.545% (4.5 points)** of the total recall. Small numerical differences reflect single-query shifts rather than systemic variance.

> **Table is generated from `outputs/search_eval_results.json`** by running `python scripts/gen_readme_table.py`. Do not edit the table by hand.

<!-- EVAL_TABLE_START -->
| Retrieval Mode | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---|---|---|
| **BM25 Only** | 54.55% | 81.82% | **86.36%** | **0.6856** |
| **Dense Only (BGE-small)** | 36.36% | 72.73% | 81.82% | 0.5379 |
| **Hybrid (RRF k=60)** | 50.00% | 81.82% | 81.82% | 0.6591 |
| **Hybrid + Cross-Encoder Rerank** | 54.55% | 81.82% | **86.36%** | 0.6833 |
<!-- EVAL_TABLE_END -->

### Key Benchmark Observations:
- BM25 and Hybrid+CrossEncoder achieve an identical **86.36% Recall@5** (19/22 queries).
- Dense search captures semantic paraphrases (e.g. warranty coverage and contact roles).
- BM25 excels at exact alphanumeric identifiers (solicitation numbers, SKU codes, telephone numbers).
- Latency figures are not captured in current eval; measure with `time.perf_counter()` in `search/eval.py` if needed.

---

## Known Limitations & Design Trade-offs

1. **Bid1 Pages 54–59 (IRS W-9 Form — Vector Outline Instructions):**
   - Page 54 is the **IRS Form W-9** (Request for Taxpayer Identification Number), rendered as an interactive PDF form with 35 fillable widget fields (Text, CheckBox, Signature). PyMuPDF's `page.widgets()` confirms 35 widgets; visible text is 5 chars (`SIGN\n`) because field labels are drawn as vector paths.
   - Pages 55–59 are the **W-9 instructions** composed entirely of vector stroke drawing objects (199–216 paths per page, 0 text chars extracted by PyMuPDF). OCR via `pytesseract` is **not available** in the current dependency set (`No module named 'pytesseract'`). Rasterization via Gemini vision would require another API call per page; this is not currently implemented. These pages are flagged `non-extractable (vector outlines — W-9 instructions)` and recommended for manual review.
   - The platform does **not** attempt to OCR these pages to avoid hallucinating W-9 content into procurement fields.
2. **Bid2 / Bid3 Bid Bond: Not Mentioned in Documents:**
   - A full-text search of all Bid2 and Bid3 documents for `bid bond`, `surety`, and `bond` returns **zero matches**. These documents are silent on the topic; the correct answer is "not mentioned in the documents", not "not required".
3. **Rate Limits on Free Tier LLMs:**
   - When using free tier Gemini API keys (15 RPM), the extraction pipeline uses a shared thread-safe rate limiter (`LLM_RATE_LIMIT_RPM=15.0`) to pace parallel extraction threads across specialist groups without throwing HTTP 429 errors.
