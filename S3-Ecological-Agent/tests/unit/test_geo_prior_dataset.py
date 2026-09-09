"""Unit tests for the M2-C geographic-prior dataset adapter
(DesignSuggestionLog.md "2026-09-09 ... Suggested next increment: M2-C
geographic-prior reproduction and locked spatial evaluation").

Every fixture here is a small, hand-written synthetic object - never real
GBIF/ALA/iNaturalist data - matching the existing
``tests/integration/test_prepare_geo_experiment.py`` convention.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from s3_ecological.experiments.geo_prior_dataset import (
    GeoPriorDatasetError,
    load_manifest,
    load_occurrence_snapshot,
    load_split_records,
    load_taxonomy_snapshot,
    load_train_records,
    load_validation_records,
)
from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.schemas.experiment import (
    GeographicScopeMode,
    ImportReportIdentity,
    OccurrenceSnapshotIdentity,
    SpatialSplitManifest,
    SplitAssignmentRow,
    SplitName,
    TaxonomySnapshotIdentity,
)
from s3_ecological.schemas.snapshot import (
    OccurrenceSnapshot,
    TaxonomySnapshot,
    TaxonomySnapshotItem,
)

_PLACEHOLDER_SHA256 = "0" * 64
_TZ_AWARE_NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _occurrence(
    *,
    source_record_id: str,
    taxon_id: str,
    latitude: float,
    longitude: float,
    event_date: str | None = "2020-01-01",
    source: str = "generic_dwc",
) -> RawOccurrenceRecord:
    return RawOccurrenceRecord(
        source=source,
        source_record_id=source_record_id,
        scientific_name_raw="placeholder",
        taxon_id=taxon_id,
        latitude=latitude,
        longitude=longitude,
        event_date=event_date,
    )


def _write_occurrence_snapshot(path: Path, records: list[RawOccurrenceRecord]) -> str:
    snapshot = OccurrenceSnapshot(
        dataset_id="test-dataset",
        source="generic_dwc",
        retrieved_at="2026-09-09T00:00:00+10:00",
        dataset_license="CC-BY 4.0",
        citation="test citation",
        source_sha256=_PLACEHOLDER_SHA256,
        mapping_version="generic_dwc-v0.1",
        snapshot_key="test-key",
        records=records,
    )
    raw = snapshot.model_dump_json().encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _write_taxonomy_snapshot(path: Path, genus_by_taxon_id: dict[str, str]) -> str:
    taxa = [
        TaxonomySnapshotItem(
            submitted_names=[f"{genus} placeholder"],
            scientific_name=f"{genus} placeholder",
            taxon_ids={"generic_dwc": taxon_id},
        )
        for taxon_id, genus in genus_by_taxon_id.items()
    ]
    snapshot = TaxonomySnapshot(
        dataset_id="test-dataset",
        source="generic_dwc",
        source_sha256=_PLACEHOLDER_SHA256,
        mapping_version="generic_dwc-v0.1",
        taxa=taxa,
    )
    raw = snapshot.model_dump_json().encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _write_manifest(
    path: Path,
    *,
    occurrence_sha256: str,
    taxonomy_sha256: str,
    rows: list[SplitAssignmentRow],
) -> SpatialSplitManifest:
    manifest = SpatialSplitManifest(
        experiment_id="test-experiment",
        created_at=_TZ_AWARE_NOW,
        occurrence_snapshot=OccurrenceSnapshotIdentity(
            dataset_id="test-dataset",
            source="generic_dwc",
            source_sha256=_PLACEHOLDER_SHA256,
            snapshot_key="test-key",
            dataset_license="CC-BY 4.0",
            citation="test citation",
            retrieved_at="2026-09-09T00:00:00+10:00",
            mapping_version="generic_dwc-v0.1",
            file_sha256=occurrence_sha256,
        ),
        taxonomy_snapshot=TaxonomySnapshotIdentity(
            dataset_id="test-dataset",
            source="generic_dwc",
            source_sha256=_PLACEHOLDER_SHA256,
            mapping_version="generic_dwc-v0.1",
            file_sha256=taxonomy_sha256,
        ),
        import_report=ImportReportIdentity(
            dataset_id="test-dataset",
            source_sha256=_PLACEHOLDER_SHA256,
            importer_version="test-importer-v0.1",
            file_sha256=_PLACEHOLDER_SHA256,
        ),
        configuration_digest=_PLACEHOLDER_SHA256,
        effective_cleaning_settings={},
        target_taxa=["Bactrocera", "Ceratitis"],
        geographic_scope="global",
        geographic_scope_mode=GeographicScopeMode.LABEL_ONLY,
        block_strategy="latitude_longitude_grid_v0.1",
        block_strategy_version="v0.1",
        grid_size_degrees=1.0,
        train_ratio=0.6,
        validation_ratio=0.2,
        test_ratio=0.2,
        seed=42,
        split_identity="test-split-identity",
        rows=rows,
        excluded_records=[],
    )
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest


def _build_fixture(tmp_path: Path):
    records = [
        _occurrence(source_record_id="1", taxon_id="t:bactrocera", latitude=10.0, longitude=20.0),
        _occurrence(source_record_id="2", taxon_id="t:bactrocera", latitude=11.0, longitude=21.0),
        _occurrence(source_record_id="3", taxon_id="t:ceratitis", latitude=12.0, longitude=22.0),
        _occurrence(
            source_record_id="4",
            taxon_id="t:ceratitis",
            latitude=13.0,
            longitude=23.0,
            event_date=None,
        ),
    ]
    occurrence_path = tmp_path / "occurrences.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    occurrence_sha256 = _write_occurrence_snapshot(occurrence_path, records)
    taxonomy_sha256 = _write_taxonomy_snapshot(
        taxonomy_path, {"t:bactrocera": "Bactrocera", "t:ceratitis": "Ceratitis"}
    )
    rows = [
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="1",
            taxon_id="t:bactrocera",
            block_id="block-a",
            split=SplitName.TRAIN,
        ),
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="2",
            taxon_id="t:bactrocera",
            block_id="block-b",
            split=SplitName.VALIDATION,
        ),
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="3",
            taxon_id="t:ceratitis",
            block_id="block-c",
            split=SplitName.TEST,
        ),
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="4",
            taxon_id="t:ceratitis",
            block_id="block-d",
            split=SplitName.TRAIN,
        ),
    ]
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_manifest(
        manifest_path,
        occurrence_sha256=occurrence_sha256,
        taxonomy_sha256=taxonomy_sha256,
        rows=rows,
    )
    return manifest_path, occurrence_path, taxonomy_path


def test_train_and_validation_loaders_return_disjoint_correctly_scoped_records(tmp_path):
    manifest_path, occurrence_path, taxonomy_path = _build_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    train = load_train_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
    )
    validation = load_validation_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
    )

    assert {r.source_record_id for r in train} == {"1", "4"}
    assert {r.source_record_id for r in validation} == {"2"}
    assert not {r.source_record_id for r in train} & {r.source_record_id for r in validation}
    assert all(r.genus == "Bactrocera" for r in train if r.source_record_id == "1")
    assert all(r.genus == "Ceratitis" for r in train if r.source_record_id == "4")


def test_load_split_records_refuses_test_split(tmp_path):
    manifest_path, occurrence_path, taxonomy_path = _build_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    with pytest.raises(GeoPriorDatasetError, match="refuses split=TEST"):
        load_split_records(
            manifest=manifest,
            occurrence_snapshot=occurrence_snapshot,
            taxonomy_snapshot=taxonomy_snapshot,
            split=SplitName.TEST,
        )


def test_require_event_date_excludes_undated_records(tmp_path):
    manifest_path, occurrence_path, taxonomy_path = _build_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    train = load_train_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
        require_event_date=True,
    )
    assert {r.source_record_id for r in train} == {"1"}


def test_occurrence_snapshot_provenance_mismatch_is_rejected(tmp_path):
    manifest_path, occurrence_path, taxonomy_path = _build_fixture(tmp_path)
    manifest = load_manifest(manifest_path)

    payload = occurrence_path.read_text(encoding="utf-8")
    tampered = payload.replace("test citation", "tampered citation")
    occurrence_path.write_text(tampered, encoding="utf-8")

    with pytest.raises(GeoPriorDatasetError, match="does not match the checksum"):
        load_occurrence_snapshot(occurrence_path, manifest=manifest)


def test_taxonomy_snapshot_provenance_mismatch_is_rejected(tmp_path):
    manifest_path, occurrence_path, taxonomy_path = _build_fixture(tmp_path)
    manifest = load_manifest(manifest_path)

    payload = taxonomy_path.read_text(encoding="utf-8")
    taxonomy_path.write_text(
        payload.replace("generic_dwc-v0.1", "generic_dwc-v0.2-tampered"), encoding="utf-8"
    )

    with pytest.raises(GeoPriorDatasetError, match="does not match the checksum"):
        load_taxonomy_snapshot(taxonomy_path, manifest=manifest)


def test_ambiguous_join_raises(tmp_path):
    records = [
        _occurrence(source_record_id="dup", taxon_id="t:bactrocera", latitude=10.0, longitude=20.0),
        _occurrence(source_record_id="dup", taxon_id="t:bactrocera", latitude=10.1, longitude=20.1),
    ]
    occurrence_path = tmp_path / "occurrences.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    occurrence_sha256 = _write_occurrence_snapshot(occurrence_path, records)
    taxonomy_sha256 = _write_taxonomy_snapshot(taxonomy_path, {"t:bactrocera": "Bactrocera"})
    rows = [
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="dup",
            taxon_id="t:bactrocera",
            block_id="block-a",
            split=SplitName.TRAIN,
        ),
    ]
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_manifest(
        manifest_path,
        occurrence_sha256=occurrence_sha256,
        taxonomy_sha256=taxonomy_sha256,
        rows=rows,
    )
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    with pytest.raises(GeoPriorDatasetError, match="ambiguously"):
        load_train_records(
            manifest=manifest,
            occurrence_snapshot=occurrence_snapshot,
            taxonomy_snapshot=taxonomy_snapshot,
        )


def test_missing_join_raises(tmp_path):
    occurrence_path = tmp_path / "occurrences.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    occurrence_sha256 = _write_occurrence_snapshot(occurrence_path, [])
    taxonomy_sha256 = _write_taxonomy_snapshot(taxonomy_path, {"t:bactrocera": "Bactrocera"})
    rows = [
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="missing",
            taxon_id="t:bactrocera",
            block_id="block-a",
            split=SplitName.TRAIN,
        ),
    ]
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_manifest(
        manifest_path,
        occurrence_sha256=occurrence_sha256,
        taxonomy_sha256=taxonomy_sha256,
        rows=rows,
    )
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    with pytest.raises(GeoPriorDatasetError, match="no matching record"):
        load_train_records(
            manifest=manifest,
            occurrence_snapshot=occurrence_snapshot,
            taxonomy_snapshot=taxonomy_snapshot,
        )


def test_taxon_id_mismatch_raises(tmp_path):
    records = [
        _occurrence(source_record_id="1", taxon_id="t:bactrocera", latitude=10.0, longitude=20.0),
    ]
    occurrence_path = tmp_path / "occurrences.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    occurrence_sha256 = _write_occurrence_snapshot(occurrence_path, records)
    taxonomy_sha256 = _write_taxonomy_snapshot(
        taxonomy_path, {"t:bactrocera": "Bactrocera", "t:ceratitis": "Ceratitis"}
    )
    rows = [
        SplitAssignmentRow(
            source="generic_dwc",
            source_record_id="1",
            taxon_id="t:ceratitis",
            block_id="block-a",
            split=SplitName.TRAIN,
        ),
    ]
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_manifest(
        manifest_path,
        occurrence_sha256=occurrence_sha256,
        taxonomy_sha256=taxonomy_sha256,
        rows=rows,
    )
    manifest = load_manifest(manifest_path)
    occurrence_snapshot = load_occurrence_snapshot(occurrence_path, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(taxonomy_path, manifest=manifest)

    with pytest.raises(GeoPriorDatasetError, match="declares taxon_id"):
        load_train_records(
            manifest=manifest,
            occurrence_snapshot=occurrence_snapshot,
            taxonomy_snapshot=taxonomy_snapshot,
        )


def test_missing_manifest_file_is_rejected(tmp_path):
    with pytest.raises(GeoPriorDatasetError, match="cannot read"):
        load_manifest(tmp_path / "does-not-exist.json")
