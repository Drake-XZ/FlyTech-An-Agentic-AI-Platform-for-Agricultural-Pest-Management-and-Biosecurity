"""Optional agent layer: LLM boundary, tool wrappers, and an optional
pydantic_ai adapter. Every authoritative field is computed by
``orchestration.pipeline`` before any code in this package runs; nothing
here may compute a score, threshold, or risk state.
"""
