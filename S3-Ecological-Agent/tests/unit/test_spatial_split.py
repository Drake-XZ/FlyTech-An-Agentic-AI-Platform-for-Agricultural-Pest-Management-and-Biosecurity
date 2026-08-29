"""Unit tests for the pure spatial-block and split-assignment logic
(DesignSuggestionLog.md "Spatial split Profile v0.1"). No file I/O, no
network - see tests/integration/test_prepare_geo_experiment.py for the
end-to-end CLI/orchestration tests.
"""

from __future__ import annotations

import pytest

from s3_ecological.experiments.spatial_split import (
    LatitudeLongitudeGridV0,
    OccurrenceForSplit,
    SplitRatios,
    assign_records_to_splits,
    assign_split_for_unit,
    compute_split_identity,
    hash_unit_interval,
)
from s3_ecological.schemas.experiment import SplitName


def test_grid_rejects_non_positive_or_too_large_grid_size():
    with pytest.raises(ValueError, match="grid_size_degrees"):
        LatitudeLongitudeGridV0(grid_size_degrees=0.0)
    with pytest.raises(ValueError, match="grid_size_degrees"):
        LatitudeLongitudeGridV0(grid_size_degrees=-1.0)
    with pytest.raises(ValueError, match="grid_size_degrees"):
        LatitudeLongitudeGridV0(grid_size_degrees=10.1)


def test_grid_accepts_boundary_grid_size_of_ten():
    LatitudeLongitudeGridV0(grid_size_degrees=10.0)


def test_block_id_is_stable_for_nearby_points_in_the_same_cell():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    assert grid.block_id_for(14.1, 121.1) == grid.block_id_for(14.9, 121.9)


def test_block_id_differs_across_a_cell_boundary():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    assert grid.block_id_for(14.9, 121.0) != grid.block_id_for(15.1, 121.0)


def test_north_and_south_pole_each_resolve_to_one_block_regardless_of_longitude():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    assert grid.block_id_for(90.0, -170.0) == grid.block_id_for(90.0, 170.0)
    assert grid.block_id_for(-90.0, -170.0) == grid.block_id_for(-90.0, 170.0)


def test_antimeridian_longitude_180_matches_negative_180():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    assert grid.block_id_for(10.0, 180.0) == grid.block_id_for(10.0, -180.0)


def test_north_pole_latitude_index_is_clamped_to_the_last_row():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    # floor((90 + 90) / 1) == 180, one past the last valid row index (179);
    # the last row must absorb it rather than creating a new, size-1 row.
    # (Longitude is separately forced to -180 at either pole, so this must
    # assert the exact id rather than compare against a non-pole latitude.)
    assert grid.block_id_for(90.0, 5.0) == "grid-v0.1:1.0:179:0"


def test_hash_unit_interval_is_deterministic_and_in_unit_range():
    value_a = hash_unit_interval(42, "block-1")
    value_b = hash_unit_interval(42, "block-1")
    assert value_a == value_b
    assert 0.0 <= value_a < 1.0


def test_hash_unit_interval_changes_with_seed_or_block_id():
    base = hash_unit_interval(42, "block-1")
    assert hash_unit_interval(43, "block-1") != base
    assert hash_unit_interval(42, "block-2") != base


def test_assign_split_for_unit_respects_ratio_boundaries():
    ratios = SplitRatios(train=0.6, validation=0.2, test=0.2)
    assert assign_split_for_unit(0.0, ratios) == SplitName.TRAIN
    assert assign_split_for_unit(0.59, ratios) == SplitName.TRAIN
    assert assign_split_for_unit(0.6, ratios) == SplitName.VALIDATION
    assert assign_split_for_unit(0.79, ratios) == SplitName.VALIDATION
    assert assign_split_for_unit(0.8, ratios) == SplitName.TEST
    assert assign_split_for_unit(0.999999, ratios) == SplitName.TEST


def test_whole_block_is_never_split_across_two_splits():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    ratios = SplitRatios(train=0.6, validation=0.2, test=0.2)
    records = [
        OccurrenceForSplit(
            source="fixture",
            source_record_id=f"rec-{i}",
            taxon_id="t1",
            latitude=14.1,
            longitude=121.1,
        )
        for i in range(5)
    ]
    result = assign_records_to_splits(records, strategy=grid, ratios=ratios, seed=42)
    assigned_splits = {a.split for a in result.assignments}
    assert len(assigned_splits) == 1
    assert len(result.block_to_split) == 1


def test_assign_records_to_splits_produces_consistent_counts():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    ratios = SplitRatios(train=0.6, validation=0.2, test=0.2)
    records = [
        OccurrenceForSplit(
            source="fixture",
            source_record_id=f"rec-{i}",
            taxon_id="t1",
            latitude=float(i),
            longitude=0.0,
        )
        for i in range(10)
    ]
    result = assign_records_to_splits(records, strategy=grid, ratios=ratios, seed=42)
    assert sum(result.counts_by_split.values()) == len(records)
    assert sum(result.counts_by_block.values()) == len(records)
    assert set(result.counts_by_split) <= {"train", "validation", "test"}


def test_repeat_assignment_with_unchanged_inputs_is_byte_identical():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    ratios = SplitRatios(train=0.6, validation=0.2, test=0.2)
    records = [
        OccurrenceForSplit(
            source="fixture",
            source_record_id=f"rec-{i}",
            taxon_id="t1",
            latitude=float(i),
            longitude=0.0,
        )
        for i in range(10)
    ]
    first = assign_records_to_splits(records, strategy=grid, ratios=ratios, seed=42)
    second = assign_records_to_splits(records, strategy=grid, ratios=ratios, seed=42)
    assert first.block_to_split == second.block_to_split
    assert [(a.block_id, a.split) for a in first.assignments] == [
        (a.block_id, a.split) for a in second.assignments
    ]


def test_split_identity_changes_with_seed_ratio_or_grid_size_and_is_stable_otherwise():
    grid = LatitudeLongitudeGridV0(grid_size_degrees=1.0)
    ratios = SplitRatios(train=0.6, validation=0.2, test=0.2)
    base = compute_split_identity(strategy=grid, ratios=ratios, seed=42)

    assert compute_split_identity(strategy=grid, ratios=ratios, seed=42) == base
    assert compute_split_identity(strategy=grid, ratios=ratios, seed=43) != base
    assert (
        compute_split_identity(
            strategy=grid, ratios=SplitRatios(train=0.5, validation=0.3, test=0.2), seed=42
        )
        != base
    )
    assert (
        compute_split_identity(
            strategy=LatitudeLongitudeGridV0(grid_size_degrees=2.0), ratios=ratios, seed=42
        )
        != base
    )
