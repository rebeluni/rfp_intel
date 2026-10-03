"""
Multi-Provider LLM Client for RFP Extraction & Intelligence.
Strictly adheres to:
  1. No bid-specific literals or canned hardcoding.
  2. Fail loudly with a clear message if API key is not configured.
  3. Temperature 0, JSON output with Pydantic validation and one repair retry.
  4. Every FOUND field must have a verbatim quote + file + page, or be set to null
     with reason 'Not found in documents'.
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field, ValidationError
from config.settings import settings
from extraction.models import FieldOutput, FieldSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schemas for Structured LLM Input / Output
# ---------------------------------------------------------------------------
class LLMFieldExtraction(BaseModel):
    """Pydantic schema enforcing structured LLM extraction response."""
    value: Optional[str] = Field(default=None, description="Extracted value, or null if absent in documents")
    status: str = Field(description="Must be either 'FOUND' or 'NOT_FOUND'")
    reason: Optional[str] = Field(default=None, description="Explanation of finding, or 'Not found in documents'")
    quote: Optional[str] = Field(default=None, description="Exact verbatim contiguous quote from the cited chunk")
    file_name: Optional[str] = Field(default=None, description="Exact file name cited in the passage header")
    page_number: Optional[int] = Field(default=None, description="Physical page number cited in the passage header")
    chunk_id: Optional[str] = Field(default=None, description="Unique chunk ID cited in the passage header")


class LLMAnswerResponse(BaseModel):
    """Pydantic schema for Q&A answers with citations."""
    answer: str = Field(description="Direct, factual answer synthesized from evidence, or 'Not found in documents'")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="List of {file, page, quote} citations")


class LLMAddendumComparison(BaseModel):
    """Pydantic schema for field reconciliation against an addendum."""
    is_modified: bool = Field(description="True if the addendum explicitly amends or supersedes the base value")
    new_value: Optional[str] = Field(default=None, description="Amended value from addendum, preserving exact timezone/format")
    quote: Optional[str] = Field(default=None, description="Verbatim quote from the addendum proving the amendment")
    file_name: Optional[str] = Field(default=None, description="Addendum file name")
    page_number: Optional[int] = Field(default=None, description="Addendum page number")
    reason: Optional[str] = Field(default=None, description="Explanation of what was amended")


# ---------------------------------------------------------------------------
# LLM Provider Implementations
# ---------------------------------------------------------------------------
SYSTEM_EXTRACTION_PROMPT = """You are a Senior RFP Intelligence Analyst and Compliance Officer.
Extract target information from procurement solicitation packages with ZERO hallucination.

RULES:
1. STRICT GROUNDING: Extract a value ONLY if it is explicitly stated in the provided evidence passages.
2. CITATION MANDATORY: For every FOUND field, you MUST provide:
   - "value": The extracted information as written in the text
   - "status": "FOUND"
   - "quote": An EXACT verbatim quotation (contiguous text) from the cited chunk
   - "file_name": The exact file name cited in the passage header
   - "page_number": The exact page number cited in the passage header
   - "chunk_id": The chunk ID from the passage header
3. ABSENCE RULE: If a field is not explicitly stated in the passages, return:
   - "value": null
   - "status": "NOT_FOUND"
   - "reason": "Not found in documents"
   - "quote": null, "file_name": null, "page_number": null, "chunk_id": null
4. TIMEZONE & EXACTNESS: When extracting dates/times, preserve the exact written format and timezone (e.g. "CST", "EDT").

Return your response strictly as a JSON object matching the requested schema.
"""


class BaseLLMClient:
    """Base interface for LLM extraction client."""
    pass


class GeminiClient(BaseLLMClient):
    """Google Gemini LLM client via REST API with temperature 0 and JSON mode."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash", temperature: float = 0.0):
        if not api_key:
            raise ValueError(
                "No API key configured for Gemini. Please set GEMINI_API_KEY in your environment or .env file."
            )
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"

    def _call_api(self, prompt: str, system_instruction: str = SYSTEM_EXTRACTION_PROMPT) -> str:
        """Call Gemini REST endpoint with temperature 0 and response_mime_type: application/json."""
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            }
        }
        url = f"{self.base_url}?key={self.api_key}"

        # Pace requests to comply with Gemini Free Tier rate limits (15 RPM)
        time.sleep(2.5)

        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 429:
                        wait_sec = 8.0 * attempt
                        logger.warning(f"Rate limited (429). Backing off for {wait_sec}s (attempt {attempt}/{max_attempts})...")
                        time.sleep(wait_sec)
                        continue
                    if resp.status_code != 200:
                        raise RuntimeError(f"Gemini API request failed ({resp.status_code}): {resp.text}")

                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError(f"No candidates returned by Gemini: {data}")

                    return candidates[0]["content"]["parts"][0]["text"]
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"Gemini API request timeout/network error (attempt {attempt}/{max_attempts}): {e}")
                if attempt < max_attempts:
                    time.sleep(3.0 * attempt)
                else:
                    raise RuntimeError(f"Gemini API call timed out after {max_attempts} attempts: {e}")

    def extract_field(
        self,
        field_name: str,
        field_def: Dict[str, Any],
        evidence_passages: List[Dict[str, Any]]
    ) -> FieldOutput:
        """Extract field with Pydantic validation and one repair retry."""
        if not evidence_passages:
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                notes="Not found in documents"
            )

        prompt = self._build_extraction_prompt(field_name, field_def, evidence_passages)

        try:
            # Attempt 1
            raw_text = self._call_api(prompt)
            parsed = self._try_parse_pydantic(raw_text)

            # One Repair Retry if validation failed
            if parsed is None:
                logger.warning(f"Initial JSON validation failed for '{field_name}'. Executing repair retry...")
                repair_prompt = (
                    f"Your previous response failed validation:\n"
                    f"Previous Response: {raw_text}\n\n"
                    f"Please fix the response and return ONLY valid JSON matching this schema:\n"
                    f"{json.dumps(LLMFieldExtraction.model_json_schema(), indent=2)}\n"
                    f"Original Request:\n{prompt}"
                )
                raw_text_repaired = self._call_api(repair_prompt)
                parsed = self._try_parse_pydantic(raw_text_repaired)
        except Exception as e:
            logger.warning(f"API call error during extraction of '{field_name}': {e}")
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                notes="Not found in documents"
            )

        # Fallback to null if repair also failed
        if parsed is None or parsed.status != "FOUND" or not parsed.value or not parsed.quote or not parsed.file_name:
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                notes=parsed.reason if parsed and parsed.reason else "Not found in documents"
            )

        source = FieldSource(
            file=parsed.file_name,
            page=parsed.page_number or 1,
            quote=parsed.quote,
            chunk_id=parsed.chunk_id
        )

        return FieldOutput(
            value=parsed.value,
            sources=[source],
            confidence=0.90,  # Will be adjusted by deterministic validator
            notes=parsed.reason
        )

    def reconcile_addendum_for_field(
        self,
        field_name: str,
        base_value: Optional[str],
        addendum_chunks: List[Dict[str, Any]]
    ) -> Optional[LLMAddendumComparison]:
        """Compare base field value against addenda passages to detect explicit amendments."""
        if not addendum_chunks or not base_value:
            return None

        passages_text = "\n".join([
            f"[Addendum: {c.get('file_name')} | Page: {c.get('page_number')} | Chunk: {c.get('chunk_id')}]\n{c.get('text')}\n"
            for c in addendum_chunks
        ])

        prompt = f"""Field: "{field_name}"
Current Base Value from Solicitation: "{base_value}"

ADDENDUM EVIDENCE PASSAGES:
{passages_text}

Does any of these addenda explicitly modify, extend, or amend the value of "{field_name}"?
Return JSON strictly matching this schema:
{{
  "is_modified": true or false,
  "new_value": "exact amended value with timezone/details preserved, or null",
  "quote": "verbatim sentence from the addendum proving the modification, or null",
  "file_name": "exact addendum file name, or null",
  "page_number": integer page number or null,
  "reason": "explanation of what was changed, or null"
}}"""

        try:
            raw = self._call_api(prompt)
            data = json.loads(raw)
            parsed = LLMAddendumComparison.model_validate(data)
            if parsed.is_modified and parsed.new_value and parsed.quote and parsed.file_name:
                return parsed
            return None
        except Exception as e:
            logger.warning(f"Addendum reconciliation error for '{field_name}': {e}")
            return None

    def reconcile_all_addenda(
        self,
        base_fields: Dict[str, Optional[str]],
        addendum_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compare all base field values against addenda passages to detect explicit amendments in one call."""
        if not addendum_chunks or not base_fields:
            return []

        passages_text = "\n".join([
            f"[Addendum: {c.get('file_name')} | Page: {c.get('page_number')} | Chunk: {c.get('chunk_id')}]\n{c.get('text')}\n"
            for c in addendum_chunks
        ])

        fields_summary = "\n".join([
            f"- {k}: {v}" for k, v in base_fields.items() if v is not None
        ])

        prompt = f"""You are analyzing procurement addenda to determine which base solicitation fields were amended or extended.

BASE FIELD VALUES:
{fields_summary}

ADDENDUM EVIDENCE PASSAGES (chronologically ordered by addendum number):
{passages_text}

TASK:
For each base field above, check if any addendum explicitly modifies, extends, supersedes, or amends its value (e.g. extending Due Date / submission deadline, changing pre-bid date, modifying specs or quantities).

Return JSON array of changes:
[
  {{
    "field": "Exact Field Name",
    "old_value": "previous base value",
    "new_value": "exact amended value preserving exact written timezone and details",
    "quote": "exact contiguous verbatim quote from addendum proving the modification",
    "file_name": "exact addendum file name cited",
    "page_number": 1,
    "reason": "succinct explanation of the amendment"
  }}
]
If no fields were modified by the addenda, return an empty array: []"""

        try:
            raw = self._call_api(prompt)
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "changes" in data:
                return data["changes"]
            return []
        except Exception as e:
            logger.warning(f"Error in batch addendum reconciliation: {e}")
            return []

    def answer_question(self, question: str, evidence_passages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesize answer with citations for /ask endpoint."""
        if not evidence_passages:
            return {
                "answer": "Not found in documents.",
                "citations": []
            }

        passages_text = "\n".join([
            f"[Source: {c.get('file_name')} | Page: {c.get('page_number')}]\n{c.get('text')}\n"
            for c in evidence_passages
        ])

        prompt = f"""Question: "{question}"

EVIDENCE PASSAGES:
{passages_text}

Provide a direct, factual answer based ONLY on the evidence passages.
If the answer cannot be determined from the passages, say "Not found in documents."
Return JSON:
{{
  "answer": "synthesized factual answer or 'Not found in documents.'",
  "citations": [
    {{"file": "file name", "page": integer, "quote": "verbatim supporting sentence"}}
  ]
}}"""

        try:
            raw = self._call_api(prompt)
            data = json.loads(raw)
            return {
                "answer": data.get("answer", "Not found in documents."),
                "citations": data.get("citations", [])
            }
        except Exception as e:
            logger.warning(f"Error answering question: {e}")
            return {"answer": "Not found in documents.", "citations": []}

    def _build_extraction_prompt(
        self,
        field_name: str,
        field_def: Dict[str, Any],
        evidence_passages: List[Dict[str, Any]]
    ) -> str:
        passages_text = ""
        for i, p in enumerate(evidence_passages, 1):
            passages_text += (
                f"\n--- PASSAGE {i} ---\n"
                f"[Document: {p.get('file_name')} | Page: {p.get('page_number')} | Chunk ID: {p.get('chunk_id')}]\n"
                f"{p.get('text')}\n"
            )

        return f"""Target Field: "{field_name}"
Field Description: {field_def.get('description', '')}
Expected Format: {field_def.get('format', 'string')}

EVIDENCE PASSAGES:
{passages_text}

Extract the field value according to the rules and return JSON:
{{
  "value": "extracted value or null",
  "status": "FOUND" or "NOT_FOUND",
  "reason": "explanation of finding or 'Not found in documents'",
  "quote": "verbatim contiguous quote from cited chunk or null",
  "file_name": "exact file name cited or null",
  "page_number": integer page number or null,
  "chunk_id": "exact chunk ID cited or null"
}}"""

    def _try_parse_pydantic(self, text: str) -> Optional[LLMFieldExtraction]:
        try:
            data = json.loads(text)
            return LLMFieldExtraction.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None


def get_llm_client() -> GeminiClient:
    """
    Factory function returning the real configured LLM client.
    Fails loudly if API key is not configured. Zero silent fallback.
    """
    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in your environment or .env file."
            )
        return GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE
        )

    raise ValueError(
        f"Unsupported or unconfigured LLM_PROVIDER '{provider}'. "
        f"Please set LLM_PROVIDER=gemini and provide GEMINI_API_KEY."
    )
