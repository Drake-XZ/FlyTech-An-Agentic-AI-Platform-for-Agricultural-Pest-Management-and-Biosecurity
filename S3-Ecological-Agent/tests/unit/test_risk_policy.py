"""Unit tests for the deterministic risk-state precedence rules (EarlyDesign.md section 9)."""

from __future__ import annotations

from typing import Any

from s3_ecological.interfaces.risk import CandidateRiskInput, RiskPolicyRequest
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.enums import EcologicalState, EvidenceQuality, RiskState

POLICY = DeterministicRiskPolicy()


def _candidate(**overrides: Any) -> CandidateRiskInput:
    defaults: dict[str, Any] = dict(
        candidate_id="c1",
        taxon_id="fixture:bactrocera",
        rank=0,
        geo_support=0.8,
        usable_occurrence_count=10,
        evidence_quality=EvidenceQuality.MEDIUM,
        environmental_conflict=False,
        ambiguous_taxonomy=False,
    )
    defaults.update(overrides)
    return CandidateRiskInput(**defaults)


def _request(candidate: CandidateRiskInput, **overrides: Any) -> RiskPolicyRequest:
    defaults: dict[str, Any] = dict(
        candidates=[candidate],
        location_available=True,
        incursion_rule_enabled=False,
        geo_supported_min=0.5,
        geo_ood_max=0.1,
        min_occurrences_for_ood=3,
    )
    defaults.update(overrides)
    return RiskPolicyRequest(**defaults)


def test_missing_location_yields_unknown_or_insufficient_evidence():
    candidate = _candidate()
    result = POLICY.evaluate(_request(candidate, location_available=False))
    assert result.case_risk_state == RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE
    assert result.review_required is True


def test_no_usable_evidence_yields_unknown_or_insufficient_evidence():
    candidate = _candidate(geo_support=None, evidence_quality=EvidenceQuality.INSUFFICIENT)
    result = POLICY.evaluate(_request(candidate))
    assert result.case_risk_state == RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE
    assert result.review_required is True


def test_incursion_rule_never_fires_in_v0_1_even_when_enabled():
    candidate = _candidate()
    result = POLICY.evaluate(_request(candidate, incursion_rule_enabled=True))
    assert result.case_risk_state != RiskState.POTENTIAL_INCURSION


def test_environmental_conflict_takes_precedence_over_supported_geo():
    candidate = _candidate(environmental_conflict=True, geo_support=0.9)
    result = POLICY.evaluate(_request(candidate))
    assert result.case_risk_state == RiskState.ENVIRONMENTAL_CONFLICT
    assert result.review_required is True


def test_geographic_ood_fires_when_enough_occurrences_and_low_geo_support():
    candidate = _candidate(usable_occurrence_count=5, geo_support=0.05)
    result = POLICY.evaluate(_request(candidate, min_occurrences_for_ood=3, geo_ood_max=0.1))
    assert result.case_risk_state == RiskState.GEOGRAPHIC_OOD
    assert result.review_required is True


def test_geographic_ood_does_not_fire_below_min_occurrences_threshold():
    candidate = _candidate(usable_occurrence_count=2, geo_support=0.05)
    result = POLICY.evaluate(_request(candidate, min_occurrences_for_ood=3, geo_ood_max=0.1))
    assert result.case_risk_state != RiskState.GEOGRAPHIC_OOD


def test_low_evidence_quality_yields_weak_ecological_support():
    candidate = _candidate(evidence_quality=EvidenceQuality.LOW, geo_support=0.8)
    result = POLICY.evaluate(_request(candidate))
    assert result.case_risk_state == RiskState.WEAK_ECOLOGICAL_SUPPORT
    assert result.review_required is False


def test_geo_support_between_ood_and_supported_thresholds_is_weak_support():
    candidate = _candidate(evidence_quality=EvidenceQuality.MEDIUM, geo_support=0.3)
    result = POLICY.evaluate(_request(candidate, geo_ood_max=0.1, geo_supported_min=0.5))
    assert result.case_risk_state == RiskState.WEAK_ECOLOGICAL_SUPPORT


def test_geo_support_at_or_above_supported_min_is_ecologically_supported():
    candidate = _candidate(geo_support=0.5)
    result = POLICY.evaluate(_request(candidate, geo_supported_min=0.5))
    assert result.case_risk_state == RiskState.ECOLOGICALLY_SUPPORTED
    assert result.review_required is False


def test_ambiguous_taxonomy_forces_review_even_when_ecologically_supported():
    candidate = _candidate(geo_support=0.9, ambiguous_taxonomy=True)
    result = POLICY.evaluate(_request(candidate))
    assert result.case_risk_state == RiskState.ECOLOGICALLY_SUPPORTED
    assert result.review_required is True
    assert "ambiguous_taxonomy" in result.review_reasons


def test_candidate_ecological_state_has_no_potential_incursion_value():
    candidate = _candidate(environmental_conflict=True)
    result = POLICY.evaluate(_request(candidate, incursion_rule_enabled=True))
    assert result.candidate_states["c1"] == EcologicalState.ENVIRONMENTAL_CONFLICT
    assert "potential_incursion" not in {state.value for state in EcologicalState}


def test_top_candidate_selected_by_rank_not_by_list_order():
    top = _candidate(candidate_id="top", rank=0, geo_support=0.9)
    other = _candidate(candidate_id="other", rank=1, geo_support=0.0, usable_occurrence_count=0)
    request = RiskPolicyRequest(
        candidates=[other, top],
        location_available=True,
        incursion_rule_enabled=False,
        geo_supported_min=0.5,
        geo_ood_max=0.1,
        min_occurrences_for_ood=3,
    )
    result = POLICY.evaluate(request)
    assert result.case_risk_state == RiskState.ECOLOGICALLY_SUPPORTED
