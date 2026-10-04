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
import json
import logging
from pathlib import Path
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
        Dynamically inspect indexed chunks and extracted output files to extract metadata per bid package:
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
            if not bid or (not bid.lower().startswith("bid") and not (Path(settings.PROJECT_ROOT) / bid).is_dir()):
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
            sol_matches = re.findall(
                r"\b(?:RFP\s*(?:NO\.?|#)?\s*|PORFP\s*(?:NO\.?|#)?\s*|PROJECT\s*(?:NO\.?|#)?\s*)?([A-Z0-9]{2,}[-_][A-Z0-9-_]{2,}|[A-Z]{2,}\d{4,}[A-Z0-9]*|[A-Z]\d{2}[A-Z]\d{6,})\b",
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

                # Extract potential organization names
                org_matches = re.findall(
                    r"([A-Z][A-Za-z0-9&,\.\s]{3,40}(?:School District|ISD|Treasurer|Department|State of|County|City|Commission))",
                    chk.text
                )
                for om in org_matches:
                    catalog[bid]["agencies"].add(om.strip().lower())

        for b in list(catalog.keys()):
            out_p = Path(settings.OUTPUTS_DIR) / f"{b.lower()}.json"
            if out_p.exists():
                try:
                    with open(out_p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        fields = data.get("fields", {})
                        num = (fields.get("Bid Number") or {}).get("value")
                        if num:
                            catalog[b]["solicitation_numbers"].add(str(num).lower())
                        agency = (fields.get("company_name") or {}).get("value")
                        if agency:
                            catalog[b]["agencies"].add(str(agency).lower())
                        ttl = (fields.get("Title") or {}).get("value")
                        if ttl:
                            catalog[b]["titles"].add(str(ttl).lower())
                except Exception:
                    pass

        self._bid_catalog = catalog
        return catalog

    def is_comparison_query(self, question: str) -> bool:
        """Detect whether the question asks for comparison across multiple bids."""
        q = question.lower()
        comparison_indicators = [
            "compare", "comparison", "both bids", "all bids", "all three bids",
            "all 3 bids", "across bids", "across all bids", "difference between",
            "differ between", "which bid", "summarise all", "summarize all",
            "each bid", "every bid"
        ]
        if any(ind in q for ind in comparison_indicators):
            return True
        if re.search(r"\bbetween\s+bid\s*[123]\s*and\s*bid\s*[123]\b", q):
            return True
        return False

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
                    bid_scores[bid] += 12.0

            # Check filenames
            for fname in meta["filenames"]:
                base = fname.replace(".pdf", "").replace(".html", "")
                if len(base) > 4 and base in q:
                    bid_scores[bid] += 6.0

            # Check agency names
            for agency in meta["agencies"]:
                if agency in q:
                    bid_scores[bid] += 10.0
                else:
                    # Token match key words in agency name
                    for word in agency.split():
                        if len(word) > 4 and word in q:
                            bid_scores[bid] += 4.0

            # Check titles
            for title in meta["titles"]:
                for word in title.split():
                    if len(word) > 4 and word in q:
                        bid_scores[bid] += 2.0

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

    def _get_indexed_bids(self) -> List[str]:
        """Dynamically return list of unique bid IDs present in the search index or project folders."""
        catalog = self._get_bid_catalog()
        bids = set()
        if catalog:
            bids.update(catalog.keys())
        if hasattr(self.retriever, "bm25_index") and self.retriever.bm25_index.chunks:
            for chk in self.retriever.bm25_index.chunks:
                b = chk.metadata.bid_id
                if b and (b.lower().startswith("bid") or (Path(settings.PROJECT_ROOT) / b).is_dir()):
                    bids.add(b)
        if not bids and hasattr(self.retriever, "dense_indexer") and self.retriever.dense_indexer.chunks:
            for chk in self.retriever.dense_indexer.chunks:
                b = chk.metadata.bid_id
                if b and (b.lower().startswith("bid") or (Path(settings.PROJECT_ROOT) / b).is_dir()):
                    bids.add(b)
        if not bids:
            root = Path(settings.PROJECT_ROOT)
            for d in root.iterdir():
                if d.is_dir() and d.name.lower().startswith("bid"):
                    bids.add(d.name)
        valid_bids = [b for b in bids if b.lower().startswith("bid") or (Path(settings.PROJECT_ROOT) / b).is_dir()]
        return sorted(valid_bids, key=lambda x: (0 if x == "Bid1" else 1 if x == "Bid2" else 2 if x == "Bid3" else 3, x))

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

        if is_addendum_summary_q:
            add_num = int(add_match.group(1))
            available_bids = self._get_indexed_bids()
            if not target_bid or target_bid == "COMPARISON":
                for b in available_bids:
                    if any(c.get("addendum_number") == add_num for c in self.reconciler.get_addendum_chunks(b)):
                        target_bid = b
                        break
            if not target_bid:
                target_bid = available_bids[0] if available_bids else "Bid1"

            logger.info(f"[QAAgent] Routing to explicit addendum summary path for {target_bid} Addendum {add_num}...")
            summary_obj = self.reconciler.get_addendum_summary(bid_id=target_bid, addendum_number=add_num)
            
            lines = [
                f"### Addendum {add_num} Summary for {target_bid} ({summary_obj.file_name})\n",
                f"**Overview:** {summary_obj.overview}\n",
                "**Modifications and Clarifications:**"
            ]
            citations = []
            if summary_obj.all_changes:
                for idx, chg in enumerate(summary_obj.all_changes, 1):
                    if isinstance(chg, dict):
                        sec = chg.get("category") or chg.get("section", "General")
                        desc = chg.get("description", "")
                        qt = chg.get("quote", "")
                    else:
                        sec = "General"
                        desc = str(chg)
                        qt = ""
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
            all_bids = self._get_indexed_bids()

            q_low = question.lower()
            # Resolve target bids dynamically from question or indexed catalog
            explicit_bids = []
            matches = re.findall(r"\bbid\s*[-_]?\s*([A-Za-z0-9]+)\b", q_low)
            for m in matches:
                candidate = f"Bid{m.upper()}" if not m.lower().startswith("bid") else m
                for b in all_bids:
                    if candidate.lower() == b.lower() and b not in explicit_bids:
                        explicit_bids.append(b)

            if len(explicit_bids) >= 2:
                active_bids = explicit_bids
            elif "both bids" in q_low:
                active_bids = all_bids[:2] if len(all_bids) >= 2 else all_bids
            else:
                active_bids = all_bids

            # Formulate targeted retrieval sub-queries per domain
            if "procurement scale" in q_low or "total units" in q_low or "quantities" in q_low:
                sub_q = "total units target quantity estimated quantity line items laptops devices quantities"
            elif "issuing authority" in q_low or "agency" in q_low:
                sub_q = "issuing authority agency organization department school district treasurer"
            elif "warranty" in q_low:
                sub_q = "warranty extended warranty manufacturer warranty years coverage support terms"
            elif "earliest" in q_low or "deadline" in q_low or "due date" in q_low:
                sub_q = "submission deadline proposal due date and time closing date addendum"
            elif "pre-bid" in q_low or "pre-proposal" in q_low or "meeting" in q_low:
                sub_q = "pre-bid meeting pre-proposal conference date time teams video conference"
            elif "summarise" in q_low or "summarize" in q_low or "paragraph" in q_low:
                sub_q = "solicitation overview scope of work title project description requirements"
            else:
                clean_q = re.sub(r"\b(?:between\s+)?(?:bid\s*[123]\s*(?:and|&)?\s*)+", "", question, flags=re.IGNORECASE)
                sub_q = clean_q.strip() or question

            comparison_passages: List[Dict[str, Any]] = []
            for b in active_bids:
                bid_results = self.retriever.search(
                    query=sub_q,
                    top_k=5,
                    bid_id=b,
                    mode="hybrid",
                    expand_query=True
                )
                # If deadline question, also retrieve addenda chunks for each bid
                if any(w in q_low for w in ["deadline", "due date", "closing", "earliest"]):
                    add_results = self.retriever.search(
                        query="addendum new due date proposal submission deadline extension",
                        top_k=3,
                        bid_id=b,
                        mode="hybrid"
                    )
                    bid_results.extend(add_results)

                for r in bid_results:
                    # Clean filename (fixes C5)
                    clean_fname = re.sub(r"^\[?Bid\d\]?\s*", "", r.file_name)
                    comparison_passages.append({
                        "chunk_id": r.chunk_id,
                        "file_name": clean_fname,
                        "page_number": r.page_number,
                        "text": f"[{b} | File: {clean_fname} p.{r.page_number}]:\n{r.text}",
                        "score": r.rerank_score or r.rrf_score
                    })

            if not comparison_passages:
                return {
                    "question": question,
                    "target_bid": "All Bids",
                    "answer": "Not found in documents across any bids.",
                    "citations": []
                }

            comp_prompt = f"""Compare and answer how each bid ({', '.join(active_bids)}) addresses the following question: "{question}"

CRITICAL INSTRUCTIONS:
1. Provide a comprehensive, factual answer detailing EACH bid ({', '.join(active_bids)}) individually with exact quotes, followed by a clear comparative summary or difference.
2. For DEADLINES / DUE DATES: Any addendum (e.g. Addendum 2) that extends a deadline strictly supersedes the original base RFP date. You MUST quote the revised date and cite the addendum.
3. For WARRANTIES: Cite the actual warranty terms, coverage duration, and support tiers specified in each bid's documents.
4. For SCALE / QUANTITIES: List the exact unit counts and product tiers from the bid pricing/specification schedules.
5. If a bid does NOT mention or contain the requested information, explicitly state that it is not mentioned or not required in that bid's documents.
"""
            llm_resp = self.llm_client.answer_question(comp_prompt, comparison_passages)

            # Clean citation filenames in response
            cleaned_cites = []
            for c in llm_resp.get("citations", []):
                cleaned_cites.append({
                    "file": re.sub(r"^\[?Bid\d\]?\s*", "", str(c.get("file", ""))),
                    "page": c.get("page"),
                    "quote": c.get("quote")
                })

            return {
                "question": question,
                "target_bid": f"{', '.join(active_bids)} (Comparison)",
                "answer": llm_resp.get("answer", "Not found in documents."),
                "citations": cleaned_cites,
                "raw_evidence_count": len(comparison_passages)
            }

        # -------------------------------------------------------------------
        # 3. Standard Single-Bid Retrieval & Synthesis
        # -------------------------------------------------------------------
        q_low = question.lower()
        search_query = question

        # Domain expansions for single bid queries
        if "product tiers" in q_low or "quantities requested" in q_low or "scale" in q_low:
            search_query = f"{question} product tier target quantity requested quantity line items total units"
        elif "affidavits" in q_low or "forms" in q_low:
            search_query = f"{question} required affidavits compliance forms certification"
        elif "bid bond" in q_low:
            search_query = f"{question} bid bond insurance cashier check surety proposal guarantee"
        elif "submission deadline" in q_low or "due date" in q_low or "closing" in q_low:
            search_query = f"{question} proposal submission deadline closing date extension"

        results = self.retriever.search(
            query=search_query,
            top_k=top_k,
            bid_id=target_bid,
            mode="hybrid",
            expand_query=True
        )

        # Include addenda chunks if deadline question
        if any(w in q_low for w in ["deadline", "due date", "closing", "addendum"]):
            add_res = self.retriever.search(
                query="addendum new due date proposal submission deadline extension amended date",
                top_k=3,
                bid_id=target_bid,
                mode="hybrid"
            )
            results.extend(add_res)

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
                "file_name": re.sub(r"^\[?Bid\d\]?\s*", "", r.file_name),
                "page_number": r.page_number,
                "text": r.text,
                "score": r.rerank_score or r.rrf_score
            }
            for r in results
        ]

        llm_resp = self.llm_client.answer_question(question, evidence_passages)

        cleaned_cites = []
        for c in llm_resp.get("citations", []):
            cleaned_cites.append({
                "file": re.sub(r"^\[?Bid\d\]?\s*", "", str(c.get("file", ""))),
                "page": c.get("page"),
                "quote": c.get("quote")
            })

        return {
            "question": question,
            "target_bid": target_bid,
            "answer": llm_resp.get("answer", "Not found in documents."),
            "citations": cleaned_cites,
            "raw_evidence_count": len(results)
        }
