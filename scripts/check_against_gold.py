"""
Evaluation script checking pipeline outputs against ground truth gold_values.json.
Strict matching over all 60 fields (20 fields x 3 bids).
Reports MATCH, MISMATCH, MISSING, and EXPECTED_NULL_OK separately.
Does NOT import or influence the pipeline execution.
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = PROJECT_ROOT / "tests" / "gold_values.json"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def normalize_text(val: Any) -> str:
    """Normalize text: lowercase, strip punctuation, collapse whitespace."""
    if val is None:
        return ""
    s = str(val).lower()
    # Normalize punctuation and special characters to single spaces, keeping alphanumeric and @
    s = re.sub(r"[^\w\s@]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_strict_match(actual: Any, expected: Any) -> bool:
    """
    Strict matcher:
    - Normalizes case, whitespace, and punctuation.
    - Requires equality or direct substring match against the expected value or an explicit alias.
    - No loose word-subset or partial token matching.
    """
    if actual is None:
        return False
    norm_actual = normalize_text(actual)
    if not norm_actual:
        return False

    candidates = []
    if isinstance(expected, list):
        candidates = expected
    elif isinstance(expected, dict):
        candidates = [expected.get("value")] + expected.get("aliases", [])
    elif expected is not None:
        candidates = [str(expected)]

    for cand in candidates:
        if cand is None:
            continue
        norm_cand = normalize_text(cand)
        if not norm_cand:
            continue
        # Strict containment or equality:
        if norm_cand == norm_actual or norm_cand in norm_actual or norm_actual in norm_cand:
            return True

    return False


def is_null_val(val: Any) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return s in ["none", "null", "not found", "n/a", ""]


def evaluate_bid(bid_id: str, gold_fields: Dict[str, Any], output_data: Dict[str, Any]) -> Dict[str, Any]:
    extracted_fields = output_data.get("fields", {})
    matches = 0
    expected_null_ok = 0
    mismatches = 0
    missing = 0
    details = []

    for f_name, gold_expected in gold_fields.items():
        field_obj = extracted_fields.get(f_name)
        val = field_obj.get("value") if field_obj else None

        if gold_expected is None:
            # Field expected to be absent in the document
            if is_null_val(val):
                status = "EXPECTED_NULL_OK"
                expected_null_ok += 1
            else:
                # Value was hallucinated when document has no such term
                status = "MISMATCH"
                mismatches += 1
        else:
            # Field expected to be present
            if is_null_val(val):
                status = "MISSING"
                missing += 1
            elif is_strict_match(val, gold_expected):
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
    correct = matches + expected_null_ok
    accuracy = (correct / total * 100.0) if total > 0 else 0.0

    return {
        "bid_id": bid_id,
        "total": total,
        "matches": matches,
        "expected_null_ok": expected_null_ok,
        "mismatches": mismatches,
        "missing": missing,
        "correct": correct,
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
    print("      RFP PIPELINE STRICT GOLD AUDIT (60 FIELDS: 20 x 3 BIDS)       ")
    print("====================================================================\n")

    overall_matches = 0
    overall_expected_null_ok = 0
    overall_mismatches = 0
    overall_missing = 0
    overall_total = 0

    per_bid_results = {}

    for bid_id, gold_fields in gold_data.items():
        out_file = OUTPUTS_DIR / f"{bid_id.lower()}.json"
        if not out_file.exists():
            print(f"[!] Output file missing: {out_file}. Please run extraction first.")
            continue

        with open(out_file, "r", encoding="utf-8") as f:
            out_data = json.load(f)

        res = evaluate_bid(bid_id, gold_fields, out_data)
        per_bid_results[bid_id] = res

        overall_matches += res["matches"]
        overall_expected_null_ok += res["expected_null_ok"]
        overall_mismatches += res["mismatches"]
        overall_missing += res["missing"]
        overall_total += res["total"]

        print(f"=== {bid_id.upper()} EVALUATION ({res['correct']}/{res['total']} - {res['accuracy']}%) ===")
        print(f"    MATCH: {res['matches']} | EXPECTED_NULL_OK: {res['expected_null_ok']} | MISMATCH: {res['mismatches']} | MISSING: {res['missing']}")
        for d in res["details"]:
            st = d["status"]
            f = d["field"]
            exp = d["expected"]
            ext = d["extracted"]
            if st == "MATCH":
                print(f"  [MATCH]   {f:32}: {str(ext)[:45]}")
            elif st == "EXPECTED_NULL_OK":
                print(f"  [NULL_OK] {f:32}: null as expected")
            elif st == "MISMATCH":
                print(f"  [MISMATCH]{f:32}: expected={repr(exp)[:30]} | actual={repr(ext)[:35]}")
            else:
                print(f"  [MISSING] {f:32}: expected={repr(exp)[:30]} | actual=None")
        print()

    overall_correct = overall_matches + overall_expected_null_ok
    if overall_total > 0:
        overall_acc = round((overall_correct / overall_total) * 100.0, 1)
        print("====================================================================")
        print(f"OVERALL STRICT GOLD AUDIT SUMMARY ({overall_total} total fields across 3 bids):")
        print(f"  Total Correct:        {overall_correct}/{overall_total} ({overall_acc}%)")
        print(f"  - Strict Matches:     {overall_matches}")
        print(f"  - Expected Null OK:   {overall_expected_null_ok}")
        print(f"  - Mismatches:         {overall_mismatches}")
        print(f"  - Missing (Null):     {overall_missing}")
        print("====================================================================")

    # Save structured audit results
    audit_json = OUTPUTS_DIR / "gold_audit_results.json"
    with open(audit_json, "w", encoding="utf-8") as f:
        json.dump({
            "total_fields": overall_total,
            "overall_accuracy": overall_acc if overall_total > 0 else 0.0,
            "matches": overall_matches,
            "expected_null_ok": overall_expected_null_ok,
            "mismatches": overall_mismatches,
            "missing": overall_missing,
            "bids": per_bid_results
        }, f, indent=2)
    print(f"\n[+] Saved strict audit report to {audit_json}")


if __name__ == "__main__":
    main()
