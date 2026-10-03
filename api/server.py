"""
FastAPI REST API for Search and Ingestion.
Endpoints:
- POST /index : Trigger incremental indexing of a bid package or all bids.
- POST /search: Retrieve top-k ranked chunks with metadata filters and citations.
- POST /ask   : Natural language question answering with cited chunk evidence.
- GET /stats  : Current search index status and statistics.
- GET /health : Service health check.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from config.settings import settings
from search.hybrid_retriever import HybridRetriever, SearchResult
from search.index_manager import IndexManager

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RFP Intelligence Platform Search API",
    version="2.0.0",
    description="Hybrid Search Engine (BM25 + BGE Embeddings + Cross-Encoder Reranking) for RFP Documents."
)

# Global service instances
index_manager = IndexManager()
retriever = HybridRetriever(
    bm25_index=index_manager.bm25_index,
    dense_indexer=index_manager.dense_indexer,
)


# Request and Response schemas
class IndexRequest(BaseModel):
    folder_path: Optional[str] = Field(default=None, description="Path to specific bid folder (e.g. 'Bid1')")
    force: bool = Field(default=False, description="Whether to bypass hash manifest cache and re-index all files")


class SearchRequest(BaseModel):
    query: str = Field(description="Search query string")
    bid_id: Optional[str] = Field(default=None, description="Filter by bid ID (e.g. 'Bid1', 'Bid2')")
    doc_type: Optional[str] = Field(default=None, description="Filter by doc_type ('rfp', 'addendum', 'specs', etc.)")
    top_k: int = Field(default=5, description="Number of results to return")
    mode: str = Field(
        default="hybrid",
        description="Retrieval mode: 'hybrid' (RRF+Rerank), 'hybrid_norerank', 'dense_only', 'bm25_only'"
    )


class AskRequest(BaseModel):
    question: str = Field(description="Natural language question to answer from RFP documents")
    bid_id: Optional[str] = Field(default=None, description="Optional bid identifier filter")
    top_k: int = Field(default=3, description="Number of supporting evidence passages to retrieve")


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "version": "2.0.0"}


@app.get("/stats")
def get_stats() -> Dict[str, Any]:
    return index_manager.get_stats()


@app.post("/index")
def trigger_index(req: IndexRequest) -> Dict[str, Any]:
    try:
        if req.folder_path:
            p = Path(req.folder_path).resolve()
            indexed, added, removed = index_manager.index_folder(p, incremental=not req.force)
            return {
                "status": "success",
                "folder": str(p),
                "files_indexed": indexed,
                "chunks_added": added,
                "chunks_removed": removed,
            }
        else:
            stats = index_manager.index_all()
            return {"status": "success", "all_bids": stats}
    except Exception as e:
        logger.error(f"Indexing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=List[SearchResult])
def search_documents(req: SearchRequest) -> List[SearchResult]:
    try:
        results = retriever.search(
            query=req.query,
            top_k=req.top_k,
            bid_id=req.bid_id,
            doc_type=req.doc_type,
            mode=req.mode,
        )
        return results
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask")
def ask_question(req: AskRequest) -> Dict[str, Any]:
    try:
        from search.qa_agent import QAAgent
        qa = QAAgent(retriever=retriever)
        return qa.ask(question=req.question, bid_id=req.bid_id, top_k=req.top_k)
    except Exception as e:
        logger.error(f"Ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExtractRequest(BaseModel):
    bid_id: str = Field(description="Bid package ID to extract (e.g. 'Bid1', 'Bid2')")


class CompareRequest(BaseModel):
    bids: List[str] = Field(default=["Bid1", "Bid2"], description="List of bid package IDs to compare")


@app.post("/extract")
def extract_bid(req: ExtractRequest) -> Dict[str, Any]:
    """Trigger multi-agent extraction workflow for a bid package."""
    try:
        from extraction.graph import ExtractionPipeline
        pipeline = ExtractionPipeline()
        res = pipeline.run(bid_id=req.bid_id)
        return json.loads(res.model_dump_json())
    except Exception as e:
        logger.error(f"Extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare")
def compare_bids_endpoint(req: CompareRequest) -> Dict[str, Any]:
    """Trigger cross-bid comparative analysis."""
    try:
        from extraction.graph import ExtractionPipeline
        from extraction.synthesis_agent import SynthesisAgent

        pipeline = ExtractionPipeline()
        synthesis = SynthesisAgent()

        bids_results = {}
        for bid_id in req.bids:
            bids_results[bid_id] = pipeline.run(bid_id=bid_id)

        comparison = synthesis.compare_bids(
            bids_results=bids_results,
            fields_defs=pipeline.extractor.field_definitions,
        )
        return json.loads(comparison.model_dump_json())
    except Exception as e:
        logger.error(f"Comparison error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
