"""Auditable dataset adapter for M2-C geographic-prior reproduction
(DesignSuggestionLog.md "2026-09-09 ... Suggested next increment: M2-C
geographic-prior reproduction and locked spatial evaluation").

This module joins an already-computed :class:`SpatialSplitManifest` with the
occurrence and taxonomy snapshots it was built from, producing per-split
records a training/evaluation script can consume directly. It performs no
network access and no spatial-splitting logic of its own - splits are
authoritative from :mod:`s3_ecological.experiments.spatial_split` (via the
manifest) and are never recomputed or reassigned here.

Anti-leakage is enforced structurally, not just documented: every public
loader takes a single ``split`` argument and returns only that split's
records - there is no function through which validation or test records can
reach a "training" call, and :func:`load_split_records` unconditionally
refuses ``SplitName.TEST`` (the locked test set is read only by the M2-C
evaluation script, directly from the S1 bundle's own prediction rows, never
through this dataset adapter).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from s3_ecological.schemas.experiment import SpatialSplitManifest, SplitName
from s3_ecological.schemas.snapshot import OccurrenceSnapshot, TaxonomySnapshot


class GeoPriorDatasetError(ValueError):
    """Raised when the manifest, occurrence snapshot, and taxonomy snapshot
    do not agree with each other, or when a caller asks this adapter for a
    split it must never supply (the locked test split)."""


@dataclass(frozen=True)
class GeoPriorDatasetRecord:
    """One trainable/selectable occurrence record: enough to fit or score a
    geographic prior, and enough to trace back to its source row."""

    source: str
    source_record_id: str | None
    taxon_id: str
    genus: str
    latitude: float
    longitude: float
    event_date: str | None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(manifest_path: Path) -> SpatialSplitManifest:
    """Load and validate the spatial split manifest produced by
    ``prepare-geo-experiment``. Raises :class:`GeoPriorDatasetError` if the
    file cannot be read or does not conform to the schema."""
    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        raise GeoPriorDatasetError(f"cannot read spatial split manifest: {manifest_path}") from exc
    try:
        return SpatialSplitManifest.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
        raise GeoPriorDatasetError(
            f"spatial split manifest at {manifest_path} failed schema validation"
        ) from exc


def _verify_snapshot_provenance(*, path: Path, declared_sha256: str, label: str) -> bytes:
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != declared_sha256:
        raise GeoPriorDatasetError(
            f"{label} at {path} does not match the checksum declared in the spatial split "
            f"manifest (declared {declared_sha256}, actual {actual}) - refusing to load "
            "unverified data"
        )
    return raw


def load_occurrence_snapshot(
    occurrence_snapshot_path: Path, *, manifest: SpatialSplitManifest
) -> OccurrenceSnapshot:
    """Load the occurrence snapshot the manifest was built from, verifying
    its SHA-256 against the manifest's declared identity. Raises
    :class:`GeoPriorDatasetError` on any mismatch."""
    raw = _verify_snapshot_provenance(
        path=occurrence_snapshot_path,
        declared_sha256=manifest.occurrence_snapshot.file_sha256,
        label="occurrence snapshot",
    )
    return OccurrenceSnapshot.model_validate_json(raw)


def load_taxonomy_snapshot(
    taxonomy_snapshot_path: Path, *, manifest: SpatialSplitManifest
) -> TaxonomySnapshot:
    """Load the taxonomy snapshot the manifest was built from, verifying its
    SHA-256 against the manifest's declared identity. Raises
    :class:`GeoPriorDatasetError` on any mismatch."""
    raw = _verify_snapshot_provenance(
        path=taxonomy_snapshot_path,
        declared_sha256=manifest.taxonomy_snapshot.file_sha256,
        label="taxonomy snapshot",
    )
    return TaxonomySnapshot.model_validate_json(raw)


def genus_by_taxon_id(taxonomy_snapshot: TaxonomySnapshot) -> dict[str, str]:
    """The first whitespace-delimited token of each taxon's scientific name,
    keyed by every stable taxon id it maps to across import sources. Mirrors
    :func:`s3_ecological.experiments.prepare._genus_by_taxon_id`'s convention
    exactly (that function is private to ``prepare.py`` and is not reused
    directly, so the two must be kept in agreement by inspection)."""
    mapping: dict[str, str] = {}
    for item in taxonomy_snapshot.taxa:
        genus = item.scientific_name.split()[0]
        for taxon_id in item.taxon_ids.values():
            mapping[taxon_id] = genus
    return mapping


def load_split_records(
    *,
    manifest: SpatialSplitManifest,
    occurrence_snapshot: OccurrenceSnapshot,
    taxonomy_snapshot: TaxonomySnapshot,
    split: SplitName,
    require_event_date: bool = False,
) -> list[GeoPriorDatasetRecord]:
    """Build the records for exactly one split. Structurally refuses
    ``SplitName.TEST`` - the locked test set must only ever be read by the
    M2-C evaluation script directly from the S1 bundle's own prediction
    rows, never through this training/selection-facing adapter.

    Raises :class:`GeoPriorDatasetError` if a manifest row's
    ``(source, source_record_id)`` does not match exactly one occurrence
    record, or if the matched occurrence's ``taxon_id`` disagrees with the
    manifest row's declared ``taxon_id``.
    """
    if split is SplitName.TEST:
        raise GeoPriorDatasetError(
            "load_split_records refuses split=TEST: the locked spatial test set must only be "
            "read by the M2-C evaluation script directly from the S1 bundle's prediction rows, "
            "never through this dataset adapter"
        )

    occurrence_index: dict[tuple[str, str | None], list[int]] = {}
    for index, record in enumerate(occurrence_snapshot.records):
        occurrence_index.setdefault((record.source, record.source_record_id), []).append(index)

    genus_lookup = genus_by_taxon_id(taxonomy_snapshot)

    records: list[GeoPriorDatasetRecord] = []
    for row in manifest.rows:
        if row.split is not split:
            continue

        key = (row.source, row.source_record_id)
        matches = occurrence_index.get(key, [])
        if len(matches) == 0:
            raise GeoPriorDatasetError(
                f"spatial split manifest row {key} has no matching record in the occurrence "
                "snapshot"
            )
        if len(matches) > 1:
            raise GeoPriorDatasetError(
                f"spatial split manifest row {key} matches {len(matches)} occurrence records "
                "ambiguously - refusing to guess which one it refers to"
            )
        occurrence = occurrence_snapshot.records[matches[0]]

        if occurrence.taxon_id != row.taxon_id:
            raise GeoPriorDatasetError(
                f"spatial split manifest row {key} declares taxon_id={row.taxon_id!r} but the "
                f"matched occurrence record declares taxon_id={occurrence.taxon_id!r}"
            )
        if occurrence.latitude is None or occurrence.longitude is None:
            raise GeoPriorDatasetError(
                f"occurrence record {key} matched by the spatial split manifest has no "
                "latitude/longitude - it should never have been assigned to a spatial block"
            )
        genus = genus_lookup.get(row.taxon_id)
        if genus is None:
            raise GeoPriorDatasetError(
                f"taxon_id={row.taxon_id!r} referenced by the spatial split manifest is not "
                "present in the taxonomy snapshot"
            )

        if require_event_date and not occurrence.event_date:
            continue

        records.append(
            GeoPriorDatasetRecord(
                source=row.source,
                source_record_id=row.source_record_id,
                taxon_id=row.taxon_id,
                genus=genus,
                latitude=occurrence.latitude,
                longitude=occurrence.longitude,
                event_date=occurrence.event_date,
            )
        )
    return records


def load_train_records(
    *,
    manifest: SpatialSplitManifest,
    occurrence_snapshot: OccurrenceSnapshot,
    taxonomy_snapshot: TaxonomySnapshot,
    require_event_date: bool = False,
) -> list[GeoPriorDatasetRecord]:
    """The spatial ``train`` split only - the only split a config's weights
    may be fit on."""
    return load_split_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
        split=SplitName.TRAIN,
        require_event_date=require_event_date,
    )


def load_validation_records(
    *,
    manifest: SpatialSplitManifest,
    occurrence_snapshot: OccurrenceSnapshot,
    taxonomy_snapshot: TaxonomySnapshot,
    require_event_date: bool = False,
) -> list[GeoPriorDatasetRecord]:
    """The spatial ``validation`` split only - the only split a config may
    be selected on."""
    return load_split_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
        split=SplitName.VALIDATION,
        require_event_date=require_event_date,
    )
