"""Offline-test LLM provider (EarlyDesign.md section 16.1, "run without an
external LLM").

``MockLLMProvider`` satisfies :class:`~s3_ecological.interfaces.llm.LLMProvider`
with no network call and no randomness: it only rearranges facts already
present in ``request.context`` (produced by ``orchestration.pipeline``) into
prose. It never invents a taxon, score, or citation, matching the same
constraint placed on a real LLM provider by section 7.2.
"""

from __future__ import annotations

from s3_ecological.interfaces.llm import AgentRequest, AgentResponse, LLMProvider


class MockLLMProvider(LLMProvider):
    """Deterministic, offline stand-in for a real LLM provider.

    Used as the default ``llm_provider`` (``S3Settings.llm_provider="mock"``)
    and by tests that must run with no network access and no API
    credentials.
    """

    async def generate(self, request: AgentRequest) -> AgentResponse:
        explanation = request.context.get("explanation")
        if explanation is None:
            explanation = (
                f"Mock provider received instruction '{request.instruction}' "
                "with no precomputed explanation in context; no authoritative "
                "field was recomputed."
            )
        tool_calls_summary = list(request.context.get("tool_calls_summary", []))
        return AgentResponse(explanation=str(explanation), tool_calls_summary=tool_calls_summary)
