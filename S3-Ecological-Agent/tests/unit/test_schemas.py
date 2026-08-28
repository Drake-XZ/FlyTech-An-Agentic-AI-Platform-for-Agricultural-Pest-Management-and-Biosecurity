"""Unit tests for the request/response contract models (EarlyDesign.md sections 8-9)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from s3_ecological.schemas.common import EvidenceReference, Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus
from s3_ecological.schemas.request import Location, ObservationRequest, VisualCandidate
from s3_ecological.schemas.response import ResolvedTaxon


def _candidate(candidate_id: str = "c1", probability: float = 1.0) -> VisualCandidate:
    return VisualCandidate(
        candidate_id=candidate_id, name="Bactrocera", visual_probability=probability
    )


def test_observation_request_accepts_minimal_valid_payload():
    request = ObservationRequest(
        schema_version="1.0.0",
        observation_id="obs-1",
        candidate_set_complete=True,
        visual_candidates=[_candidate()],
    )
    assert request.location is None
    assert request.observed_at is None
    assert request.other_agent_evidence == []


def test_observation_request_rejects_duplicate_candidate_ids():
    with pytest.raises(ValidationError, match="duplicate candidate_id"):
        ObservationRequest(
            schema_version="1.0.0",
            observation_id="obs-1",
            candidate_set_complete=True,
            visual_candidates=[_candidate("c1"), _candidate("c1")],
        )


def test_observation_request_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ObservationRequest(
            schema_version="1.0.0",
            observation_id="obs-1",
            candidate_set_complete=True,
            visual_candidates=[_candidate()],
            unexpected_field="not allowed",  # type: ignore[call-arg]
        )


def test_visual_probability_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        VisualCandidate(candidate_id="c1", name="Bactrocera", visual_probability=1.5)


def test_visual_probability_rejects_non_finite_value():
    # nan/inf are already outside [0, 1], so pydantic's own ge/le bound check
    # rejects them before the custom finiteness validator ever runs.
    with pytest.raises(ValidationError):
        VisualCandidate(candidate_id="c1", name="Bactrocera", visual_probability=float("nan"))


def test_location_rejects_latitude_out_of_range():
    with pytest.raises(ValidationError):
        Location(latitude=95.0, longitude=0.0)


def test_location_preserves_none_coordinate_uncertainty():
    location = Location(latitude=0.0, longitude=0.0)
    assert location.coordinate_uncertainty_m is None


def test_resolved_taxon_round_trips_through_json_schema_and_json():
    taxon = ResolvedTaxon(
        scientific_name="Bactrocera", rank="genus", taxon_ids={"fixture": "fixture:bactrocera"}
    )
    schema = ResolvedTaxon.model_json_schema()
    assert schema["title"] == "ResolvedTaxon"
    restored = ResolvedTaxon.model_validate_json(taxon.model_dump_json())
    assert restored == taxon


def test_tool_result_generic_envelope_exports_json_schema():
    schema = ToolResult[ResolvedTaxon].model_json_schema()
    assert "properties" in schema
    assert "status" in schema["properties"]


def test_issue_and_evidence_reference_construct_with_required_fields():
    issue = Issue(code=IssueCode.NO_RECORDS, message="no records", component="test")
    assert issue.retryable is False
    reference = EvidenceReference(evidence_id="evidence-1", source="fixture")
    assert reference.source_record_id is None


def test_tool_status_and_retryable_status_membership():
    assert ToolStatus.TIMEOUT.value == "timeout"
    from s3_ecological.schemas.enums import RETRYABLE_TOOL_STATUSES

    assert ToolStatus.TIMEOUT in RETRYABLE_TOOL_STATUSES
    assert ToolStatus.SUCCESS not in RETRYABLE_TOOL_STATUSES
