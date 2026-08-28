"""Integration tests: the optional agent loop runs fully offline (EarlyDesign.md
section 16.1, "run without an external LLM").

Exercises the typed tool wrappers (``agent/tools.py``) directly and the
:class:`MockLLMProvider`, with no network access and no API credentials.
"""

from __future__ import annotations

import asyncio

from s3_ecological.agent.mock_provider import MockLLMProvider
from s3_ecological.agent.tools import (
    estimate_environmental_suitability,
    estimate_geo_prior,
    flag_out_of_range_or_unknown,
    query_occurrences,
    resolve_taxonomy,
)
from s3_ecological.interfaces.llm import AgentRequest
from s3_ecological.interfaces.priors import GeoPriorCandidateTaxon, GeoPriorRequest
from s3_ecological.interfaces.risk import CandidateRiskInput, RiskPolicyRequest
from s3_ecological.interfaces.suitability import SuitabilityCandidateTaxon, SuitabilityRequest
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider, build_taxonomy_provider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.enums import EvidenceQuality, ToolStatus
from s3_ecological.settings import S3Settings
from s3_ecological.suitability.null_model import NullSuitabilityModel


def test_resolve_taxonomy_tool_call_through_wrapper():
    settings = S3Settings()
    provider = build_taxonomy_provider(settings)
    result = resolve_taxonomy("Bactrocera", None, provider=provider)
    assert result.status == ToolStatus.SUCCESS
    assert result.data is not None
    assert result.data.resolved_taxon is not None
    assert result.data.resolved_taxon.scientific_name == "Bactrocera"


def test_query_occurrences_tool_call_through_wrapper():
    settings = S3Settings(occurrence_provider="in_memory")
    provider = build_occurrence_provider(settings)
    result = query_occurrences("fixture:bactrocera", None, None, None, provider=provider)
    assert result.status == ToolStatus.NO_RECORDS


def test_estimate_geo_prior_tool_call_through_wrapper():
    settings = S3Settings()
    occurrence_provider = build_occurrence_provider(settings)
    model = NearestDistanceGeoPriorModel(occurrence_provider, settings)
    request = GeoPriorRequest(
        candidate_taxa=[GeoPriorCandidateTaxon(candidate_id="c1", taxon_id="fixture:bactrocera")],
        latitude=0.0,
        longitude=0.0,
    )
    result = estimate_geo_prior(request, model=model)
    assert result.status in (ToolStatus.SUCCESS, ToolStatus.PARTIAL)


def test_estimate_environmental_suitability_tool_call_never_fabricates_a_score():
    model = NullSuitabilityModel()
    request = SuitabilityRequest(
        candidate_taxa=[
            SuitabilityCandidateTaxon(candidate_id="c1", taxon_id="fixture:bactrocera")
        ],
        latitude=0.0,
        longitude=0.0,
    )
    result = estimate_environmental_suitability(request, model=model)
    assert result.data is not None
    assert result.data[0].suitability is None


def test_flag_out_of_range_or_unknown_tool_call_through_wrapper():
    policy = DeterministicRiskPolicy()
    candidate = CandidateRiskInput(
        candidate_id="c1",
        taxon_id="fixture:bactrocera",
        rank=0,
        geo_support=0.9,
        usable_occurrence_count=5,
        evidence_quality=EvidenceQuality.MEDIUM,
    )
    request = RiskPolicyRequest(
        candidates=[candidate],
        location_available=True,
        incursion_rule_enabled=False,
        geo_supported_min=0.5,
        geo_ood_max=0.1,
        min_occurrences_for_ood=3,
    )
    result = flag_out_of_range_or_unknown(request, policy=policy)
    assert result.review_required is False


def test_mock_llm_provider_never_calls_the_network_and_only_rearranges_context():
    provider = MockLLMProvider()
    request = AgentRequest(
        instruction="Explain the assessment",
        context={
            "explanation": "top candidate is ecologically supported",
            "tool_calls_summary": ["a", "b"],
        },
    )
    response = asyncio.run(provider.generate(request))
    assert response.explanation == "top candidate is ecologically supported"
    assert response.tool_calls_summary == ["a", "b"]


def test_mock_llm_provider_never_invents_an_explanation_when_context_is_empty():
    provider = MockLLMProvider()
    response = asyncio.run(provider.generate(AgentRequest(instruction="Explain")))
    assert "no precomputed explanation" in response.explanation
    assert response.tool_calls_summary == []
