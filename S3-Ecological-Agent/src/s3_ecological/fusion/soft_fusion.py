"""Soft-fusion scoring (EarlyDesign.md Profile v0.1, "v0.1 fusion semantics").

``combined_log_score`` is a log-linear combination of the raw visual
probability and every *available* ecological component; an unavailable
component is omitted from the sum (never substituted with 0 or 1).
``rerank_score`` is a softmax of ``combined_log_score`` across only the
submitted candidate set - a within-set ranking score, not a posterior over
all possible taxa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FusionInput:
    """One candidate's scores going into fusion, in original S1 submission order."""

    candidate_id: str
    resolved_taxon_id: str | None
    visual_probability_raw: float
    geo_support: float | None
    environmental_suitability: float | None


@dataclass(frozen=True)
class FusionOutput:
    candidate_id: str
    combined_log_score: float
    rerank_score: float


def fuse(
    inputs: list[FusionInput],
    *,
    fusion_epsilon: float,
    fusion_weight_geo: float,
    fusion_weight_environment: float,
) -> list[FusionOutput]:
    """Compute ``combined_log_score`` and ``rerank_score`` for every candidate.

    Order is preserved: the returned list has the same length and order as
    ``inputs``, so a tie in ``combined_log_score`` is naturally broken by
    original S1 candidate order and then by ``resolved_taxon_id`` when the
    caller sorts the result (EarlyDesign.md: "break an exact score tie by
    the original S1 candidate order, then by stable resolved taxon
    identifier").
    """
    combined_log_scores = [
        _combined_log_score(
            item,
            fusion_epsilon=fusion_epsilon,
            fusion_weight_geo=fusion_weight_geo,
            fusion_weight_environment=fusion_weight_environment,
        )
        for item in inputs
    ]
    rerank_scores = _softmax(combined_log_scores)

    return [
        FusionOutput(
            candidate_id=item.candidate_id,
            combined_log_score=combined_log_score,
            rerank_score=rerank_score,
        )
        for item, combined_log_score, rerank_score in zip(
            inputs, combined_log_scores, rerank_scores, strict=True
        )
    ]


def _combined_log_score(
    item: FusionInput,
    *,
    fusion_epsilon: float,
    fusion_weight_geo: float,
    fusion_weight_environment: float,
) -> float:
    score = math.log(item.visual_probability_raw + fusion_epsilon)
    if item.geo_support is not None:
        score += fusion_weight_geo * math.log(item.geo_support + fusion_epsilon)
    if item.environmental_suitability is not None:
        score += fusion_weight_environment * math.log(
            item.environmental_suitability + fusion_epsilon
        )
    return score


def _softmax(values: list[float]) -> list[float]:
    """Numerically stable softmax over the submitted candidate set only."""
    if not values:
        return []
    max_value = max(values)
    exp_values = [math.exp(value - max_value) for value in values]
    total = sum(exp_values)
    return [value / total for value in exp_values]


def tie_break_key(
    candidate_id: str,
    combined_log_score: float,
    original_index: int,
    resolved_taxon_id: str | None,
) -> tuple[float, int, str]:
    """Sort key for ranking candidates by descending score with documented tie-breaks.

    Use as ``sorted(candidates, key=lambda c: tie_break_key(...))`` after
    negating ``combined_log_score`` for descending order, or wrap the call
    site's comparator accordingly - kept as plain values here rather than a
    negated tuple so the ordering rule stays readable at the call site.
    """
    return (-combined_log_score, original_index, resolved_taxon_id or candidate_id)
