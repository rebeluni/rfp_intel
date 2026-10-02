"""
CLI Command Interface for Extraction and Multi-Agent Synthesis (Phase 3).
Commands:
  - python -m extraction.cli extract --bid-id Bid1
  - python -m extraction.cli compare --bids Bid1,Bid2
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from config.settings import settings
from extraction.graph import ExtractionPipeline
from extraction.synthesis_agent import SynthesisAgent
from extraction.models import BidExtractionResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("extraction.cli")


def run_extract(bid_id: str, output_file: Optional[Path] = None) -> BidExtractionResult:
    pipeline = ExtractionPipeline()
    result = pipeline.run(bid_id=bid_id)

    out_path = output_file or (settings.OUTPUTS_DIR / f"{bid_id.lower()}_extraction.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

    print(f"\n========================================================")
    print(f"EXTRACTION COMPLETE: {bid_id}")
    print(f"Compliance Score: {result.overall_compliance_score}%")
    print(f"Fields Found: {sum(1 for f in result.fields.values() if f.status == 'FOUND')}/{len(result.fields)}")
    print(f"Saved to: {out_path}")
    print(f"========================================================\n")

    for name, field in result.fields.items():
        val = field.value if field.value is not None else "[NOT FOUND]"
        val_status = "VALID" if result.validations.get(name, {}).is_valid else "ISSUE"
        print(f"  • {name:<30}: {str(val):<40} [{val_status}]")

    return result


def run_compare(bids_str: str, output_file: Optional[Path] = None, force: bool = False):
    bids = [b.strip() for b in bids_str.split(",") if b.strip()]
    pipeline = ExtractionPipeline()
    synthesis = SynthesisAgent()

    bids_results = {}
    for bid_id in bids:
        cached_file = settings.OUTPUTS_DIR / f"{bid_id.lower()}_extraction.json"
        if cached_file.exists() and not force:
            logger.info(f"Loading cached extractions for {bid_id} from {cached_file}...")
            with open(cached_file, "r", encoding="utf-8") as f:
                bids_results[bid_id] = BidExtractionResult.model_validate_json(f.read())
        else:
            bids_results[bid_id] = pipeline.run(bid_id=bid_id)

    comparison = synthesis.compare_bids(
        bids_results=bids_results,
        fields_defs=pipeline.extractor.field_definitions,
    )

    report_md = synthesis.generate_markdown_report(comparison)

    out_md = output_file or (settings.OUTPUTS_DIR / "bids_comparison_matrix.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(report_md)

    out_json = settings.OUTPUTS_DIR / "bids_comparison.json"
    with open(out_json, "w", encoding="utf-8") as f:
        f.write(comparison.model_dump_json(indent=2))

    print(f"\n========================================================")
    print(f"CROSS-BID COMPARISON COMPLETE: {', '.join(bids)}")
    print(f"Generated Markdown Report: {out_md}")
    print(f"Generated JSON Schema:     {out_json}")
    print(f"========================================================\n")
    print(report_md[:1200] + "\n...\n[Full report saved to outputs/bids_comparison_matrix.md]")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent RFP Extraction & Comparison CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract command
    p_extract = subparsers.add_parser("extract", help="Extract fields from a bid package")
    p_extract.add_argument("--bid-id", required=True, help="Bid identifier (e.g. Bid1, Bid2)")
    p_extract.add_argument("--out", type=Path, default=None, help="Custom output JSON path")

    # compare command
    p_compare = subparsers.add_parser("compare", help="Compare multiple bids")
    p_compare.add_argument("--bids", default="Bid1,Bid2", help="Comma-separated bid IDs (e.g. Bid1,Bid2)")
    p_compare.add_argument("--out", type=Path, default=None, help="Custom output Markdown report path")

    args = parser.parse_args()

    if args.command == "extract":
        run_extract(args.bid_id, args.out)
    elif args.command == "compare":
        run_compare(args.bids, args.out)


if __name__ == "__main__":
    main()
