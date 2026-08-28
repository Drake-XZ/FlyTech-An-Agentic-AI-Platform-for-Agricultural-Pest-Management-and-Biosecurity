# 0002: `pydantic-ai` and `fastapi` stay optional, never imported by the deterministic core

## Status

Accepted (Milestone 0/1 prototype).

## Context

EarlyDesign.md requires the ecological core logic to be deterministic and
independent of PydanticAI/FastAPI/provider SDKs, and requires that an LLM
must never calculate or override taxon identity, occurrence records,
coordinates, geographic support, component/fusion scores, thresholds, risk
states, evidence, or provenance. The prototype must also run fully offline
without any LLM.

## Decision

- `pydantic>=2` is the only hard runtime dependency. `pydantic-ai` (extra
  group `agent`) and `fastapi`/`uvicorn` (extra group `api`) are optional
  extras declared in `pyproject.toml`.
- `interfaces/llm.py` defines an `LLMProvider` Protocol and
  `AgentRequest`/`AgentResponse` models with no dependency on `pydantic_ai`.
- `agent/mock_provider.py` implements `LLMProvider` in pure Python (a
  deterministic offline/test double), so agent-loop behavior is fully
  testable without any optional dependency installed and without network
  access.
- `agent/pydantic_ai_adapter.py` imports `pydantic_ai` inside a guarded
  `try/except ImportError` block at module import time, exposing an
  `AVAILABLE` flag. Constructing the adapter without the extra installed
  raises at construction time, not at import time, so importing the module
  itself never breaks the deterministic core.
- `taxonomy/`, `occurrence/`, `priors/`, `suitability/`, `fusion/`, `risk/`,
  and `evidence/` never import `s3_ecological.agent`, `pydantic_ai`, or
  `fastapi`. This is enforced by
  `tests/integration/test_import_boundaries.py`, which parses each module's
  AST and fails if a forbidden import appears.
- The LLM boundary is request-interpretation/tool-selection/explanation
  only: `orchestration/pipeline.py` (the deterministic core) never calls
  `LLMProvider` at all in this prototype — an LLM-driven agent loop, when
  used, sits strictly in front of the pipeline and can only choose which
  already-implemented tool to call with what arguments, never compute or
  override a score, threshold, or risk state itself.

## Consequences

- `pytest` passes with zero optional dependencies installed; a
  `pydantic_ai`-specific test is written to `skip` (not fail) when that
  package is absent.
- Adding a real LLM provider later means adding a new module under
  `agent/`, not touching any deterministic module.
