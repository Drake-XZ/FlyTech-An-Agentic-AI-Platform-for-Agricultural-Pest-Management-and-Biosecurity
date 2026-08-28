"""Unit tests for soft-fusion scoring (EarlyDesign.md v0.1 fusion semantics)."""

from __future__ import annotations

import math

import pytest

from s3_ecological.fusion.soft_fusion import FusionInput, fuse, tie_break_key

FUSION_KWARGS = dict(fusion_epsilon=1e-6, fusion_weight_geo=1.0, fusion_weight_environment=0.0)


def _input(
    candidate_id: str, taxon_id: str | None, visual: float, geo: float | None
) -> FusionInput:
    return FusionInput(
        candidate_id,
        taxon_id,
        visual_probability_raw=visual,
        geo_support=geo,
        environmental_suitability=None,
    )


def test_rerank_scores_sum_to_one_over_submitted_set():
    inputs = [_input("c1", "t1", 0.7, 0.9), _input("c2", "t2", 0.3, 0.2)]
    outputs = fuse(inputs, **FUSION_KWARGS)
    assert math.isclose(sum(o.rerank_score for o in outputs), 1.0, rel_tol=1e-9)


def test_unavailable_geo_support_is_omitted_not_substituted():
    with_geo = fuse([_input("c1", "t1", 0.5, 0.5)], **FUSION_KWARGS)[0]
    without_geo = fuse([_input("c1", "t1", 0.5, None)], **FUSION_KWARGS)[0]
    visual_only = math.log(0.5 + FUSION_KWARGS["fusion_epsilon"])
    assert math.isclose(without_geo.combined_log_score, visual_only, rel_tol=1e-9)
    assert without_geo.combined_log_score != with_geo.combined_log_score


def test_higher_visual_probability_yields_higher_combined_log_score_all_else_equal():
    outputs = fuse(
        [_input("low", "t1", 0.1, 0.5), _input("high", "t2", 0.9, 0.5)], **FUSION_KWARGS
    )
    scores = {o.candidate_id: o.combined_log_score for o in outputs}
    assert scores["high"] > scores["low"]


def test_fuse_preserves_input_order_and_length():
    inputs = [
        _input("c1", None, 0.5, None),
        _input("c2", None, 0.5, None),
        _input("c3", None, 0.5, None),
    ]
    outputs = fuse(inputs, **FUSION_KWARGS)
    assert [o.candidate_id for o in outputs] == ["c1", "c2", "c3"]


def test_fuse_on_empty_input_returns_empty_list():
    assert fuse([], **FUSION_KWARGS) == []


def test_tie_break_key_orders_by_score_then_original_index_then_taxon_id():
    key_a = tie_break_key("a", combined_log_score=-1.0, original_index=1, resolved_taxon_id="zzz")
    key_b = tie_break_key("b", combined_log_score=-1.0, original_index=0, resolved_taxon_id="aaa")
    key_c = tie_break_key("c", combined_log_score=-2.0, original_index=0, resolved_taxon_id="aaa")
    # Equal scores: lower original_index sorts first (index 0 before index 1).
    assert sorted([key_a, key_b]) == [key_b, key_a]
    # A strictly higher combined_log_score (less negative) must sort before a lower one.
    assert sorted([key_a, key_c])[0] == key_a


def test_tie_break_key_falls_back_to_candidate_id_when_taxon_id_missing():
    key = tie_break_key(
        "candidate-x", combined_log_score=0.0, original_index=0, resolved_taxon_id=None
    )
    assert key == (0.0, 0, "candidate-x")


@pytest.mark.parametrize("weight_geo", [0.5, 1.0, 2.0])
def test_geo_weight_scales_geo_contribution(weight_geo):
    kwargs = dict(fusion_epsilon=1e-6, fusion_weight_geo=weight_geo, fusion_weight_environment=0.0)
    output = fuse([_input("c1", "t1", 0.5, 0.8)], **kwargs)[0]
    expected = math.log(0.5 + kwargs["fusion_epsilon"]) + weight_geo * math.log(
        0.8 + kwargs["fusion_epsilon"]
    )
    assert math.isclose(output.combined_log_score, expected, rel_tol=1e-9)
