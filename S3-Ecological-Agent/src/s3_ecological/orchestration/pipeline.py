"""Deterministic Observe-Reason-Act-Learn pipeline (EarlyDesign.md section 7).

``run_assessment`` is the one library entry point required by the DoD
(section 23.1, "one deterministic library entry point"). It never imports
``pydantic_ai`` or ``fastapi`` and never calls an LLM: every score, state,
and evidence link comes from the deterministic modules it wires together
(``taxonomy``, ``occurrence``, ``priors``, ``suitability``, ``fusion``,
``risk``, ``evidence``). An optional agent layer (``agent/``) may call this
function and then substitute only ``explanation`` with an LLM-authored
summary; it must never re-derive an authoritative field itself.

``analysis_id`` and ``generated_at`` are supplied by the caller rather than
generated here (``uuid4()``/``datetime.now()``) so this function stays a
pure, deterministic function of its inputs - required for reproducible
tests and for the "ecological core logic must be deterministic" DoD item.
"""

from __future__ import annotations

from datetime import datetime

from s3_ecological.evidence.records import build_evidence_records
from s3_ecological.fusion.soft_fusion import FusionInput, fuse, tie_break_key
from s3_ecological.interfaces.occurrence import OccurrenceProvider, OccurrenceQuery
from s3_ecological.interfaces.priors import (
    GeoPriorCandidateTaxon,
    GeoPriorModel,
    GeoPriorRequest,
)
from s3_ecological.interfaces.risk import CandidateRiskInput, RiskPolicy, RiskPolicyRequest
from s3_ecological.interfaces.suitability import (
    SuitabilityCandidateTaxon,
    SuitabilityModel,
    SuitabilityRequest,
)
from s3_ecological.interfaces.taxonomy import TaxonomyProvider
from s3_ecological.occurrence.cleaning import clean_occurrences
from s3_ecological.orchestration.validation import (
    validate_candidate_probabilities,
    validate_no_duplicate_resolved_taxa,
    validate_schema_version,
)
from s3_ecological.schemas.common import Issue
from s3_ecological.schemas.enums import (
    AssessmentStatus,
    EcologicalState,
    EvidenceQuality,
    IssueCode,
    RiskState,
    UncertaintyLevel,
)
from s3_ecological.schemas.request import ObservationRequest, VisualCandidate
from s3_ecological.schemas.response import (
    AssessmentResult,
    EvidenceRecord,
    RerankedCandidate,
    ResolvedTaxon,
    UncertaintyInfo,
)
from s3_ecological.settings import S3Settings
from s3_ecological.taxonomy.resolve import resolve_candidate_names

# The output-contract version this build implements (EarlyDesign.md section 9).
RESPONSE_SCHEMA_VERSION = "1.0.0"
SUPPORTED_REQUEST_SCHEMA_VERSIONS = frozenset({"1.0.0"})


def run_assessment(
    request: ObservationRequest,
    *,
    settings: S3Settings,
    taxonomy_provider: TaxonomyProvider,
    occurrence_provider: OccurrenceProvider,
    geo_prior_model: GeoPriorModel,
    suitability_model: SuitabilityModel,
    risk_policy: RiskPolicy,
    analysis_id: str,
    generated_at: datetime,
) -> AssessmentResult:
    """Run one deterministic S3 assessment. Never raises for a handled input.

    An unexpected internal failure is caught and reported as
    ``AssessmentStatus.FAILED`` with a redacted error (EarlyDesign.md
    section 9, "failed") rather than propagating a traceback to the caller.
    """
    try:
        return _run_assessment_body(
            request,
            settings=settings,
            taxonomy_provider=taxonomy_provider,
            occurrence_provider=occurrence_provider,
            geo_prior_model=geo_prior_model,
            suitability_model=suitability_model,
            risk_policy=risk_policy,
            analysis_id=analysis_id,
            generated_at=generated_at,
        )
    except Exception as exc:  # noqa: BLE001 - last-resort safety net, see docstring
        return _failed_result(
            request,
            settings=settings,
            analysis_id=analysis_id,
            generated_at=generated_at,
            error_type=type(exc).__name__,
        )


def _run_assessment_body(
    request: ObservationRequest,
    *,
    settings: S3Settings,
    taxonomy_provider: TaxonomyProvider,
    occurrence_provider: OccurrenceProvider,
    geo_prior_model: GeoPriorModel,
    suitability_model: SuitabilityModel,
    risk_policy: RiskPolicy,
    analysis_id: str,
    generated_at: datetime,
) -> AssessmentResult:
    validation_errors = [
        *validate_schema_version(request, SUPPORTED_REQUEST_SCHEMA_VERSIONS),
        *validate_candidate_probabilities(request, settings),
    ]
    if validation_errors:
        return _validation_failure_result(
            request, settings=settings, analysis_id=analysis_id, generated_at=generated_at,
            errors=validation_errors,
        )

    # Reason steps 2 and 5: resolve names/synonyms, then evaluate record quality.
    resolution_by_name = resolve_candidate_names(
        [candidate.name for candidate in request.visual_candidates], taxonomy_provider
    )
    resolved_taxon_by_candidate_id = {
        candidate.candidate_id: _resolved_taxon_for(candidate, resolution_by_name)
        for candidate in request.visual_candidates
    }

    duplicate_errors = validate_no_duplicate_resolved_taxa(
        {
            candidate_id: _taxon_id_or_none(resolved, settings.taxonomy_provider)
            for candidate_id, resolved in resolved_taxon_by_candidate_id.items()
        }
    )
    if duplicate_errors:
        return _validation_failure_result(
            request, settings=settings, analysis_id=analysis_id, generated_at=generated_at,
            errors=duplicate_errors,
        )

    warnings: list[Issue] = []
    errors: list[Issue] = []
    for result in resolution_by_name.values():
        warnings.extend(result.warnings)
        errors.extend(result.errors)

    location_available = request.location is not None
    location = request.location
    missing_evidence: list[str] = []
    requested_evidence: list[str] = []
    if not location_available:
        missing_evidence.append("location")
        requested_evidence.append("location")

    geo_support_by_candidate_id: dict[str, object] = {}
    evidence_records: list[EvidenceRecord] = []
    resolved_candidates = [
        candidate
        for candidate in request.visual_candidates
        if resolved_taxon_by_candidate_id[candidate.candidate_id] is not None
    ]

    if location is not None and resolved_candidates:
        geo_request = GeoPriorRequest(
            candidate_taxa=[
                GeoPriorCandidateTaxon(candidate_id=candidate.candidate_id, taxon_id=taxon_id)
                for candidate in resolved_candidates
                if (
                    taxon_id := _taxon_id_or_none(
                        resolved_taxon_by_candidate_id[candidate.candidate_id],
                        settings.taxonomy_provider,
                    )
                )
                is not None
            ],
            latitude=location.latitude,
            longitude=location.longitude,
            observed_at=request.observed_at,
        )
        geo_result = geo_prior_model.estimate(geo_request)
        warnings.extend(geo_result.warnings)
        errors.extend(geo_result.errors)
        geo_support_by_candidate_id = {
            item.candidate_id: item for item in (geo_result.data or [])
        }
        evidence_records = _collect_evidence(
            resolved_candidates, resolved_taxon_by_candidate_id, occurrence_provider,
            settings=settings, retrieved_at=generated_at,
        )

    suitability_by_candidate_id: dict[str, object] = {}
    if location is not None and resolved_candidates:
        suitability_request = SuitabilityRequest(
            candidate_taxa=[
                SuitabilityCandidateTaxon(candidate_id=candidate.candidate_id, taxon_id=taxon_id)
                for candidate in resolved_candidates
                if (
                    taxon_id := _taxon_id_or_none(
                        resolved_taxon_by_candidate_id[candidate.candidate_id],
                        settings.taxonomy_provider,
                    )
                )
                is not None
            ],
            latitude=location.latitude,
            longitude=location.longitude,
        )
        suitability_result = suitability_model.estimate(suitability_request)
        warnings.extend(suitability_result.warnings)
        errors.extend(suitability_result.errors)
        suitability_by_candidate_id = {
            item.candidate_id: item for item in (suitability_result.data or [])
        }

    fusion_inputs = [
        FusionInput(
            candidate_id=candidate.candidate_id,
            resolved_taxon_id=_taxon_id_or_none(
                resolved_taxon_by_candidate_id[candidate.candidate_id], settings.taxonomy_provider
            ),
            visual_probability_raw=candidate.visual_probability,
            geo_support=_geo_support_value(geo_support_by_candidate_id.get(candidate.candidate_id)),
            environmental_suitability=_suitability_value(
                suitability_by_candidate_id.get(candidate.candidate_id)
            ),
        )
        for candidate in request.visual_candidates
    ]
    fusion_outputs = {
        output.candidate_id: output
        for output in fuse(
            fusion_inputs,
            fusion_epsilon=settings.fusion_epsilon,
            fusion_weight_geo=settings.fusion_weight_geo,
            fusion_weight_environment=settings.fusion_weight_environment,
        )
    }

    risk_candidates = [
        CandidateRiskInput(
            candidate_id=candidate.candidate_id,
            taxon_id=_taxon_id_or_none(
                (resolved_taxon := resolved_taxon_by_candidate_id[candidate.candidate_id]),
                settings.taxonomy_provider,
            ),
            rank=rank,
            geo_support=_geo_support_value(geo_support_by_candidate_id.get(candidate.candidate_id)),
            usable_occurrence_count=_usable_count(
                geo_support_by_candidate_id.get(candidate.candidate_id)
            ),
            evidence_quality=_evidence_quality(geo_support_by_candidate_id.get(candidate.candidate_id)),
            environmental_conflict=False,
            ambiguous_taxonomy=bool(resolved_taxon and resolved_taxon.ambiguous),
        )
        for rank, candidate in enumerate(
            _rerank_order(
                request.visual_candidates,
                fusion_outputs,
                resolved_taxon_by_candidate_id,
                settings.taxonomy_provider,
            )
        )
    ]
    risk_result = risk_policy.evaluate(
        RiskPolicyRequest(
            candidates=risk_candidates,
            location_available=location_available,
            incursion_rule_enabled=settings.incursion_rule_enabled,
            geo_supported_min=settings.geo_supported_min,
            geo_ood_max=settings.geo_ood_max,
            min_occurrences_for_ood=settings.min_occurrences_for_ood,
        )
    )

    reranked_candidates = [
        _build_reranked_candidate(
            candidate,
            resolved_taxon_by_candidate_id[candidate.candidate_id],
            fusion_outputs[candidate.candidate_id],
            geo_support_by_candidate_id.get(candidate.candidate_id),
            risk_result.candidate_states[candidate.candidate_id],
        )
        for candidate in _rerank_order(
            request.visual_candidates,
            fusion_outputs,
            resolved_taxon_by_candidate_id,
            settings.taxonomy_provider,
        )
    ]

    top_candidate = reranked_candidates[0]
    review_required = risk_result.review_required
    review_reasons = list(risk_result.review_reasons)

    status = (
        AssessmentStatus.COMPLETED_WITH_WARNINGS
        if warnings or errors or missing_evidence
        else AssessmentStatus.COMPLETED
    )

    return AssessmentResult(
        schema_version=RESPONSE_SCHEMA_VERSION,
        observation_id=request.observation_id,
        analysis_id=analysis_id,
        status=status,
        reranked_candidates=reranked_candidates,
        risk_state=risk_result.case_risk_state,
        review_required=review_required,
        review_reasons=review_reasons,
        uncertainty=_uncertainty_for(top_candidate, missing_evidence),
        missing_evidence=missing_evidence,
        requested_evidence=requested_evidence,
        evidence=evidence_records,
        warnings=warnings,
        errors=errors,
        profile_version=settings.profile_version,
        configuration_version=settings.configuration_version,
        model_versions=_model_versions(request),
        threshold_versions={"s3_risk_policy": "deterministic-v0.1"},
        data_snapshot_versions=_data_snapshot_versions(evidence_records),
        explanation=_build_explanation(
            request, top_candidate, risk_result.case_risk_state, missing_evidence
        ),
        generated_at=generated_at,
    )


def _resolved_taxon_for(
    candidate: VisualCandidate, resolution_by_name: dict
) -> ResolvedTaxon | None:
    resolution = resolution_by_name[candidate.name].data
    return resolution.resolved_taxon if resolution else None


def _taxon_id_or_none(resolved: ResolvedTaxon | None, taxonomy_provider_key: str) -> str | None:
    """Read the taxon id keyed by the configured taxonomy provider's name.

    ``ResolvedTaxon.taxon_ids`` is a ``{provider_name: id}`` map so a future
    live GBIF/ALA taxonomy provider can coexist with the fixture provider
    without changing this lookup - only ``settings.taxonomy_provider``
    selects which key the pipeline reads.
    """
    if resolved is None:
        return None
    return resolved.taxon_ids.get(taxonomy_provider_key)


def _geo_support_value(geo_support) -> float | None:
    return geo_support.geo_support if geo_support is not None else None


def _usable_count(geo_support) -> int:
    return geo_support.usable_occurrence_count if geo_support is not None else 0


def _evidence_quality(geo_support) -> EvidenceQuality:
    return geo_support.evidence_quality if geo_support is not None else EvidenceQuality.INSUFFICIENT


def _suitability_value(suitability) -> float | None:
    return suitability.suitability if suitability is not None else None


def _rerank_order(
    candidates: list[VisualCandidate],
    fusion_outputs: dict,
    resolved_taxon_by_candidate_id: dict,
    taxonomy_provider_key: str,
) -> list[VisualCandidate]:
    """Descending combined_log_score, tie-broken by original order then taxon id.

    EarlyDesign.md: "break an exact score tie by the original S1 candidate
    order, then by stable resolved taxon identifier."
    """
    return sorted(
        candidates,
        key=lambda candidate: tie_break_key(
            candidate.candidate_id,
            fusion_outputs[candidate.candidate_id].combined_log_score,
            candidates.index(candidate),
            _taxon_id_or_none(
                resolved_taxon_by_candidate_id[candidate.candidate_id], taxonomy_provider_key
            ),
        ),
    )


def _build_reranked_candidate(
    candidate: VisualCandidate,
    resolved_taxon: ResolvedTaxon | None,
    fusion_output,
    geo_support,
    ecological_state: EcologicalState,
) -> RerankedCandidate:
    return RerankedCandidate(
        submitted_name=candidate.name,
        candidate_id=candidate.candidate_id,
        resolved_taxon=resolved_taxon,
        visual_probability_raw=candidate.visual_probability,
        geo_support=_geo_support_value(geo_support),
        min_occurrence_distance_km=(
            geo_support.min_occurrence_distance_km if geo_support is not None else None
        ),
        usable_occurrence_count=_usable_count(geo_support),
        temporal_support=None,
        environmental_suitability=None,
        combined_log_score=fusion_output.combined_log_score,
        rerank_score=fusion_output.rerank_score,
        ecological_state=ecological_state,
        evidence_quality=_evidence_quality(geo_support),
        conflicts=[],
        supporting_evidence_ids=(geo_support.supporting_evidence_ids if geo_support else []),
    )


def _collect_evidence(
    resolved_candidates: list[VisualCandidate],
    resolved_taxon_by_candidate_id: dict,
    occurrence_provider: OccurrenceProvider,
    *,
    settings: S3Settings,
    retrieved_at: datetime,
) -> list[EvidenceRecord]:
    """Build the full traceable evidence list for the response.

    Queries occurrences once per distinct resolved taxon. This repeats the
    query already made inside ``geo_prior_model.estimate`` rather than
    having that Protocol leak raw records back into the pipeline - keeping
    the geographic-prior boundary a pure scoring interface (EarlyDesign.md
    section 6.4) is worth the duplicate, in-memory, offline query.
    """
    evidence: list[EvidenceRecord] = []
    seen_taxon_ids: set[str] = set()
    for candidate in resolved_candidates:
        taxon_id = _taxon_id_or_none(
            resolved_taxon_by_candidate_id[candidate.candidate_id], settings.taxonomy_provider
        )
        if taxon_id is None or taxon_id in seen_taxon_ids:
            continue
        seen_taxon_ids.add(taxon_id)
        occurrence_result = occurrence_provider.query(OccurrenceQuery(taxon_id=taxon_id))
        records = occurrence_result.data or []
        cleaned = clean_occurrences(records, settings).cleaned
        evidence.extend(build_evidence_records(cleaned, retrieved_at))
    return evidence


def _uncertainty_for(
    top_candidate: RerankedCandidate, missing_evidence: list[str]
) -> UncertaintyInfo:
    """A v0.1 heuristic derived from ecological_state/evidence_quality - not a
    validated uncertainty model.
    """
    reasons: list[str] = list(missing_evidence)
    if top_candidate.ecological_state == EcologicalState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE:
        reasons.append("insufficient_ecological_evidence")
        return UncertaintyInfo(level=UncertaintyLevel.HIGH, reasons=reasons)
    if top_candidate.evidence_quality == EvidenceQuality.LOW or top_candidate.ecological_state in (
        EcologicalState.WEAK_ECOLOGICAL_SUPPORT,
        EcologicalState.GEOGRAPHIC_OOD,
        EcologicalState.ENVIRONMENTAL_CONFLICT,
    ):
        reasons.append("low_or_conflicting_evidence")
        return UncertaintyInfo(level=UncertaintyLevel.MEDIUM, reasons=reasons)
    return UncertaintyInfo(level=UncertaintyLevel.LOW, reasons=reasons)


def _model_versions(request: ObservationRequest) -> dict[str, str]:
    return {
        candidate.candidate_id: candidate.model_version
        for candidate in request.visual_candidates
        if candidate.model_version is not None
    }


def _data_snapshot_versions(evidence_records: list[EvidenceRecord]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for record in evidence_records:
        if record.snapshot_or_cache_key is not None:
            versions[record.source] = record.snapshot_or_cache_key
    return versions


def _build_explanation(
    request: ObservationRequest,
    top_candidate: RerankedCandidate,
    risk_state: RiskState,
    missing_evidence: list[str],
) -> str:
    """A deterministic, template-based explanation - no LLM required.

    An optional agent layer may replace this string with an LLM-authored
    summary of the same facts; it must never change any other field.
    """
    resolved_name = (
        top_candidate.resolved_taxon.scientific_name
        if top_candidate.resolved_taxon
        else "unresolved"
    )
    parts = [
        f"Top candidate '{top_candidate.submitted_name}' (resolved: {resolved_name}) "
        f"has visual_probability_raw={top_candidate.visual_probability_raw:.4f}, "
        f"geo_support={top_candidate.geo_support}, risk_state={risk_state.value}."
    ]
    if missing_evidence:
        parts.append(f"Missing evidence: {', '.join(missing_evidence)}.")
    return " ".join(parts)


def _validation_failure_result(
    request: ObservationRequest,
    *,
    settings: S3Settings,
    analysis_id: str,
    generated_at: datetime,
    errors: list[Issue],
) -> AssessmentResult:
    return AssessmentResult(
        schema_version=RESPONSE_SCHEMA_VERSION,
        observation_id=request.observation_id,
        analysis_id=analysis_id,
        status=AssessmentStatus.FAILED_VALIDATION,
        reranked_candidates=[],
        risk_state=RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE,
        review_required=True,
        review_reasons=["failed_validation"],
        uncertainty=UncertaintyInfo(level=UncertaintyLevel.HIGH, reasons=["failed_validation"]),
        missing_evidence=[],
        requested_evidence=[],
        evidence=[],
        warnings=[],
        errors=errors,
        profile_version=settings.profile_version,
        configuration_version=settings.configuration_version,
        model_versions={},
        threshold_versions={},
        data_snapshot_versions={},
        explanation="Request failed profile-dependent validation; see errors.",
        generated_at=generated_at,
    )


def _failed_result(
    request: ObservationRequest,
    *,
    settings: S3Settings,
    analysis_id: str,
    generated_at: datetime,
    error_type: str,
) -> AssessmentResult:
    return AssessmentResult(
        schema_version=RESPONSE_SCHEMA_VERSION,
        observation_id=request.observation_id,
        analysis_id=analysis_id,
        status=AssessmentStatus.FAILED,
        reranked_candidates=[],
        risk_state=RiskState.UNKNOWN_OR_INSUFFICIENT_EVIDENCE,
        review_required=True,
        review_reasons=["internal_processing_failure"],
        uncertainty=UncertaintyInfo(
            level=UncertaintyLevel.HIGH, reasons=["internal_processing_failure"]
        ),
        missing_evidence=[],
        requested_evidence=[],
        evidence=[],
        warnings=[],
        errors=[
            Issue(
                code=IssueCode.INVALID_RESPONSE,
                message=f"internal processing failure ({error_type}); see server-side logs",
                component="orchestration.pipeline",
                retryable=False,
            )
        ],
        profile_version=settings.profile_version,
        configuration_version=settings.configuration_version,
        model_versions={},
        threshold_versions={},
        data_snapshot_versions={},
        explanation=(
            "No safe assessment could be returned because of an internal processing failure."
        ),
        generated_at=generated_at,
    )
