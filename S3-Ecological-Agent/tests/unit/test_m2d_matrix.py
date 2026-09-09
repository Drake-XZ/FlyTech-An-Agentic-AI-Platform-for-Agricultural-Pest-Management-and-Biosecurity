"""Tests for the pre-declared M2-D robustness matrix
(config/m2d_robustness_matrix.json), written and frozen before any new
training or test-set inference (DesignSuggestionLog.md "M2-D robustness,
ablation, and generalisation audit").
"""

from __future__ import annotations

import json
from pathlib import Path

from s3_ecological.experiments import m2c_reference
from s3_ecological.experiments.spatial_split import (
    LatitudeLongitudeGridV0,
    SplitRatios,
    compute_split_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "config" / "m2d_robustness_matrix.json"


def _load_matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _split_ratios(matrix: dict) -> SplitRatios:
    raw = matrix["split_ratios"]
    return SplitRatios(
        train=raw["train_ratio"],
        validation=raw["validation_ratio"],
        test=raw["test_ratio"],
    )


def test_matrix_file_exists_and_parses():
    matrix = _load_matrix()
    assert matrix["partitions"]


def test_matrix_covers_required_grid_sizes_and_seeds():
    matrix = _load_matrix()
    grid_sizes = {partition["grid_size_degrees"] for partition in matrix["partitions"]}
    seeds = {partition["seed"] for partition in matrix["partitions"]}
    assert {0.5, 1.0, 2.0}.issubset(grid_sizes)
    assert {7, 42, 123}.issubset(seeds)
    assert len(grid_sizes) >= 3
    assert len(seeds) >= 3


def test_matrix_declares_all_three_methods():
    matrix = _load_matrix()
    assert set(matrix["methods"]) == {"s1_only", "geo_only", "fusion"}


def test_matrix_declares_the_ablation_spec():
    matrix = _load_matrix()
    ablation = matrix["ablation"]
    assert ablation["partition_id"] == "reference"
    assert ablation["baseline_config_id"] == "filts256_dateTrue"
    assert ablation["ablated_config_id"] == "filts256_dateFalse"
    assert ablation["training_status"].startswith("Already trained")


def test_matrix_declares_the_frozen_recipe_matching_m2c():
    matrix = _load_matrix()
    recipe = matrix["frozen_training_recipe"]
    assert recipe["config_id"] == m2c_reference.M2C_FROZEN_CONFIG_ID
    assert recipe["config"] == {"num_filts": 256, "use_date_feats": True}
    assert recipe["hyperparameters"]["seed"] == 42


def test_reference_partition_identity_matches_m2c_frozen_identity():
    matrix = _load_matrix()
    ratios = _split_ratios(matrix)
    reference = next(p for p in matrix["partitions"] if p["partition_id"] == "reference")
    identity = compute_split_identity(
        strategy=LatitudeLongitudeGridV0(reference["grid_size_degrees"]),
        ratios=ratios,
        seed=reference["seed"],
    )
    assert identity == m2c_reference.M2C_SPATIAL_SPLIT_IDENTITY


def test_new_partition_identities_are_distinct_from_reference_and_each_other():
    matrix = _load_matrix()
    ratios = _split_ratios(matrix)
    identities = {}
    for partition in matrix["partitions"]:
        identity = compute_split_identity(
            strategy=LatitudeLongitudeGridV0(partition["grid_size_degrees"]),
            ratios=ratios,
            seed=partition["seed"],
        )
        identities[partition["partition_id"]] = identity

    assert identities["reference"] == m2c_reference.M2C_SPATIAL_SPLIT_IDENTITY
    new_partition_ids = [pid for pid in identities if pid != "reference"]
    assert len(new_partition_ids) == 4
    new_identities = [identities[pid] for pid in new_partition_ids]
    assert len(set(new_identities)) == len(new_identities)
    for identity in new_identities:
        assert identity != m2c_reference.M2C_SPATIAL_SPLIT_IDENTITY


def test_identity_recomputation_is_deterministic():
    matrix = _load_matrix()
    ratios = _split_ratios(matrix)
    reference = next(p for p in matrix["partitions"] if p["partition_id"] == "reference")
    first = compute_split_identity(
        strategy=LatitudeLongitudeGridV0(reference["grid_size_degrees"]),
        ratios=ratios,
        seed=reference["seed"],
    )
    second = compute_split_identity(
        strategy=LatitudeLongitudeGridV0(reference["grid_size_degrees"]),
        ratios=ratios,
        seed=reference["seed"],
    )
    assert first == second
