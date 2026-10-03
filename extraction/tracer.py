"""
Structured Execution Tracer for RFP Multi-Agent System.
Logs each step: agent, input, tool_calls, output, tokens, latency_ms.
Saves complete execution trace to outputs/sample_trace.json.
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from config.settings import settings

logger = logging.getLogger(__name__)


class ToolCallRecord(BaseModel):
    tool: str
    args: Dict[str, Any]
    output_summary: Optional[str] = None


class TraceStep(BaseModel):
    step_id: int
    timestamp: str
    agent: str
    input: Dict[str, Any]
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    output: Dict[str, Any]
    tokens: int = 0
    latency_ms: float = 0.0


class StructuredTracer:
    """Thread-safe tracer collecting multi-agent execution steps."""

    def __init__(self, trace_path: Optional[Path] = None):
        self.trace_path = trace_path or (settings.OUTPUTS_DIR / "sample_trace.json")
        self.steps: List[TraceStep] = []
        self._step_counter = 0

    def start_step(self, agent: str, step_input: Dict[str, Any]) -> "StepContext":
        """Context manager to measure latency and record a trace step."""
        self._step_counter += 1
        return StepContext(self, self._step_counter, agent, step_input)

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def save(self) -> Path:
        """Persist trace records to outputs/sample_trace.json."""
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        data = [step.model_dump() for step in self.steps]
        with open(self.trace_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.steps)} trace steps to {self.trace_path}")
        return self.trace_path


class StepContext:
    def __init__(self, tracer: StructuredTracer, step_id: int, agent: str, step_input: Dict[str, Any]):
        self.tracer = tracer
        self.step_id = step_id
        self.agent = agent
        self.step_input = step_input
        self.tool_calls: List[ToolCallRecord] = []
        self.tokens: int = 0
        self.start_time: float = 0.0
        self._completed: bool = False

    def record_tool_call(self, tool_name: str, args: Dict[str, Any], output_summary: Optional[str] = None) -> None:
        self.tool_calls.append(ToolCallRecord(
            tool=tool_name,
            args=args,
            output_summary=output_summary
        ))

    def add_tokens(self, count: int) -> None:
        self.tokens += count

    def __enter__(self) -> "StepContext":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._completed and not exc_type:
            return
        latency = (time.perf_counter() - self.start_time) * 1000.0
        step = TraceStep(
            step_id=self.step_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            agent=self.agent,
            input=self.step_input,
            tool_calls=self.tool_calls,
            output={"status": "error" if exc_type else "success", "error": str(exc_val) if exc_val else None},
            tokens=self.tokens,
            latency_ms=round(latency, 2),
        )
        self.tracer.add_step(step)

    def complete(self, output: Dict[str, Any], tokens: Optional[int] = None) -> None:
        if tokens is not None:
            self.tokens = tokens
        latency = (time.perf_counter() - self.start_time) * 1000.0
        step = TraceStep(
            step_id=self.step_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            agent=self.agent,
            input=self.step_input,
            tool_calls=self.tool_calls,
            output=output,
            tokens=self.tokens,
            latency_ms=round(latency, 2),
        )
        self.tracer.add_step(step)
        self._completed = True
