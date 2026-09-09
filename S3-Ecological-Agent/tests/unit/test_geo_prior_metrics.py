"""Unit tests for M2-C's pure-Python metrics and fixed-fusion glue
(DesignSuggestionLog.md "2026-09-09 ... Suggested next increment: M2-C
geographic-prior reproduction and locked spatial evaluation").

The fixed-fusion tests pin Prototype Implementation Profile v0.1's frozen
soft-fusion constants and hand-compute the expected log-linear score, so
this fails loudly if either the frozen constants or
``fusion.soft_fusion``'s formula ever change.
"""

from __future__ import annotations

import math

from s3_ecological.experiments.geo_prior_metrics import (
    GeoFusionCandidate,
    accuracy,
    bootstrap_confidence_interval,
    confusion_matrix,
    fuse_predictions,
    macro_f1,
    per_class_metrics,
    summarize,
    top_candidate_id,
)
from s3_ecological.settings import S3Settings

# Prototype Implementation Profile v0.1 frozen defaults (settings.py) - pinned
# here, not re-derived, so a change to the frozen values breaks this test
# rather than silently changing M2-C's evaluation.
_FROZEN_FUSION_EPSILON = 0.000001
_FROZEN_FUSION_WEIGHT_GEO = 1.0
_FROZEN_FUSION_WEIGHT_ENVIRONMENT = 0.0


def test_frozen_fusion_constants_match_profile_v0_1_defaults():
    settings = S3Settings()
    assert settings.fusion_epsilon == _FROZEN_FUSION_EPSILON
    assert settings.fusion_weight_geo == _FROZEN_FUSION_WEIGHT_GEO
    assert settings.fusion_weight_environment == _FROZEN_FUSION_WEIGHT_ENVIRONMENT


def test_confusion_matrix_and_accuracy_hand_computed():
    truth = [0, 0, 1, 1, 1]
    predicted = [0, 1, 1, 1, 0]
    matrix = confusion_matrix(truth, predicted, class_count=2)
    assert matrix == [[1, 1], [1, 2]]
    assert accuracy(truth, predicted) == 3 / 5


def test_per_class_metrics_and_macro_f1_hand_computed():
    # class 0: TP=1, FP=1 (from class 1), FN=1 -> precision=0.5, recall=0.5, f1=0.5
    # class 1: TP=2, FP=1, FN=1 -> precision=2/3, recall=2/3, f1=2/3
    matrix = [[1, 1], [1, 2]]
    per_class = per_class_metrics(matrix)
    assert per_class[0]["precision"] == 0.5
    assert per_class[0]["recall"] == 0.5
    assert per_class[0]["f1"] == 0.5
    assert per_class[0]["support"] == 2.0
    assert math.isclose(per_class[1]["precision"], 2 / 3)
    assert math.isclose(per_class[1]["recall"], 2 / 3)
    assert math.isclose(per_class[1]["f1"], 2 / 3)
    assert per_class[1]["support"] == 3.0
    assert math.isclose(macro_f1(matrix), (0.5 + 2 / 3) / 2)


def test_summarize_matches_hand_computed_totals():
    truth = [0, 0, 1, 1, 1]
    predicted = [0, 1, 1, 1, 0]
    result = summarize(truth, predicted, class_count=2)
    assert result["accuracy"] == 3 / 5
    assert math.isclose(result["macro_f1"], (0.5 + 2 / 3) / 2)
    assert result["confusion_matrix"] == [[1, 1], [1, 2]]
    assert len(result["per_class"]) == 2


def test_empty_class_reports_zero_not_a_crash():
    matrix = confusion_matrix([], [], class_count=3)
    per_class = per_class_metrics(matrix)
    assert all(item["precision"] == 0.0 for item in per_class)
    assert all(item["f1"] == 0.0 for item in per_class)
    assert accuracy([], []) == 0.0


def test_bootstrap_confidence_interval_is_deterministic_given_fixed_seed():
    truth = [0, 0, 1, 1, 1, 0, 1, 0, 1, 1]
    predicted = [0, 1, 1, 1, 0, 0, 1, 1, 1, 0]

    first = bootstrap_confidence_interval(
        truth, predicted, class_count=2, metric="accuracy", seed=42, resamples=200
    )
    second = bootstrap_confidence_interval(
        truth, predicted, class_count=2, metric="accuracy", seed=42, resamples=200
    )
    assert first == second

    lower, upper = first
    assert 0.0 <= lower <= upper <= 1.0


def test_bootstrap_confidence_interval_macro_f1_is_deterministic_given_fixed_seed():
    truth = [0, 0, 1, 1, 1, 0, 1, 0, 1, 1]
    predicted = [0, 1, 1, 1, 0, 0, 1, 1, 1, 0]

    first = bootstrap_confidence_interval(
        truth, predicted, class_count=2, metric="macro_f1", seed=42, resamples=200
    )
    second = bootstrap_confidence_interval(
        truth, predicted, class_count=2, metric="macro_f1", seed=42, resamples=200
    )
    assert first == second


def test_fuse_predictions_matches_hand_computed_log_linear_score():
    candidates = [
        GeoFusionCandidate(
            candidate_id="a", resolved_taxon_id="t:a", visual_probability_raw=0.7, geo_support=0.9
        ),
        GeoFusionCandidate(
            candidate_id="b", resolved_taxon_id="t:b", visual_probability_raw=0.3, geo_support=None
        ),
    ]
    outputs = fuse_predictions(
        candidates,
        fusion_epsilon=_FROZEN_FUSION_EPSILON,
        fusion_weight_geo=_FROZEN_FUSION_WEIGHT_GEO,
        fusion_weight_environment=_FROZEN_FUSION_WEIGHT_ENVIRONMENT,
    )

    expected_a = math.log(0.7 + _FROZEN_FUSION_EPSILON) + _FROZEN_FUSION_WEIGHT_GEO * math.log(
        0.9 + _FROZEN_FUSION_EPSILON
    )
    expected_b = math.log(0.3 + _FROZEN_FUSION_EPSILON)

    assert math.isclose(outputs[0].combined_log_score, expected_a)
    assert math.isclose(outputs[1].combined_log_score, expected_b)

    max_score = max(expected_a, expected_b)
    exp_a = math.exp(expected_a - max_score)
    exp_b = math.exp(expected_b - max_score)
    expected_softmax = [exp_a / (exp_a + exp_b), exp_b / (exp_a + exp_b)]
    assert math.isclose(outputs[0].rerank_score, expected_softmax[0])
    assert math.isclose(outputs[1].rerank_score, expected_softmax[1])

    assert top_candidate_id(candidates, outputs) == "a"


def test_fuse_predictions_absent_geo_support_never_substitutes_zero_or_one():
    with_none = fuse_predictions(
        [
            GeoFusionCandidate(
                candidate_id="a",
                resolved_taxon_id=None,
                visual_probability_raw=0.5,
                geo_support=None,
            )
        ],
        fusion_epsilon=_FROZEN_FUSION_EPSILON,
        fusion_weight_geo=_FROZEN_FUSION_WEIGHT_GEO,
        fusion_weight_environment=_FROZEN_FUSION_WEIGHT_ENVIRONMENT,
    )
    visual_only_expected = math.log(0.5 + _FROZEN_FUSION_EPSILON)
    assert math.isclose(with_none[0].combined_log_score, visual_only_expected)
