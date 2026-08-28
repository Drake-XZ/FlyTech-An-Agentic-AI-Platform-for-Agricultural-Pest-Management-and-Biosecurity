"""Typed tool wrappers for an optional agent loop (EarlyDesign.md section 7.3).

Each function is a thin, synchronous call-through to a deterministic
Protocol implementation (``TaxonomyProvider``, ``OccurrenceProvider``,
``GeoPriorModel``, ``SuitabilityModel``, ``RiskPolicy``). They exist so an
agent layer - the mock provider, or a future ``pydantic_ai`` agent - has a
flat, typed function surface to select from ("resolve_taxonomy",
"query_occurrences", ...) without importing or reimplementing any
ecological logic itself. None of these functions computes a score or
threshold; they only forward to the already-implemented deterministic core.
"""

from __future__ import annotations

from datetime import date

from s3_ecological.interfaces.occurrence import (
    OccurrenceProvider,
    OccurrenceQuery,
    RawOccurrenceRecord,
)
from s3_ecological.interfaces.priors import (
    CandidateGeoSupport,
    GeoPriorModel,
    GeoPriorRequest,
)
from s3_ecological.interfaces.risk import RiskPolicy, RiskPolicyRequest, RiskPolicyResult
from s3_ecological.interfaces.suitability import (
    CandidateSuitability,
    SuitabilityModel,
    SuitabilityRequest,
)
from s3_ecological.interfaces.taxonomy import TaxonomyProvider, TaxonomyQuery, TaxonomyResolution
from s3_ecological.schemas.common import ToolResult


def resolve_taxonomy(
    name: str, rank: str | None, *, provider: TaxonomyProvider
) -> ToolResult[TaxonomyResolution]:
    return provider.resolve(TaxonomyQuery(name=name, rank=rank))


def query_occurrences(
    taxon_id: str,
    region: dict[str, float] | None,
    time_range: tuple[date, date] | None,
    quality_filters: dict[str, object] | None,
    *,
    provider: OccurrenceProvider,
) -> ToolResult[list[RawOccurrenceRecord]]:
    return provider.query(
        OccurrenceQuery(
            taxon_id=taxon_id,
            region=region,
            time_range=time_range,
            quality_filters=quality_filters,
        )
    )


def estimate_geo_prior(
    request: GeoPriorRequest, *, model: GeoPriorModel
) -> ToolResult[list[CandidateGeoSupport]]:
    return model.estimate(request)


def estimate_environmental_suitability(
    request: SuitabilityRequest, *, model: SuitabilityModel
) -> ToolResult[list[CandidateSuitability]]:
    return model.estimate(request)


def flag_out_of_range_or_unknown(
    request: RiskPolicyRequest, *, policy: RiskPolicy
) -> RiskPolicyResult:
    return policy.evaluate(request)
