"""
RFP Intelligence Platform - Interactive Streamlit UI
Single-file web application with 3 functional tabs:
  1. Search: Hybrid, BM25, and Dense passage retrieval with metadata filters.
  2. Ask: Q&A agent with dynamic bid routing, LLM synthesis, and verbatim citations.
  3. Extract: Multi-agent structured 20-field extraction, addenda reconciliation log,
     validation breakdown, and visual tags for null/needs_review fields.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import streamlit as st

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from search.index_manager import IndexManager
from search.hybrid_retriever import HybridRetriever
from search.qa_agent import QAAgent
from extraction.graph import ExtractionPipeline


# Page configuration
st.set_page_config(
    page_title="RFP Intelligence Platform",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-passed {
        background-color: #DCFCE7;
        color: #166534;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-failed {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-notfound {
        background-color: #F1F5F9;
        color: #475569;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-review {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-amended {
        background-color: #DBEAFE;
        color: #1E40AF;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


def discover_bid_dirs() -> List[Path]:
    """Find all bid directories in project root dynamically."""
    dirs = []
    for item in sorted(PROJECT_ROOT.iterdir()):
        if item.is_dir() and (item.name.lower().startswith("bid") or (item / "solicitations").exists()):
            dirs.append(item)
    return dirs


@st.cache_resource(show_spinner="Initializing Search Index & Embedding Models...")
def load_resources():
    """Load and cache IndexManager, Retriever, and QAAgent."""
    idx_mgr = IndexManager()
    # Check if index exists or build from existing bid folders
    if not (idx_mgr.bm25_index.bm25 is not None and len(idx_mgr.bm25_index.chunks) > 0):
        for bid_dir in discover_bid_dirs():
            idx_mgr.index_bid_directory(bid_dir, bid_id=bid_dir.name)

    retriever = HybridRetriever(
        bm25_index=idx_mgr.bm25_index,
        dense_indexer=idx_mgr.dense_indexer
    )
    qa_agent = QAAgent(retriever=retriever)
    return idx_mgr, retriever, qa_agent


idx_mgr, retriever, qa_agent = load_resources()


def get_available_bids() -> List[str]:
    """Get list of active bid IDs dynamically."""
    bids = set()
    if idx_mgr.bm25_index.chunks:
        for chunk in idx_mgr.bm25_index.chunks:
            bid_id = getattr(chunk.metadata, "bid_id", None) if hasattr(chunk.metadata, "bid_id") else (chunk.metadata.get("bid_id") if isinstance(chunk.metadata, dict) else None)
            if bid_id:
                bids.add(bid_id)
    if not bids:
        for p in discover_bid_dirs():
            bids.add(p.name)
    return sorted(list(bids)) if bids else ["Bid1", "Bid2", "Bid3"]


available_bids = get_available_bids()

# Header
st.markdown('<div class="main-header">📋 RFP Intelligence Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-Agent Procurement Analysis, Hybrid Search, Addendum Reconciliation & Verification</div>', unsafe_allow_html=True)

# Tabs
tab_search, tab_ask, tab_extract = st.tabs(["🔍 Search Passages", "💬 Ask Q&A", "📊 Extract & Reconcile"])


# ---------------------------------------------------------------------------
# TAB 1: SEARCH
# ---------------------------------------------------------------------------
with tab_search:
    st.subheader("Hybrid Passage Search")
    st.write("Retrieve document chunks across indexed RFP packages with BM25 keyword matching, BGE dense embeddings, and cross-encoder reranking.")

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_query = st.text_input(
            "Search Query",
            placeholder="e.g. liquidated damages per day or Dell laptop specifications",
            key="search_query"
        )
    with col2:
        bid_filter = st.selectbox(
            "Filter by Bid",
            options=["All Bids"] + available_bids,
            key="search_bid_filter"
        )
    with col3:
        doc_type_filter = st.selectbox(
            "Filter Doc Type",
            options=["All Types", "solicitation", "addendum", "pricing_sheet", "attachment"],
            key="search_doc_filter"
        )

    col_mode, col_topk, col_btn = st.columns([2, 1, 1])
    with col_mode:
        retrieval_mode = st.radio(
            "Retrieval Mode",
            options=["hybrid", "bm25", "dense"],
            index=0,
            horizontal=True,
            key="search_mode"
        )
    with col_topk:
        top_k = st.slider("Results to show", min_value=1, max_value=20, value=5, key="search_topk")
    with col_btn:
        st.write("")
        st.write("")
        do_search = st.button("Search", type="primary", use_container_width=True)

    if do_search or search_query:
        if not search_query.strip():
            st.warning("Please enter a search query.")
        else:
            selected_bid = None if bid_filter == "All Bids" else bid_filter
            selected_type = None if doc_type_filter == "All Types" else doc_type_filter

            with st.spinner(f"Running {retrieval_mode.upper()} retrieval..."):
                results = retriever.search(
                    query=search_query,
                    bid_id=selected_bid,
                    doc_type=selected_type,
                    top_k=top_k,
                    mode=retrieval_mode
                )

            if not results:
                st.info("No matching passages found for your query and filters.")
            else:
                st.success(f"Found {len(results)} relevant passage(s):")
                for i, r in enumerate(results, 1):
                    score = getattr(r, "rerank_score", None) or getattr(r, "rrf_score", None) or getattr(r, "bm25_score", None) or getattr(r, "score", 0.0) if not isinstance(r, dict) else r.get("score", 0.0)
                    if score is None:
                        score = 0.0
                    file_name = getattr(r, "file_name", "Unknown File") if not isinstance(r, dict) else r.get("file_name", "Unknown File")
                    page_num = getattr(r, "page_number", 1) if not isinstance(r, dict) else r.get("page_number", 1)
                    bid = getattr(r, "bid_id", "Unknown") if not isinstance(r, dict) else r.get("bid_id", "Unknown")
                    dtype = getattr(r, "doc_type", "document") if not isinstance(r, dict) else r.get("doc_type", "document")
                    chunk_id = getattr(r, "chunk_id", "") if not isinstance(r, dict) else r.get("chunk_id", "")
                    text = getattr(r, "text", "") if not isinstance(r, dict) else r.get("text", "")

                    with st.expander(f"#{i} [{bid}] {file_name} (Page {page_num}) — Score: {score:.4f}", expanded=(i <= 2)):
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.caption(f"**Doc Type:** {dtype}")
                        col_m2.caption(f"**Chunk ID:** `{chunk_id}`")
                        col_m3.caption(f"**Page:** {page_num}")
                        st.markdown(f"```\n{text}\n```")


# ---------------------------------------------------------------------------
# TAB 2: ASK (Q&A AGENT)
# ---------------------------------------------------------------------------
with tab_ask:
    st.subheader("RFP Question Answering with Verbatim Citations")
    st.write("Ask natural language questions across one or all bids. The system dynamically routes queries to the relevant package and provides answers grounded in document quotes.")

    q_col1, q_col2 = st.columns([4, 1])
    with q_col1:
        question_input = st.text_input(
            "Enter Question",
            placeholder="e.g. When is the proposal due date for Dallas ISD? or Compare warranties across all bids.",
            key="ask_question_input"
        )
    with q_col2:
        bid_target = st.selectbox(
            "Target Bid",
            options=["Auto-Route"] + available_bids,
            key="ask_bid_target"
        )

    ask_btn = st.button("Ask Question", type="primary")

    if ask_btn or question_input:
        if not question_input.strip():
            st.warning("Please enter a question.")
        else:
            override_bid = None if bid_target == "Auto-Route" else bid_target
            with st.spinner("Synthesizing answer from grounded evidence..."):
                response = qa_agent.ask(question=question_input, bid_id=override_bid)

            routed_bid = response.get("target_bid", "Cross-Bid Synthesis")
            answer_text = response.get("answer", "No answer generated.")
            citations = response.get("citations", [])

            st.markdown(f"**Target RFP / Routing:** `{routed_bid}`")
            st.markdown("### Answer")
            st.info(answer_text)

            if citations:
                st.markdown("### Verbatim Supporting Citations")
                for j, cite in enumerate(citations, 1):
                    cf = cite.get("file", "Document")
                    cp = cite.get("page", 1)
                    cq = cite.get("quote", "")
                    st.markdown(f"- **[{j}] `{cf}` (Page {cp})**")
                    if cq:
                        st.markdown(f"  > *\"{cq}\"*")
            else:
                st.caption("No specific citations returned for this synthesis.")


# ---------------------------------------------------------------------------
# TAB 3: EXTRACT & RECONCILE
# ---------------------------------------------------------------------------
with tab_extract:
    st.subheader("Structured 20-Field Extraction & Addendum Reconciliation")
    st.write("Extract procurement metadata and requirements with deterministic validation, contiguous substring verification, dynamic confidence, and addendum supersession tracking.")

    ext_col1, ext_col2, ext_col3 = st.columns([2, 1, 1])
    with ext_col1:
        extract_bid = st.selectbox(
            "Select Bid Package",
            options=available_bids,
            key="extract_bid_select"
        )
    with ext_col2:
        load_existing = st.button("Load Saved JSON", use_container_width=True)
    with ext_col3:
        run_extract = st.button("Run Full Pipeline", type="primary", use_container_width=True)

    result_data: Optional[Dict[str, Any]] = None

    if load_existing:
        out_path = settings.OUTPUTS_DIR / f"{extract_bid.lower()}.json"
        if out_path.exists():
            with open(out_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            st.success(f"Loaded existing results from `{out_path.name}`")
        else:
            st.error(f"Saved file `{out_path.name}` not found. Please click 'Run Full Pipeline' to generate it.")

    elif run_extract:
        with st.spinner(f"Running multi-agent extraction pipeline for {extract_bid}..."):
            pipeline = ExtractionPipeline(retriever=retriever)
            res = pipeline.run(extract_bid)
            result_data = res.model_dump()

            # Save to outputs/<bid_id.lower()>.json
            out_file = settings.OUTPUTS_DIR / f"{extract_bid.lower()}.json"
            settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            st.success(f"Pipeline finished! Saved to `{out_file.name}`")

    # If neither button was clicked in this run, default to loading existing saved file if present
    if result_data is None:
        default_file = settings.OUTPUTS_DIR / f"{extract_bid.lower()}.json"
        if default_file.exists():
            with open(default_file, "r", encoding="utf-8") as f:
                result_data = json.load(f)

    if result_data:
        val = result_data.get("validation", {})
        passed = val.get("passed", [])
        failed = val.get("failed", [])
        not_found = val.get("not_found", [])
        errors = val.get("errors", [])
        completeness = result_data.get("completeness", result_data.get("overall_compliance_score", 0.0))
        addendum_changes = result_data.get("addendum_changes", [])

        # Metrics row
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Completeness", f"{completeness}%")
        m2.metric("Passed", len(passed))
        m3.metric("Failed Checks", len(failed))
        m4.metric("Not Found", len(not_found))
        m5.metric("Amended by Addenda", len(addendum_changes))

        # Addendum changes log (if any)
        if addendum_changes:
            st.markdown("### 📝 Addendum Reconciliation Log")
            st.info(f"Detected and verified **{len(addendum_changes)}** field modification(s) introduced by solicitation addenda:")
            for chg in addendum_changes:
                f_name = chg.get("field")
                old_v = chg.get("old_value")
                new_v = chg.get("new_value")
                src = chg.get("source", {})
                sf = src.get("file", "Addendum")
                sp = src.get("page", 1)
                sq = src.get("quote", "")
                reason = chg.get("reason", "")

                with st.container():
                    st.markdown(f"**Field:** `{f_name}` <span class='badge-amended'>AMENDED</span>", unsafe_allow_html=True)
                    st.markdown(f"- **Old Base Value:** `{old_v}`")
                    st.markdown(f"- **Amended Value:** **`{new_v}`**")
                    st.markdown(f"- **Citation:** `{sf}` (p.{sp})")
                    if sq:
                        st.markdown(f"  > *\"{sq}\"*")
                    if reason:
                        st.caption(f"Reason: {reason}")
                    st.divider()

        # Fields table
        st.markdown("### 📋 Extracted Fields (20-Field Schema)")
        fields = result_data.get("fields", {})

        for f_name, f_info in fields.items():
            val_text = f_info.get("value")
            conf = f_info.get("confidence", 0.0)
            sources = f_info.get("sources", [])
            needs_review = f_info.get("needs_review", False)
            review_reason = f_info.get("review_reason", "")
            notes = f_info.get("notes", "")

            # Tag determination
            if f_name in errors or f_info.get("status") == "ERROR":
                tag_html = "<span class='badge-failed'>ERROR</span>"
            elif val_text is None or f_name in not_found:
                tag_html = "<span class='badge-notfound'>NOT FOUND / NULL</span>"
            elif f_name in failed or needs_review:
                tag_html = "<span class='badge-review'>NEEDS REVIEW</span>"
            else:
                tag_html = "<span class='badge-passed'>PASSED</span>"

            cite_str = "None"
            quote_str = ""
            if sources:
                s0 = sources[0]
                cite_str = f"{s0.get('file', '')} (p.{s0.get('page', '')})"
                quote_str = s0.get("quote", "")

            with st.expander(f"{f_name}: {val_text if val_text is not None else 'null'} (Confidence: {conf:.2f})"):
                c_a, c_b = st.columns([3, 1])
                with c_a:
                    st.markdown(f"**Value:** `{val_text}`")
                    st.markdown(f"**Citation:** `{cite_str}`")
                    if quote_str:
                        st.markdown(f"**Verbatim Quote:** *\"{quote_str}\"*")
                    if notes and notes != "None":
                        st.caption(f"Notes: {notes}")
                    if review_reason:
                        st.warning(f"Review Flag: {review_reason}")
                with c_b:
                    st.markdown(f"**Status:** {tag_html}", unsafe_allow_html=True)
                    st.metric("Confidence", f"{conf:.2f}")

    else:
        st.info("No extraction data loaded yet. Click 'Run Full Pipeline' or 'Load Saved JSON'.")
