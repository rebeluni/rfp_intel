# Phase 2 — First Commit Audit Report (Ingestion Patches)

**Git Commit**: `f97c695`  
**Remote Repository**: [https://github.com/rebeluni/rfp_intel.git](https://github.com/rebeluni/rfp_intel.git)  
**Status**: All 5 patches implemented, regression-tested (29/29 passing), and pushed to `master` and `main`.

---

## 1. Summary of Completed Patches

| # | Patch Item | Before (Phase 1) | After (Commit `f97c695`) | Verification |
|---|------------|-------------------|--------------------------|--------------|
| **1** | **Vector-outlined pages (Bid1 p.54–59 IRS W-9)** | Falsely flagged as 0-char empty pages; form widget data discarded. | Logged as `"non-extractable (vector outlines)"` (`drawings > 20`, `text < 30`). Extracted all 35 form widgets on p.54 (1,162 chars). Generated per-doc coverage report in `outputs/coverage_reports/`. | Verified on Bid1 p.54–59: 35 widgets captured, JSON coverage reports written. |
| **2** | **No cross-page chunk merging (p.10 & p.13)** | p.10 and p.13 small text was greedily merged into p.9 and p.12 because `_merge_small_chunks` only checked `file_name`. | Merging restricted strictly to the **same page** (`prev.metadata.page_number == chk.metadata.page_number`). Added `page_start`/`page_end` metadata fields. | Pages 9, 10, 12, 13 each retain their own discrete chunks with accurate page citations. |
| **3** | **Chunk-start section labeling (PORFP p.1 & p.3)** | p.1 was labeled with bottom section (`Bid Submission Instructions`); p.3 was labeled with bottom section (`Section 5`). | Evaluates line 0 of chunk; chunk adopts heading active at its START. Continuing prose inherits active section from prior chunk. | PORFP p.1 is `Section: Section 1 – General Information`. PORFP p.3 is `Section: Section 2 – Agency Point of Contact (POC) Information`. |
| **4** | **Rejoin emails and URLs** | PDF line wraps split emails (`thawkins@treasurer.state.md\n.us`) and URLs (`.../emma-\nqrgs/`). | `TextCleaner.fix_split_urls_and_emails()` rejoins domain splits, `@` splits, and hyphenated/slashed URLs. | `thawkins@treasurer.state.md.us` and `https://procurement.maryland.gov/emma-qrgs/` remain whole. |
| **5** | **Remove phone keys & strip running headers / bare page numbers** | Portal HTML had `- **410-260-7533**: Thawkins@...`. PDFs had repeated running headers (`Purchase Order Request for Proposals (PORFP)`) and bare numbers (`1`, `3`). | Discarded keys matching phone patterns; consolidated `Contact Info`. Stripped repeated running headers and bare page digits in header/footer zones. | HTML portal text has zero phone keys; PORFP page text starts directly with section headings without header clutter. |

---

## 2. Chunk Comparison Before vs. After (PORFP `PORFP_-_Dell_Laptop_Final.pdf`)

```text
[BEFORE PATCHES]
Chunk 1: [Bid2 | RFP | PORFP Dell Laptop Final | p.1 | Section: Bid Submission Instructions]  <-- Mislabelled (took last heading on page)
Chunk 2: [Bid2 | RFP | PORFP Dell Laptop Final | p.2 | Section: Section 2 – Agency Point of]
Chunk 3: [Bid2 | RFP | PORFP Dell Laptop Final | p.3 | Section: Section 5 – Evaluation Criteria]  <-- Mislabelled (took last heading on page)
Chunk 4: [Bid2 | RFP | PORFP Dell Laptop Final | p.4 | Section: General]

[AFTER COMMIT f97c695]
Chunk 1: [Bid2 | RFP | PORFP Dell Laptop Final | p.1 | Section: Section 1 – General Information]  <-- CORRECT (heading at start of chunk)
Chunk 2: [Bid2 | RFP | PORFP Dell Laptop Final | p.2 | Section: Bid Submission Instructions]
Chunk 3: [Bid2 | RFP | PORFP Dell Laptop Final | p.3 | Section: Section 2 – Agency Point of]   <-- CORRECT (continuing POC section)
Chunk 4: [Bid2 | RFP | PORFP Dell Laptop Final | p.4 | Section: Section 5 – Evaluation Criteria]
```

---

## 3. Bid 1 RFP Pages 9–14 Chunks After Cross-Page Merge Fix

```text
Chunk ID: Bid1_..._p9_c0_...   | Page: 9  | Words: 229
Chunk ID: Bid1_..._p9_c1_...   | Page: 9  | Words: 264
Chunk ID: Bid1_..._p10_c0_...  | Page: 10 | Words: 96   <-- Independent chunk, NOT merged into p.9!
Chunk ID: Bid1_..._p11_c0_...  | Page: 11 | Words: 310
Chunk ID: Bid1_..._p12_c0_...  | Page: 12 | Words: 107
Chunk ID: Bid1_..._p12_c1_...  | Page: 12 | Words: 150
Chunk ID: Bid1_..._p13_c0_...  | Page: 13 | Words: 46   <-- Independent chunk, NOT merged into p.12!
```

---

## 4. Vector Outline & Form Widget Coverage Report (Bid 1 RFP)

Extracted coverage metadata from `outputs/coverage_reports/Bid1_JA_207652_Student_and_Staff_Computing_Devices_FINAL_coverage.json`:
- **Total Pages**: 62
- **Vector Outline Pages**: Pages 54, 55, 56, 57, 58, 59
- **Logged Status**: `"non-extractable (vector outlines)"`
- **Page 54 Form Widgets (35 fields extracted)**:
  - `Name1`: text
  - `Business Name`: text
  - `Address`: text
  - `City State Zip`: text
  - `Account number`: text
  - `Requester name`: text
  - `Individual`, `Corporation`, `S Corporation`, `Partnership`, `Trust`, `LLC`, `Other`: CheckBox
  - `Exempt1`, `FATCA`, `Text18` through `Text36`: text
  - `Signature37`: signature
- **Total Text Extracted on Page 54**: 1,162 characters of structured form data.

---

## 5. Test Suite Verification

`pytest tests/test_ingestion.py`
```text
tests/test_ingestion.py .............................  [100%]
======================= 29 passed in 2.91s =======================
```
Regression tests cover:
- `test_no_cross_page_merging_preserves_pages`: proves p.10 and p.13 remain distinct.
- `test_section_label_heading_at_start_of_chunk`: proves chunk-start heading semantics.
- `test_rejoin_split_emails_and_urls`: proves email & URL line wrap recovery.
- `test_portal_phone_key_removal`: proves phone key deletion and contact info consolidation.
- `test_kerning_regression_preserves_valid_words`: proves valid words remain uncorrupted.
