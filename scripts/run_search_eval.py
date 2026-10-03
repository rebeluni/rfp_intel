"""
Benchmark runner script for Search Engine Phase 2.
Executes RetrievalEvaluator across all 4 modes, logs metrics, and prints markdown table.
"""

import json
from pathlib import Path
from search.eval import RetrievalEvaluator


def main():
    evaluator = RetrievalEvaluator()
    results = evaluator.run_benchmark(modes=["dense_only", "bm25_only", "hybrid_norerank", "hybrid_rerank"])

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "search_eval_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print("PHASE 2 SEARCH RETRIEVAL BENCHMARK RESULTS (22 Queries)")
    print("=" * 70)
    print(f"| {'Mode':<22} | {'Recall@1':<10} | {'Recall@3':<10} | {'Recall@5':<10} | {'MRR':<10} |")
    print(f"|{'-'*24}|{'-'*12}|{'-'*12}|{'-'*12}|{'-'*12}|")

    mode_display = {
        "dense_only": "Dense (BGE-Small)",
        "bm25_only": "BM25 Only",
        "hybrid_norerank": "Hybrid (RRF k=60)",
        "hybrid_rerank": "Hybrid + CrossEncoder"
    }

    for mode, m in results["metrics"].items():
        name = mode_display.get(mode, mode)
        print(f"| {name:<22} | {m['recall_at_1']:<10.4f} | {m['recall_at_3']:<10.4f} | {m['recall_at_5']:<10.4f} | {m['mrr']:<10.4f} |")
    print("=" * 70 + "\n")
    print(f"Saved evaluation details to {out_file}")


if __name__ == "__main__":
    main()
