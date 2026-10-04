"""
Evaluation script checking pipeline outputs against ground truth gold_values.json.
Prints MATCH / MISMATCH / MISSING for each target field and calculates accuracy percentage.
Does NOT import or influence the pipeline execution.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = PROJECT_ROOT / "tests" / "gold_values.json"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def normalize_str(s: Any) -> str:
    if s is None:
        return ""
    return str(s).lower().strip().replace("-", " ").replace("_", " ")


def is_match(extracted_val: Any, gold_val: str) -> bool:
    if extracted_val is None:
        return False
    ext_norm = normalize_str(extracted_val)
    gold_norm = normalize_str(gold_val)

    # Check for direct substring inclusion or exact match
    if gold_norm in ext_norm or ext_norm in gold_norm:
        return True

    # Check if all key words of gold appear in extracted
    gold_words = [w for w in gold_norm.split() if len(w) > 2]
    if gold_words and all(w in ext_norm for w in gold_words):
        return True

    return False


def evaluate_bid(bid_id: str, gold_fields: Dict[str, str], output_data: Dict[str, Any]) -> Dict[str, Any]:
    extracted_fields = output_data.get("fields", {})
    matches = 0
    mismatches = 0
    missing = 0
    details = []

    for f_name, gold_expected in gold_fields.items():
        field_obj = extracted_fields.get(f_name)
        val = field_obj.get("value") if field_obj else None

        if val is None:
            status = "MISSING"
            missing += 1
        elif is_match(val, gold_expected):
            status = "MATCH"
            matches += 1
        else:
            status = "MISMATCH"
            mismatches += 1

        details.append({
            "field": f_name,
            "status": status,
            "expected": gold_expected,
            "extracted": val
        })

    total = len(gold_fields)
    accuracy = (matches / total * 100.0) if total > 0 else 0.0

    return {
        "bid_id": bid_id,
        "total": total,
        "matches": matches,
        "mismatches": mismatches,
        "missing": missing,
        "accuracy": round(accuracy, 1),
        "details": details
    }


def main():
    if not GOLD_PATH.exists():
        print(f"Error: {GOLD_PATH} does not exist.")
        sys.exit(1)

    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        gold_data = json.load(f)

    print("====================================================================")
    print("           RFP PIPELINE ACCURACY AUDIT (AGAINST GOLD VALUES)        ")
    print("====================================================================\n")

    overall_matches = 0
    overall_total = 0

    for bid_id, gold_fields in gold_data.items():
        out_file = OUTPUTS_DIR / f"{bid_id.lower()}.json"
        if not out_file.exists():
            print(f"[!] Output file missing: {out_file}. Please run extraction first.")
            continue

        with open(out_file, "r", encoding="utf-8") as f:
            out_data = json.load(f)

        res = evaluate_bid(bid_id, gold_fields, out_data)
        overall_matches += res["matches"]
        overall_total += res["total"]

        print(f"=== {bid_id.upper()} EVALUATION ({res['matches']}/{res['total']} - {res['accuracy']}%) ===")
        for d in res["details"]:
            st = d["status"]
            f = d["field"]
            exp = d["expected"]
            ext = d["extracted"]
            if st == "MATCH":
                print(f"  [PASS] {f}: MATCH")
                print(f"         Expected: {exp}")
                print(f"         Extracted: {ext}")
            elif st == "MISMATCH":
                print(f"  [FAIL] {f}: MISMATCH")
                print(f"         Expected: {exp}")
                print(f"         Extracted: {ext}")
            else:
                print(f"  [MISS] {f}: MISSING (null)")
                print(f"         Expected: {exp}")
        print()

    if overall_total > 0:
        overall_acc = round((overall_matches / overall_total) * 100.0, 1)
        print("====================================================================")
        print(f"OVERALL GOLD MATCH ACCURACY: {overall_acc}% ({overall_matches}/{overall_total} fields matched)")
        print("====================================================================")


if __name__ == "__main__":
    main()
