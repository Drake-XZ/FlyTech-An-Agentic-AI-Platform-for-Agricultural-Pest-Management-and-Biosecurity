"""Optional ``pydantic_ai``-backed :class:`LLMProvider` (EarlyDesign.md
section 16.1: "PydanticAI ... as an optional, replaceable agent layer").

The import of ``pydantic_ai`` is guarded so this module - and everything
that imports it - loads even when the ``agent`` extra is not installed. The
adapter only raises if a caller actually constructs it without the package
present. No deterministic module depends on this file.

This adapter is exercised only by a guarded/skippable test (see
``tests/integration/test_pydantic_ai_adapter.py``): the test runs when
``pydantic_ai`` is installed and is skipped otherwise, never failed.
"""

from __future__ import annotations

from typing import Any

from s3_ecological.interfaces.llm import AgentRequest, AgentResponse, LLMProvider

try:
    from pydantic_ai import Agent  # type: ignore[reportMissingImports]
    from pydantic_ai.models.test import TestModel  # type: ignore[reportMissingImports]

    PYDANTIC_AI_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the extra is absent
    Agent = None  # type: ignore[assignment, misc]
    TestModel = None  # type: ignore[assignment, misc]
    PYDANTIC_AI_AVAILABLE = False

_SYSTEM_PROMPT = (
    "You summarize an already-computed ecological assessment for a human "
    "reviewer. Every score, risk state, and evidence item you are given is "
    "final and authoritative. Never invent a taxon, coordinate, score, "
    "citation, or threshold, and never state that a species is confirmed "
    "absent from a region. Only restate and summarize the given context."
)


class PydanticAIAdapter(LLMProvider):
    """Wraps a ``pydantic_ai.Agent`` behind the :class:`LLMProvider` Protocol.

    Defaults to ``pydantic_ai``'s own ``TestModel`` so this adapter can be
    exercised in tests without any API credentials or network access; a
    real model may be passed via ``model`` once the project owner supplies
    one and enables it through ``S3Settings``.
    """

    def __init__(self, model: Any | None = None):
        if not PYDANTIC_AI_AVAILABLE:
            raise RuntimeError(
                "pydantic_ai is not installed; install the 's3-ecological[agent]' "
                "extra to use PydanticAIAdapter, or use MockLLMProvider instead."
            )
        self._agent = Agent(  # type: ignore[reportOptionalCall]
            model or TestModel(), output_type=str, system_prompt=_SYSTEM_PROMPT  # type: ignore[reportOptionalCall]
        )

    async def generate(self, request: AgentRequest) -> AgentResponse:
        result = await self._agent.run(request.instruction, deps=request.context)
        return AgentResponse(explanation=str(result.output), tool_calls_summary=[])
