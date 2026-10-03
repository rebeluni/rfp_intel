"""
Multi-Agent Extraction Engine (Phase 3).
"""

from extraction.models import (
    FieldSource,
    FieldEvidence,
    FieldOutput,
    ExtractedField,
    AddendumChange,
    ValidationSummary,
    FieldValidation,
    BidExtractionResult,
    CrossBidComparison,
)
from extraction.llm_client import get_llm_client
from extraction.extractor_agent import ExtractorAgent
from extraction.validator_agent import ValidatorAgent
from extraction.reconciliation_agent import ReconciliationAgent
from extraction.synthesis_agent import SynthesisAgent
from extraction.graph import ExtractionPipeline
from extraction.tracer import StructuredTracer

__all__ = [
    "FieldSource",
    "FieldEvidence",
    "FieldOutput",
    "ExtractedField",
    "AddendumChange",
    "ValidationSummary",
    "FieldValidation",
    "BidExtractionResult",
    "CrossBidComparison",
    "get_llm_client",
    "ExtractorAgent",
    "ValidatorAgent",
    "ReconciliationAgent",
    "SynthesisAgent",
    "ExtractionPipeline",
    "StructuredTracer",
]
