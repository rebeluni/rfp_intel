"""
Data models for Multi-Agent Extraction Engine (Phase 3).
Strictly matches Section 8.1 of the RFP Intelligence specification:
  - fields: Dict[str, FieldOutput] where FieldOutput has value, sources [{file, page}], confidence, notes
  - addendum_changes: List[AddendumChange] (field, old_value, new_value, source, reason)
  - validation: ValidationSummary (passed: List[str], failed: List[str], not_found: List[str])
No field may have empty sources unless null.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FieldSource(BaseModel):
    """Citation source matching Section 8.1: file, page, and chunk quote verification."""
    file: str = Field(description="Source file name containing the evidence")
    page: int = Field(description="Physical page number in the source document")
    quote: Optional[str] = Field(default=None, description="Exact contiguous verbatim quote from the cited chunk")
    chunk_id: Optional[str] = Field(default=None, description="Unique chunk identifier")

    def format_citation(self) -> str:
        q_str = f': "{self.quote.strip()}"' if self.quote else ""
        return f"[{self.file} (p.{self.page})]{q_str}"


# Backwards compatibility alias
FieldEvidence = FieldSource


class FieldOutput(BaseModel):
    """Field schema matching Section 8.1: value, sources, confidence, notes."""
    value: Optional[Any] = Field(default=None, description="Extracted value, or null if NOT_FOUND")
    sources: List[FieldSource] = Field(default_factory=list, description="Verbatim citations with file and page")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence computed from retrieval + validation")
    notes: Optional[str] = Field(default=None, description="Context, addendum annotations, or absence explanation")
    status: Optional[str] = Field(default=None, description="'FOUND', 'NOT_FOUND', or 'ERROR'")
    specialist: Optional[str] = Field(default=None, description="Assigned specialist category")


# Backwards compatibility alias
ExtractedField = FieldOutput


class AddendumChange(BaseModel):
    """Record of an amended field value caused by an addendum."""
    field: str = Field(description="Name of the amended field")
    old_value: Optional[str] = Field(default=None, description="Base value before addendum")
    new_value: str = Field(description="Amended value from addendum, preserving exact timezone and details")
    source: Optional[FieldSource] = Field(default=None, description="Citation in the addendum document")
    quote: Optional[str] = Field(default=None, description="Exact contiguous verbatim quote from the cited chunk")
    file: Optional[str] = Field(default=None, description="Source file name containing the evidence")
    page: Optional[int] = Field(default=None, description="Physical page number in the source document")
    reason: Optional[str] = Field(default=None, description="Explanation of amendment")


class AddendumSummary(BaseModel):
    """Comprehensive summary of all changes in a specific addendum."""
    bid_id: str
    addendum_number: Optional[int] = None
    file_name: str
    overview: str
    all_changes: List[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    """Validation breakdown matching Section 8.1 with error tracking."""
    passed: List[str] = Field(default_factory=list, description="Fields passing deterministic grounding & checks")
    failed: List[str] = Field(default_factory=list, description="Fields failing validation or contiguous quote check")
    not_found: List[str] = Field(default_factory=list, description="Fields confirmed absent in documents")
    errors: List[str] = Field(default_factory=list, description="Fields that failed due to API / provider errors")


class FieldValidation(BaseModel):
    """Detailed per-field validation result."""
    field_name: str
    is_valid: bool = Field(description="True if extraction is grounded and passes checks")
    is_grounded: bool = Field(description="True if verbatim quote is found in retrieved source text")
    has_addendum_conflict: bool = Field(default=False, description="True if addendum overrides original RFP value")
    issue_type: Optional[str] = Field(default=None, description="Type of validation issue if any")
    feedback: str = Field(default="", description="Detailed validation explanation")
    suggested_value: Optional[Any] = Field(default=None, description="Corrected value if validation detected conflict")


class BidExtractionResult(BaseModel):
    """Complete extraction package matching Section 8.1 format."""
    bid_id: str = Field(description="Bid package identifier (e.g. 'Bid1', 'Bid2')")
    fields: Dict[str, FieldOutput] = Field(description="Extracted fields dictionary keyed by field_name")
    addendum_changes: List[AddendumChange] = Field(default_factory=list, description="Full addendum change log")
    validation: ValidationSummary = Field(default_factory=ValidationSummary, description="Validation summary")
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
