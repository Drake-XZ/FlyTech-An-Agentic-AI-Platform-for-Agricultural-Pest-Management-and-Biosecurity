"""Optional LLM provider boundary (EarlyDesign.md section 16.1).

An ``LLMProvider`` may plan tool calls, select allowed tools, and turn an
already-computed :class:`~s3_ecological.schemas.response.AssessmentResult`
into prose. It must never compute or override scores, thresholds, risk
states, evidence, or provenance - those fields are produced exclusively by
``orchestration/pipeline.py`` before any LLM sees the result.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class AgentRequest(BaseModel):
    """Instruction plus read-only context for an optional LLM turn."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """A validated orchestration or explanation result from an LLM provider.

    ``explanation`` may be substituted for the deterministic explanation
    string; every other field of the authoritative
    :class:`~s3_ecological.schemas.response.AssessmentResult` is produced
    before the LLM runs and is never touched afterwards.
    """

    model_config = ConfigDict(extra="forbid")

    explanation: str
    tool_calls_summary: list[str] = Field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """S3-owned model boundary (EarlyDesign.md section 16.1)."""

    async def generate(self, request: AgentRequest) -> AgentResponse:
        """Return a validated orchestration or explanation result."""
        ...
