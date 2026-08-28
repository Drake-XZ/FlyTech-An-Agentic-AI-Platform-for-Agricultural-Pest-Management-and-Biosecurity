"""Output contract (EarlyDesign.md section 9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.common import Issue
from s3_ecological.schemas.enums import (
    AssessmentStatus,
    EcologicalState,
    EvidenceQuality,
    RiskState,
    UncertaintyLevel,
)


class ResolvedTaxon(BaseModel):
    """Result of taxonomy resolution for one submitted candidate name."""

    model_config = ConfigDict(extra="forbid")

    scientific_name: str
    rank: str
    taxon_ids: dict[str, str] = Field(default_factory=dict)
    synonym_of: str | None = None
    ambiguous: bool = False


class RerankedCandidate(BaseModel):
    """One candidate after ecological scoring and soft fusion."""

    model_config = ConfigDict(extra="forbid")

    submitted_name: str
    candidate_id: str
    resolved_taxon: ResolvedTaxon | None = None
    visual_probability_raw: float
    geo_support: float | None = None
    min_occurrence_distance_km: float | None = None
    usable_occurrence_count: int = 0
    temporal_support: float | None = None
    environmental_suitability: float | None = None
    combined_log_score: float | None = None
    rerank_score: float | None = None
    ecological_state: EcologicalState
    evidence_quality: EvidenceQuality
    conflicts: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class UncertaintyInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: UncertaintyLevel
    reasons: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """A single traceable occurrence or derived evidence item (section 10)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: str
    source_record_id: str | None = None
    dataset_id: str | None = None
    source_url: str | None = None
    retrieved_at: datetime
    scientific_name_raw: str
    taxon_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_uncertainty_m: float | None = None
    event_date: str | None = None
    basis_of_record: str | None = None
    license: str | None = None
    media_license: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    cleaning_actions: list[str] = Field(default_factory=list)
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot_or_cache_key: str | None = None


class AssessmentResult(BaseModel):
    """Top-level S3 assessment response (EarlyDesign.md section 9)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    observation_id: str
    analysis_id: str
    status: AssessmentStatus
    reranked_candidates: list[RerankedCandidate] = Field(default_factory=list)
    risk_state: RiskState
    review_required: bool
    review_reasons: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyInfo
    missing_evidence: list[str] = Field(default_factory=list)
    requested_evidence: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    errors: list[Issue] = Field(default_factory=list)
    profile_version: str
    configuration_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    threshold_versions: dict[str, str] = Field(default_factory=dict)
    data_snapshot_versions: dict[str, str] = Field(default_factory=dict)
    explanation: str
    generated_at: datetime
