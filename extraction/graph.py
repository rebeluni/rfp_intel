"""
LangGraph Multi-Agent Orchestrator (Phase 3).
Compiles a cyclical StateGraph coordinating:
  1. Evidence Retrieval Node
  2. Extractor Agent Node
  3. Validator Agent Node
  4. Conditional Refinement Node (handles addendum conflicts and re-retrieval)
  5. Finalizer Node (compliance score & export)
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from extraction.models import BidExtractionResult, ExtractedField, FieldValidation, FieldEvidence
from extraction.extractor_agent import ExtractorAgent
from extraction.validator_agent import ValidatorAgent
from extraction.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class ExtractionState(TypedDict):
    bid_id: str
    field_defs: Dict[str, Any]
    retrieved_evidence: Dict[str, List[Dict[str, Any]]]
    extracted_fields: Dict[str, ExtractedField]
    validations: Dict[str, FieldValidation]
    needs_refinement: bool
    refinement_count: int
    result: Optional[BidExtractionResult]


class ExtractionPipeline:
    """Compiles and executes the LangGraph state graph for a bid package."""

    def __init__(
        self,
        extractor: Optional[ExtractorAgent] = None,
        validator: Optional[ValidatorAgent] = None,
    ):
        self.extractor = extractor or ExtractorAgent()
        self.validator = validator or ValidatorAgent()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(ExtractionState)

        # Add Nodes
        builder.add_node("retrieve_evidence", self._retrieve_evidence_node)
        builder.add_node("extract_fields", self._extract_fields_node)
        builder.add_node("validate_extractions", self._validate_node)
        builder.add_node("refine_conflicts", self._refine_conflicts_node)
        builder.add_node("finalize", self._finalize_node)

        # Define Edges
        builder.set_entry_point("retrieve_evidence")
        builder.add_edge("retrieve_evidence", "extract_fields")
        builder.add_edge("extract_fields", "validate_extractions")

        # Conditional Edge after validation
        builder.add_conditional_edges(
            "validate_extractions",
            self._check_refinement_needed,
            {
                "refine": "refine_conflicts",
                "finalize": "finalize"
            }
        )

        builder.add_edge("refine_conflicts", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    # --- Node Implementations ---

    def _retrieve_evidence_node(self, state: ExtractionState) -> Dict[str, Any]:
        bid_id = state["bid_id"]
        field_defs = state["field_defs"]
        logger.info(f"[Graph Node: retrieve_evidence] Querying hybrid index for {bid_id}...")

        evidence_map: Dict[str, List[Dict[str, Any]]] = {}
        for f_name, f_def in field_defs.items():
            passages = self.extractor.retrieve_evidence_for_field(f_name, f_def, bid_id, top_k=5)
            evidence_map[f_name] = passages

        return {"retrieved_evidence": evidence_map}

    def _extract_fields_node(self, state: ExtractionState) -> Dict[str, Any]:
        field_defs = state["field_defs"]
        evidence_map = state["retrieved_evidence"]
        logger.info("[Graph Node: extract_fields] Extracting structured fields via LLM/rules...")

        extracted_map: Dict[str, ExtractedField] = {}
        for f_name, f_def in field_defs.items():
            passages = evidence_map.get(f_name, [])
            ext = self.extractor.llm_client.extract_field(f_name, f_def, passages)
            extracted_map[f_name] = ext

        return {"extracted_fields": extracted_map}

    def _validate_node(self, state: ExtractionState) -> Dict[str, Any]:
        bid_id = state["bid_id"]
        extracted_fields = state["extracted_fields"]
        evidence_map = state["retrieved_evidence"]
        logger.info("[Graph Node: validate_extractions] Validator agent auditing citations & addenda...")

        # Gather any addendum passages from all retrieved evidence
        all_addenda_chunks = []
        for passages in evidence_map.values():
            for p in passages:
                if "addendum" in p.get("file_name", "").lower():
                    all_addenda_chunks.append(p)

        validations = self.validator.validate_package(
            extracted_fields=extracted_fields,
            retrieved_evidence_map=evidence_map,
            addenda_chunks=all_addenda_chunks,
        )

        # Check if any field has an addendum conflict that needs refinement
        has_conflicts = any(v.has_addendum_conflict for v in validations.values())
        needs_refinement = has_conflicts and (state.get("refinement_count", 0) < 1)

        return {
            "validations": validations,
            "needs_refinement": needs_refinement
        }

    def _check_refinement_needed(self, state: ExtractionState) -> str:
        if state.get("needs_refinement", False):
            return "refine"
        return "finalize"

    def _refine_conflicts_node(self, state: ExtractionState) -> Dict[str, Any]:
        logger.info("[Graph Node: refine_conflicts] Overriding superseded fields with Addenda values...")
        extracted_fields = dict(state["extracted_fields"])
        validations = dict(state["validations"])

        for f_name, val in validations.items():
            if val.has_addendum_conflict and val.suggested_value:
                orig = extracted_fields[f_name]
                extracted_fields[f_name] = ExtractedField(
                    field_name=f_name,
                    value=val.suggested_value,
                    status="FOUND",
                    confidence=1.0,
                    evidence=orig.evidence,
                    notes=f"Overridden by Addendum (Previously: {orig.value})",
                    specialist=orig.specialist,
                )
                validations[f_name] = FieldValidation(
                    field_name=f_name,
                    is_valid=True,
                    is_grounded=True,
                    has_addendum_conflict=False,
                    feedback=f"Successfully reconciled with Addendum amendment ({val.suggested_value})."
                )

        return {
            "extracted_fields": extracted_fields,
            "validations": validations,
            "refinement_count": state.get("refinement_count", 0) + 1,
            "needs_refinement": False,
        }

    def _finalize_node(self, state: ExtractionState) -> Dict[str, Any]:
        bid_id = state["bid_id"]
        fields = state["extracted_fields"]
        validations = state["validations"]
        field_defs = state["field_defs"]

        # Calculate overall compliance & completeness score
        found_count = sum(1 for f in fields.values() if f.status == "FOUND")
        valid_count = sum(1 for v in validations.values() if v.is_valid)
        total_fields = max(1, len(field_defs))

        compliance_pct = round(((found_count + valid_count) / (2 * total_fields)) * 100, 1)

        total_evidence_chunks = sum(len(ev) for ev in state["retrieved_evidence"].values())

        summary = (
            f"Extraction completed for {bid_id}: {found_count}/{total_fields} fields identified "
            f"with {valid_count}/{total_fields} validations passing ({compliance_pct}% compliance score)."
        )

        res = BidExtractionResult(
            bid_id=bid_id,
            fields=fields,
            validations=validations,
            overall_compliance_score=compliance_pct,
            summary=summary,
            raw_evidence_count=total_evidence_chunks,
        )

        return {"result": res}

    def run(self, bid_id: str) -> BidExtractionResult:
        """Run the full extraction workflow for a single bid."""
        initial_state: ExtractionState = {
            "bid_id": bid_id,
            "field_defs": self.extractor.field_definitions,
            "retrieved_evidence": {},
            "extracted_fields": {},
            "validations": {},
            "needs_refinement": False,
            "refinement_count": 0,
            "result": None,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state["result"]
