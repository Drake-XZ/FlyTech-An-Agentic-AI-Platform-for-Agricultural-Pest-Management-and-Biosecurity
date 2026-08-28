"""Environmental-suitability interface (EarlyDesign.md sections 7.3, 12.3).

Post-MVP (Milestone 3). The v0.1 profile ships only
:class:`~s3_ecological.suitability.null_model.NullSuitabilityModel`, which
always reports the component as unavailable. This Protocol exists now so a
real MaxEnt-style adapter (``elapid``) can be added later without touching
fusion or risk logic.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.common import ToolResult


class SuitabilityCandidateTaxon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    taxon_id: str


class SuitabilityRequest(BaseModel):
    """Input to ``estimate_environmental_suitability`` (section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    candidate_taxa: list[SuitabilityCandidateTaxon] = Field(min_length=1)
    latitude: float
    longitude: float
    covariates: dict[str, float] | None = None


class CandidateSuitability(BaseModel):
    """Suitability result for one candidate.

    Suitability is not occurrence probability and is not incursion
    probability (EarlyDesign.md section 12.3) - it must only ever be
    consumed as one optional fusion component.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    taxon_id: str
    suitability: float | None
    within_model_support: bool | None = None


@runtime_checkable
class SuitabilityModel(Protocol):
    """Interface every environmental-suitability implementation must satisfy."""

    def estimate(self, request: SuitabilityRequest) -> ToolResult[list[CandidateSuitability]]:
        """Estimate environmental suitability for each candidate taxon."""
        ...
