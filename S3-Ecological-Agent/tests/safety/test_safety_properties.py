"""Safety-property tests (EarlyDesign.md core safety invariants).

These are the properties the prototype must never violate regardless of
input: no occurrence-absence claim, no confirmed/potential incursion
statement in v0.1, every cited evidence id must be traceable, and a
misconfigured provider must degrade safely rather than crash or silently
fall back to fixture data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.orchestration.pipeline import run_assessment
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.enums import AssessmentStatus, IssueCode, RiskState
from s3_ecological.schemas.request import Location, ObservationRequest, VisualCandidate
from s3_ecological.settings import S3Settings
from s3_ecological.suitability.null_model import NullSuitabilityModel

GENERATED_AT = datetime(2026, 1, 1, tzinfo=UTC)

FORBIDDEN_INCURSION_STATES = {
    RiskState.POTENTIAL_INCURSION,
    RiskState.CONFLICTING_MULTIMODAL_EVIDENCE,
}


def _request(location: Location | None) -> ObservationRequest:
    return ObservationRequest(
        schema_version="1.0.0",
        observation_id="obs-safety",
        candidate_set_complete=True,
        visual_candidates=[
            VisualCandidate(candidate_id="c1", name="Bactrocera", visual_probability=1.0)
        ],
        location=location,
    )


def _assessment(occurrence_provider, settings: S3Settings, *, location: Location | None):
    return run_assessment(
        _request(location),
        settings=settings,
        taxonomy_provider=FixtureTaxonomyProvider(),
        occurrence_provider=occurrence_provider,
        geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
        suitability_model=NullSuitabilityModel(),
        risk_policy=DeterministicRiskPolicy(),
        analysis_id="safety-test",
        generated_at=GENERATED_AT,
    )


def test_zero_occurrence_records_is_never_reported_as_absence():
    settings = S3Settings()
    occurrence_provider = InMemoryOccurrenceProvider(records=[])
    result = _assessment(
        occurrence_provider, settings, location=Location(latitude=0.0, longitude=0.0)
    )

    top = result.reranked_candidates[0]
    assert top.geo_support is None
    assert not any(error.code == IssueCode.INVALID_INPUT for error in result.errors)
    assert "absent" not in result.explanation.lower()
    assert "no records" not in result.explanation.lower() or top.geo_support is None


def test_incursion_rule_never_fires_and_never_reports_confirmed_incursion():
    settings = S3Settings(incursion_rule_enabled=True)
    record = RawOccurrenceRecord(
        source="test",
        source_record_id="rec-1",
        scientific_name_raw="Bactrocera",
        taxon_id="fixture:bactrocera",
        latitude=0.0,
        longitude=0.0,
        coordinate_uncertainty_m=100.0,
    )
    occurrence_provider = InMemoryOccurrenceProvider(records=[record])
    result = _assessment(
        occurrence_provider, settings, location=Location(latitude=0.0, longitude=0.0)
    )

    assert result.risk_state not in FORBIDDEN_INCURSION_STATES
    assert "confirmed_incursion" not in {state.value for state in RiskState}


def test_every_cited_evidence_id_resolves_to_a_real_evidence_record():
    settings = S3Settings()
    records = [
        RawOccurrenceRecord(
            source="test",
            source_record_id=f"rec-{i}",
            scientific_name_raw="Bactrocera",
            taxon_id="fixture:bactrocera",
            latitude=0.0,
            longitude=0.0,
            coordinate_uncertainty_m=100.0,
        )
        for i in range(3)
    ]
    occurrence_provider = InMemoryOccurrenceProvider(records=records)
    result = _assessment(
        occurrence_provider, settings, location=Location(latitude=0.0, longitude=0.0)
    )

    known_evidence_ids = {item.evidence_id for item in result.evidence}
    for candidate in result.reranked_candidates:
        for evidence_id in candidate.supporting_evidence_ids:
            assert evidence_id in known_evidence_ids


def test_provider_not_configured_degrades_safely_without_crashing_or_faking_data():
    settings = S3Settings(occurrence_provider="live_gbif")
    occurrence_provider = build_occurrence_provider(settings)
    result = _assessment(
        occurrence_provider, settings, location=Location(latitude=0.0, longitude=0.0)
    )

    assert result.status != AssessmentStatus.FAILED
    assert any(error.code == IssueCode.PROVIDER_NOT_CONFIGURED for error in result.errors)
    top = result.reranked_candidates[0]
    assert top.geo_support is None


def test_missing_location_never_guesses_a_supported_risk_state():
    settings = S3Settings()
    occurrence_provider = InMemoryOccurrenceProvider(records=[])
    result = _assessment(occurrence_provider, settings, location=None)

    assert result.risk_state == RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE
    assert result.review_required is True
    assert "location" in result.requested_evidence
