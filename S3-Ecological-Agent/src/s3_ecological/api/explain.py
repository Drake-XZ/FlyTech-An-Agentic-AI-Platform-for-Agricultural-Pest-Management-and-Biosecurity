"""Builds a plain-language narrative from a real AssessmentResult only.

Every sentence here is derived from fields already present on the request
or the pipeline's own result - nothing is fabricated (no Grad-CAM, no
inferred location, no manufactured confidence language).
"""

from __future__ import annotations

from ..schemas.request import ObservationRequest
from ..schemas.response import AssessmentResult

_CONTEXT_FIELDS = ("host", "trap_type", "habitat", "land_cover", "climate", "elevation_m", "season")

_NO_MORPHOLOGICAL_EXPLANATION = (
    "This demo does not provide a morphological-region (e.g. Grad-CAM) "
    "explanation of the visual prediction."
)


def build_narrative(request: ObservationRequest, result: AssessmentResult) -> list[str]:
    lines: list[str] = []

    if not result.reranked_candidates:
        lines.append(
            "No candidate could be ranked for this input. This is a research "
            "demo result, not a pest-identification or biosecurity conclusion."
        )
        lines.append(_NO_MORPHOLOGICAL_EXPLANATION)
        return lines

    top = result.reranked_candidates[0]
    top_name = top.submitted_name
    lines.append(
        f"The visual model's highest closed-set probability among the four "
        f"recognized genera is {top_name} ({top.visual_probability_raw:.1%})."
    )

    if top.rerank_score is not None:
        lines.append(
            f"After fusing with the geographic prior, {top_name} has a fused "
            f"rerank score of {top.rerank_score:.3f}. This is a within-set "
            "ranking score, not a probability that this is the correct taxon "
            "and not a species-level confirmation."
        )

    if request.location is None:
        lines.append(
            "No location was provided, so the geographic prior was not used; "
            "the ranking above is based on the visual model alone."
        )
    elif top.geo_support is None:
        lines.append(
            "The geographic prior could not produce a usable score for this "
            "request (for example, because an observation date is required "
            "but was not provided, or the geographic model is unavailable)."
        )
    else:
        lines.append(
            f"The geographic prior's support score for {top_name} at the "
            f"entered coordinates is {top.geo_support:.3f} (a model score, "
            "not an occurrence count or a confirmation of presence or absence)."
        )

    if request.location is not None and request.observed_at is None:
        lines.append(
            "No observation date was provided; the current geographic prior "
            "configuration uses date information, so this may reduce the "
            "usable geographic evidence rather than the model inventing a date."
        )

    provided_context: list[str] = []
    if request.context is not None:
        for field_name in _CONTEXT_FIELDS:
            if getattr(request.context, field_name, None) is not None:
                provided_context.append(field_name)
        if request.context.environmental_covariates:
            provided_context.extend(sorted(request.context.environmental_covariates))
    if provided_context:
        lines.append(
            "The following context fields were recorded as entered but are "
            "not currently incorporated into the visual or geographic models: "
            + ", ".join(provided_context)
            + "."
        )

    if result.review_required:
        lines.append(
            "This result is flagged for suggested manual review. This is not "
            "a confirmed incursion, a pest-quarantine conclusion, or a "
            "biosecurity determination."
        )

    if result.missing_evidence:
        lines.append(
            "Evidence noted as missing for this assessment: "
            + ", ".join(result.missing_evidence)
            + "."
        )

    lines.append(
        "Occurrence-based evidence records shown alongside this result come "
        "from a small synthetic fixture dataset used for demonstration; they "
        "are not live GBIF or ALA records, and they are not the direct input "
        "to the geographic-prior score above, which comes from a learned "
        "location model instead."
    )

    lines.append(_NO_MORPHOLOGICAL_EXPLANATION)
    return lines
