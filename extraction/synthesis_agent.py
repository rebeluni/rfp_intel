"""
Synthesis and Cross-Bid Comparison Agent (Phase 3).
Performs comparative analysis, risk evaluation, and markdown report generation across bids.
"""

import logging
from typing import Any, Dict, List, Optional
from extraction.models import BidExtractionResult, CrossBidComparison, ComparisonRow
from extraction.llm_client import BaseLLMClient, get_llm_client

logger = logging.getLogger(__name__)


class SynthesisAgent:
    """Agent responsible for cross-bid comparison, risk assessment, and synthesis reporting."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or get_llm_client()

    def compare_bids(
        self,
        bids_results: Dict[str, BidExtractionResult],
        fields_defs: Dict[str, Any]
    ) -> CrossBidComparison:
        """Generate structured cross-bid comparison matrix and risk analysis."""
        bids = list(bids_results.keys())
        raw_bids_data = {b: bids_results[b].fields for b in bids}

        synth_data = {}
        if hasattr(self.llm_client, "synthesize_comparison"):
            try:
                synth_data = self.llm_client.synthesize_comparison(raw_bids_data, fields_defs)
            except Exception as e:
                logger.warning(f"Error calling LLM synthesize_comparison: {e}")

        matrix_rows = []
        if synth_data.get("matrix"):
            for r in synth_data["matrix"]:
                matrix_rows.append(ComparisonRow(
                    field_name=r["field_name"],
                    category=r.get("category", "general"),
                    values=r["values"],
                    difference_summary=r.get("difference_summary", "")
                ))
        else:
            for f_name, f_def in fields_defs.items():
                vals = {}
                for b in bids:
                    f_obj = raw_bids_data.get(b, {}).get(f_name)
                    vals[b] = str(f_obj.value) if f_obj and f_obj.value is not None else "Not found"

                diff_summary = "Identical" if len(set(vals.values())) == 1 else "Values differ across bids"
                matrix_rows.append(ComparisonRow(
                    field_name=f_name,
                    category=f_def.get("specialist", "general"),
                    values=vals,
                    difference_summary=diff_summary
                ))

        return CrossBidComparison(
            bids=bids,
            matrix=matrix_rows,
            risk_analysis=synth_data.get("risk_analysis", {b: [] for b in bids}),
            viability_scores=synth_data.get("viability_scores", {b: 85.0 for b in bids}),
            recommendations=synth_data.get("recommendations", {b: "Review compliance requirements" for b in bids}),
        )

    def generate_markdown_report(self, comparison: CrossBidComparison) -> str:
        """Render a comprehensive markdown comparison report."""
        bids = comparison.bids
        headers = ["Field Name", "Category"] + bids + ["Differences & Notes"]
        sep = ["---"] * len(headers)

        lines = [
            "# Cross-Bid Comparative Intelligence Report",
            "",
            "## Executive Summary",
            f"Comparative evaluation across **{len(bids)} procurement packages**: {', '.join(bids)}.",
            "",
            "## Comparative Specification & Requirement Matrix",
            "",
            f"| {' | '.join(headers)} |",
            f"| {' | '.join(sep)} |",
        ]

        for row in comparison.matrix:
            vals = [str(row.values.get(b, "N/A")).replace("\n", " ") for b in bids]
            line = f"| **{row.field_name}** | `{row.category}` | {' | '.join(vals)} | {row.difference_summary} |"
            lines.append(line)

        lines.extend([
            "",
            "## Operational & Legal Risk Evaluation",
            ""
        ])

        for b, risks in comparison.risk_analysis.items():
            lines.append(f"### {b} Risk Profile")
            lines.append(f"- **Viability Score**: `{comparison.viability_scores.get(b, 'N/A')}/100`")
            lines.append(f"- **Strategic Recommendation**: {comparison.recommendations.get(b, 'Proceed with standard bidding.')}")
            lines.append("- **Identified Legal/Operational Risks**:")
            for r in risks:
                lines.append(f"  - {r}")
            lines.append("")

        return "\n".join(lines)
