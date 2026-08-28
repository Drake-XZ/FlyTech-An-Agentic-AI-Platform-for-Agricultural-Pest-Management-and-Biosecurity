"""Guarded/skippable integration test for the optional pydantic_ai adapter.

Runs only when the ``agent`` extra (``pydantic_ai``) is installed; skipped,
never failed, otherwise (EarlyDesign.md section 16.1: PydanticAI is an
"optional, replaceable agent layer").
"""

from __future__ import annotations

import asyncio

import pytest

from s3_ecological.agent.pydantic_ai_adapter import PYDANTIC_AI_AVAILABLE, PydanticAIAdapter
from s3_ecological.interfaces.llm import AgentRequest

pytestmark = pytest.mark.skipif(
    not PYDANTIC_AI_AVAILABLE, reason="pydantic_ai extra is not installed"
)


def test_pydantic_ai_adapter_generates_a_response_using_test_model():
    adapter = PydanticAIAdapter()
    response = asyncio.run(
        adapter.generate(AgentRequest(instruction="Summarize the assessment", context={}))
    )
    assert isinstance(response.explanation, str)
    assert response.explanation != ""


def test_pydantic_ai_adapter_raises_a_clear_error_without_the_package_when_forced_unavailable(
    monkeypatch,
):
    import s3_ecological.agent.pydantic_ai_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "PYDANTIC_AI_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pydantic_ai is not installed"):
        adapter_module.PydanticAIAdapter()
