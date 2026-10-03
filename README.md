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
├── main.py                       # Unified CLI interface (extract, ask, serve)
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

### 2. Run Extraction via CLI
```bash
# Extract Bid1 with full Addendum reconciliation & save to outputs/bid1.json
python main.py extract --bid ./Bid1

# Extract Bid2
python main.py extract --bid ./Bid2
```

### 3. Ask Natural Language Questions
```bash
# Natural language bid routing automatically routes this to Bid2
python main.py ask "What is the due date for the Dell laptop bid?"

# Questions routed to Bid1
python main.py ask "When are proposals due for Dallas ISD?"
```

### 4. Start API Server
```bash
python main.py serve --port 8000
```

### 5. Run Search Engine Evaluation Benchmark
```bash
python search/eval.py
```

### 6. Run Test Suite
```bash
pytest tests/ -v
```
