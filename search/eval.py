"""
Evaluation Benchmark for Phase 2 Search Engine.
Compares 4 retrieval modes:
  1. Dense-only (BAAI/bge-small-en-v1.5)
  2. BM25-only (Specialized compound/alphanumeric tokenizer)
  3. Hybrid (RRF fusion, k=60)
  4. Hybrid + Cross-Encoder Rerank (cross-encoder/ms-marco-MiniLM-L-6-v2)

Ground truths are labeled by text substring + (file_name, page_number) so metrics survive re-chunking.
Metrics: Recall@1, Recall@3, Recall@5, MRR.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from config.settings import settings
from search.hybrid_retriever import HybridRetriever, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class EvalBenchmarkItem:
    query_id: str
    query: str
    target_substring: str
    expected_file: str
    expected_page: int
    query_type: str  # 'exact_match', 'specs', 'dates', 'legal', 'general'
    notes: str = ""


# 22 Hand-Verified Benchmark Questions
BENCHMARK_ITEMS: List[EvalBenchmarkItem] = [
    EvalBenchmarkItem(
        query_id="Q01_bid_num_1",
        query="What is the solicitation number for Student and Staff Computing Devices?",
        target_substring="JA-207652",
        expected_file="Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html",
        expected_page=1,
        query_type="exact_match",
        notes="Exact match solicitation number for Bid 1"
    ),
    EvalBenchmarkItem(
        query_id="Q02_bid_num_2",
        query="What is the eMMA project number or solicitation number for Dell Laptops?",
        target_substring="BPM044557",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=1,
        query_type="exact_match",
        notes="Exact match eMMA project number for Bid 2"
    ),
    EvalBenchmarkItem(
        query_id="Q03_sku_base",
        query="210-BLYZ",
        target_substring="210-BLYZ",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="exact_match",
        notes="Exact SKU query for Dell Latitude 5550 XCTO Base"
    ),
    EvalBenchmarkItem(
        query_id="Q04_sku_processor",
        query="What is the processor SKU for Intel Core Ultra 5 125U?",
        target_substring="379-BFNZ",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="exact_match",
        notes="Processor SKU lookup in technical specs"
    ),
    EvalBenchmarkItem(
        query_id="Q05_email_poc",
        query="thawkins@treasurer.state.md.us",
        target_substring="thawkins@treasurer.state.md.us",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="exact_match",
        notes="Exact match email address for agency POC"
    ),
    EvalBenchmarkItem(
        query_id="Q06_phone_poc",
        query="What is the agency point of contact phone number for Tamaira Hawkins?",
        target_substring="410-260-7533",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="exact_match",
        notes="Phone number lookup in PORFP"
    ),
    EvalBenchmarkItem(
        query_id="Q07_addendum1_usb",
        query="Does the display monitor non-touch require a 3.1 USB port or is 3.0 ok?",
        target_substring="3.1 USB port",
        expected_file="Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="specs",
        notes="Addendum 1 clarification item 1"
    ),
    EvalBenchmarkItem(
        query_id="Q08_addendum2_header",
        query="What addendum changes were made in Addendum No. 2 for JA-207652?",
        target_substring="ADDENDUM No. 2",
        expected_file="Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="general",
        notes="Addendum 2 deadline extension notice"
    ),
    EvalBenchmarkItem(
        query_id="Q09_laptop_qty",
        query="How many Dell Latitude laptops are to be purchased in the PORFP?",
        target_substring="Quantity",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=4,
        query_type="specs",
        notes="Quantity (30) in Scope of Work table"
    ),
    EvalBenchmarkItem(
        query_id="Q10_delivery_address",
        query="Where should the hardware be delivered for the Maryland State Treasurer?",
        target_substring="80 Calvert Street",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="dates_logistics",
        notes="Delivery address in Section 2/3"
    ),
    EvalBenchmarkItem(
        query_id="Q11_contract_term",
        query="What is the length of contract or contract duration for Dallas ISD?",
        target_substring="LENGTH OF CONTRACT",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=2,
        query_type="legal",
        notes="Length of contract layout block on page 2"
    ),
    EvalBenchmarkItem(
        query_id="Q12_mwbe_forms",
        query="What are the M/WBE form requirements for Dallas ISD submission?",
        target_substring="M/WBE",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=14,
        query_type="legal",
        notes="M/WBE department instructions and forms"
    ),
    EvalBenchmarkItem(
        query_id="Q13_mercury_affidavit",
        query="What are the mercury free equipment certification requirements?",
        target_substring="Mercury",
        expected_file="Mercury_Affidavit.pdf",
        expected_page=1,
        query_type="legal",
        notes="State of Maryland Mercury Affidavit"
    ),
    EvalBenchmarkItem(
        query_id="Q14_contract_affidavit",
        query="What corporate registration and tax payment affirmations are required?",
        target_substring="CERTIFICATION OF REGISTRATION",
        expected_file="Contract_Affidavit.pdf",
        expected_page=1,
        query_type="legal",
        notes="Contract Affidavit Section B"
    ),
    EvalBenchmarkItem(
        query_id="Q15_eval_criteria",
        query="What is the technical evaluation criteria and basis for award in Bid 2?",
        target_substring="Accuracy of Bid (Meets All Requirements)",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=4,
        query_type="legal",
        notes="Technical evaluation criteria Section 5"
    ),
    EvalBenchmarkItem(
        query_id="Q16_prebid_conference",
        query="When is the pre-proposal conference scheduled for Dallas ISD computing devices?",
        target_substring="Pre-Proposal Meeting",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=2,
        query_type="dates",
        notes="Pre-proposal meeting schedule on page 2"
    ),
    EvalBenchmarkItem(
        query_id="Q17_questions_due",
        query="What is the questions due deadline on the portal for Dallas ISD?",
        target_substring="06/11/2024",
        expected_file="Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html",
        expected_page=1,
        query_type="dates",
        notes="Portal Questions Due date key"
    ),
    EvalBenchmarkItem(
        query_id="Q18_warranty_fa",
        query="What functional area covers manufacturer extended warranty in Bid 2?",
        target_substring="FA V",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=1,
        query_type="specs",
        notes="Functional Area V for Extended Warranty"
    ),
    EvalBenchmarkItem(
        query_id="Q19_power_adapter",
        query="What power adapter wattage is specified for the Dell Latitude laptops?",
        target_substring="65W AC adapter",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs",
        notes="AC adapter line item in specs table"
    ),
    EvalBenchmarkItem(
        query_id="Q20_hot_swap",
        query="What process is required for maintaining an inventory of hot swap devices?",
        target_substring="hot swap",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=9,
        query_type="general",
        notes="Hot swap inventory question 11 on page 9"
    ),
    EvalBenchmarkItem(
        query_id="Q21_w9_requirement",
        query="Where does the offeror need to submit the W9 form in the submission?",
        target_substring="W9 Form",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=33,
        query_type="legal",
        notes="Required submission attachments table on page 33"
    ),
    EvalBenchmarkItem(
        query_id="Q22_ram_specs",
        query="What RAM memory configuration is required for the Latitude 5550?",
        target_substring="16 GB",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs",
        notes="RAM configuration (16 GB: 2 x 8 GB DDR5)"
    ),
]


class RetrievalEvaluator:
    """Evaluates search retrieval modes against hand-verified benchmark items."""

    def __init__(self, retriever: Optional[HybridRetriever] = None):
        self.retriever = retriever or HybridRetriever()

    def evaluate_item(
        self,
        item: EvalBenchmarkItem,
        mode: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Evaluate a single benchmark item for a given retrieval mode.
        Checks whether any top-k result contains target_substring AND matches expected file.
        """
        results: List[SearchResult] = self.retriever.search(
            query=item.query,
            top_k=top_k,
            mode=mode,
        )

        matched_rank: Optional[int] = None
        matched_chunk_id: Optional[str] = None

        for rank, res in enumerate(results, 1):
            text_match = item.target_substring.lower() in res.text.lower()
            file_match = (
                item.expected_file.lower() in res.file_name.lower()
                or res.file_name.lower() in item.expected_file.lower()
            )
            # Match is successful if the ground-truth text substring is present in the cited document
            if text_match and file_match:
                matched_rank = rank
                matched_chunk_id = res.chunk_id
                break

        reciprocal_rank = 1.0 / matched_rank if matched_rank else 0.0

        return {
            "query_id": item.query_id,
            "query": item.query,
            "mode": mode,
            "matched_rank": matched_rank,
            "matched_chunk_id": matched_chunk_id,
            "recall_at_1": 1 if matched_rank == 1 else 0,
            "recall_at_3": 1 if (matched_rank and matched_rank <= 3) else 0,
            "recall_at_5": 1 if (matched_rank and matched_rank <= 5) else 0,
            "reciprocal_rank": reciprocal_rank,
            "top_result_citation": results[0].format_citation() if results else "None",
            "top_result_snippet": results[0].text[:200] if results else "None",
        }

    def run_benchmark(self, modes: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run all benchmark items across modes and compute aggregate metrics.
        """
        modes = modes or ["dense_only", "bm25_only", "hybrid_norerank", "hybrid"]
        mode_metrics = {}
        all_eval_details = {m: [] for m in modes}

        for m in modes:
            logger.info(f"Running evaluation benchmark on mode: '{m}'...")
            items_evaluated = []
            for item in BENCHMARK_ITEMS:
                res = self.evaluate_item(item, mode=m, top_k=5)
                items_evaluated.append(res)
                all_eval_details[m].append(res)

            total = len(items_evaluated)
            r1 = sum(i["recall_at_1"] for i in items_evaluated) / total
            r3 = sum(i["recall_at_3"] for i in items_evaluated) / total
            r5 = sum(i["recall_at_5"] for i in items_evaluated) / total
            mrr = sum(i["reciprocal_rank"] for i in items_evaluated) / total

            mode_metrics[m] = {
                "total_queries": total,
                "recall_at_1": round(r1, 4),
                "recall_at_3": round(r3, 4),
                "recall_at_5": round(r5, 4),
                "mrr": round(mrr, 4),
            }

        return {
            "metrics": mode_metrics,
            "details": all_eval_details,
        }
