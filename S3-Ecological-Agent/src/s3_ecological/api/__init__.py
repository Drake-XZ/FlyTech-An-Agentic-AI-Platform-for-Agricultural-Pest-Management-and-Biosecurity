"""Deferred HTTP API stub.

EarlyDesign.md section 23.1 (Definition of Done) requires only "one
deterministic library entry point and one fixture-backed CLI command before
adding an HTTP API" for this prototype. ``s3_ecological.run_assessment`` and
the ``s3-ecological`` CLI (see ``s3_ecological.cli``) satisfy that.

No FastAPI route, app, or dependency is defined here. When an HTTP surface
is justified, it should be a thin wrapper that calls
``s3_ecological.run_assessment`` and must not re-implement, duplicate, or
bypass any of its validation, scoring, or risk logic. ``fastapi``/``uvicorn``
are already declared as the optional ``api`` extra in ``pyproject.toml`` for
that future work; nothing in this module imports them yet.
"""
