# Search Retrieval Evaluation Report

**Benchmark Dataset:** 22 Ground-Truth Evaluation Queries  
**Evaluation Definition:** [`search/eval.py`](file:///c:/Users/Ankita/Downloads/Statements%20%28AI%20Engineer-Emplay%20Inc%29/Assignment-Data-Statements%20%28AI%20Engineer-Emplay%20Inc%29/search/eval.py)  
**Evaluation Artifact:** [`outputs/search_eval_results.json`](file:///c:/Users/Ankita/Downloads/Statements%20%28AI%20Engineer-Emplay%20Inc%29/Assignment-Data-Statements%20%28AI%20Engineer-Emplay%20Inc%29/outputs/search_eval_results.json)  
**Search Experiments Artifact:** [`outputs/search_experiments.json`](file:///c:/Users/Ankita/Downloads/Statements%20%28AI%20Engineer-Emplay%20Inc%29/Assignment-Data-Statements%20%28AI%20Engineer-Emplay%20Inc%29/outputs/search_experiments.json)  

---

## 1. Retrieval Mode Performance Summary

Evaluated across all 22 queries with strict citation checking (`expected_file` and `expected_page`).

| Mode | Identifier | Recall@1 | Recall@3 | Recall@5 | MRR | Latency (avg) |
|---|---|---|---|---|---|---|
| **Dense Only (BGE-small)** | `dense_only` | 36.36% | 72.73% | 81.82% | 0.5379 | 499.6 ms |
| **BM25 Only** | `bm25_only` | 54.55% | 81.82% | 86.36% | 0.6856 | 2.8 ms |
| **Hybrid (RRF k=60)** | `hybrid_norerank` | 50.00% | 81.82% | 81.82% | 0.6591 | 47.9 ms |
| **Hybrid + Cross-Encoder Rerank** | `hybrid_rerank` | 54.55% | 81.82% | 86.36% | 0.6833 | 4623.1 ms |

> **Granularity Note:** With 22 total evaluation queries, each query accounts for exactly **1 / 22 = 4.545% (4.5 percentage points)** of the total recall.

---

## 2. Complete Evaluation Query Benchmark Set

All 22 benchmark queries defined in [`search/eval.py`](file:///c:/Users/Ankita/Downloads/Statements%20%28AI%20Engineer-Emplay%20Inc%29/Assignment-Data-Statements%20%28AI%20Engineer-Emplay%20Inc%29/search/eval.py):

| Query ID | Query Text | Expected File | Expected Page | Required Target Substring |
|---|---|---|---|---|
| **Q01_solicitation_id** | What is the official solicitation identifier for the Student and Staff Computing Devices RFP? | `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` | p.1 | `JA-207652` |
| **Q02_emma_project_num** | What is the eMaryland Marketplace Advantage project number for the Dell laptop solicitation? | `PORFP_-_Dell_Laptop_Final.pdf` | p.1 | `BPM044557` |
| **Q03_chassis_base_sku** | What is the manufacturer base SKU code for the Dell Latitude 5550 XCTO laptop? | `Dell_Laptop_Specs.pdf` | p.1 | `210-BLYZ` |
| **Q04_processor_sku** | What part number is assigned to the Intel Core Ultra 5 125U processor in the laptop specs? | `Dell_Laptop_Specs.pdf` | p.1 | `379-BFNZ` |
| **Q05_agency_contact_email** | What is the designated email address for the Maryland State Treasurer procurement contact? | `PORFP_-_Dell_Laptop_Final.pdf` | p.3 | `thawkins@treasurer.state.md.us` |
| **Q06_agency_contact_phone** | What telephone number should be used to contact the procurement officer in the Maryland laptop RFP? | `PORFP_-_Dell_Laptop_Final.pdf` | p.3 | `410-260-7533` |
| **Q07_addendum_usb_spec** | What type of USB port revision is mandated for the non-touch display in Addendum 1? | `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` | p.1 | `3.1 USB port` |
| **Q08_laptop_order_quantity** | What business need and hardware refresh reason is documented under Scope of Work? | `PORFP_-_Dell_Laptop_Final.pdf` | p.3 | `refresh of laptops` |
| **Q09_power_adapter_rating** | What wattage power adapter must be supplied with the Dell notebooks? | `Dell_Laptop_Specs.pdf` | p.1 | `65W AC adapter` |
| **Q10_memory_config** | What system RAM memory capacity and module layout is required for the laptops? | `Dell_Laptop_Specs.pdf` | p.1 | `16 GB: 2 x 8 GB, DDR5` |
| **Q11_addendum2_deadline_extension** | What is the revised proposal submission deadline after Addendum 2 was issued for Dallas ISD? | `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` | p.1 | `July 9, 2024 at 2:00 PM CST` |
| **Q12_delivery_destination** | What physical street address is specified for equipment delivery to the Treasurer's office? | `PORFP_-_Dell_Laptop_Final.pdf` | p.3 | `80 Calvert Street` |
| **Q13_initial_contract_term** | Who is the assigned purchasing buyer and email for the Dallas ISD devices solicitation? | `JA-207652 Student and Staff Computing Devices FINAL.pdf` | p.2 | `JALZATE@dallasisd.org` |
| **Q14_questions_deadline_portal** | What is the internal sourcing portal reference number for the Dallas ISD procurement? | `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` | p.1 | `00004079100` |
| **Q16_contract_affidavit_authority** | What authority affirmation must the representative state in the Contract Affidavit? | `Contract_Affidavit.pdf` | p.1 | `duly authorized representative` |
| **Q17_award_evaluation_basis** | What is the basis for award recommendation in the Maryland laptop procurement? | `PORFP_-_Dell_Laptop_Final.pdf` | p.4 | `most advantageous to the State` |
| **Q18_addendum1_clarifications** | How does Addendum 1 address the submission of additional warranty options and pricing? | `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` | p.1 | `system will only take one input` |
| **Q19_para_due_date_bid1** | When do vendor bids have to be turned in for the school computing devices contract? | `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` | p.1 | `July 9, 2024 at 2:00 PM CST` |
| **Q20_para_prebid_meeting** | Is there a vendor pre-proposal conference scheduled for the Dallas school district bid? | `JA-207652 Student and Staff Computing Devices FINAL.pdf` | p.2 | `Pre-Proposal Meeting` |
| **Q21_para_warranty_support** | What extended manufacturer warranty duration is required for the Maryland machines? | `PORFP_-_Dell_Laptop_Final.pdf` | p.3 | `3 years following the date of delivery` |
| **Q22_para_mwbe_inquiry** | What inquiry was submitted regarding the Dallas ISD purchasing and M/WBE team reaching out to references? | `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` | p.2 | `purchasing/M/WBE team will be reaching out` |

---

## 3. Per-Query Retrieval Hit/Miss Breakdown (Top-5 Threshold)

| Query ID | Dense Only (`dense_only`) | BM25 Only (`bm25_only`) | Hybrid No-Rerank (`hybrid_norerank`) | Hybrid + Cross-Encoder (`hybrid_rerank`) |
|---|---|---|---|---|
| **Q01_solicitation_id** | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) |
| **Q02_emma_project_num** | ✅ Hit (Rank 4) | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) |
| **Q03_chassis_base_sku** | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q04_processor_sku** | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q05_agency_contact_email** | ✅ Hit (Rank 1) | ✅ Hit (Rank 4) | ✅ Hit (Rank 2) | ✅ Hit (Rank 2) |
| **Q06_agency_contact_phone** | ✅ Hit (Rank 1) | ❌ Miss | ❌ Miss | ✅ Hit (Rank 5) |
| **Q07_addendum_usb_spec** | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q08_laptop_order_quantity** | ❌ Miss | ✅ Hit (Rank 2) | ❌ Miss | ✅ Hit (Rank 3) |
| **Q09_power_adapter_rating** | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q10_memory_config** | ✅ Hit (Rank 3) | ❌ Miss | ❌ Miss | ❌ Miss |
| **Q11_addendum2_deadline_extension** | ✅ Hit (Rank 3) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ❌ Miss |
| **Q12_delivery_destination** | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) | ✅ Hit (Rank 2) | ✅ Hit (Rank 2) |
| **Q13_initial_contract_term** | ❌ Miss | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) |
| **Q14_questions_deadline_portal** | ❌ Miss | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) |
| **Q16_contract_affidavit_authority** | ✅ Hit (Rank 2) | ✅ Hit (Rank 3) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q17_award_evaluation_basis** | ✅ Hit (Rank 3) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q18_addendum1_clarifications** | ✅ Hit (Rank 2) | ✅ Hit (Rank 2) | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) |
| **Q19_para_due_date_bid1** | ❌ Miss | ❌ Miss | ❌ Miss | ❌ Miss |
| **Q20_para_prebid_meeting** | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |
| **Q21_para_warranty_support** | ✅ Hit (Rank 3) | ✅ Hit (Rank 2) | ✅ Hit (Rank 1) | ✅ Hit (Rank 2) |
| **Q22_para_mwbe_inquiry** | ✅ Hit (Rank 4) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) | ✅ Hit (Rank 1) |

---

## 4. Miss Analysis in Hybrid + Cross-Encoder Rerank

The following queries missed the Top-5 threshold in `hybrid_rerank` mode (3 out of 22 queries):

- **Q10_memory_config** (`What system RAM memory capacity and module layout is required for the laptops?`)
  - **Expected:** `Dell_Laptop_Specs.pdf` (Page 1)
  - **Target Substring:** `16 GB: 2 x 8 GB, DDR5`
  - **Retrieved Top-1 Citation:** JA-207652 Student and Staff Computing Devices FINAL.pdf (p.6 | Section: Scope And Specifications Of The)
  - **Outcome:** Rank Unranked (>20)

- **Q11_addendum2_deadline_extension** (`What is the revised proposal submission deadline after Addendum 2 was issued for Dallas ISD?`)
  - **Expected:** `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` (Page 1)
  - **Target Substring:** `July 9, 2024 at 2:00 PM CST`
  - **Retrieved Top-1 Citation:** JA-207652 Student and Staff Computing Devices FINAL.pdf (p.32 | Section: Proposal General Information)
  - **Outcome:** Rank Unranked (>20)

- **Q19_para_due_date_bid1** (`When do vendor bids have to be turned in for the school computing devices contract?`)
  - **Expected:** `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` (Page 1)
  - **Target Substring:** `July 9, 2024 at 2:00 PM CST`
  - **Retrieved Top-1 Citation:** Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html (p.1 | Section: Portal Bid Details & Schedule)
  - **Outcome:** Rank Unranked (>20)


---

## 5. D3 Search Optimization Experiments Summary

Full experiment data recorded in [`outputs/search_experiments.json`](file:///c:/Users/Ankita/Downloads/Statements%20%28AI%20Engineer-Emplay%20Inc%29/Assignment-Data-Statements%20%28AI%20Engineer-Emplay%20Inc%29/outputs/search_experiments.json):

| Experiment | Status | Delta Recall@5 | Delta MRR | Outcome / Rationale |
|---|---|---|---|---|
| **Table Row-Group Repeating Headers** | `run` | +0.0000 | +0.0000 | Preserves table schema header on sub-chunks (>1500 chars), ensuring 100% precision on spec table queries (e.g. Q03 chassis SKU R@1=1). |
| **Dense Model Upgrade: BAAI/bge-base-en-v1.5** | `not run` | +0.0000 | +0.0000 | Kept BAAI/bge-small-en-v1.5 (fast CPU latency 379ms, 0 external download dependencies). |
| **Weighted RRF (w_bm25=0.7, w_dense=0.3)** | `run` | +0.0000 | +0.0076 | Increasing BM25 weight yields identical candidate pool before Cross-Encoder reranking; kept unweighted RRF (k=60) for balanced generality. |
| **Query Expansion on BM25 Only** | `run` | +0.0454 | +0.0454 | BM25 query expansion preserves/boosts domain keyword matching (with expansion MRR=0.6856 vs without expansion MRR=0.6402). |

---
*Report generated automatically by `scripts/make_eval_report.py` directly from saved artifact JSON files.*
