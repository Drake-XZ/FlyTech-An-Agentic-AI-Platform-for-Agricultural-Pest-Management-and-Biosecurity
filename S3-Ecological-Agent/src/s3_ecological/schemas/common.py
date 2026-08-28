"""Shared building blocks used by both the request/response contracts and the
internal tool contracts (EarlyDesign.md section 7.3).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.enums import IssueCode, ToolStatus

T = TypeVar("T")


class Issue(BaseModel):
    """A structured warning or error.

    ``details`` must never contain credentials, raw stack traces, or other
    sensitive configuration (EarlyDesign.md section 9) - callers populating
    this field are responsible for redacting secrets before construction.
    """

    model_config = ConfigDict(extra="forbid")

    code: IssueCode
    message: str
    component: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class EvidenceReference(BaseModel):
    """A lightweight pointer to a full :class:`EvidenceRecord`.

    Tool results carry references rather than full evidence records so a
    single evidence item can be produced once (by occurrence retrieval) and
    cited by many downstream tool calls without duplicating its payload.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: str
    source_record_id: str | None = None
    source_url: str | None = None


class ToolResult(BaseModel, Generic[T]):
    """Typed envelope returned by every S3 tool (EarlyDesign.md section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    status: ToolStatus
    data: T | None = None
    warnings: list[Issue] = Field(default_factory=list)
    errors: list[Issue] = Field(default_factory=list)
    provenance: list[EvidenceReference] = Field(default_factory=list)
