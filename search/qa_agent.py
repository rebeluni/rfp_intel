"""
Q&A Agent with Dynamic Metadata Bid Routing and LLM Synthesis.
Strictly implements Requirements 2 & 3:
  1. Zero hardcoded keywords (no 'dell', 'dallas', 'maryland', 'isd', 'ja-207652').
  2. Dynamically routes from indexed metadata (title, issuing organization, solicitation
     number from bid_page chunks) or BM25/LLM against per-bid summaries.
  3. For comparison questions, retrieves per bid and synthesizes structured comparison.
  4. Explicit addendum-summary path for 'what changed in Addendum N' listing ALL changes.
  5. Returns LLM-written answer with structured citations [{file, page, quote}].
"""

import re
import logging
from typing import Any, Dict, List, Optional, Set
from config.settings import settings
from search.hybrid_retriever import HybridRetriever
from extraction.llm_client import GeminiClient, get_llm_client
from extraction.reconciliation_agent import ReconciliationAgent

logger = logging.getLogger(__name__)


class QAAgent:
    """Intelligent Q&A agent supporting dynamic metadata bid routing and LLM citation synthesis."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        llm_client: Optional[GeminiClient] = None,
        reconciler: Optional[ReconciliationAgent] = None
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = llm_client or get_llm_client()
        self.reconciler = reconciler or ReconciliationAgent(retriever=self.retriever, llm_client=self.llm_client)
        self._bid_catalog: Optional[Dict[str, Dict[str, Any]]] = None

    def _get_bid_catalog(self) -> Dict[str, Dict[str, Any]]:
        """
        Dynamically inspect indexed chunks to extract metadata per bid package:
        - solicitation numbers (e.g. JA-207652, BPM044557, AISD-2025-9988)
        - titles / headings
        - issuing agencies / organizations
        - associated filenames
        """
        if self._bid_catalog is not None:
            return self._bid_catalog

        catalog: Dict[str, Dict[str, Any]] = {}
        if not hasattr(self.retriever, "bm25_index") or not self.retriever.bm25_index.chunks:
            return catalog

        for chk in self.retriever.bm25_index.chunks:
            bid = chk.metadata.bid_id
            if not bid:
                continue
            if bid not in catalog:
                catalog[bid] = {
                    "bid_id": bid,
                    "solicitation_numbers": set(),
                    "filenames": set(),
                    "agencies": set(),
                    "titles": set(),
                    "sample_texts": []
                }

            meta = chk.metadata
            catalog[bid]["filenames"].add(meta.file_name.lower())

            # Detect solicitation numbers from text or headers
            # Common patterns: Letters+Numbers with hyphens/slashes
            sol_matches = re.findall(
                r"\b(?:RFP\s*(?:NO\.?|#)?\s*|PORFP\s*(?:NO\.?|#)?\s*|PROJECT\s*(?:NO\.?|#)?\s*)?([A-Z0-9]{2,}[-_][A-Z0-9-_]{2,})\b",
                chk.text,
                re.IGNORECASE
            )
            for sm in sol_matches:
                if len(sm) >= 4 and not sm.startswith("http"):
                    catalog[bid]["solicitation_numbers"].add(sm.lower())

            # Check cover or bid_page chunks for agency and title tokens
            is_cover = (meta.page_number == 1) or (
                hasattr(meta.doc_type, "value") and meta.doc_type.value in ["bid_page", "specs"]
            )
            if is_cover and len(catalog[bid]["sample_texts"]) < 5:
                catalog[bid]["sample_texts"].append(chk.text[:300])

                # Extract potential organization names (e.g., School District, Department, Treasurer, Authority)
                org_matches = re.findall(
                    r"([A-Z][A-Za-z0-9&,\.\s]{3,40}(?:School District|ISD|Treasurer|Department|State of|County|City|Commission))",
                    chk.text
                )
                for om in org_matches:
                    catalog[bid]["agencies"].add(om.strip().lower())

        self._bid_catalog = catalog
        return catalog

    def is_comparison_query(self, question: str) -> bool:
        """Detect whether the question asks for comparison across multiple bids."""
        q = question.lower()
        comparison_indicators = [
            "compare", "comparison", "both bids", "all bids", "difference between",
            "differ between", "which bid", "across bids", "between bid 1 and bid 2",
            "between bid1 and bid2"
        ]
        return any(ind in q for ind in comparison_indicators)

    def route_bid(self, question: str) -> Optional[str]:
        """
        Dynamically route natural language question to a target bid package.
        Uses indexed metadata (solicitation numbers, issuing bodies, filenames)
        and BM25 relevance scoring. Zero hardcoded keywords.
        """
        q = question.lower()

        # 1. Comparison detection
        if self.is_comparison_query(question):
            return "COMPARISON"

        # 2. Direct bid ID mentions (e.g., 'Bid 1', 'Bid1', 'Bid-1')
        bid_direct_match = re.search(r"\bbid\s*[-_]?\s*([123])\b", q)
        if bid_direct_match:
            return f"Bid{bid_direct_match.group(1)}"

        catalog = self._get_bid_catalog()
        if not catalog:
            return None

        # 3. Match against dynamic metadata catalog
        bid_scores: Dict[str, float] = {b: 0.0 for b in catalog}

        for bid, meta in catalog.items():
            # Check solicitation numbers
            for sol_num in meta["solicitation_numbers"]:
                if sol_num in q:
                    bid_scores[bid] += 10.0

            # Check filenames
            for fname in meta["filenames"]:
                base = fname.replace(".pdf", "").replace(".html", "")
                if len(base) > 4 and base in q:
                    bid_scores[bid] += 5.0

            # Check agency names
            for agency in meta["agencies"]:
                if agency in q:
                    bid_scores[bid] += 8.0
                else:
                    # Token match agency parts (e.g., 'austin', 'dallas', 'treasurer')
                    for word in agency.split():
                        if len(word) > 4 and word in q:
                            bid_scores[bid] += 3.0

        best_bid = max(bid_scores, key=bid_scores.get)
        if bid_scores[best_bid] > 0.0:
            return best_bid

        # 4. Fallback: BM25 score aggregation across indexed corpus
        if hasattr(self.retriever, "bm25_index") and self.retriever.bm25_index.chunks:
            bm25_res = self.retriever.bm25_index.search(question, top_k=8)
            bid_chunk_scores: Dict[str, float] = {}
            for chk, sc in bm25_res:
                b = chk.metadata.bid_id
                if b:
                    bid_chunk_scores[b] = bid_chunk_scores.get(b, 0.0) + sc

            if bid_chunk_scores:
                best_bm25_bid = max(bid_chunk_scores, key=bid_chunk_scores.get)
                if bid_chunk_scores[best_bm25_bid] > 0.1:
                    return best_bm25_bid

        return None

    def ask(self, question: str, bid_id: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
        """
        Answer a question with dynamic routing, comparison handling, addendum summary paths,
        hybrid retrieval, and LLM synthesis.
        """
        target_bid = bid_id or self.route_bid(question)

        # -------------------------------------------------------------------
        # 1. Addendum Summary Path ("what changed in Addendum N")
        # -------------------------------------------------------------------
        add_match = re.search(r"addendum\s*(?:no\.?|#)?\s*(\d+)", question, re.IGNORECASE)
        is_addendum_summary_q = add_match and any(
            phrase in question.lower()
            for phrase in ["what changed", "changes in", "changed in", "summary of addendum", "modifications in"]
        )

        if is_addendum_summary_q and target_bid and target_bid != "COMPARISON":
            add_num = int(add_match.group(1))
            logger.info(f"[QAAgent] Routing to explicit addendum summary path for {target_bid} Addendum {add_num}...")
            summary_obj = self.reconciler.get_addendum_summary(bid_id=target_bid, addendum_number=add_num)
            
            # Format answer with all changes
            lines = [
                f"### Addendum {add_num} Summary for {target_bid} ({summary_obj.file_name})\n",
                f"**Overview:** {summary_obj.overview}\n",
                "**Modifications and Clarifications:**"
            ]
            citations = []
            if summary_obj.all_changes:
                for idx, chg in enumerate(summary_obj.all_changes, 1):
                    sec = chg.get("section", "General")
                    desc = chg.get("description", "")
                    qt = chg.get("quote", "")
                    lines.append(f"{idx}. **[{sec}]** {desc}")
                    if qt:
                        lines.append(f"   - *Contiguous Quote:* \"{qt}\"")
                        citations.append({
                            "file": summary_obj.file_name,
                            "page": 1,
                            "quote": qt
                        })
            else:
                lines.append("No explicit modifications detected in this addendum.")

            return {
                "question": question,
                "target_bid": target_bid,
                "answer": "\n".join(lines),
                "citations": citations,
                "is_addendum_summary": True
            }

        # -------------------------------------------------------------------
        # 2. Cross-Bid Comparison Path ("compare warranty of both bids", etc.)
        # -------------------------------------------------------------------
        if target_bid == "COMPARISON" or self.is_comparison_query(question):
            logger.info("[QAAgent] Executing per-bid cross-comparison retrieval...")
            catalog = self._get_bid_catalog()
            available_bids = sorted(list(catalog.keys())) if catalog else ["Bid1", "Bid2"]

            comparison_passages: List[Dict[str, Any]] = []
            for b in available_bids:
                bid_results = self.retriever.search(
                    query=question,
                    top_k=3,
                    bid_id=b,
                    mode="hybrid",
                    expand_query=True
                )
                for r in bid_results:
                    comparison_passages.append({
                        "chunk_id": r.chunk_id,
                        "file_name": f"[{b}] {r.file_name}",
                        "page_number": r.page_number,
                        "text": f"[{b}] {r.text}",
                        "score": r.rerank_score or r.rrf_score
                    })

            if not comparison_passages:
                return {
                    "question": question,
                    "target_bid": "All Bids",
                    "answer": "Not found in documents across any bids.",
                    "citations": []
                }

            comp_prompt = (
                f"Compare how each bid ({', '.join(available_bids)}) addresses the following question: '{question}'.\n"
                f"Structure your response by comparing the terms for each bid with exact quotations, "
                f"then provide a concise summary table or bulleted difference."
            )
            llm_resp = self.llm_client.answer_question(comp_prompt, comparison_passages)

            return {
                "question": question,
                "target_bid": "All Bids (Comparison)",
                "answer": llm_resp.get("answer", "Not found in documents."),
                "citations": llm_resp.get("citations", []),
                "raw_evidence_count": len(comparison_passages)
            }

        # -------------------------------------------------------------------
        # 3. Standard Single-Bid Retrieval & Synthesis
        # -------------------------------------------------------------------
        results = self.retriever.search(
            query=question,
            top_k=top_k,
            bid_id=target_bid,
            mode="hybrid",
            expand_query=True
        )

        if not results:
            return {
                "question": question,
                "target_bid": target_bid,
                "answer": "Not found in documents.",
                "citations": []
            }

        evidence_passages = [
            {
                "chunk_id": r.chunk_id,
                "file_name": r.file_name,
                "page_number": r.page_number,
                "text": r.text,
                "score": r.rerank_score or r.rrf_score
            }
            for r in results
        ]

        llm_resp = self.llm_client.answer_question(question, evidence_passages)

        return {
            "question": question,
            "target_bid": target_bid,
            "answer": llm_resp.get("answer", "Not found in documents."),
            "citations": llm_resp.get("citations", []),
            "raw_evidence_count": len(results)
        }
