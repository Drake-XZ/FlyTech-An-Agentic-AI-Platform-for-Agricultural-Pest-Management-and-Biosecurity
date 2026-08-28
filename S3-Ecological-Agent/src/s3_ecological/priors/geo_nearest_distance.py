"""v0.1 nearest-clean-occurrence geographic baseline.

EarlyDesign.md Profile v0.1, "Deterministic geographic baseline" steps 1-7:
clean occurrence records, take the haversine distance to the nearest usable
one, and convert it to a support score. This exists to prove the request,
scoring, and risk contracts end-to-end before a learned geographic prior
(Baseline B, Milestone 2) implements the same :class:`GeoPriorModel`
Protocol.
"""

from __future__ import annotations

import math

from s3_ecological.evidence.records import evidence_id_for_occurrence
from s3_ecological.interfaces.occurrence import (
    OccurrenceProvider,
    OccurrenceQuery,
    RawOccurrenceRecord,
)
from s3_ecological.interfaces.priors import (
    CandidateGeoSupport,
    GeoPriorCandidateTaxon,
    GeoPriorModel,
    GeoPriorRequest,
)
from s3_ecological.occurrence.cleaning import clean_occurrences
from s3_ecological.occurrence.distance import haversine_km
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import EvidenceQuality, IssueCode, ToolStatus
from s3_ecological.settings import S3Settings


class NearestDistanceGeoPriorModel(GeoPriorModel):
    """Deterministic v0.1 baseline: geo_support from nearest usable occurrence distance."""

    def __init__(self, occurrence_provider: OccurrenceProvider, settings: S3Settings):
        self._occurrence_provider = occurrence_provider
        self._settings = settings

    def estimate(self, request: GeoPriorRequest) -> ToolResult[list[CandidateGeoSupport]]:
        results: list[CandidateGeoSupport] = []
        warnings: list[Issue] = []
        errors: list[Issue] = []
        degraded = False

        for candidate in request.candidate_taxa:
            occurrence_result = self._occurrence_provider.query(
                OccurrenceQuery(taxon_id=candidate.taxon_id)
            )

            if occurrence_result.status == ToolStatus.PROVIDER_NOT_CONFIGURED:
                degraded = True
                errors.extend(occurrence_result.errors)
                results.append(_insufficient_support(candidate))
                continue

            if occurrence_result.status not in (ToolStatus.SUCCESS, ToolStatus.NO_RECORDS):
                degraded = True
                errors.extend(occurrence_result.errors)
                warnings.extend(occurrence_result.warnings)
                results.append(_insufficient_support(candidate))
                continue

            records = occurrence_result.data or []
            usable = clean_occurrences(records, self._settings).usable

            if not usable:
                warnings.append(
                    Issue(
                        code=IssueCode.NO_RECORDS,
                        message=(
                            f"No usable occurrence records for taxon "
                            f"'{candidate.taxon_id}' after cleaning"
                        ),
                        component="priors.geo_nearest_distance",
                        retryable=False,
                    )
                )
                results.append(_insufficient_support(candidate))
                continue

            min_distance_km = min(
                _distance_to_usable_record(request, item.record) for item in usable
            )
            geo_support = math.exp(-min_distance_km / self._settings.geo_distance_scale_km)

            results.append(
                CandidateGeoSupport(
                    candidate_id=candidate.candidate_id,
                    taxon_id=candidate.taxon_id,
                    geo_support=geo_support,
                    min_occurrence_distance_km=min_distance_km,
                    usable_occurrence_count=len(usable),
                    evidence_quality=_evidence_quality_for_count(len(usable), self._settings),
                    supporting_evidence_ids=[
                        evidence_id_for_occurrence(item.record) for item in usable
                    ],
                )
            )

        status = ToolStatus.PARTIAL if degraded else ToolStatus.SUCCESS
        return ToolResult(status=status, data=results, warnings=warnings, errors=errors)


def _distance_to_usable_record(request: GeoPriorRequest, record: RawOccurrenceRecord) -> float:
    """Haversine distance to one record already filtered to ``usable_for_distance``.

    That filter (``occurrence/cleaning.py``) guarantees valid, non-null
    coordinates, but the schema still types them as optional for records in
    general - the assert documents and enforces that invariant here rather
    than silently coercing ``None`` to a bogus coordinate.
    """
    assert record.latitude is not None and record.longitude is not None
    return haversine_km(request.latitude, request.longitude, record.latitude, record.longitude)


def _insufficient_support(candidate: GeoPriorCandidateTaxon) -> CandidateGeoSupport:
    """No usable evidence: EarlyDesign.md step 5, "return geo_support=null ...
    do not return zero and do not infer absence".
    """
    return CandidateGeoSupport(
        candidate_id=candidate.candidate_id,
        taxon_id=candidate.taxon_id,
        geo_support=None,
        min_occurrence_distance_km=None,
        usable_occurrence_count=0,
        evidence_quality=EvidenceQuality.INSUFFICIENT,
        supporting_evidence_ids=[],
    )


def _evidence_quality_for_count(usable_count: int, settings: S3Settings) -> EvidenceQuality:
    """Steps 5-7: insufficient (0), low (1-2 by default), medium (>= min_occurrences_for_ood).

    ``high`` is reserved for a future validated policy and is never produced
    by this baseline.
    """
    if usable_count >= settings.min_occurrences_for_ood:
        return EvidenceQuality.MEDIUM
    if usable_count >= 1:
        return EvidenceQuality.LOW
    return EvidenceQuality.INSUFFICIENT
