"""Risk-policy interface (EarlyDesign.md sections 7.3, 9).

Encapsulates the deterministic precedence rules ("Risk-state ownership and
deterministic precedence") behind a Protocol so thresholds or the rule
implementation can be replaced by a versioned successor without touching the
fusion or evidence layers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.enums import EcologicalState, EvidenceQuality, RiskState


class CandidateRiskInput(BaseModel):
    """Per-candidate facts the risk policy needs, in rank order (rank 0 = top)."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    taxon_id: str | None
    rank: int = Field(ge=0)
    geo_support: float | None
    usable_occurrence_count: int
    evidence_quality: EvidenceQuality
    environmental_conflict: bool = False
    ambiguous_taxonomy: bool = False


class RiskPolicyRequest(BaseModel):
    """Input to ``flag_out_of_range_or_unknown`` (EarlyDesign.md section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateRiskInput] = Field(min_length=1)
    location_available: bool
    incursion_rule_enabled: bool
    geo_supported_min: float
    geo_ood_max: float
    min_occurrences_for_ood: int


class RiskPolicyResult(BaseModel):
    """Output of the deterministic risk-state precedence rules."""

    model_config = ConfigDict(extra="forbid")

    candidate_states: dict[str, EcologicalState]
    case_risk_state: RiskState
    review_required: bool
    review_reasons: list[str] = Field(default_factory=list)


@runtime_checkable
class RiskPolicy(Protocol):
    """Interface every risk-state policy implementation must satisfy."""

    def evaluate(self, request: RiskPolicyRequest) -> RiskPolicyResult:
        """Apply the deterministic risk-state precedence rules."""
        ...
