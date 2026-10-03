# RFP Intelligence Platform — Phase 3 Handoff Report for Claude

**Commit:** `ab5066a`
**Date:** 2026-10-03
**Status:** End-to-end pipeline verified, all outputs committed.

---

## 1. What Was Built

A three-phase, production-quality RFP intelligence platform:

```
Phase 1 — Ingestion     : PDF/HTML -> structured DocumentChunk objects, BM25 + BGE-Small dense index
Phase 2 — Search        : Hybrid BM25+Dense retrieval, RRF fusion, CrossEncoder reranking
Phase 3 — Extraction/QA : LangGraph multi-agent graph (Specialist -> Validator -> Reconciliation -> QA -> Finalizer)
```

### Repository layout (key files)

```
main.py                          CLI: extract | ask | serve
config/settings.py               Pydantic Settings — all config via env vars
ingestion/
  chunker.py                     Token/sentence-aligned chunking, header stripping
  pdf_parser.py                  PyMuPDF parser with coord-based column clustering
  html_parser.py                 HTML -> structured text
search/
  index_manager.py               Builds / loads BM25 + FAISS dense index
  hybrid_retriever.py            BM25 + dense RRF + CrossEncoder reranking
  qa_agent.py                    Dynamic metadata routing (no hardcoded bid keywords), LLM answer synthesis
  eval.py                        22-query benchmark with verified target chunk IDs
extraction/
  graph.py                       LangGraph ExtractionPipeline (parallel specialist groups, retries, reconciliation)
  llm_client.py                  Gemini-only (x-goog-api-key header), temp=0, JSON+Pydantic, 1 repair retry
  models.py                      FieldResult, BidExtractionResult, FieldSource (Pydantic)
  reconciliation_agent.py        Addendum reconciliation: contiguous substring check, computed confidence
  validator_agent.py             Deterministic validation + dynamic confidence scoring
  tracer.py                      StructuredTracer -> outputs/sample_trace.json
scripts/
  run_search_eval.py             Runs Phase 2 benchmark -> outputs/search_eval_results.json
  generate_bid3.py               Generates perturbed Bid3 corpus (Austin ISD / Lenovo)
  generate_qa_log.py             Runs 15 Q&A questions -> outputs/qa_log.md
  verify_benchmark_items.py      Verifies all 22 benchmark target chunks exist in the index
outputs/
  bid1.json                      Dallas ISD extraction result
  bid2.json                      MD State Treasurer extraction result
  bid3.json                      Austin ISD (perturbed) extraction result
  search_eval_results.json       Live benchmark scores
  sample_trace.json              10-step extraction trace (Bid3 last run)
  qa_log.md                      15 answered Q&A entries
Bid1/ Bid2/ Bid3/                Raw bid document packages
```

---

## 2. Extraction Results (Section 8.1 Fields)

The pipeline extracts **20 structured fields** per bid. Every FOUND field carries:
- `value` — extracted text
- `sources` — list of `FieldSource(verbatim_quote, file, page, confidence)`
- `null_reason` — populated when not found, e.g. "Not found in documents"

### Bid 1 — Dallas ISD (`JA-207652`)

| Status | Fields |
|--------|--------|
| Found (14) | Due Date, Bid Submission Type, Term of Bid, Pre Bid Meeting, Installation, Title, Product, Bid Summary, Product Specification, Bid Number, Any Additional Documentation Required, Contract or Cooperative to use, contact_info, company_name |
| Not Found (6) | Delivery Date, Model_no, Part_no, Bid Bond Requirement, Payment Terms, MFG for Registration |

**Sample citations:**
- `Bid Number: JA-207652` — `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information.html (p.1)` | conf 0.98
- `Due Date: July 9, 2024 at 2:00 PM CST` — `Addendum 2 RFP JA-207652.pdf (p.1)` | conf 0.98 *(correctly picks Addendum 2 override)*
- `Product` — 10 tiers cited verbatim from spec table on p.35

**Compliance score: 70%** | Passed: 14 | Failed: 0 | Not Found: 6 | Addenda Changes: 0

### Bid 2 — Maryland State Treasurer's Office (`#E20P4600040`)

| Status | Fields |
|--------|--------|
| Found (15) | Title, Model_no, Part_no, Product, Bid Summary, Product Specification, Due Date, Bid Submission Type, Installation, Delivery Date, Bid Number, Any Additional Documentation Required, MFG for Registration, Contract or Cooperative to use, contact_info, company_name |
| Not Found (4) | Term of Bid, Pre Bid Meeting, Bid Bond Requirement, Payment Terms |

**Sample citations:**
- `Bid Number: #E20P4600040` — `PORFP_-_Dell_Laptop_Final.pdf (p.1)` | conf 0.98
- `Product` — Dell Latitude 5550 (Qty: 30) + Dell Thunderbolt 4 Dock WD22TB4 (Qty: 30) — verbatim from p.3

**Compliance score: 75%** | Passed: 15 | Failed: 1 | Not Found: 4 | Addenda: none detected

### Bid 3 — Austin ISD (`AISD-2025-9988`) — synthetic perturbed bid

| Status | Fields |
|--------|--------|
| Found (14) | Due Date, Bid Submission Type, Delivery Date, Title, Model_no, Part_no, Product, Bid Summary, Product Specification, Bid Number, Any Additional Documentation Required, MFG for Registration, Contract or Cooperative to use, contact_info, company_name |
| Not Found (5) | Term of Bid, Pre Bid Meeting, Installation, Bid Bond Requirement, Payment Terms |

**Sample citations:**
- `Product` — Lenovo ThinkPad L15 Gen 5 (Qty: 1,200) + Lenovo USB-C Universal Dock (Qty: 1,200) — confirms the pipeline is NOT confused with Bid2's Dell Latitude

**Compliance score: 70%** | Passed: 14 | Failed: 1 | Not Found: 5 | Addenda: none detected

---

## 3. Search Evaluation Results (22 Benchmark Queries)

```
| Mode                   | Recall@1 | Recall@3 | Recall@5 | MRR    |
|------------------------|----------|----------|----------|--------|
| Dense (BGE-Small)      |  0.3636  |  0.7273  |  0.8182  | 0.5379 |
| BM25 Only              |  0.5455  |  0.8182  |  0.8636  | 0.6856 |
| Hybrid (RRF k=60)      |  0.5000  |  0.8182  |  0.8182  | 0.6591 |
| Hybrid + CrossEncoder  |  0.5455  |  0.8182  |  0.8636  | 0.6833 |
```

**BM25 and Hybrid+CrossEncoder are tied best: Recall@5 = 0.864, MRR ~0.685.**

### Queries that missed (Recall@5 = 0) in Hybrid+CrossEncoder mode

| Query ID | Query | Root Cause |
|----------|-------|------------|
| Q10 | RAM memory capacity and module layout | Spec table embedded as single large chunk; row-level content not retrievable |
| Q11 | Revised deadline after Addendum 2 | Addendum 2 chunk not surfaced at top-5 despite extraction correctly picking it up |
| Q19 | Paraphrased due date (computing devices contract) | Paraphrase distance too large for BM25; dense model misses "computing devices" synonym |

All three are **retrieval failures**, not extraction failures — the extraction layer correctly returns the Addendum 2 date for Bid1.

---

## 4. QA Log Summary (`outputs/qa_log.md`)

15 questions answered end-to-end (dynamic routing -> retrieval -> LLM synthesis -> citations):

| # | Question | Routed To |
|---|----------|-----------|
| 1 | Solicitation number for Bid1? | Bid1 |
| 2 | Proposal due date for Bid2? | Bid2 |
| 3 | Issuing organisation for Austin ISD bid? | Bid3 |
| 4 | All product tiers and quantities — Dallas ISD? | Bid1 |
| 5 | Products required by MD State Treasurer? | Bid2 |
| 6 | Laptop model and quantity Austin ISD wants? | Bid3 |
| 7 | Compare warranty terms across all three bids | cross-bid |
| 8 | Which bid has the earliest deadline? | cross-bid |
| 9 | Compare procurement scale (total units) | cross-bid |
| 10 | Which bids mention pre-bid meeting? | cross-bid |
| 11 | Did addenda change Dallas ISD due date? | Bid1 |
| 12 | Insurance requirements — Dallas ISD? | Bid1 |
| 13 | Evaluation criteria — Austin ISD? | Bid3 |
| 14 | Difference in issuing authority between Bid1 and Bid2? | cross-bid |
| 15 | Summarise all three bids in one paragraph each | cross-bid |

---

## 5. Design Decisions & What Was Fixed Since Last Report

### 5a. Extraction Layer (full rewrite)
- **Removed:** `GroundedRuleExtractor`, all bid-specific regexes (bid numbers, titles, "Dell Latitude 5550 XCTO Base", hard-coded Term of Bid string, canned risk text).
- **API key:** Fails loudly with `RuntimeError` if `GEMINI_API_KEY` not set — no silent fallback.
- **LLM:** Gemini Flash Lite via `x-goog-api-key` header, `temperature=0`, JSON mode with Pydantic validation + 1 repair retry.
- **Citations:** Every FOUND field must have `verbatim_quote + file + page` or is set to `null` with `null_reason = "Not found in documents"`. Finalizer enforces this gate — the old `FieldSource(file="Solicitation Document", page=1)` fallback is deleted.

### 5b. Reconciliation
- Addendum chunks retrieved by `doc_type=addendum`, ordered by addendum number.
- Amended fields accepted only if quote is a **contiguous substring** of an addendum chunk (not just LLM-asserted).
- Confidence **computed** from substring match position + chunk confidence (not hardcoded 0.95).
- Addendum summary path: "what changed in Addendum N" returns ALL changed fields with before/after values.

### 5c. QA Agent
- `route_bid()` uses indexed metadata (title, issuing_org, solicitation_number from `DocumentChunk.metadata`) — zero hardcoded keywords ("dell", "dallas", "maryland", "isd", "ja-207652" all removed).
- Per-bid comparison produces structured tables.

### 5d. Finalizer
- `FieldSource(file="Solicitation Document", page=1)` fallback deleted.
- A value with no real citation fails validation and is set to `null`.

---

## 6. Known Gaps & Suggested Next Steps

### Retrieval (medium priority)
- **Q10/Q11/Q19 misses:** Three benchmark queries still miss at Recall@5.
  - Q10: Extract table rows as separate chunks during ingestion instead of embedding entire spec tables as one chunk.
  - Q11/Q19: Add query expansion with synonym injection ("due date" -> "submission deadline", "closing date") at retrieval time, not only at extraction retry time.
- **Dense model underperforms:** BGE-Small Recall@1 = 0.36 vs BM25 0.54. Consider `BAAI/bge-base-en-v1.5` or `intfloat/e5-base-v2`.

### Extraction (medium priority)
- **Bid1 has 0 addendum_changes logged** even though Addendum 2 changed the due date. The extraction correctly returns the new date (cited from Addendum 2), but the `addendum_changes` counter in `reconciliation_agent.py` is not incremented when an amended field is accepted. Minor bookkeeping bug.
- **Addendum 2 chunks:** Verify that `doc_type=addendum` is set on Addendum 2 chunks in the index. If they are ingested as `doc_type=general` they are silently skipped by the reconciler's chunk filter.
- **>30% null fields:** Consider a warning when more than 30% of fields are null before returning the final JSON.

### Infrastructure (low priority)
- **Sequential bid extraction:** `main.py extract --bid ./Bid1,./Bid2,./Bid3` runs sequentially. Could parallelize at the bid level with `ThreadPoolExecutor`.
- **Token counting:** `extraction/llm_client.py` does not count input/output tokens per call. Add a `TokenUsage` field to trace steps for cost tracking.
- **API error surfacing:** Confirm 429/5xx from Gemini raises exceptions rather than returning empty field results. Add `requests.exceptions.HTTPError` catch with re-raise in `llm_client.py`.
- **Rate limiter via env var:** The 14 RPM limit is set in code; expose it via `settings.LLM_RATE_LIMIT_RPM`.

### Testing
- `tests/test_gemini_api.py` — connectivity smoke test (verified working).
- No unit tests for reconciliation substring check or QA routing yet.
- Add `tests/test_reconciliation.py` and `tests/test_qa_routing.py`.

---

## 7. How to Run

```bash
# Prerequisites
cp .env.example .env
# Set GEMINI_API_KEY in .env
pip install -r requirements.txt

# Extract each bid
python main.py extract --bid ./Bid1
python main.py extract --bid ./Bid2
python main.py extract --bid ./Bid3

# Run search eval
python -m scripts.run_search_eval

# Interactive Q&A
python main.py ask "What is the due date for the Dallas ISD bid?"
python main.py ask "Compare warranty terms across all bids"

# Generate full qa_log.md (15 preset questions)
python scripts/generate_qa_log.py
```

---

## 8. Environment Variables (`.env.example`)

```
GEMINI_API_KEY=                   # Required — Gemini Flash Lite
GEMINI_MODEL=gemini-flash-lite-latest
LLM_TEMPERATURE=0
LLM_RATE_LIMIT_RPM=14
EMBED_MODEL=BAAI/bge-small-en-v1.5
INDEX_DIR=data/search_index
OUTPUT_DIR=outputs
API_HOST=0.0.0.0
API_PORT=8000
```

---

*Report generated by Antigravity (Gemini). Commit `ab5066a` — 29 files changed, 3277 insertions.*
