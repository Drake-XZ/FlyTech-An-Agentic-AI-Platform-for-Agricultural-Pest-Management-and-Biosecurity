"""Pure spatial-block and split-assignment logic for the offline
pre-Milestone 2 readiness gate (DesignSuggestionLog.md, "Spatial split
Profile v0.1"). No file I/O here - see :mod:`s3_ecological.experiments.prepare`
for the orchestration that reads/writes files and calls this module.

Whole blocks, never individual records, are assigned to a split. Assignment
is a deterministic hash of ``"<seed>:<block_id>"``, so the same block always
lands in the same split for a given seed, and re-running the tool with
unchanged config produces byte-identical results.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from s3_ecological.schemas.experiment import SplitName

_MIN_GRID_SIZE_DEGREES = 0.0
_MAX_GRID_SIZE_DEGREES = 10.0
_HASH_BYTES = 8
_HASH_SPACE = 2 ** (8 * _HASH_BYTES)


@runtime_checkable
class SpatialBlockStrategy(Protocol):
    """Extension point for future H3, equal-area, state, or ecoregion
    grouping strategies without rewriting readiness reporting.

    ``name``/``version`` are declared as read-only properties (not plain
    attributes) so a frozen dataclass implementation - whose fields are
    read-only - satisfies this protocol structurally."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def block_id_for(self, latitude: float, longitude: float) -> str: ...

    def identity_parameters(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class LatitudeLongitudeGridV0:
    """``latitude_longitude_grid_v0.1`` - equal-angle grid cells. Cells are
    not equal-area and are not a production ecological-region definition;
    see the geo-experiment-readiness data card."""

    grid_size_degrees: float
    name: str = "latitude_longitude_grid"
    version: str = "0.1"

    def __post_init__(self) -> None:
        if not math.isfinite(self.grid_size_degrees) or not (
            _MIN_GRID_SIZE_DEGREES < self.grid_size_degrees <= _MAX_GRID_SIZE_DEGREES
        ):
            raise ValueError(
                "grid_size_degrees must be finite and in (0, 10], got "
                f"{self.grid_size_degrees}"
            )

    def block_id_for(self, latitude: float, longitude: float) -> str:
        b = self.grid_size_degrees
        longitude_for_index = (
            -180.0 if longitude == 180.0 or latitude in (-90.0, 90.0) else longitude
        )
        latitude_cell_count = math.ceil(180.0 / b)
        latitude_index = min(latitude_cell_count - 1, math.floor((latitude + 90.0) / b))
        longitude_index = math.floor((longitude_for_index + 180.0) / b)
        return f"grid-v0.1:{b}:{latitude_index}:{longitude_index}"

    def identity_parameters(self) -> Mapping[str, Any]:
        return {"grid_size_degrees": self.grid_size_degrees}


@dataclass(frozen=True)
class SplitRatios:
    train: float
    validation: float
    test: float


@dataclass(frozen=True)
class OccurrenceForSplit:
    """The minimal identity + coordinates a usable, cleaned occurrence needs
    to be assigned a spatial block and split."""

    source: str
    source_record_id: str | None
    taxon_id: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SplitAssignment:
    occurrence: OccurrenceForSplit
    block_id: str
    split: SplitName


@dataclass(frozen=True)
class SpatialSplitResult:
    assignments: list[SplitAssignment]
    block_to_split: dict[str, SplitName]
    counts_by_block: dict[str, int]
    counts_by_split: dict[str, int]


def hash_unit_interval(seed: int, block_id: str) -> float:
    """SHA-256 of ``"<seed>:<block_id>"``, first 8 digest bytes as an
    unsigned 64-bit big-endian integer divided by 2**64, giving a value in
    ``[0, 1)`` that is stable across processes, platforms, and Python
    versions."""
    digest = hashlib.sha256(f"{seed}:{block_id}".encode()).digest()
    as_int = int.from_bytes(digest[:_HASH_BYTES], byteorder="big", signed=False)
    return as_int / _HASH_SPACE


def assign_split_for_unit(u: float, ratios: SplitRatios) -> SplitName:
    if u < ratios.train:
        return SplitName.TRAIN
    if u < ratios.train + ratios.validation:
        return SplitName.VALIDATION
    return SplitName.TEST


def assign_records_to_splits(
    records: Sequence[OccurrenceForSplit],
    *,
    strategy: SpatialBlockStrategy,
    ratios: SplitRatios,
    seed: int,
) -> SpatialSplitResult:
    """Assign every record to a block via ``strategy``, then assign every
    distinct block (not each record) to a split. A block that already has a
    split assignment is never reassigned, so no block ever spans splits."""
    block_to_split: dict[str, SplitName] = {}
    assignments: list[SplitAssignment] = []
    for record in records:
        block_id = strategy.block_id_for(record.latitude, record.longitude)
        split = block_to_split.get(block_id)
        if split is None:
            split = assign_split_for_unit(hash_unit_interval(seed, block_id), ratios)
            block_to_split[block_id] = split
        assignments.append(SplitAssignment(occurrence=record, block_id=block_id, split=split))

    counts_by_block = dict(Counter(a.block_id for a in assignments))
    counts_by_split = dict(Counter(a.split.value for a in assignments))
    return SpatialSplitResult(
        assignments=assignments,
        block_to_split=block_to_split,
        counts_by_block=counts_by_block,
        counts_by_split=counts_by_split,
    )


def compute_split_identity(
    *,
    strategy: SpatialBlockStrategy,
    ratios: SplitRatios,
    seed: int,
) -> str:
    """A digest that changes whenever the block strategy, its parameters,
    the split ratios, or the seed change - so consumers can detect a split
    definition change without comparing every row."""
    payload = json.dumps(
        {
            "strategy_name": strategy.name,
            "strategy_version": strategy.version,
            "strategy_parameters": dict(strategy.identity_parameters()),
            "train_ratio": ratios.train,
            "validation_ratio": ratios.validation,
            "test_ratio": ratios.test,
            "seed": seed,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
