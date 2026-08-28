"""Golden acceptance tests (EarlyDesign.md section 20.3).

Each of the six named cases is run through the real ``run_assessment``
library entry point (never a mock of the pipeline itself) and checked
against the specific expectations recorded in that case's ``expected.json``.
"""

from __future__ import annotations

import math
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from s3_ecological.fixtures.golden_loader import GOLDEN_CASE_NAMES, load_golden_case
from s3_ecological.orchestration.pipeline import run_assessment
from s3_ecological.schemas.enums import AssessmentStatus, IssueCode, RiskState

GENERATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _run(case_name: str):
    case = load_golden_case(case_name)
    result = run_assessment(
        case.request,
        settings=case.settings,
        taxonomy_provider=case.taxonomy_provider,
        occurrence_provider=case.occurrence_provider,
        geo_prior_model=case.geo_prior_model,
        suitability_model=case.suitability_model,
        risk_policy=case.risk_policy,
        analysis_id=f"golden-{case_name}",
        generated_at=GENERATED_AT,
    )
    return case, result


@pytest.mark.parametrize("case_name", GOLDEN_CASE_NAMES)
def test_golden_case_runs_without_raising(case_name):
    _, result = _run(case_name)
    assert result.status != AssessmentStatus.FAILED


def test_supported_same_location_reports_full_geo_support():
    case, result = _run("supported_same_location")
    top = result.reranked_candidates[0]
    assert top.candidate_id == case.expect["top_candidate_id"]
    assert top.geo_support == case.expect["geo_support"]
    assert result.risk_state == RiskState(case.expect["risk_state"])
    assert result.review_required == case.expect["review_required"]


def test_geographic_ood_review_flags_out_of_range_candidate():
    case, result = _run("geographic_ood_review")
    top = result.reranked_candidates[0]
    assert top.candidate_id == case.expect["top_candidate_id"]
    assert top.geo_support < case.expect["geo_support_below"]
    assert result.risk_state == RiskState(case.expect["risk_state"])
    assert result.review_required == case.expect["review_required"]
    assert result.risk_state.value not in case.expect["forbidden_risk_states"]


def test_no_occurrence_records_never_claims_absence():
    case, result = _run("no_occurrence_records")
    top = result.reranked_candidates[0]
    assert top.candidate_id == case.expect["top_candidate_id"]
    assert top.geo_support == case.expect["geo_support"]
    assert result.status == AssessmentStatus(case.expect["status"])
    assert result.risk_state == RiskState(case.expect["risk_state"])


def test_provider_not_configured_does_not_crash_and_surfaces_typed_error():
    case, result = _run("provider_not_configured")
    top = result.reranked_candidates[0]
    assert top.candidate_id == case.expect["top_candidate_id"]
    assert result.status != AssessmentStatus.FAILED
    error_codes = {error.code for error in result.errors}
    assert IssueCode.PROVIDER_NOT_CONFIGURED in error_codes


def test_missing_location_requests_location_and_skips_distance_calculation():
    case, result = _run("missing_location")
    top = result.reranked_candidates[0]
    assert top.candidate_id == case.expect["top_candidate_id"]
    assert result.status == AssessmentStatus(case.expect["status"])
    assert result.risk_state == RiskState(case.expect["risk_state"])
    assert result.requested_evidence == case.expect["requested_evidence"]
    assert top.geo_support == case.expect["geo_support"]


def test_truncated_top_k_rerank_score_is_driven_by_visual_probability_ratio():
    case, result = _run("truncated_top_k")
    scores: dict[str, float] = {
        c.candidate_id: c.rerank_score
        for c in result.reranked_candidates
        if c.rerank_score is not None
    }
    assert len(scores) == len(result.reranked_candidates)
    tolerance = case.expect["rerank_score_tolerance"]
    for candidate_id, expected_score in case.expect["rerank_score_approx"].items():
        assert math.isclose(scores[candidate_id], expected_score, abs_tol=tolerance)
    assert math.isclose(sum(scores.values()), 1.0, rel_tol=1e-9)


def test_cli_demo_subcommand_runs_supported_same_location_offline():
    completed = subprocess.run(
        [sys.executable, "-m", "s3_ecological.cli", "demo", "--fixture", "supported_same_location"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0
    assert '"status"' in completed.stdout
