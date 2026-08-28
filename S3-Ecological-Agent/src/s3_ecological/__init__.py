"""FlyTech S3 Ecological Agent - offline-first ecological plausibility core.

Prototype Implementation Profile v0.1 (see ``EarlyDesign.md``). The single
supported library entry point is :func:`run_assessment`: it never calls an
LLM, never makes a network request, and never imports ``pydantic_ai`` or
``fastapi`` - every score, risk state, and evidence link it returns comes
from the deterministic modules under this package.
"""

from __future__ import annotations

from s3_ecological.orchestration.pipeline import run_assessment
from s3_ecological.settings import S3Settings

__all__ = ["run_assessment", "S3Settings"]

__version__ = "0.1.0"
