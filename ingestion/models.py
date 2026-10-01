"""
Data models for the Document Ingestion & Parsing layer.
Uses Pydantic for validation, strict type hints, and serialization.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocType(str, Enum):
    BID_PAGE = "bid_page"
    RFP = "rfp"
    ADDENDUM = "addendum"
    SPECS = "specs"
    AFFIDAVIT = "affidavit"
    FORM = "form"
    OTHER = "other"


class DocumentMetadata(BaseModel):
    """Metadata attached to every document chunk and page."""
    bid_id: str = Field(description="Identifier of the bid folder (e.g., Bid1, Bid2, unseen bid)")
    file_name: str = Field(description="Original name of the source file")
    file_path: str = Field(description="Relative or absolute path to the source file")
    doc_type: DocType = Field(description="Inferred document type")
    addendum_number: Optional[int] = Field(default=None, description="Numeric addendum/amendment index if applicable")
    page_number: int = Field(default=1, description="1-indexed physical page number in the original document")
    page_label: Optional[str] = Field(default=None, description="Printed page label (e.g. 'Page 3 of 5' or roman numeral)")
    document_date: Optional[str] = Field(default=None, description="Document issuance date if found")
    published_date: Optional[str] = Field(default=None, description="Publication or issuance date")
    section: Optional[str] = Field(default=None, description="Nearest section or heading title")
    is_table: bool = Field(default=False, description="Whether this chunk represents a structured table")
    table_caption: Optional[str] = Field(default=None, description="Optional caption or heading for the table")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary additional metadata")


class DocumentChunk(BaseModel):
    """An individual text/table chunk stored in search indices."""
    chunk_id: str = Field(description="Unique deterministic identifier for the chunk")
    text: str = Field(description="Normalized text content or markdown table representation with context header")
    context_header: Optional[str] = Field(default=None, description="Contextual breadcrumb header")
    metadata: DocumentMetadata = Field(description="Associated document metadata")

    def to_search_dict(self) -> Dict[str, Any]:
        """Convert chunk into a searchable payload."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "context_header": self.context_header,
            "bid_id": self.metadata.bid_id,
            "file_name": self.metadata.file_name,
            "file_path": self.metadata.file_path,
            "doc_type": self.metadata.doc_type.value,
            "addendum_number": self.metadata.addendum_number,
            "page_number": self.metadata.page_number,
            "page_label": self.metadata.page_label,
            "document_date": self.metadata.document_date or self.metadata.published_date,
            "published_date": self.metadata.published_date or self.metadata.document_date,
            "section": self.metadata.section,
            "is_table": self.metadata.is_table,
        }


class ParsedTable(BaseModel):
    """Extracted table representation."""
    page_number: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown: str = ""


class ParsedPage(BaseModel):
    """A single parsed page of a document."""
    page_number: int
    page_label: Optional[str] = None
    raw_text: str
    cleaned_text: str
    tables: List[ParsedTable] = Field(default_factory=list)
    is_scanned: bool = False
    is_blank: bool = False


class ParsedDocument(BaseModel):
    """A fully parsed document package containing pages and chunks."""
    file_name: str
    file_path: str
    bid_id: str
    doc_type: DocType
    doc_type_confidence: float = 1.0
    addendum_number: Optional[int] = None
    document_date: Optional[str] = None
    pages: List[ParsedPage] = Field(default_factory=list)
    chunks: List[DocumentChunk] = Field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)
