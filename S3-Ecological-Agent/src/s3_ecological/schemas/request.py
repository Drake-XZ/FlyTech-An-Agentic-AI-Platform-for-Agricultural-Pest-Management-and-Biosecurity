"""Input contract (EarlyDesign.md section 8).

This module only enforces *structural* validation - types, ranges, and
uniqueness that hold regardless of runtime configuration. Profile-dependent
rules (the candidate-set-complete probability-sum check, which needs a
configurable tolerance) are deliberately deferred to
``orchestration.validation`` so this schema never depends on runtime
settings (EarlyDesign.md section 16.3, "keep ecological domain logic
independent").
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


def _reject_non_finite(value: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number, got {value!r}")
    return value


class Location(BaseModel):
    """Observation location.

    ``coordinate_uncertainty_m`` is preserved as ``None`` when unknown; it
    must never be assumed to be zero (EarlyDesign.md section 10).
    """

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    coordinate_uncertainty_m: float | None = Field(default=None, ge=0.0)

    @field_validator("latitude", "longitude")
    @classmethod
    def _finite(cls, value: float, info) -> float:
        return _reject_non_finite(value, info.field_name)


class VisualCandidate(BaseModel):
    """One S1 candidate taxon with its raw, un-renormalized probability."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    rank: str | None = None
    visual_probability: Probability
    model_version: str | None = None

    @field_validator("visual_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        return _reject_non_finite(value, "visual_probability")


class ObservationContext(BaseModel):
    """Optional observation metadata (EarlyDesign.md section 7.1)."""

    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    trap_type: str | None = None
    habitat: str | None = None
    land_cover: str | None = None
    climate: str | None = None
    elevation_m: float | None = None
    season: str | None = None
    environmental_covariates: dict[str, float] | None = None


class ExternalAgentEvidence(BaseModel):
    """Versioned, framework-neutral evidence supplied by another FlyTech agent.

    Standalone S3 validates and preserves these items as integration context
    only; it never reinterprets an unknown payload or performs cross-agent
    fusion (EarlyDesign.md section 8).
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    schema_version: str
    producer_agent: str
    evidence_type: str
    status: str
    candidate_id: str | None = None
    value: float | str | bool | None = None
    unit: str | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    generated_at: datetime


class ObservationRequest(BaseModel):
    """Top-level S3 assessment request (EarlyDesign.md section 8)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    observation_id: str = Field(min_length=1)
    source: str | None = None
    candidate_set_complete: bool
    omitted_probability_mass: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_at: datetime | None = None
    location: Location | None = None
    visual_candidates: list[VisualCandidate] = Field(min_length=1)
    context: ObservationContext | None = None
    other_agent_evidence: list[ExternalAgentEvidence] = Field(default_factory=list)

    @field_validator("omitted_probability_mass")
    @classmethod
    def _finite_omitted_mass(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _reject_non_finite(value, "omitted_probability_mass")

    @model_validator(mode="after")
    def _candidate_ids_unique(self) -> ObservationRequest:
        seen: set[str] = set()
        for candidate in self.visual_candidates:
            if candidate.candidate_id in seen:
                raise ValueError(
                    f"duplicate candidate_id '{candidate.candidate_id}' in visual_candidates"
                )
            seen.add(candidate.candidate_id)
        return self
