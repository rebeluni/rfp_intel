"""
Q&A Agent with Bid Routing and LLM Synthesis.
Strictly implements Item 7:
  - Route bid from natural language queries (e.g. "the Dell laptop bid", "Bid1", "Dallas ISD").
  - Retrieve relevant chunks via hybrid retriever.
  - Return LLM-written answer with structured citations [{file, page, quote}], or 'Not found in documents.'
"""

import re
import logging
from typing import Any, Dict, List, Optional
from config.settings import settings
from search.hybrid_retriever import HybridRetriever
from extraction.llm_client import GeminiClient, get_llm_client

logger = logging.getLogger(__name__)


class QAAgent:
    """Intelligent Q&A agent supporting natural language bid routing and LLM citation synthesis."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        llm_client: Optional[GeminiClient] = None
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = llm_client or get_llm_client()

    def route_bid(self, question: str) -> Optional[str]:
        """
        Route natural language question to a target bid package.
        Supports explicit names, vendor/device references, or agency names.
        """
        q = question.lower()

        # Direct bid IDs
        if "bid 1" in q or "bid1" in q:
            return "Bid1"
        if "bid 2" in q or "bid2" in q:
            return "Bid2"
        if "bid 3" in q or "bid3" in q:
            return "Bid3"

        # Content-based routing
        if any(term in q for term in ["dell", "laptop", "latitude", "porfp", "baltimore", "maryland", "doit"]):
            return "Bid2"
        if any(term in q for term in ["dallas", "student and staff", "computing devices", "isd", "ja-207652"]):
            return "Bid1"

        return None

    def ask(self, question: str, bid_id: Optional[str] = None, top_k: int = 5) -> Dict[str, Any]:
        """
        Answer a question with natural language routing, hybrid retrieval, and LLM synthesis.
        """
        # Resolve target bid if not explicitly passed
        target_bid = bid_id or self.route_bid(question)

        # Retrieve candidate evidence
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

        # Call LLM to synthesize answer
        llm_resp = self.llm_client.answer_question(question, evidence_passages)

        return {
            "question": question,
            "target_bid": target_bid,
            "answer": llm_resp.get("answer", "Not found in documents."),
            "citations": llm_resp.get("citations", []),
            "raw_evidence_count": len(results)
        }
