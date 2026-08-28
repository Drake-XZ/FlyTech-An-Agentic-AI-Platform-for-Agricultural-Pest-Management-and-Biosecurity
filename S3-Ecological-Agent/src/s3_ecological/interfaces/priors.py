"""Geographic-prior interface (EarlyDesign.md sections 7.3, 12.1).

The v0.1 nearest-clean-occurrence baseline (``priors/geo_nearest_distance.py``)
implements this Protocol. A future learned prior (Baseline B, Milestone 2)
must implement the same Protocol so fusion and risk logic never change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.common import ToolResult
from s3_ecological.schemas.enums import EvidenceQuality


class GeoPriorCandidateTaxon(BaseModel):
    """One resolved candidate taxon to score against occurrence evidence."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    taxon_id: str


class GeoPriorRequest(BaseModel):
    """Input to ``estimate_geo_prior`` (EarlyDesign.md section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    candidate_taxa: list[GeoPriorCandidateTaxon] = Field(min_length=1)
    latitude: float
    longitude: float
    observed_at: datetime | None = None


class CandidateGeoSupport(BaseModel):
    """Geographic-support result for one candidate.

    ``geo_support=None`` means "no usable evidence", never "zero support" -
    absence of a record is never treated as evidence of absence
    (EarlyDesign.md Profile v0.1, geographic baseline step 5).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    taxon_id: str
    geo_support: float | None
    min_occurrence_distance_km: float | None
    usable_occurrence_count: int
    evidence_quality: EvidenceQuality
    supporting_evidence_ids: list[str] = Field(default_factory=list)


@runtime_checkable
class GeoPriorModel(Protocol):
    """Interface every geographic-prior implementation must satisfy."""

    def estimate(self, request: GeoPriorRequest) -> ToolResult[list[CandidateGeoSupport]]:
        """Estimate geographic support for each candidate taxon."""
        ...
