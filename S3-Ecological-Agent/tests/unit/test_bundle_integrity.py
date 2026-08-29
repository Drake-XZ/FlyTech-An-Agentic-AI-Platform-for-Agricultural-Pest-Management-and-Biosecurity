"""Unit tests for bundle authentication (experiments/bundle_integrity.py -
DesignSuggestionLog.md "Authenticate the imported bundle"). No file I/O -
hand-constructed snapshot/report models only. See
tests/integration/test_prepare_geo_experiment.py for the end-to-end,
file-backed tampering tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from s3_ecological.experiments.bundle_integrity import (
    CODE_BUNDLE_METADATA_MISMATCH,
    CODE_DUPLICATE_BUNDLE_CHECKSUM,
    CODE_MISSING_BUNDLE_CHECKSUM,
    CODE_OCCURRENCE_CHECKSUM_MISMATCH,
    CODE_TAXONOMY_CHECKSUM_MISMATCH,
    BundleIntegrityError,
    authenticate_bundle,
)
from s3_ecological.schemas.snapshot import (
    ImportReport,
    ImportStatus,
    OccurrenceSnapshot,
    OutputFileChecksum,
    TaxonomySnapshot,
)

_OCCURRENCE_FILE_SHA256 = "a" * 64
_TAXONOMY_FILE_SHA256 = "b" * 64
_SOURCE_SHA256 = "c" * 64


def _occurrence(**overrides: object) -> OccurrenceSnapshot:
    kwargs: dict[str, object] = {
        "dataset_id": "dataset-1",
        "source": "gbif",
        "retrieved_at": "2026-08-28T00:00:00+10:00",
        "dataset_license": "CC-BY 4.0",
        "citation": "Test citation",
        "source_sha256": _SOURCE_SHA256,
        "mapping_version": "occurrence-mapping-v1",
        "snapshot_key": "key",
    }
    kwargs.update(overrides)
    return OccurrenceSnapshot.model_validate(kwargs)


def _taxonomy(**overrides: object) -> TaxonomySnapshot:
    kwargs: dict[str, object] = {
        "dataset_id": "dataset-1",
        "source": "gbif",
        "source_sha256": _SOURCE_SHA256,
        "mapping_version": "taxonomy-mapping-v1",
    }
    kwargs.update(overrides)
    return TaxonomySnapshot.model_validate(kwargs)


def _import_report(**overrides: object) -> ImportReport:
    kwargs: dict[str, object] = {
        "dataset_id": "dataset-1",
        "source": "gbif",
        "retrieved_at": "2026-08-28T00:00:00+10:00",
        "dataset_license": "CC-BY 4.0",
        "citation": "Test citation",
        "importer_version": "s3-ecological-importer-0.1.0",
        "occurrence_mapping_version": "occurrence-mapping-v1",
        "taxonomy_mapping_version": "taxonomy-mapping-v1",
        "input_filename": "input.csv",
        "source_sha256": _SOURCE_SHA256,
        "started_at": datetime(2026, 8, 28, tzinfo=UTC),
        "completed_at": datetime(2026, 8, 28, tzinfo=UTC),
        "encoding": "utf-8",
        "delimiter": ",",
        "input_record_count": 2,
        "accepted_record_count": 2,
        "rejected_record_count": 0,
        "output_files": {
            "occurrences": OutputFileChecksum(
                filename="occurrences.json", sha256=_OCCURRENCE_FILE_SHA256
            ),
            "taxonomy": OutputFileChecksum(
                filename="taxonomy.json", sha256=_TAXONOMY_FILE_SHA256
            ),
        },
        "status": ImportStatus.COMPLETED,
    }
    kwargs.update(overrides)
    return ImportReport.model_validate(kwargs)


def _authenticate(**overrides: object) -> None:
    kwargs: dict[str, object] = {
        "occurrence": _occurrence(),
        "occurrence_file_sha256": _OCCURRENCE_FILE_SHA256,
        "taxonomy": _taxonomy(),
        "taxonomy_file_sha256": _TAXONOMY_FILE_SHA256,
        "import_report": _import_report(),
    }
    kwargs.update(overrides)
    authenticate_bundle(**cast(Any, kwargs))


def test_fully_consistent_bundle_passes_silently():
    _authenticate()


def test_occurrence_checksum_mismatch_is_rejected():
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(occurrence_file_sha256="f" * 64)
    assert exc_info.value.code == CODE_OCCURRENCE_CHECKSUM_MISMATCH
    assert "occurrences.json" in str(exc_info.value)


def test_taxonomy_checksum_mismatch_is_rejected():
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(taxonomy_file_sha256="f" * 64)
    assert exc_info.value.code == CODE_TAXONOMY_CHECKSUM_MISMATCH
    assert "taxonomy.json" in str(exc_info.value)


def test_missing_occurrence_checksum_entry_is_rejected():
    report = _import_report(
        output_files={
            "taxonomy": OutputFileChecksum(
                filename="taxonomy.json", sha256=_TAXONOMY_FILE_SHA256
            )
        }
    )
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(import_report=report)
    assert exc_info.value.code == CODE_MISSING_BUNDLE_CHECKSUM
    assert "occurrences.json" in str(exc_info.value)


def test_duplicate_occurrence_checksum_entry_is_rejected():
    report = _import_report(
        output_files={
            "occurrences": OutputFileChecksum(
                filename="occurrences.json", sha256=_OCCURRENCE_FILE_SHA256
            ),
            "occurrences_duplicate": OutputFileChecksum(
                filename="occurrences.json", sha256=_OCCURRENCE_FILE_SHA256
            ),
            "taxonomy": OutputFileChecksum(
                filename="taxonomy.json", sha256=_TAXONOMY_FILE_SHA256
            ),
        }
    )
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(import_report=report)
    assert exc_info.value.code == CODE_DUPLICATE_BUNDLE_CHECKSUM
    assert "occurrences.json" in str(exc_info.value)


@pytest.mark.parametrize(
    "field_name",
    [
        "dataset_id",
        "source_sha256",
        "source",
        "retrieved_at",
        "dataset_license",
        "citation",
        "occurrence_mapping_version",
        "taxonomy_mapping_version",
    ],
)
def test_identity_matrix_field_mismatch_is_rejected(field_name: str):
    report = _import_report(**{field_name: "a-different-value"})
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(import_report=report)
    assert exc_info.value.code == CODE_BUNDLE_METADATA_MISMATCH
    assert field_name in str(exc_info.value)


def test_bundle_metadata_mismatch_error_never_includes_record_data():
    report = _import_report(dataset_id="a-different-value")
    with pytest.raises(BundleIntegrityError) as exc_info:
        _authenticate(import_report=report)
    message = str(exc_info.value)
    # Only filenames and field labels may appear - never coordinates or any
    # other record-level content.
    assert "-33." not in message
    assert "151." not in message
