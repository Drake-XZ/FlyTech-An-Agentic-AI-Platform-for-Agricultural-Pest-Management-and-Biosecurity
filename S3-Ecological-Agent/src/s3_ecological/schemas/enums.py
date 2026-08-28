"""Shared enumerations for the S3 request/response contracts.

These enums are the single source of truth for the vocabulary defined in
EarlyDesign.md sections 8-10. Values are frozen for schema stability; adding a
new value is a backward-compatible extension, removing or renaming one is not
(EarlyDesign.md section 16.1, "version public schemas").
"""

from __future__ import annotations

from enum import StrEnum


class ToolStatus(StrEnum):
    """Status returned by every S3 tool call (EarlyDesign.md section 7.3)."""

    SUCCESS = "success"
    NO_RECORDS = "no_records"
    PARTIAL = "partial"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


# Tool statuses that a caller may safely retry without changing the request.
RETRYABLE_TOOL_STATUSES = frozenset(
    {ToolStatus.TIMEOUT, ToolStatus.RATE_LIMITED, ToolStatus.UNAVAILABLE}
)


class IssueCode(StrEnum):
    """Minimum warning/error codes required by EarlyDesign.md section 9."""

    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    AMBIGUOUS_TAXONOMY = "ambiguous_taxonomy"
    NO_RECORDS = "no_records"
    COMPONENT_UNAVAILABLE = "component_unavailable"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    SCORE_NOT_COMPUTABLE = "score_not_computable"

    # Documented extension beyond the EarlyDesign.md section 9 minimum set:
    # a submitted name matched nothing in the taxonomy provider at all (as
    # opposed to AMBIGUOUS_TAXONOMY, which means multiple/uncertain matches).
    TAXON_NOT_FOUND = "taxon_not_found"


class EvidenceQuality(StrEnum):
    """Confidence in the ecological evidence backing a score, not the score itself.

    ``high`` is reserved for a future validated evidence-quality policy
    (EarlyDesign.md Profile v0.1, geographic baseline step 7) and must not be
    produced by the v0.1 nearest-distance baseline.
    """

    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UncertaintyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EcologicalState(StrEnum):
    """Per-candidate ecological state (EarlyDesign.md section 9).

    Deliberately excludes ``potential_incursion`` and
    ``conflicting_multimodal_evidence``: those are case-level-only states per
    the "Risk-state ownership and deterministic precedence" rules.
    """

    ECOLOGICALLY_SUPPORTED = "ecologically_supported"
    WEAK_ECOLOGICAL_SUPPORT = "weak_ecological_support"
    GEOGRAPHIC_OOD = "geographic_ood"
    ENVIRONMENTAL_CONFLICT = "environmental_conflict"
    UNKNOWN_OR_INSUFFICIENT_EVIDENCE = "unknown_or_insufficient_evidence"


class RiskState(StrEnum):
    """Case-level risk state (EarlyDesign.md section 9).

    Superset of :class:`EcologicalState` plus the two case-only states
    ``potential_incursion`` and ``conflicting_multimodal_evidence``.
    """

    ECOLOGICALLY_SUPPORTED = "ecologically_supported"
    WEAK_ECOLOGICAL_SUPPORT = "weak_ecological_support"
    GEOGRAPHIC_OOD = "geographic_ood"
    ENVIRONMENTAL_CONFLICT = "environmental_conflict"
    POTENTIAL_INCURSION = "potential_incursion"
    UNKNOWN_OR_INSUFFICIENT_EVIDENCE = "unknown_or_insufficient_evidence"
    CONFLICTING_MULTIMODAL_EVIDENCE = "conflicting_multimodal_evidence"


class AssessmentStatus(StrEnum):
    """Top-level processing status, distinct from ecological risk (section 9)."""

    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED_VALIDATION = "failed_validation"
    FAILED = "failed"
