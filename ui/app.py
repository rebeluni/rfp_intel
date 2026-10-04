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

# Custom Styling (Elevated Modern Design)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.2rem;
        background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .stat-box {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    .badge-passed {
        background-color: rgba(34, 197, 94, 0.15);
        color: #4ADE80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
    }
    .badge-failed {
        background-color: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
    }
    .badge-notfound {
        background-color: rgba(148, 163, 184, 0.15);
        color: #CBD5E1;
        border: 1px solid rgba(148, 163, 184, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
    }
    .badge-amended {
        background-color: rgba(59, 130, 246, 0.15);
        color: #60A5FA;
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
    }
    .badge-rel-high {
        background-color: rgba(34, 197, 94, 0.15);
        color: #4ADE80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-rel-med {
        background-color: rgba(234, 179, 8, 0.15);
        color: #FACC15;
        border: 1px solid rgba(234, 179, 8, 0.3);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .quote-box {
        background: rgba(15, 23, 42, 0.6);
        border-left: 3px solid #3B82F6;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin: 8px 0;
        font-family: inherit;
        font-size: 0.92rem;
        line-height: 1.5;
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

# Sidebar: Platform Stats & Unseen Bid Uploader
with st.sidebar:
    st.markdown("### 📋 RFP Intelligence")
    st.caption("AI-powered Procurement Intelligence & Verification Engine")
    
    st.markdown("---")
    st.markdown("#### ⚙️ Engine Status")
    total_chunks = len(idx_mgr.bm25_index.chunks) if idx_mgr.bm25_index else 0
    st.markdown(f"""
    <div class="stat-box">
        <div style="font-size: 0.8rem; color: #94A3B8;">Active Bids: <b>{len(available_bids)}</b> ({', '.join(available_bids)})</div>
        <div style="font-size: 0.8rem; color: #94A3B8;">Indexed Chunks: <b>{total_chunks}</b></div>
        <div style="font-size: 0.8rem; color: #94A3B8;">Dense Model: <code>bge-small-en-v1.5</code></div>
        <div style="font-size: 0.8rem; color: #94A3B8;">Re-ranker: <code>ms-marco-MiniLM-L6</code></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    with st.expander("📁 Ingest Unseen Bid Package", expanded=False):
        st.caption("Upload PDFs or HTML to test on a new, unseen solicitation.")
        new_bid_id = st.text_input("New Bid ID", placeholder="e.g. Bid4", key="new_bid_name_input")
        uploaded_files = st.file_uploader(
            "Upload RFP Documents",
            type=["pdf", "html", "htm"],
            accept_multiple_files=True,
            key="new_bid_files"
        )
        if st.button("⚡ Parse & Index Package", use_container_width=True, type="primary"):
            if not new_bid_id.strip():
                st.error("Please provide a Bid ID.")
            elif not uploaded_files:
                st.error("Please upload at least one PDF or HTML file.")
            else:
                with st.spinner(f"Ingesting and building vector index for {new_bid_id}..."):
                    target_dir = PROJECT_ROOT / new_bid_id.strip()
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for uf in uploaded_files:
                        save_path = target_dir / uf.name
                        with open(save_path, "wb") as f_out:
                            f_out.write(uf.getvalue())
                    # Index the new directory
                    idx_mgr.index_bid_directory(target_dir, bid_id=new_bid_id.strip())
                    st.success(f"Successfully indexed {new_bid_id}! Updating...")
                    st.rerun()

# Header
st.markdown('<div class="main-header">📋 RFP Intelligence Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-Agent Procurement Analysis, Hybrid Search, Addendum Reconciliation & Deterministic Verification</div>', unsafe_allow_html=True)

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

            mode_map = {
                "hybrid": "hybrid",
                "bm25": "bm25_only",
                "dense": "dense_only",
            }
            mapped_mode = mode_map.get(retrieval_mode, "hybrid")

            with st.spinner(f"Running {retrieval_mode.upper()} retrieval..."):
                raw_results = retriever.search(
                    query=search_query,
                    bid_id=selected_bid,
                    doc_type=selected_type,
                    top_k=top_k,
                    mode=mapped_mode
                )

            # Filter out non-matches below relevance thresholds
            valid_results = []
            for r in raw_results:
                s = getattr(r, "rerank_score", None) or getattr(r, "rrf_score", None) or getattr(r, "bm25_score", None) or getattr(r, "score", 0.0) if not isinstance(r, dict) else r.get("score", 0.0)
                if mapped_mode == "bm25_only" and (s is None or s <= 0.0):
                    continue
                if mapped_mode == "dense_only" and (s is None or s < 0.35):
                    continue
                if mapped_mode == "hybrid" and (s is not None and s < -6.5):
                    continue
                valid_results.append(r)

            if not valid_results:
                st.info(f"No relevant passages found for '{search_query}' with the selected filters.")
            else:
                st.success(f"Found {len(valid_results)} relevant passage(s):")
                for i, r in enumerate(valid_results, 1):
                    score = getattr(r, "rerank_score", None) or getattr(r, "rrf_score", None) or getattr(r, "bm25_score", None) or getattr(r, "score", 0.0) if not isinstance(r, dict) else r.get("score", 0.0)
                    if score is None:
                        score = 0.0
                    file_name = getattr(r, "file_name", "Unknown File") if not isinstance(r, dict) else r.get("file_name", "Unknown File")
                    page_num = getattr(r, "page_number", 1) if not isinstance(r, dict) else r.get("page_number", 1)
                    bid = getattr(r, "bid_id", "Unknown") if not isinstance(r, dict) else r.get("bid_id", "Unknown")
                    dtype = getattr(r, "doc_type", "document") if not isinstance(r, dict) else r.get("doc_type", "document")
                    chunk_id = getattr(r, "chunk_id", "") if not isinstance(r, dict) else r.get("chunk_id", "")
                    text = getattr(r, "text", "") if not isinstance(r, dict) else r.get("text", "")

                    # Determine relevance pill
                    if (mapped_mode == "hybrid" and score >= -2.5) or (mapped_mode == "bm25_only" and score >= 5.0) or (mapped_mode == "dense_only" and score >= 0.60):
                        rel_badge = '<span class="badge-rel-high">🟢 High Match</span>'
                    else:
                        rel_badge = '<span class="badge-rel-med">🟡 Moderate Match</span>'

                    with st.expander(f"#{i} [{bid}] {file_name} (Page {page_num}) — Score: {score:.4f}", expanded=(i <= 2)):
                        col_m1, col_m2, col_m3, col_m4 = st.columns([1, 1, 1, 1])
                        col_m1.caption(f"**Doc Type:** `{dtype}`")
                        col_m2.caption(f"**Page:** `{page_num}`")
                        col_m3.caption(f"**Chunk ID:** `{chunk_id}`")
                        col_m4.markdown(rel_badge, unsafe_allow_html=True)
                        st.markdown(f'<div class="quote-box">{text}</div>', unsafe_allow_html=True)


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
