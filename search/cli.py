"""
Search Command-Line Interface (CLI).
Provides commands to index bid folders, execute hybrid search, and ask questions with citations.
Usage:
  python -m search.cli index [folder_path]
  python -m search.cli search "query" [--bid Bid1] [--top-k 5] [--mode hybrid]
  python -m search.cli ask "query" [--bid Bid1]
"""

import argparse
import sys
from pathlib import Path
from config.settings import settings
from search.hybrid_retriever import HybridRetriever
from search.index_manager import IndexManager


def main():
    parser = argparse.ArgumentParser(description="RFP Intelligence Platform - Search CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: index
    index_parser = subparsers.add_parser("index", help="Index a bid folder or all bids")
    index_parser.add_argument("path", nargs="?", default=None, help="Path to bid folder (e.g. Bid1, Bid2)")
    index_parser.add_argument("--force", action="store_true", help="Force re-indexing ignoring manifest cache")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Execute search across indexed documents")
    search_parser.add_argument("query", help="Search query string")
    search_parser.add_argument("--bid", default=None, help="Filter by bid ID (e.g. Bid1, Bid2)")
    search_parser.add_argument("--doc-type", default=None, help="Filter by document type (rfp, addendum, specs, etc.)")
    search_parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    search_parser.add_argument(
        "--mode",
        choices=["hybrid", "dense_only", "bm25_only", "hybrid_norerank"],
        default="hybrid",
        help="Retrieval mode (default: hybrid with reranking)"
    )

    # Command: ask
    ask_parser = subparsers.add_parser("ask", help="Ask a question and receive cited retrieval context")
    ask_parser.add_argument("question", help="Question to answer from RFP documents")
    ask_parser.add_argument("--bid", default=None, help="Filter by bid ID (e.g. Bid1, Bid2)")
    ask_parser.add_argument("--top-k", type=int, default=3, help="Number of supporting passages to retrieve")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "index":
        manager = IndexManager()
        if args.path:
            target_path = Path(args.path).resolve()
            print(f"Indexing bid folder: {target_path}...")
            indexed, added, removed = manager.index_folder(target_path, incremental=not args.force)
            print(f"Index complete: {indexed} files processed, {added} chunks added, {removed} stale chunks removed.")
        else:
            print("Indexing all bid folders in repository...")
            stats = manager.index_all()
            print("Indexing complete:")
            for bname, s in stats.get("summary", {}).items():
                print(f"  - {bname}: {s['files_indexed']} files, {s['chunks_added']} chunks added")
            print(f"Total BM25 Chunks: {stats['total_bm25_chunks']}, Total Dense Vectors: {stats['total_dense_vectors']}")

    elif args.command == "search":
        retriever = HybridRetriever()
        print(f"\nSearching for: '{args.query}' (Mode: {args.mode}, Bid: {args.bid or 'All'})...\n")
        results = retriever.search(
            query=args.query,
            top_k=args.top_k,
            bid_id=args.bid,
            doc_type=args.doc_type,
            mode=args.mode,
        )

        if not results:
            print("No relevant passages found.")
            return

        for idx, res in enumerate(results, 1):
            print(f"=== Result {idx} | Score: {res.rerank_score or res.rrf_score} ===")
            print(f"Citation: {res.format_citation()}")
            print(f"Chunk ID: {res.chunk_id}")
            print(f"Content:\n{res.text.strip()}\n")

    elif args.command == "ask":
        retriever = HybridRetriever()
        print(f"\nQuerying RFP intelligence on: '{args.question}'...\n")
        results = retriever.search(
            query=args.question,
            top_k=args.top_k,
            bid_id=args.bid,
            mode="hybrid",
        )

        if not results:
            print("Not found in documents.")
            return

        print("--- Top Retrieved Evidence & Citations ---")
        for idx, res in enumerate(results, 1):
            print(f"\n[{idx}] {res.format_citation()} (Score: {res.rerank_score or res.rrf_score}):")
            # Print body omitting context header for readability
            lines = res.text.splitlines()
            body = "\n".join(lines[1:]) if len(lines) > 1 and lines[0].startswith("[") else res.text
            print(body[:400] + ("..." if len(body) > 400 else ""))


if __name__ == "__main__":
    main()
