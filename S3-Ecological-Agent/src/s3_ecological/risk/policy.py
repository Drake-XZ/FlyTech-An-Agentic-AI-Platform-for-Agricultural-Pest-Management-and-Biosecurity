"""Deterministic risk-state precedence (EarlyDesign.md section 9,
"Risk-state ownership and deterministic precedence").

The six-rule first-match precedence is implemented once in
``_apply_precedence`` and reused for both the per-candidate
``EcologicalState`` (rules 1, 3-6; rule 2 is excluded because
``EcologicalState`` has no ``potential_incursion`` value) and the case-level
``RiskState`` (all six rules, evaluated on the highest-ranked candidate) -
this avoids duplicating the threshold comparisons in two places.
"""

from __future__ import annotations

from s3_ecological.interfaces.risk import (
    CandidateRiskInput,
    RiskPolicy,
    RiskPolicyRequest,
    RiskPolicyResult,
)
from s3_ecological.schemas.enums import EcologicalState, EvidenceQuality, RiskState


class DeterministicRiskPolicy(RiskPolicy):
    """The six-rule first-match precedence frozen by Profile v0.1."""

    def evaluate(self, request: RiskPolicyRequest) -> RiskPolicyResult:
        candidate_states = {
            candidate.candidate_id: _candidate_ecological_state(candidate, request)
            for candidate in request.candidates
        }

        top_candidate = min(request.candidates, key=lambda candidate: candidate.rank)
        case_risk_state, review_required, reasons = _case_risk_state(top_candidate, request)

        if any(candidate.ambiguous_taxonomy for candidate in request.candidates):
            review_required = True
            reasons = [*reasons, "ambiguous_taxonomy"]

        return RiskPolicyResult(
            candidate_states=candidate_states,
            case_risk_state=case_risk_state,
            review_required=review_required,
            review_reasons=reasons,
        )


def _has_no_usable_evidence(candidate: CandidateRiskInput) -> bool:
    return (
        candidate.geo_support is None
        or candidate.evidence_quality == EvidenceQuality.INSUFFICIENT
    )


def _potential_incursion_rule_fires(
    candidate: CandidateRiskInput, request: RiskPolicyRequest
) -> bool:
    """No validated incursion rule exists yet in Profile v0.1.

    EarlyDesign.md section 9 rule 2 requires "a separately documented,
    versioned, validated rule" before ``potential_incursion`` may fire, even
    when ``incursion_rule_enabled=true``. No such rule is implemented in
    this prototype, so this always returns False; an out-of-range case
    remains ``geographic_ood`` as the spec requires until one is added.
    """
    return False


def _apply_precedence(
    candidate: CandidateRiskInput, request: RiskPolicyRequest, *, check_incursion: bool
) -> tuple[str, bool]:
    """First-match precedence over rules 1 and 3-6, plus rule 2 when requested.

    Returns ``(state_name, review_required)``. ``check_incursion`` is True
    only for the case-level evaluation, since rule 2's output
    (``potential_incursion``) is not a valid per-candidate
    :class:`EcologicalState`.
    """
    if not request.location_available or _has_no_usable_evidence(candidate):
        return "unknown_or_insufficient_evidence", True

    if (
        check_incursion
        and request.incursion_rule_enabled
        and _potential_incursion_rule_fires(candidate, request)
    ):
        return "potential_incursion", True

    if candidate.environmental_conflict:
        return "environmental_conflict", True

    if (
        candidate.usable_occurrence_count >= request.min_occurrences_for_ood
        and candidate.geo_support is not None
        and candidate.geo_support <= request.geo_ood_max
    ):
        return "geographic_ood", True

    if candidate.evidence_quality == EvidenceQuality.LOW or (
        candidate.geo_support is not None
        and request.geo_ood_max < candidate.geo_support < request.geo_supported_min
    ):
        return "weak_ecological_support", False

    if candidate.geo_support is not None and candidate.geo_support >= request.geo_supported_min:
        return "ecologically_supported", False

    return "unknown_or_insufficient_evidence", True


def _candidate_ecological_state(
    candidate: CandidateRiskInput, request: RiskPolicyRequest
) -> EcologicalState:
    state_name, _ = _apply_precedence(candidate, request, check_incursion=False)
    return EcologicalState(state_name)


def _case_risk_state(
    top_candidate: CandidateRiskInput, request: RiskPolicyRequest
) -> tuple[RiskState, bool, list[str]]:
    state_name, review_required = _apply_precedence(top_candidate, request, check_incursion=True)
    reasons = [state_name] if review_required else []
    return RiskState(state_name), review_required, reasons
