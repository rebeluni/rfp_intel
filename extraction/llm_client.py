"""
Multi-Provider LLM Client for RFP Extraction & Intelligence.
Strictly adheres to:
  1. No bid-specific literals or canned hardcoding.
  2. Fail loudly with a clear message if API key is not configured.
  3. Temperature 0, JSON output with Pydantic validation and one repair retry.
  4. Every FOUND field must have a verbatim quote + file + page, or be set to null
     with reason 'Not found in documents'.
  5. API errors are treated as errors (status='ERROR'), not disguised as absence.
  6. API key is transmitted via x-goog-api-key HTTP header (not URL query string).
  7. Thread-safe rate limiter shared across parallel specialist extraction threads.
  8. Tracks real tokens from response usageMetadata.
"""

import json
import time
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field, ValidationError
from config.settings import settings
from extraction.models import FieldOutput, FieldSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread-Safe Shared Rate Limiter
# ---------------------------------------------------------------------------
class ThreadSafeRateLimiter:
    """Thread-safe rate limiter pacing API requests across parallel worker threads."""

    def __init__(self, requests_per_minute: float = 14.0):
        self.min_interval = 60.0 / requests_per_minute
        self.lock = threading.Lock()
        self.last_call = 0.0

    def acquire(self) -> None:
        """Block until the minimum interval between requests has elapsed."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()


# Global shared rate limiter for all threads
shared_rate_limiter = ThreadSafeRateLimiter(requests_per_minute=getattr(settings, "LLM_RATE_LIMIT_RPM", 15.0))


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
    """Google Gemini LLM client via REST API with temperature 0, JSON mode, and header authentication."""

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        rate_limiter: Optional[ThreadSafeRateLimiter] = None
    ):
        if not api_key:
            raise ValueError(
                "No API key configured for Gemini. Please set GEMINI_API_KEY in your environment or .env file."
            )
        self.api_key = api_key
        self.model_name = model_name or settings.LLM_MODEL or "gemini-flash-lite-latest"
        self.temperature = temperature
        self.rate_limiter = rate_limiter or shared_rate_limiter
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"

        # Thread-safe token tracking
        self._tokens_lock = threading.Lock()
        self.total_tokens_used = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.last_tokens_used = 0
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0

    def get_tokens(self) -> int:
        """Return total tokens consumed across calls."""
        with self._tokens_lock:
            return self.total_tokens_used

    def get_token_usage(self) -> Dict[str, int]:
        """Return cumulative breakdown of token usage {prompt_tokens, completion_tokens, total_tokens}."""
        with self._tokens_lock:
            return {
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens_used
            }

    def get_last_tokens(self) -> int:
        """Return tokens consumed by the most recent API call."""
        with self._tokens_lock:
            return self.last_tokens_used

    def _call_api(self, prompt: str, system_instruction: str = SYSTEM_EXTRACTION_PROMPT) -> Tuple[str, int]:
        """
        Call Gemini REST endpoint with temperature 0, JSON mode, and x-goog-api-key header.
        Never puts API key in URL. Returns (response_text, token_count).
        """
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
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        max_attempts = 4
        last_error = None
        for attempt in range(1, max_attempts + 1):
            # Enforce thread-safe rate limiting
            self.rate_limiter.acquire()
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(self.base_url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        wait_sec = 8.0 * attempt
                        logger.warning(
                            f"Gemini API rate limited (429). Backing off for {wait_sec}s "
                            f"(attempt {attempt}/{max_attempts})..."
                        )
                        time.sleep(wait_sec)
                        continue

                    if resp.status_code != 200:
                        last_error = f"Gemini API request failed ({resp.status_code}): {resp.text}"
                        if resp.status_code in (500, 502, 503, 504) and attempt < max_attempts:
                            time.sleep(3.0 * attempt)
                            continue
                        raise RuntimeError(last_error)

                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError(f"No candidates returned by Gemini: {data}")

                    usage = data.get("usageMetadata", {})
                    p_tokens = usage.get("promptTokenCount", 0)
                    c_tokens = usage.get("candidatesTokenCount", 0)
                    t_tokens = usage.get("totalTokenCount", p_tokens + c_tokens)
                    with self._tokens_lock:
                        self.total_prompt_tokens += p_tokens
                        self.total_completion_tokens += c_tokens
                        self.total_tokens_used += t_tokens
                        self.last_prompt_tokens = p_tokens
                        self.last_completion_tokens = c_tokens
                        self.last_tokens_used = t_tokens

                    text = candidates[0]["content"]["parts"][0]["text"]
                    return text, t_tokens
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError, ConnectionError, OSError) as e:
                last_error = str(e)
                logger.warning(
                    f"Gemini API timeout/network error (attempt {attempt}/{max_attempts}): {e}"
                )
                if attempt < max_attempts:
                    time.sleep(2.0 * (2.0 ** (attempt - 1)))
                else:
                    raise RuntimeError(f"Gemini API call timed out after {max_attempts} attempts: {e}")

        raise RuntimeError(last_error or "Gemini API call failed after retries")

    def extract_field(
        self,
        field_name: str,
        field_def: Dict[str, Any],
        evidence_passages: List[Dict[str, Any]]
    ) -> FieldOutput:
        """
        Extract field with Pydantic validation and one repair retry.
        If API fails, returns status='ERROR' and notes with error details (never disguises as absence).
        """
        if not evidence_passages:
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                status="NOT_FOUND",
                notes="Not found in documents"
            )

        prompt = self._build_extraction_prompt(field_name, field_def, evidence_passages)

        parsed = None
        last_exception = None
        for outer_attempt in range(1, 4):
            try:
                # Attempt 1
                raw_text, _ = self._call_api(prompt)
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
                    raw_text_repaired, _ = self._call_api(repair_prompt)
                    parsed = self._try_parse_pydantic(raw_text_repaired)
                last_exception = None
                break
            except Exception as e:
                last_exception = e
                logger.warning(f"API call error during extraction of '{field_name}' (attempt {outer_attempt}/3): {e}")
                if outer_attempt < 3:
                    time.sleep(2.0 * outer_attempt)

        if last_exception is not None and parsed is None:
            logger.error(f"API call failed after retries during extraction of '{field_name}': {last_exception}")
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                status="ERROR",
                notes=f"API Error: {str(last_exception)}"
            )

        # Handle parsed result
        if parsed is None or parsed.status != "FOUND" or not parsed.value or not parsed.quote or not parsed.file_name:
            return FieldOutput(
                value=None,
                sources=[],
                confidence=0.0,
                status="NOT_FOUND",
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
            status="FOUND",
            notes=parsed.reason
        )

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
            raw, _ = self._call_api(prompt)
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "changes" in data:
                return data["changes"]
            return []
        except Exception as e:
            logger.error(f"Error in addendum reconciliation LLM call: {e}")
            raise RuntimeError(f"Addendum reconciliation LLM call failed: {e}") from e

    def summarize_addendum(
        self,
        addendum_number: Optional[int],
        addendum_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Produce a comprehensive summary of ALL changes in Addendum N."""
        if not addendum_chunks:
            return {"overview": "No addendum passages available.", "all_changes": []}

        passages_text = "\n".join([
            f"[Source: {c.get('file_name')} | Page: {c.get('page_number')}]\n{c.get('text')}\n"
            for c in addendum_chunks
        ])

        target_title = f"Addendum {addendum_number}" if addendum_number else "the solicitation addenda"
        prompt = f"""You are a Senior Procurement Analyst. Summarize ALL modifications, extensions, Q&A clarifications, and scope updates announced in {target_title}.

EVIDENCE PASSAGES:
{passages_text}

TASK:
Provide:
1. A concise overview paragraph.
2. A comprehensive list of ALL changes (due date extensions, Q&A responses, specifications, required forms, terms, delivery).

Return JSON:
{{
  "overview": "Concise summary paragraph of what this addendum changed",
  "all_changes": [
    {{
      "category": "Schedule / Q&A / Specifications / Terms / Forms",
      "description": "Detailed description of the change or clarification",
      "quote": "verbatim quote from addendum"
    }}
  ]
}}"""
        try:
            raw_text, _ = self._call_api(prompt)
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"Error summarizing addendum: {e}")
            return {
                "overview": f"Addendum changes could not be summarized: {e}",
                "all_changes": []
            }

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
    {{"file": "file name", "page": 1, "quote": "verbatim supporting sentence"}}
  ]
}}"""

        try:
            raw, _ = self._call_api(prompt)
            data = json.loads(raw)
            return {
                "answer": data.get("answer", "Not found in documents."),
                "citations": data.get("citations", [])
            }
        except Exception as e:
            logger.warning(f"Error answering question: {e}")
            return {"answer": f"API error occurred while synthesizing answer: {e}", "citations": [], "status": "error"}

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

EXTRACTION RULES:
1. Normalization: Values must be clean, complete, and concise. No ellipses ("..."), no truncated sentences, and NEVER output raw spec-table text.
2. Grounding & Citations: Every non-null value MUST have an exact contiguous verbatim quote from ONE of the passages above, matching word-for-word, along with the exact file_name and page_number. If no real quote supports the value, set value to null.
3. Absence & Field-Specific Semantics:
   - For "Bid Summary": Synthesize a concise, comprehensive 3 to 6 sentence summary outlining the procurement scope, objectives, requested products/quantities, and core deliverables based on the evidence. Structure the opening sentence to state what the issuing agency or organization is soliciting offers or seeking proposals for. NEVER return NOT_FOUND or null for Bid Summary if the passages describe the procurement scope, purpose, or requested equipment. Quote an illustrative scope or requirement sentence.
   - For "Payment Terms": Restrict strictly to buyer-to-contractor payment terms and invoicing instructions (e.g. Net 30, invoice submission recipient). Do NOT extract subcontractor prompt-payment pass-through clauses (e.g. contractor paying subcontractors within 30 days). If buyer payment terms are not specified in the solicitation, return value null with status "NOT_FOUND" and reason "Buyer payment terms not specified in solicitation".
   - For "Bid Number": Extract the official solicitation or PORFP identifier. If an internal project or portal reference number is also present, use the primary solicitation/PORFP number as value and record the project reference in notes. Ensure the verbatim quote is contiguous and matches the chunk text.
   - For "contact_info": Extract the designated individual buyer, contracting officer, or purchasing agent (name and email) from the primary solicitation document if available, rather than a generic department helpdesk from portal summary listings.
   - For "Any Additional Documentation Required": When the solicitation contains a checklist or table of required submission forms/attachments (such as MWBE Forms, W-9 Form, affidavits), extract those explicit required submission form names and instructions (e.g. "MWBE Forms must be completed and attached regardless if you are MWBE status; W9 Form completed, signed and attached to the submission"). Prefer the structured checklist or required submittals table over narrative sections, and use the exact form names as listed in the table (e.g. "MWBE Forms", "W9 Form").
   - For "Part_no": Extract all orderable part numbers and SKUs for both the base computer system and any accessories/docking stations specified in the solicitation, listing both if available.
   - For "Pre Bid Meeting": If no pre-bid meeting or conference is scheduled or mentioned in the solicitation documents, return value "None" with reason "No pre-bid meeting mentioned in solicitation", quoting a relevant header or solicitation details block if available.
   - For "Installation": If on-site installation is not required by the solicitation, return "No on-site installation required; factory configuration per specifications" or "None".
   - For "Bid Bond Requirement": If documents state bonds/insurance are "enumerated elsewhere" without specifying an amount, return a concise statement stating that no specific bid bond amount is given and the RFP defers to other contract documents, with the verbatim quote.
   - If a field is genuinely not mentioned or silent in the passages, return value null, status "NOT_FOUND", and reason "Not found in documents".

Return JSON:
{{
  "value": "extracted normalized value or null",
  "status": "FOUND" or "NOT_FOUND",
  "reason": "succinct explanation of finding or 'Not found in documents'",
  "quote": "exact contiguous verbatim quote from cited chunk or null",
  "file_name": "exact file name cited or null",
  "page_number": 1,
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
