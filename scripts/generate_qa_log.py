"""
Generate qa_log.md by running 10+ natural-language questions through the QA agent.
Output: outputs/qa_log.md
"""
import sys, io, json, textwrap
from pathlib import Path
from datetime import datetime, timezone

# UTF-8 safe output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from search.index_manager import IndexManager
from search.hybrid_retriever import HybridRetriever
from search.qa_agent import QAAgent

QUESTIONS = [
    # --- Bid-specific ---
    ("What is the solicitation/bid number for Bid1?", "Bid1"),
    ("What is the proposal due date for Bid2 (Dell laptops)?", "Bid2"),
    ("Who is the issuing organisation for the Austin ISD bid?", "Bid3"),
    ("List all product tiers and quantities requested in the Dallas ISD solicitation.", "Bid1"),
    ("What products and quantities are required by the Maryland State Treasurer's Office?", "Bid2"),
    ("What laptop model and quantity does Austin ISD want in Bid3?", "Bid3"),
    # --- Cross-bid comparison ---
    ("Compare the warranty terms across all three bids.", None),
    ("Which bid has the earliest submission deadline?", None),
    ("Compare the procurement scale (total units) across Bid1, Bid2, and Bid3.", None),
    ("Which bids mention a pre-bid meeting or pre-proposal conference?", None),
    # --- Addendum / compliance ---
    ("Did any addenda change the due date for the Dallas ISD RFP? If so, what is the new date?", "Bid1"),
    ("What are the insurance requirements mentioned in the Dallas ISD solicitation?", "Bid1"),
    ("What evaluation criteria are used for the Austin ISD laptop procurement?", "Bid3"),
    # --- General ---
    ("What is the difference in issuing authority between Bid1 and Bid2?", None),
    ("Summarise all three bids in one paragraph each.", None),
    # --- Task C6 Additions ---
    ("What is the submission deadline for Bid1 after all addendums?", "Bid1"),
    ("Which affidavits are required for the Dell laptop bid?", "Bid2"),
    ("Is a bid bond required, and if so, how much for Bid1?", "Bid1"),
    ("Is a bid bond required, and if so, how much for Bid2?", "Bid2"),
    ("Is a bid bond required, and if so, how much for Bid3?", "Bid3"),
    ("What changed in Addendum 2 compared to the original RFP?", "Bid1"),
    ("Compare the warranty requirements of both bids.", None),
    ("What is the required fuel efficiency rating for delivery vehicles across the bids?", None),
]

def run_qa_log():
    idx_mgr = IndexManager()
    retriever = HybridRetriever(
        bm25_index=idx_mgr.bm25_index,
        dense_indexer=idx_mgr.dense_indexer,
    )
    qa = QAAgent(retriever=retriever)

    lines = []
    lines.append("# QA Log — RFP Intelligence Platform\n")
    lines.append(f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_\n")
    lines.append(f"_Total questions: {len(QUESTIONS)}_\n\n")
    lines.append("---\n\n")

    for i, (question, bid_override) in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] Asking: {question!r} (bid={bid_override})")
        try:
            resp = qa.ask(question=question, bid_id=bid_override)
        except Exception as e:
            resp = {"answer": f"ERROR: {e}", "citations": [], "target_bid": bid_override}

        lines.append(f"## Q{i}: {question}\n\n")
        if resp.get("target_bid"):
            lines.append(f"**Routed to:** `{resp['target_bid']}`\n\n")

        answer = resp.get("answer", "").strip()
        lines.append(f"**Answer:**\n\n{answer}\n\n")

        citations = resp.get("citations", [])
        if citations:
            lines.append("**Citations:**\n\n")
            for j, c in enumerate(citations, 1):
                q_txt = f': "{c.get("quote")}"' if c.get("quote") else ""
                lines.append(f"{j}. `{c.get('file')}` (p.{c.get('page')}){q_txt}\n")
            lines.append("\n")
        else:
            lines.append("_No citations returned._\n\n")

        lines.append("---\n\n")

    out_path = ROOT / "outputs" / "qa_log.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"\n[+] qa_log.md written to {out_path}")


if __name__ == "__main__":
    run_qa_log()
