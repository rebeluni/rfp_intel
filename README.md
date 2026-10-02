# RFP Intelligence Platform

An enterprise-grade RFP Intelligence Platform combining a hybrid RAG search engine (BM25 + Dense Embeddings + Cross-Encoder re-ranking) with a multi-agent system (LangGraph) to parse, query, and extract structured data from complex bid solicitations and RFPs.

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
                        │   - Dense MiniLM Embeddings  │
                        │   - Reciprocal Rank Fusion   │
                        │   - Cross-Encoder Re-ranker  │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │    Multi-Agent Extraction    │
                        │   - Question Router          │
                        │   - Specialist Extractors    │
                        │   - Addendum Reconciler      │
                        │   - Dual-Layer Validator     │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │  FastAPI + Interactive UI    │
                        │  (Extraction, Citations, Q&A)│
                        └──────────────────────────────┘
```

---

## Directory Structure

```
├── Bid1/                         # Sample RFP solicitation 1 (Dallas ISD)
├── Bid2/                         # Sample RFP solicitation 2 (Maryland STO)
├── config/
│   ├── fields.yaml               # 20 standardized target extraction fields
│   └── settings.py               # Pydantic environment configuration
├── docs/                         # Audit reports and review documentation
├── ingestion/                    # Document ingestion and parsing engine
│   ├── cleaner.py                # Kerning, whitespace, running header/footer stripping
│   ├── pdf_parser.py             # PyMuPDF parser, coordinate specs tables, form filters
│   ├── html_parser.py            # Portal page parsing and scope deduplication
│   ├── chunker.py                # Sentence/paragraph-aligned token chunking (~500/75 tokens)
│   ├── metadata_classifier.py    # Document type inference (heuristics + fallback)
│   ├── models.py                 # Core domain models (DocumentChunk, ParsedDocument, etc.)
│   └── pipeline.py               # Package-level ingestion orchestrator
├── search/                       # (Phase 2) Hybrid search, BM25, embeddings, RRF, re-ranker
├── agents/                       # (Phase 3) LangGraph multi-agent extraction and reconciliation
├── api/                          # (Phase 4) FastAPI backend endpoints
├── scripts/
│   ├── export_phase1_review.py   # Ingestion benchmark and review exporter
│   ├── export_requested_chunks.py# Review chunk generator
│   └── dev/                      # Development & debugging inspection scripts
├── tests/
│   └── test_ingestion.py         # 25 comprehensive unit tests (100% pass)
└── requirements.txt              # Production and development dependencies
```

---

## Quick Start

### 1. Installation
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run Tests
```bash
pytest tests/test_ingestion.py -v
```

### 3. Ingestion Pipeline
```python
from pathlib import Path
from ingestion.pipeline import IngestionPipeline

pipeline = IngestionPipeline()
parsed_bid = pipeline.ingest_folder(Path("Bid1"))
print(f"Successfully ingested {len(parsed_bid.documents)} documents across {len(parsed_bid.all_chunks)} chunks.")
```
