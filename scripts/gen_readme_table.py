"""
Generate the README search benchmark table directly from outputs/search_eval_results.json.
Usage: python scripts/gen_readme_table.py
Updates the README.md EVAL_TABLE_START ... EVAL_TABLE_END block in-place.
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = PROJECT_ROOT / "outputs" / "search_eval_results.json"
README_FILE = PROJECT_ROOT / "README.md"

MODE_LABELS = {
    "bm25_only": "BM25 Only",
    "dense_only": "Dense Only (BGE-small)",
    "hybrid_norerank": "Hybrid (RRF k=60)",
    "hybrid_rerank": "Hybrid + Cross-Encoder Rerank",
}

MODES_ORDER = ["bm25_only", "dense_only", "hybrid_norerank", "hybrid_rerank"]


def build_table(metrics: dict) -> str:
    lines = [
        "| Retrieval Mode | Recall@1 | Recall@3 | Recall@5 | MRR |",
        "|---|---|---|---|---|",
    ]
    for mode in MODES_ORDER:
        if mode not in metrics:
            continue
        m = metrics[mode]
        label = MODE_LABELS.get(mode, mode)
        r1 = f"{m['recall_at_1'] * 100:.2f}%"
        r3 = f"{m['recall_at_3'] * 100:.2f}%"
        r5 = f"{m['recall_at_5'] * 100:.2f}%"
        mrr = f"{m['mrr']:.4f}"
        # Bold best recall@5
        best_r5 = max(metrics[m2]["recall_at_5"] for m2 in metrics)
        if m["recall_at_5"] >= best_r5:
            r5 = f"**{r5}**"
        # Bold best mrr
        best_mrr = max(metrics[m2]["mrr"] for m2 in metrics)
        if m["mrr"] >= best_mrr:
            mrr = f"**{mrr}**"
        lines.append(f"| **{label}** | {r1} | {r3} | {r5} | {mrr} |")
    return "\n".join(lines)


def main():
    if not RESULTS_FILE.exists():
        print(f"ERROR: {RESULTS_FILE} does not exist. Run search eval first.")
        return

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = data.get("metrics", {})
    table = build_table(metrics)

    readme_text = README_FILE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"<!-- EVAL_TABLE_START -->.*?<!-- EVAL_TABLE_END -->",
        re.DOTALL
    )
    m = pattern.search(readme_text)
    if not m:
        print("WARNING: EVAL_TABLE markers not found in README.md. No changes made.")
        print("Generated table:")
        print(table)
        return

    replacement = f"<!-- EVAL_TABLE_START -->\n{table}\n<!-- EVAL_TABLE_END -->"
    new_text = readme_text[:m.start()] + replacement + readme_text[m.end():]
    README_FILE.write_text(new_text, encoding="utf-8")
    print("README.md benchmark table updated from search_eval_results.json:")
    print(table)


if __name__ == "__main__":
    main()
