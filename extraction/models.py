"""
Data models for Multi-Agent Extraction Engine (Phase 3).
Defines schemas for field extractions, evidence citations, validations, and cross-bid comparisons.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FieldEvidence(BaseModel):
    """Verbatim evidence citation supporting an extracted value."""
    file_name: str = Field(description="Source file name containing the evidence")
    page_number: int = Field(description="Physical page number in the source document")
    chunk_id: str = Field(description="Unique ID of the document chunk")
    quote: str = Field(description="Exact verbatim quote from the source text")
    relevance_score: Optional[float] = Field(default=None, description="Retrieval or confidence score")

    def format_citation(self) -> str:
        return f"[{self.file_name} (p.{self.page_number})]: \"{self.quote.strip()}\""


class ExtractedField(BaseModel):
    """Extracted field value with metadata and citations."""
    field_name: str = Field(description="Standardized name of the field from fields.yaml")
    value: Optional[Any] = Field(default=None, description="Extracted value, or null if NOT_FOUND")
    status: str = Field(default="FOUND", description="'FOUND', 'NOT_FOUND', or 'AMBIGUOUS'")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    evidence: List[FieldEvidence] = Field(default_factory=list, description="List of evidence citations")
    notes: Optional[str] = Field(default=None, description="Extraction or context notes")
    specialist: Optional[str] = Field(default=None, description="Assigned specialist category")


class FieldValidation(BaseModel):
    """Validation report for an extracted field."""
    field_name: str
    is_valid: bool = Field(description="True if extraction is grounded and passes checks")
    is_grounded: bool = Field(description="True if verbatim quote is found in retrieved source text")
    has_addendum_conflict: bool = Field(default=False, description="True if addendum overrides original RFP value")
    issue_type: Optional[str] = Field(default=None, description="Type of validation issue if any")
    feedback: str = Field(default="", description="Detailed validation explanation")
    suggested_value: Optional[Any] = Field(default=None, description="Corrected value if validation detected conflict")


class BidExtractionResult(BaseModel):
    """Complete extraction result for a single bid package."""
    bid_id: str = Field(description="Bid package identifier (e.g. 'Bid1', 'Bid2')")
    fields: Dict[str, ExtractedField] = Field(description="Extracted fields dictionary keyed by field_name")
    validations: Dict[str, FieldValidation] = Field(default_factory=dict, description="Per-field validation results")
    overall_compliance_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Completeness & compliance %")
    summary: Optional[str] = Field(default=None, description="Executive summary of the bid")
    raw_evidence_count: int = Field(default=0, description="Total chunks retrieved during extraction")


class ComparisonRow(BaseModel):
    """Single row comparing a field across multiple bids."""
    field_name: str
    category: str
    values: Dict[str, Optional[str]] = Field(description="Map of bid_id -> formatted value string")
    difference_summary: str = Field(description="Brief summary of differences across bids")


class CrossBidComparison(BaseModel):
    """Comprehensive comparative analysis between bids."""
    bids: List[str]
    matrix: List[ComparisonRow]
    risk_analysis: Dict[str, List[str]] = Field(description="Map of bid_id -> list of identified operational/legal risks")
    viability_scores: Dict[str, float] = Field(description="Map of bid_id -> viability score 0-100")
    recommendations: Dict[str, str] = Field(description="Map of bid_id -> strategic recommendation")
