"""Unit tests for the local demo's narrative builder.

Every assertion here checks that the narrative is built purely from fields
already present on the request/result - no fabricated numbers, no
biosecurity-decision language.
"""

from __future__ import annotations

from datetime import UTC, datetime

from s3_ecological.api.explain import build_narrative
from s3_ecological.schemas.enums import (
    AssessmentStatus,
    EcologicalState,
    EvidenceQuality,
    RiskState,
    UncertaintyLevel,
)
from s3_ecological.schemas.request import (
    Location,
    ObservationContext,
    ObservationRequest,
    VisualCandidate,
)
from s3_ecological.schemas.response import AssessmentResult, RerankedCandidate, UncertaintyInfo

_GENERATED_AT = datetime(2024, 5, 1, tzinfo=UTC)


def _candidate(name: str, *, geo_support=None, rerank_score=None) -> RerankedCandidate:
    return RerankedCandidate(
        submitted_name=name,
        candidate_id=f"fixture:{name.lower()}",
        visual_probability_raw=0.7,
        geo_support=geo_support,
        rerank_score=rerank_score,
        ecological_state=EcologicalState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE,
        evidence_quality=EvidenceQuality.INSUFFICIENT,
    )


def _request(*, location=None, observed_at=None, context=None) -> ObservationRequest:
    return ObservationRequest(
        schema_version="1.0.0",
        observation_id="obs-1",
        candidate_set_complete=True,
        observed_at=observed_at,
        location=location,
        visual_candidates=[
            VisualCandidate(
                candidate_id="fixture:anastrepha", name="Anastrepha", visual_probability=0.7
            )
        ],
        context=context,
    )


def _result(
    *, reranked_candidates, review_required=False, missing_evidence=None
) -> AssessmentResult:
    return AssessmentResult(
        schema_version="1.0.0",
        observation_id="obs-1",
        analysis_id="analysis-1",
        status=AssessmentStatus.COMPLETED,
        reranked_candidates=reranked_candidates,
        risk_state=RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE,
        review_required=review_required,
        missing_evidence=missing_evidence or [],
        uncertainty=UncertaintyInfo(level=UncertaintyLevel.HIGH),
        profile_version="0.1.0",
        configuration_version="0.1.0",
        explanation="",
        generated_at=_GENERATED_AT,
    )


def test_no_candidates_ranked_produces_safe_fallback():
    request = _request()
    result = _result(reranked_candidates=[])
    lines = build_narrative(request, result)
    assert any("No candidate could be ranked" in line for line in lines)


def test_no_location_notes_visual_only_ranking():
    request = _request(location=None)
    result = _result(reranked_candidates=[_candidate("Anastrepha")])
    lines = build_narrative(request, result)
    assert any("No location was provided" in line for line in lines)


def test_missing_geo_support_is_reported_as_unusable_not_zero():
    request = _request(location=Location(latitude=1.0, longitude=2.0))
    result = _result(reranked_candidates=[_candidate("Anastrepha", geo_support=None)])
    lines = build_narrative(request, result)
    assert any("could not produce a usable score" in line for line in lines)


def test_numeric_geo_support_is_described_as_a_model_score():
    request = _request(location=Location(latitude=1.0, longitude=2.0))
    result = _result(reranked_candidates=[_candidate("Anastrepha", geo_support=0.42)])
    lines = build_narrative(request, result)
    assert any("0.420" in line and "model score" in line for line in lines)


def test_missing_date_with_location_is_noted():
    request = _request(location=Location(latitude=1.0, longitude=2.0), observed_at=None)
    result = _result(reranked_candidates=[_candidate("Anastrepha")])
    lines = build_narrative(request, result)
    assert any("No observation date was provided" in line for line in lines)


def test_context_fields_are_echoed_as_not_incorporated():
    context = ObservationContext(host="guava", environmental_covariates={"temperature_c": 21.0})
    request = _request(location=Location(latitude=1.0, longitude=2.0), context=context)
    result = _result(reranked_candidates=[_candidate("Anastrepha")])
    lines = build_narrative(request, result)
    joined = " ".join(lines)
    assert "host" in joined and "temperature_c" in joined
    assert "not currently incorporated" in joined


def test_review_required_uses_safe_language():
    request = _request(location=Location(latitude=1.0, longitude=2.0))
    result = _result(reranked_candidates=[_candidate("Anastrepha")], review_required=True)
    lines = build_narrative(request, result)
    joined = " ".join(lines)
    assert "suggested manual review" in joined
    lowered = joined.lower()
    assert "confirmed incursion" not in lowered or "not a confirmed incursion" in lowered


def test_missing_evidence_is_listed():
    request = _request()
    result = _result(reranked_candidates=[_candidate("Anastrepha")], missing_evidence=["location"])
    lines = build_narrative(request, result)
    assert any("location" in line for line in lines if "missing" in line.lower())


def test_no_morphological_explanation_sentence_always_present():
    request = _request()
    result = _result(reranked_candidates=[_candidate("Anastrepha")])
    lines = build_narrative(request, result)
    assert any("Grad-CAM" in line for line in lines)


def test_narrative_never_uses_unsafe_phrases():
    # "not a confirmed incursion" is intentional, safe negated framing - only
    # an unqualified affirmative claim would be unsafe here.
    request = _request(location=Location(latitude=1.0, longitude=2.0))
    result = _result(
        reranked_candidates=[_candidate("Anastrepha", geo_support=0.9)], review_required=True
    )
    joined = " ".join(build_narrative(request, result)).lower()
    for phrase in ("quarantine cleared", "species confirmation", "is a confirmed incursion"):
        assert phrase not in joined
    assert "not a confirmed incursion" in joined
