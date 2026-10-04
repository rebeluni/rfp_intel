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


def generate_experiments_table() -> str:
    exp_file = PROJECT_ROOT / "outputs" / "search_experiments.json"
    if not exp_file.exists():
        return ""
    with open(exp_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    headers = ["Experiment", "Status", "Recall@1", "Recall@3", "Recall@5", "MRR", "Delta MRR", "Decision"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for key, exp in data.items():
        name = exp.get("name", key)
        status = exp.get("status", "run")
        if status == "not run":
            r1, r3, r5, mrr, delta_mrr = "-", "-", "-", "-", "-"
            decision = "Not Run"
        else:
            r1 = f"{exp.get('recall_at_1', 0.0) * 100:.2f}%"
            r3 = f"{exp.get('recall_at_3', 0.0) * 100:.2f}%"
            r5 = f"{exp.get('recall_at_5', 0.0) * 100:.2f}%"
            mrr = f"{exp.get('mrr', 0.0):.4f}"
            d_mrr = exp.get('delta_mrr', 0.0)
            delta_mrr = f"+{d_mrr:.4f}" if d_mrr > 0 else f"{d_mrr:.4f}"
            decision = "**Kept**" if exp.get("kept") else "Discarded"

        lines.append(f"| {name} | `{status}` | {r1} | {r3} | {r5} | {mrr} | {delta_mrr} | {decision} |")

    return "\n".join(lines)


def update_readme():
    readme_path = PROJECT_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    table = generate_table(include_latency=True)

    # 1. Replace benchmark table
    import re
    pattern = r"(\| Retrieval Mode \|.*?\n(?:\|.*?\n)+)"
    match = re.search(pattern, content)
    if match:
        content = content[:match.start()] + table + "\n" + content[match.end():]
        print(f"[+] Updated benchmark table in {readme_path}")
    else:
        print("[-] Could not find benchmark table pattern in README.md")

    # 2. Add or replace D3 Search Experiments table
    exp_table = generate_experiments_table()
    if exp_table:
        exp_section = (
            "### D3 Search Optimization Experiments (22-Query Benchmark)\n\n"
            + exp_table + "\n\n"
        )
        if "### D3 Search Optimization Experiments" in content:
            exp_pattern = r"(### D3 Search Optimization Experiments.*?\n\n\| Experiment \|.*?\n(?:\|.*?\n)+\n)"
            content = re.sub(exp_pattern, exp_section, content, flags=re.DOTALL)
        else:
            # Insert before ## Known Limitations
            target_str = "## Known Limitations & Design Trade-offs"
            if target_str in content:
                content = content.replace(target_str, exp_section + target_str)
        print(f"[+] Updated D3 experiments table in {readme_path}")

    readme_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    table = generate_table(include_latency=True)
    print("Generated Benchmark Table:\n")
    print(table)
    exp_table = generate_experiments_table()
    print("\nGenerated Experiments Table:\n")
    print(exp_table)
    update_readme()
