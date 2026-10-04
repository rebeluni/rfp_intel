"""
Format Benchmark Table from outputs/search_eval_results.json.
Generates exact Markdown table for README.md and docs/final_report.md directly from JSON data.
Strictly adheres to: Never type numbers by hand.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = PROJECT_ROOT / "outputs" / "search_eval_results.json"


def generate_table(include_latency: bool = True) -> str:
    if not RESULTS_FILE.exists():
        raise FileNotFoundError(f"Missing {RESULTS_FILE}")

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = data.get("metrics", {})

    mode_display = {
        "bm25_only": "**BM25 Only**",
        "dense_only": "**Dense Only (BGE-small)**",
        "hybrid_norerank": "**Hybrid (No Rerank)**",
        "hybrid_rerank": "**Hybrid + Cross-Encoder Rerank**",
    }

    modes = ["bm25_only", "dense_only", "hybrid_norerank", "hybrid_rerank"]

    if include_latency:
        headers = ["Retrieval Mode", "Recall@1", "Recall@3", "Recall@5", "MRR", "Latency (avg)"]
        sep = ["---", "---", "---", "---", "---", "---"]
    else:
        headers = ["Retrieval Mode", "Recall@1", "Recall@3", "Recall@5", "MRR"]
        sep = ["---", "---", "---", "---", "---"]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]

    for m in modes:
        if m not in metrics:
            continue
        vals = metrics[m]
        r1 = f"{vals.get('recall_at_1', 0.0) * 100:.2f}%"
        r3 = f"{vals.get('recall_at_3', 0.0) * 100:.2f}%"
        r5 = f"{vals.get('recall_at_5', 0.0) * 100:.2f}%"
        mrr = f"{vals.get('mrr', 0.0):.4f}"

        row = [mode_display.get(m, m), r1, r3, r5, mrr]
        if include_latency:
            lat = f"{vals.get('latency_ms', 0.0):.1f} ms"
            row.append(lat)

        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def update_readme():
    readme_path = PROJECT_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    table = generate_table(include_latency=True)

    # Replace table between ## Search Retrieval Evaluation Benchmark and ### Key Benchmark Observations
    import re
    pattern = r"(\| Retrieval Mode \|.*?\n(?:\|.*?\n)+)"
    match = re.search(pattern, content)
    if match:
        new_content = content[:match.start()] + table + "\n" + content[match.end():]
        readme_path.write_text(new_content, encoding="utf-8")
        print(f"[+] Updated {readme_path} with table:\n{table}")
    else:
        print("[-] Could not find benchmark table pattern in README.md")


if __name__ == "__main__":
    table = generate_table(include_latency=True)
    print("Generated Table:\n")
    print(table)
    update_readme()
