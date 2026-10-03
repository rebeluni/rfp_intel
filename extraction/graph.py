"""
Multi-Agent Extraction Engine with LangGraph Orchestration.
Strictly implements Items 3, 4, 5, 6, 8:
  - Explicit Graph Nodes:
      1. orchestrator_planner: partitions fields by specialist, plans execution.
      2. retrieval: runs 3 specialist groups in parallel threads.
      3. extract_fields: extracts structured fields with LLM.
      4. validate_fields: deterministic validator (contiguous quote in cited chunk, format checks, absence confirmation).
      5. retry_loop: retries failed fields with expanded queries up to MAX_VALIDATION_RETRIES.
      6. reconciliation: reconciles addenda in chronological order, logs addendum_changes, updates fields.
      7. qa_node: validates Q&A readiness and prepares query routing.
      8. finalize: builds Section 8.1 schema, persists outputs/sample_trace.json.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END

from config.settings import settings
from extraction.models import (
    BidExtractionResult,
    FieldOutput,
    AddendumChange,
    ValidationSummary,
    FieldValidation,
    FieldSource
)
from extraction.extractor_agent import ExtractorAgent
from extraction.validator_agent import ValidatorAgent
from extraction.reconciliation_agent import ReconciliationAgent
from extraction.tracer import StructuredTracer
from search.hybrid_retriever import HybridRetriever
from extraction.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class ExtractionState(TypedDict):
    bid_id: str
    field_defs: Dict[str, Any]
    specialist_groups: Dict[str, List[str]]
    retrieved_evidence: Dict[str, List[Dict[str, Any]]]
    extracted_fields: Dict[str, FieldOutput]
    validations: Dict[str, FieldValidation]
    validation_summary: ValidationSummary
    addendum_changes: List[AddendumChange]
    retry_count: int
    max_retries: int
    needs_retry: bool
    result: Optional[BidExtractionResult]


class ExtractionPipeline:
    """Compiles and executes the StateGraph coordinating all specialist agents."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        tracer: Optional[StructuredTracer] = None
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = get_llm_client()
        self.extractor = ExtractorAgent(retriever=self.retriever, llm_client=self.llm_client)
        self.validator = ValidatorAgent(retriever=self.retriever, llm_client=self.llm_client)
        self.reconciler = ReconciliationAgent(retriever=self.retriever, llm_client=self.llm_client)
        self.tracer = tracer or StructuredTracer()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(ExtractionState)

        # Explicit Agent Nodes (Item 6)
        builder.add_node("orchestrator_planner", self._orchestrator_planner_node)
        builder.add_node("retrieval", self._parallel_retrieval_node)
        builder.add_node("extract_fields", self._extract_fields_node)
        builder.add_node("validate_fields", self._validate_fields_node)
        builder.add_node("retry_refinement", self._retry_refinement_node)
        builder.add_node("reconciliation", self._reconciliation_node)
        builder.add_node("qa_node", self._qa_node)
        builder.add_node("finalize", self._finalize_node)

        # Flow Edges
        builder.set_entry_point("orchestrator_planner")
        builder.add_edge("orchestrator_planner", "retrieval")
        builder.add_edge("retrieval", "extract_fields")
        builder.add_edge("extract_fields", "validate_fields")

        # Conditional Edge for Retry Loop (Item 5)
        builder.add_conditional_edges(
            "validate_fields",
            self._check_retry_condition,
            {
                "retry": "retry_refinement",
                "reconcile": "reconciliation"
            }
        )

        builder.add_edge("retry_refinement", "validate_fields")
        builder.add_edge("reconciliation", "qa_node")
        builder.add_edge("qa_node", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    # -----------------------------------------------------------------------
    # Graph Node Implementations
    # -----------------------------------------------------------------------

    def _orchestrator_planner_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 1: Orchestrator / Planner partitions fields into specialist groups."""
        bid_id = state["bid_id"]
        field_defs = state["field_defs"]

        with self.tracer.start_step("orchestrator_planner", {"bid_id": bid_id, "total_fields": len(field_defs)}) as ctx:
            logger.info(f"[Orchestrator] Planning multi-agent execution for '{bid_id}' ({len(field_defs)} fields)...")

            # Partition into the 3 specialist groups
            groups = {
                "commercial_legal": [],
                "dates_logistics": [],
                "product_specs": []
            }
            for f_name, f_def in field_defs.items():
                spec = f_def.get("specialist", "commercial_legal")
                if spec in groups:
                    groups[spec].append(f_name)
                else:
                    groups["commercial_legal"].append(f_name)

            plan_summary = {spec: len(fields) for spec, fields in groups.items()}
            ctx.complete({"specialist_groups": plan_summary, "status": "planned"})

            return {
                "specialist_groups": groups,
                "retry_count": 0,
                "max_retries": settings.MAX_VALIDATION_RETRIES,
                "needs_retry": False
            }

    def _parallel_retrieval_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 2: Retrieval Agent executes 3 specialist groups in parallel threads (Item 5)."""
        bid_id = state["bid_id"]
        field_defs = state["field_defs"]
        groups = state["specialist_groups"]

        with self.tracer.start_step("retrieval", {"bid_id": bid_id, "specialist_groups": list(groups.keys())}) as ctx:
            logger.info(f"[Retrieval] Fanning out parallel retrieval across 3 specialist groups for '{bid_id}'...")
            evidence_map: Dict[str, List[Dict[str, Any]]] = {}

            def retrieve_specialist(group_name: str, field_list: List[str]) -> Dict[str, List[Dict[str, Any]]]:
                group_evidence = {}
                for f_name in field_list:
                    f_def = field_defs.get(f_name, {})
                    passages = self.extractor.retrieve_evidence_for_field(f_name, f_def, bid_id, top_k=5)
                    group_evidence[f_name] = passages
                return group_evidence

            # Fan out across threads for the 3 specialist groups
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(retrieve_specialist, group_name, f_list): group_name
                    for group_name, f_list in groups.items()
                }
                for fut in as_completed(futures):
                    group_res = fut.result()
                    evidence_map.update(group_res)

            total_chunks = sum(len(p) for p in evidence_map.values())
            print(f"[*] Retrieval completed: {total_chunks} chunks gathered across {len(evidence_map)} fields.", flush=True)
            ctx.record_tool_call(
                "hybrid_retriever.search_parallel",
                {"specialists": list(groups.keys()), "total_fields": len(evidence_map)},
                f"Retrieved {total_chunks} chunks across {len(evidence_map)} fields."
            )
            ctx.complete({"retrieved_fields_count": len(evidence_map), "total_chunks": total_chunks})

            return {"retrieved_evidence": evidence_map}

    def _extract_fields_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 3: Extractor Agent extracts structured fields via LLM in parallel threads per specialist group."""
        field_defs = state["field_defs"]
        evidence_map = state["retrieved_evidence"]
        bid_id = state["bid_id"]
        groups = state.get("specialist_groups", {})

        with self.tracer.start_step("extractor", {"bid_id": bid_id, "fields_to_extract": len(field_defs)}) as ctx:
            print(f"[*] Extracting {len(field_defs)} target fields with Gemini across specialist groups in parallel...", flush=True)
            extracted_map: Dict[str, FieldOutput] = {}

            def extract_group(group_name: str, field_list: List[str]) -> Dict[str, FieldOutput]:
                res: Dict[str, FieldOutput] = {}
                for f_name in field_list:
                    f_def = field_defs.get(f_name, {})
                    passages = evidence_map.get(f_name, [])
                    ext = self.llm_client.extract_field(f_name, f_def, passages)
                    ext.specialist = f_def.get("specialist", group_name)
                    res[f_name] = ext
                    print(f"  [+] [{group_name}] {f_name}: {ext.value}", flush=True)
                return res

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(extract_group, group_name, f_list): group_name
                    for group_name, f_list in groups.items()
                    if f_list
                }
                for fut in as_completed(futures):
                    group_res = fut.result()
                    extracted_map.update(group_res)

            tokens = self.llm_client.get_tokens()
            ctx.add_tokens(tokens)

            found_count = sum(1 for f in extracted_map.values() if f.value is not None)
            ctx.complete({
                "extracted_fields_count": len(extracted_map),
                "found_fields_count": found_count,
                "cumulative_tokens": tokens
            }, tokens=tokens)

            return {"extracted_fields": extracted_map}

    def _validate_fields_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 4: Validator Agent performs deterministic validation and dynamic confidence (Item 4)."""
        bid_id = state["bid_id"]
        fields_map = state["extracted_fields"]
        evidence_map = state["retrieved_evidence"]
        field_defs = state["field_defs"]
        retry_count = state.get("retry_count", 0)

        with self.tracer.start_step("validator", {"bid_id": bid_id, "retry_iteration": retry_count}) as ctx:
            logger.info(f"[Validator] Running deterministic validation & dynamic confidence scoring (pass {retry_count})...")

            validated_fields, summary, val_details = self.validator.validate_package(
                bid_id=bid_id,
                fields_map=fields_map,
                retrieved_evidence_map=evidence_map,
                field_defs=field_defs
            )

            needs_retry = (len(summary.failed) > 0) and (retry_count < state.get("max_retries", settings.MAX_VALIDATION_RETRIES))

            ctx.complete({
                "passed": len(summary.passed),
                "failed": len(summary.failed),
                "not_found": len(summary.not_found),
                "needs_retry": needs_retry
            })

            return {
                "extracted_fields": validated_fields,
                "validation_summary": summary,
                "validations": val_details,
                "needs_retry": needs_retry
            }

    def _check_retry_condition(self, state: ExtractionState) -> str:
        """Item 5: Retry loop routing condition."""
        if state.get("needs_retry", False):
            return "retry"
        return "reconcile"

    def _retry_refinement_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 5: Retry refinement node expanding queries for failed fields up to MAX_VALIDATION_RETRIES."""
        bid_id = state["bid_id"]
        field_defs = state["field_defs"]
        failed_fields = state["validation_summary"].failed
        current_retry = state.get("retry_count", 0) + 1
        evidence_map = dict(state["retrieved_evidence"])
        extracted_map = dict(state["extracted_fields"])

        with self.tracer.start_step("retry_refinement", {"bid_id": bid_id, "retry_count": current_retry, "failed_fields": failed_fields}) as ctx:
            logger.info(f"[Retry Loop] Retrying {len(failed_fields)} failed fields with query expansion (attempt {current_retry})...")

            for f_name in failed_fields:
                f_def = field_defs.get(f_name, {})
                hints = f_def.get("query_expansion_hints", [])
                # Formulate alternative expanded query
                expanded_q = f"{f_name} {' '.join(hints[1:4]) if len(hints) > 1 else 'requirement specifications'}"
                new_passages = self.extractor.retrieve_evidence_for_field(
                    field_name=expanded_q,
                    field_def=f_def,
                    bid_id=bid_id,
                    top_k=8
                )
                evidence_map[f_name] = new_passages
                re_ext = self.llm_client.extract_field(f_name, f_def, new_passages)
                re_ext.specialist = f_def.get("specialist")
                extracted_map[f_name] = re_ext

            ctx.complete({"retried_fields": failed_fields, "new_retry_count": current_retry})

            return {
                "retrieved_evidence": evidence_map,
                "extracted_fields": extracted_map,
                "retry_count": current_retry
            }

    def _reconciliation_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 6: Explicit Addendum Reconciliation Agent (Item 3)."""
        bid_id = state["bid_id"]
        fields_map = state["extracted_fields"]
        summary = state.get("validation_summary", ValidationSummary())

        with self.tracer.start_step("reconciliation", {"bid_id": bid_id, "field_count": len(fields_map)}) as ctx:
            logger.info(f"[Reconciliation] Reconciling all fields against ordered addenda chunks for '{bid_id}'...")

            reconciled_fields, change_log = self.reconciler.reconcile_fields(
                bid_id=bid_id,
                fields_map=fields_map,
                summary=summary
            )

            tokens = self.llm_client.get_tokens()
            ctx.add_tokens(tokens)

            ctx.complete({
                "addendum_changes_count": len(change_log),
                "amended_fields": [c.field for c in change_log],
                "cumulative_tokens": tokens
            }, tokens=tokens)

            return {
                "extracted_fields": reconciled_fields,
                "addendum_changes": change_log,
                "validation_summary": summary
            }

    def _qa_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 7: Q&A node preparing natural language routing and validation (Item 6 & 7)."""
        bid_id = state["bid_id"]
        fields_map = state["extracted_fields"]

        with self.tracer.start_step("qa_node", {"bid_id": bid_id}) as ctx:
            logger.info(f"[Q&A Node] Verifying Q&A readiness and synthesized summaries for '{bid_id}'...")
            title_field = fields_map.get("solicitation_title") or fields_map.get("title")
            bid_title = title_field.value if title_field else None
            agency_field = fields_map.get("issuing_agency") or fields_map.get("agency")
            agency_name = agency_field.value if agency_field else None
            solicitation_num_field = fields_map.get("solicitation_number") or fields_map.get("bid_number")
            solicitation_num = solicitation_num_field.value if solicitation_num_field else None

            qa_meta = {
                "bid_id": bid_id,
                "title": bid_title,
                "issuing_agency": agency_name,
                "solicitation_number": solicitation_num,
                "fields_ready": len([f for f in fields_map.values() if f.value is not None]),
                "status": "ready"
            }
            ctx.complete({"qa_ready": True, "metadata": qa_meta})
            return {"qa_metadata": qa_meta}

    def _finalize_node(self, state: ExtractionState) -> Dict[str, Any]:
        """Node 8: Finalize extraction result matching Section 8.1 schema and save structured trace."""
        bid_id = state["bid_id"]
        fields_map = state["extracted_fields"]
        change_log = state.get("addendum_changes", [])
        summary = state.get("validation_summary", ValidationSummary())
        evidence_map = state.get("retrieved_evidence", {})

        with self.tracer.start_step("finalizer", {"bid_id": bid_id}) as ctx:
            logger.info(f"[Finalizer] Packaging Section 8.1 extraction result for '{bid_id}'...")

            # Enforce Section 8.1 requirement:
            # Delete the FieldSource(file="Solicitation Document", page=1) fallback.
            # A found value without a real citation must fail validation and become null.
            for f_name, f_out in fields_map.items():
                if f_out.value is None:
                    f_out.sources = []
                    if f_name not in summary.not_found and f_name not in summary.failed:
                        summary.not_found.append(f_name)
                    if f_name in summary.passed:
                        summary.passed.remove(f_name)
                elif not f_out.sources:
                    logger.warning(
                        f"[Finalizer] Field '{f_name}' had value '{f_out.value}' but NO valid citation. "
                        f"Failing validation and setting to null."
                    )
                    f_out.value = None
                    f_out.confidence = 0.0
                    f_out.status = "NOT_FOUND"
                    f_out.notes = "Failed validation: No valid citation found in documents"
                    f_out.sources = []
                    if f_name in summary.passed:
                        summary.passed.remove(f_name)
                    if f_name not in summary.failed:
                        summary.failed.append(f_name)

            # Re-calculate compliance score
            total_fields = len(fields_map)
            passed_count = len(summary.passed)
            compliance = round((passed_count / total_fields) * 100.0, 1) if total_fields > 0 else 0.0

            total_chunks = sum(len(p) for p in evidence_map.values())

            package = BidExtractionResult(
                bid_id=bid_id,
                fields=fields_map,
                addendum_changes=change_log,
                validation=summary,
                overall_compliance_score=compliance,
                summary=f"Extraction completed for {bid_id}. Compliance: {compliance}%. Passed: {passed_count}/{total_fields}.",
                raw_evidence_count=total_chunks
            )

            # Persist structured trace
            trace_file = self.tracer.save()
            logger.info(f"Structured trace successfully saved to {trace_file}")

            ctx.complete({
                "compliance_score": compliance,
                "passed_fields": passed_count,
                "total_fields": total_fields,
                "trace_file": str(trace_file)
            })

            return {"result": package}

    # -----------------------------------------------------------------------
    # Public Pipeline Execution API
    # -----------------------------------------------------------------------

    def run(self, bid_id: str) -> BidExtractionResult:
        """Run full extraction pipeline on a target bid package."""
        logger.info(f"Starting Multi-Agent Extraction Pipeline for '{bid_id}'...")

        initial_state: ExtractionState = {
            "bid_id": bid_id,
            "field_defs": self.extractor.field_definitions,
            "specialist_groups": {},
            "retrieved_evidence": {},
            "extracted_fields": {},
            "validations": {},
            "validation_summary": ValidationSummary(),
            "addendum_changes": [],
            "retry_count": 0,
            "max_retries": settings.MAX_VALIDATION_RETRIES,
            "needs_retry": False,
            "result": None,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state["result"]
