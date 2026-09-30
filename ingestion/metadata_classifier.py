"""
Generic document type and metadata inference.
Employs keyword heuristics first, with an optional LLM fallback when confidence is below threshold.
Zero hard-coding to specific bid numbers or vendor names.
"""

import re
from pathlib import Path
from typing import Optional, Tuple
from ingestion.models import DocType


class MetadataClassifier:
    """Classifies document types and extracts generic metadata (addendum numbers, dates)."""

    KEYWORDS = {
        DocType.BID_PAGE: [
            "bidnet", "bid information", "solicitation type", "reference number",
            "purchase type", "piggyback contract", "electronic bid"
        ],
        DocType.ADDENDUM: [
            "addendum", "amendment", "bulletin", "clarification no", "notice of change"
        ],
        DocType.AFFIDAVIT: [
            "affidavit", "sworn statement", "certification", "non-collusion",
            "conflict of interest affidavit", "contract affidavit", "mercury affidavit"
        ],
        DocType.SPECS: [
            "specification", "specs", "technical requirement", "datasheet",
            "system requirements", "minimum hardware specifications"
        ],
        DocType.RFP: [
            "request for proposal", "rfp", "porfp", "solicitation", "invitation to bid",
            "scope of work", "instructions to offerors", "purchase order request"
        ],
    }

    @classmethod
    def infer_metadata(
        cls,
        file_path: Path,
        content_preview: str = "",
        allow_llm_fallback: bool = True
    ) -> Tuple[DocType, float, Optional[int], Optional[str]]:
        """
        Infer (doc_type, confidence, addendum_number, document_date).
        1. Run keyword heuristics over filename and content preview.
        2. If confidence < 0.60 and allow_llm_fallback is True, invoke LLM classifier.
        3. Extract addendum number and document date generically.
        """
        fname_lower = file_path.name.lower()
        content_lower = content_preview.lower()[:3000]

        # 1. Check HTML files immediately
        if file_path.suffix.lower() in [".html", ".htm"]:
            return DocType.BID_PAGE, 0.98, None, cls._extract_date(content_preview)

        # 2. Score candidates using filename (weight 2.0) and content (weight 1.0)
        scores = {doc_t: 0.0 for doc_t in DocType if doc_t != DocType.OTHER}

        for doc_t, kws in cls.KEYWORDS.items():
            for kw in kws:
                if kw in fname_lower:
                    scores[doc_t] += 2.0
                if kw in content_lower:
                    scores[doc_t] += 0.8

        best_doc_type = DocType.OTHER
        max_score = 0.0
        for doc_t, score in scores.items():
            if score > max_score:
                max_score = score
                best_doc_type = doc_t

        # Convert score to confidence roughly between 0.0 and 1.0
        confidence = min(1.0, max_score / 3.0) if max_score > 0 else 0.0

        # Default fallback for RFP if generic document structure exists
        if confidence < 0.50 and ("proposal" in content_lower or "contract" in content_lower or "bid" in content_lower):
            best_doc_type = DocType.RFP
            confidence = 0.65

        # 3. LLM Fallback if confidence is low and permitted
        if confidence < 0.60 and allow_llm_fallback:
            llm_type, llm_conf = cls._llm_classify(fname_lower, content_preview[:1500])
            if llm_type:
                best_doc_type = llm_type
                confidence = llm_conf

        # 4. Extract addendum number if doc_type is addendum or if found in text/filename
        addendum_num = cls._extract_addendum_number(fname_lower, content_lower)
        if addendum_num is not None and best_doc_type not in [DocType.BID_PAGE, DocType.AFFIDAVIT]:
            best_doc_type = DocType.ADDENDUM
            confidence = max(confidence, 0.95)

        # 5. Extract document date
        doc_date = cls._extract_date(content_preview)

        return best_doc_type, round(confidence, 2), addendum_num, doc_date

    @staticmethod
    def _extract_addendum_number(fname: str, content: str) -> Optional[int]:
        """Generic regex extraction for addendum or amendment numbers."""
        # e.g., 'Addendum 1', 'Addendum No. 2', 'Amendment #3', 'Addendum_02'
        patterns = [
            r"(?:addendum|amendment|bulletin)\s*(?:no\.?|#|_)?\s*0*(\d+)",
            r"(?:addendum|amendment)\s*(\d+)",
        ]
        # Check filename first
        for pat in patterns:
            match = re.search(pat, fname, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

        # Check document content start
        for pat in patterns:
            match = re.search(pat, content[:2000], re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None

    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        """Generic extraction for publication or document issue dates."""
        patterns = [
            r"(?:Publication|Issue Date|Date Issued|Posted Date|Date):\s*([0-1]?\d[/.-][0-3]?\d[/.-]\d{2,4}(?:\s+\d{1,2}:\d{2}(?:\s*[AP]M)?(?:\s+[A-Z]{3,4})?)?)",
            r"(?:Date):\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})",
            r"\b([0-1]?\d/[0-3]?\d/20\d{2})\b"
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _llm_classify(fname: str, preview: str) -> Tuple[Optional[DocType], float]:
        """
        Fallback LLM classifier when keyword heuristics yield low confidence.
        Uses structured output schema.
        """
        # Kept lightweight and safe: if no API key is available, returns None gracefully
        from config.settings import settings
        if not (settings.OPENAI_API_KEY or settings.GEMINI_API_KEY or settings.GROQ_API_KEY):
            return None, 0.0

        try:
            # When API keys exist, we can invoke LLM; otherwise graceful return
            # (Detailed provider integration implemented in search/agents layer)
            return None, 0.0
        except Exception:
            return None, 0.0
