"""
Addendum Reconciliation Agent (Phase 3).
Strictly implements Item 3:
  1. Retrieve doc_type=addendum chunks for the target bid package.
  2. Order chunks chronologically by addendum number (1, 2, ...).
  3. Prompt LLM to compare against base value for ALL fields.
  4. Produce a full change log (field, old_value, new_value, source, reason).
  5. Update field values, sources, and notes accordingly (e.g. Due Date -> 'July 9, 2024 2:00 PM CST').
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from extraction.models import AddendumChange, FieldOutput, FieldSource
from extraction.llm_client import GeminiClient, get_llm_client
from search.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


class ReconciliationAgent:
    """Agent that performs explicit addendum supersession and reconciliation."""

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        llm_client: Optional[GeminiClient] = None
    ):
        self.retriever = retriever or HybridRetriever()
        self.llm_client = llm_client or get_llm_client()

    def get_addendum_chunks(self, bid_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all addendum chunks for a bid, ordered by addendum number.
        """
        raw_chunks = []
        if hasattr(self.retriever, "bm25_index") and self.retriever.bm25_index.chunks:
            for chk in self.retriever.bm25_index.chunks:
                meta = chk.metadata
                if meta.bid_id == bid_id or not bid_id:
                    is_addendum = (
                        (hasattr(meta.doc_type, "value") and meta.doc_type.value == "addendum")
                        or meta.doc_type == "addendum"
                        or "addendum" in meta.file_name.lower()
                    )
                    if is_addendum:
                        add_num = meta.addendum_number
                        if add_num is None:
                            # Parse addendum number from file name or text
                            m = re.search(r"addendum\s*(?:no\.?|#)?\s*(\d+)", meta.file_name, re.IGNORECASE)
                            add_num = int(m.group(1)) if m else 1

                        raw_chunks.append({
                            "chunk_id": chk.chunk_id,
                            "file_name": meta.file_name,
                            "page_number": meta.page_number,
                            "addendum_number": add_num,
                            "text": chk.text,
                            "score": 1.0,
                        })

        # Order chronologically by addendum number, then page number
        raw_chunks.sort(key=lambda c: (c.get("addendum_number", 999), c.get("page_number", 1)))
        return raw_chunks

    def reconcile_fields(
        self,
        bid_id: str,
        fields_map: Dict[str, FieldOutput],
        addendum_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Dict[str, FieldOutput], List[AddendumChange]]:
        """
        Reconcile all fields against the addenda passages and build full change log.
        """
        if addendum_chunks is None:
            addendum_chunks = self.get_addendum_chunks(bid_id)

        if not addendum_chunks:
            logger.info(f"No addenda detected for bid '{bid_id}'. Skipping addendum reconciliation.")
            return fields_map, []

        logger.info(
            f"Reconciling {len(fields_map)} fields against {len(addendum_chunks)} "
            f"addendum chunks for '{bid_id}'..."
        )

        change_log: List[AddendumChange] = []
        updated_fields = dict(fields_map)

        base_fields = {
            k: str(v.value) if v.value is not None else None
            for k, v in fields_map.items()
        }

        # Check if llm_client has reconcile_all_addenda
        if hasattr(self.llm_client, "reconcile_all_addenda"):
            raw_changes = self.llm_client.reconcile_all_addenda(base_fields, addendum_chunks)
            for item in raw_changes:
                field_name = item.get("field")
                if not field_name or field_name not in updated_fields:
                    # Case-insensitive lookup fallback
                    matching = [k for k in updated_fields if k.lower() == field_name.lower()]
                    if matching:
                        field_name = matching[0]
                    else:
                        continue

                new_val = item.get("new_value")
                quote = item.get("quote")
                file_name = item.get("file_name") or "Addendum"
                page_no = item.get("page_number") or 1
                reason = item.get("reason") or "Amended by addendum"

                if new_val:
                    logger.info(
                        f"[Reconciliation] Field '{field_name}' amended by addendum: "
                        f"'{updated_fields[field_name].value}' -> '{new_val}'"
                    )
                    source = FieldSource(
                        file=file_name,
                        page=int(page_no) if str(page_no).isdigit() else 1,
                        quote=quote
                    )
                    change = AddendumChange(
                        field=field_name,
                        old_value=str(updated_fields[field_name].value) if updated_fields[field_name].value is not None else None,
                        new_value=new_val,
                        source=source,
                        reason=reason
                    )
                    change_log.append(change)

                    updated_fields[field_name] = FieldOutput(
                        value=new_val,
                        sources=[source] + [s for s in updated_fields[field_name].sources if s.file != source.file],
                        confidence=0.95,
                        notes=f"Amended by {file_name}: {reason}".strip(),
                        status="FOUND",
                        specialist=updated_fields[field_name].specialist
                    )
        else:
            # Fallback to per-field
            for field_name, current_output in fields_map.items():
                base_val = current_output.value
                comparison = self.llm_client.reconcile_addendum_for_field(
                    field_name=field_name,
                    base_value=str(base_val) if base_val is not None else None,
                    addendum_chunks=addendum_chunks
                )
                if comparison and comparison.is_modified and comparison.new_value:
                    source = FieldSource(
                        file=comparison.file_name or "Addendum",
                        page=comparison.page_number or 1,
                        quote=comparison.quote,
                    )
                    change = AddendumChange(
                        field=field_name,
                        old_value=str(base_val) if base_val is not None else None,
                        new_value=comparison.new_value,
                        source=source,
                        reason=comparison.reason or "Amended by addendum"
                    )
                    change_log.append(change)
                    updated_fields[field_name] = FieldOutput(
                        value=comparison.new_value,
                        sources=[source] + [s for s in current_output.sources if s.file != source.file],
                        confidence=0.95,
                        notes=f"Amended by {comparison.file_name}: {comparison.reason or ''}".strip(),
                        status="FOUND",
                        specialist=current_output.specialist
                    )

        return updated_fields, change_log
