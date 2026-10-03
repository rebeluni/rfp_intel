"""
RFP Intelligence Platform - Unified Command-Line Interface.
Supports:
  1. extract: python main.py extract --bid ./Bid1
  2. ask:     python main.py ask "What is the due date for the Dell laptop bid?"
  3. serve:   python main.py serve --port 8000
"""

import sys
import io

# Ensure UTF-8 output on all consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import logging
import argparse
from pathlib import Path
from typing import Optional

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def normalize_bid_id(bid_input: str) -> str:
    """Normalize input path or name like './Bid1', 'Bid1/', or 'bid1' to 'Bid1'."""
    p = Path(bid_input)
    name = p.name if p.name else p.stem
    if not name:
        name = str(bid_input).strip("/\\")
    # Title-case e.g. bid1 -> Bid1
    if name.lower().startswith("bid"):
        num = name.lower().replace("bid", "").strip("_- ")
        return f"Bid{num}"
    return name


def cmd_extract(args: argparse.Namespace) -> None:
    """Execute end-to-end multi-agent extraction for one or more bid packages."""
    from search.index_manager import IndexManager
    from search.hybrid_retriever import HybridRetriever
    from extraction.graph import ExtractionPipeline

    bid_inputs = [b.strip() for b in args.bid.split(",") if b.strip()]

    for bid_raw in bid_inputs:
        bid_path = Path(bid_raw)
        bid_id = normalize_bid_id(bid_raw)

        print(f"\n=======================================================")
        print(f"[*] RFP EXTRACTION PIPELINE: {bid_id}")
        print(f"=======================================================")

        # Ensure document indexing
        idx_mgr = IndexManager()
        if bid_path.is_dir():
            print(f"[*] Ingesting and indexing bid directory: {bid_path}...")
            idx_mgr.index_bid_directory(bid_path, bid_id=bid_id)

        retriever = HybridRetriever(
            bm25_index=idx_mgr.bm25_index,
            dense_indexer=idx_mgr.dense_indexer
        )

        pipeline = ExtractionPipeline(retriever=retriever)
        result = pipeline.run(bid_id)

        # Save to outputs/<bid_id.lower()>.json matching Section 8.1
        out_file = settings.OUTPUTS_DIR / f"{bid_id.lower()}.json"
        settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)

        print(f"\n[+] Extraction successfully completed and saved to: {out_file}")
        print(f"[+] Overall Compliance Score: {result.overall_compliance_score}%")
        print(f"[+] Passed Fields: {len(result.validation.passed)}")
        print(f"[+] Failed Fields: {len(result.validation.failed)}")
        print(f"[+] Not Found: {len(result.validation.not_found)}")
        print(f"[+] Addendum Changes Logged: {len(result.addendum_changes)}")

        if result.addendum_changes:
            print("\n--- ADDENDUM RECONCILIATION LOG ---")
            for chg in result.addendum_changes:
                print(f"  * {chg.field}: '{chg.old_value}' -> '{chg.new_value}'")
                print(f"    Source: [{chg.source.file} p.{chg.source.page}]")
                print(f"    Reason: {chg.reason}")

        print("\n--- SAMPLE EXTRACTED FIELDS ---")
        for f_name in ["Bid Number", "Title", "Due Date", "company_name", "Product"]:
            if f_name in result.fields:
                f = result.fields[f_name]
                cite = f.sources[0].format_citation() if f.sources else "No source"
                print(f"  * {f_name}: {f.value}")
                print(f"    Citation: {cite} | Confidence: {f.confidence}")


def cmd_ask(args: argparse.Namespace) -> None:
    """Execute natural language Q&A with bid routing and LLM citations."""
    from search.index_manager import IndexManager
    from search.hybrid_retriever import HybridRetriever
    from search.qa_agent import QAAgent

    question = args.question
    bid_override = normalize_bid_id(args.bid) if args.bid else None

    idx_mgr = IndexManager()
    retriever = HybridRetriever(
        bm25_index=idx_mgr.bm25_index,
        dense_indexer=idx_mgr.dense_indexer
    )

    qa = QAAgent(retriever=retriever)
    resp = qa.ask(question=question, bid_id=bid_override)

    print(f"\n=======================================================")
    print(f"[?] QUESTION: {question}")
    if resp.get("target_bid"):
        print(f"[*] ROUTED BID: {resp.get('target_bid')}")
    print(f"=======================================================\n")
    print(f"ANSWER:\n{resp.get('answer')}\n")

    citations = resp.get("citations", [])
    if citations:
        print("CITATIONS:")
        for i, c in enumerate(citations, 1):
            q_txt = f': "{c.get("quote")}"' if c.get("quote") else ""
            print(f"  [{i}] {c.get('file')} (p.{c.get('page')}){q_txt}")
    else:
        print("No citations found.")


def cmd_serve(args: argparse.Namespace) -> None:
    """Run FastAPI server exposing /search, /ask, /extract, /compare."""
    import uvicorn
    host = args.host or settings.API_HOST
    port = args.port or settings.API_PORT
    print(f"Starting RFP Intelligence Platform API on http://{host}:{port}...")
    uvicorn.run("api.server:app", host=host, port=port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="RFP Intelligence Platform - AI-powered ingestion, search, extraction & reconciliation."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: extract
    p_extract = subparsers.add_parser("extract", help="Extract all fields from a bid package")
    p_extract.add_argument("--bid", required=True, help="Path to bid directory or bid identifier (e.g. ./Bid1)")

    # Command: ask
    p_ask = subparsers.add_parser("ask", help="Ask a question across RFP packages with citations")
    p_ask.add_argument("question", help="Natural language question to ask")
    p_ask.add_argument("--bid", required=False, default=None, help="Optional bid ID override (e.g. Bid1, Bid2)")

    # Command: serve
    p_serve = subparsers.add_parser("serve", help="Start the FastAPI backend server")
    p_serve.add_argument("--host", default=None, help="Host address (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=None, help="Port number (default: 8000)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
