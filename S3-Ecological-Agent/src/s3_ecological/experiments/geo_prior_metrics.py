"""Pure-Python evaluation metrics and fixed-fusion glue for M2-C
(DesignSuggestionLog.md "2026-09-09 ... Suggested next increment: M2-C
geographic-prior reproduction and locked spatial evaluation").

No numpy, no torch - this module is imported from both the main venv (unit
tests) and, unmodified, from the isolated S1 venv (which also has pydantic
and numpy available) when the M2-C evaluation script computes locked-test
metrics. It never touches :mod:`s3_ecological.fusion.soft_fusion`'s formula -
:func:`fuse_predictions` only builds inputs for, and calls, ``fuse()``
unmodified.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from s3_ecological.fusion.soft_fusion import FusionInput, FusionOutput, fuse, tie_break_key


def confusion_matrix(truth: list[int], predicted: list[int], class_count: int) -> list[list[int]]:
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for actual, guess in zip(truth, predicted, strict=True):
        matrix[actual][guess] += 1
    return matrix


def accuracy(truth: list[int], predicted: list[int]) -> float:
    if not truth:
        return 0.0
    correct = sum(1 for actual, guess in zip(truth, predicted, strict=True) if actual == guess)
    return correct / len(truth)


def per_class_metrics(matrix: list[list[int]]) -> list[dict[str, float]]:
    """Precision/recall/F1/support for each class, in class-index order.

    An absent-both-ways class (no true instances and no predictions)
    reports precision/recall/F1 as 0.0, matching
    ``scripts/train_tf4_visual_baseline.py``'s ``_metrics`` convention.
    """
    class_count = len(matrix)
    results: list[dict[str, float]] = []
    for index in range(class_count):
        true_positive = matrix[index][index]
        false_positive = sum(matrix[row][index] for row in range(class_count)) - true_positive
        false_negative = sum(matrix[index]) - true_positive
        support = sum(matrix[index])
        precision_denominator = true_positive + false_positive
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall_denominator = true_positive + false_negative
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results.append(
            {"precision": precision, "recall": recall, "f1": f1, "support": float(support)}
        )
    return results


def macro_f1(matrix: list[list[int]]) -> float:
    per_class = per_class_metrics(matrix)
    if not per_class:
        return 0.0
    return sum(item["f1"] for item in per_class) / len(per_class)


def summarize(truth: list[int], predicted: list[int], class_count: int) -> dict[str, Any]:
    """The full metrics bundle M2-C reports: accuracy, macro precision/
    recall/F1, per-class breakdown (with support), and the confusion
    matrix."""
    matrix = confusion_matrix(truth, predicted, class_count)
    per_class = per_class_metrics(matrix)
    class_count_safe = len(per_class) or 1
    return {
        "accuracy": accuracy(truth, predicted),
        "macro_precision": sum(item["precision"] for item in per_class) / class_count_safe,
        "macro_recall": sum(item["recall"] for item in per_class) / class_count_safe,
        "macro_f1": sum(item["f1"] for item in per_class) / class_count_safe,
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def bootstrap_confidence_interval(
    truth: list[int],
    predicted: list[int],
    class_count: int,
    *,
    metric: str,
    seed: int,
    resamples: int = 2000,
    lower_percentile: float = 2.5,
    upper_percentile: float = 97.5,
) -> tuple[float, float]:
    """Fixed-seed observation-level bootstrap confidence interval for
    ``metric`` in ``{"accuracy", "macro_f1"}``. Resampling (with
    replacement) is over observation indices, driven entirely by
    ``random.Random(seed)`` - identical inputs and seed always produce an
    identical interval."""
    if metric not in {"accuracy", "macro_f1"}:
        raise ValueError(f"unsupported bootstrap metric: {metric!r}")
    if not truth:
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(truth)
    values: list[float] = []
    for _ in range(resamples):
        indices = [rng.randrange(n) for _ in range(n)]
        sample_truth = [truth[i] for i in indices]
        sample_predicted = [predicted[i] for i in indices]
        if metric == "accuracy":
            values.append(accuracy(sample_truth, sample_predicted))
        else:
            values.append(macro_f1(confusion_matrix(sample_truth, sample_predicted, class_count)))

    values.sort()
    return (_percentile(values, lower_percentile), _percentile(values, upper_percentile))


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    return sorted_values[lower_index] + fraction * (
        sorted_values[upper_index] - sorted_values[lower_index]
    )


@dataclass(frozen=True)
class GeoFusionCandidate:
    """One candidate's inputs for :func:`fuse_predictions`, in original S1
    submission order."""

    candidate_id: str
    resolved_taxon_id: str | None
    visual_probability_raw: float
    geo_support: float | None


def fuse_predictions(
    candidates: list[GeoFusionCandidate],
    *,
    fusion_epsilon: float,
    fusion_weight_geo: float,
    fusion_weight_environment: float,
) -> list[FusionOutput]:
    """Thin glue over :func:`s3_ecological.fusion.soft_fusion.fuse` - never
    reimplements the formula. ``environmental_suitability`` is always
    ``None`` here: M2-C evaluates a visual+geographic fusion only, and the
    Profile v0.1 default ``fusion_weight_environment=0.0`` means an absent
    environmental term is mathematically inert regardless."""
    inputs = [
        FusionInput(
            candidate_id=candidate.candidate_id,
            resolved_taxon_id=candidate.resolved_taxon_id,
            visual_probability_raw=candidate.visual_probability_raw,
            geo_support=candidate.geo_support,
            environmental_suitability=None,
        )
        for candidate in candidates
    ]
    return fuse(
        inputs,
        fusion_epsilon=fusion_epsilon,
        fusion_weight_geo=fusion_weight_geo,
        fusion_weight_environment=fusion_weight_environment,
    )


def top_candidate_id(candidates: list[GeoFusionCandidate], outputs: list[FusionOutput]) -> str:
    """The winning ``candidate_id`` after applying the documented tie-break
    order (:func:`s3_ecological.fusion.soft_fusion.tie_break_key`): highest
    ``combined_log_score``, then original submission order, then stable
    resolved taxon identifier."""
    ranked = sorted(
        enumerate(zip(candidates, outputs, strict=True)),
        key=lambda entry: tie_break_key(
            entry[1][1].candidate_id,
            entry[1][1].combined_log_score,
            entry[0],
            entry[1][0].resolved_taxon_id,
        ),
    )
    return ranked[0][1][1].candidate_id
