"""Bundle authentication for the offline pre-Milestone 2 readiness builder
(DesignSuggestionLog.md, "2026-08-29 20:18 Australia/Sydney - Suggested
hardening increment: readiness integrity and contract corrections",
"Authenticate the imported bundle").

Verifies that the three Milestone 1.5 bundle files
(``occurrences.json``/``taxonomy.json``/``import-report.json``) actually
belong together: each file's checksum matches the corresponding
``import-report.json`` ``output_files`` entry (located by its declared
``filename``, never by dict/list order), and a fixed identity matrix of
shared metadata fields agrees across all three files.

Pure and file-I/O-free: callers already hold the parsed models and the
already-computed file SHA-256 digests (``prepare.py``'s ``_load_snapshot``
reads and checksums files before this module ever runs). Error messages
never include record data, coordinates, or any bundle content beyond
filenames and field labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s3_ecological.schemas.snapshot import ImportReport, OccurrenceSnapshot, TaxonomySnapshot

OCCURRENCES_FILENAME = "occurrences.json"
TAXONOMY_FILENAME = "taxonomy.json"

CODE_MISSING_BUNDLE_CHECKSUM = "missing_bundle_checksum"
CODE_DUPLICATE_BUNDLE_CHECKSUM = "duplicate_bundle_checksum"
CODE_OCCURRENCE_CHECKSUM_MISMATCH = "occurrence_checksum_mismatch"
CODE_TAXONOMY_CHECKSUM_MISMATCH = "taxonomy_checksum_mismatch"
CODE_BUNDLE_METADATA_MISMATCH = "bundle_metadata_mismatch"


class BundleIntegrityError(Exception):
    """A bundle-authentication failure. ``code`` is one of the stable
    ``CODE_*`` constants in this module; ``message`` never contains record
    data or coordinates, only filenames and field labels."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _IdentityField:
    """One row of the cross-file identity matrix. ``None`` marks a field
    that is not present in that particular schema (e.g. ``taxonomy.json``
    has no ``retrieved_at``) - it is excluded from comparison rather than
    treated as a mismatch."""

    label: str
    values: tuple[str | None, str | None, str | None]


def _find_checksum_entry_by_filename(import_report: ImportReport, filename: str) -> str:
    """Returns the matching entry's sha256. Matches only on the entry's own
    declared ``filename`` field - never on the ``output_files`` dict key or
    iteration order, since neither is a documented contract."""
    matches = [
        entry.sha256
        for entry in import_report.output_files.values()
        if entry.filename == filename
    ]
    if not matches:
        raise BundleIntegrityError(
            CODE_MISSING_BUNDLE_CHECKSUM,
            f"import-report.json has no output_files entry with filename '{filename}'",
        )
    if len(matches) > 1:
        raise BundleIntegrityError(
            CODE_DUPLICATE_BUNDLE_CHECKSUM,
            f"import-report.json has {len(matches)} output_files entries with "
            f"filename '{filename}', expected exactly one",
        )
    return matches[0]


def _distinct_non_none(values: tuple[str | None, str | None, str | None]) -> set[str]:
    return {value for value in values if value is not None}


def _identity_matrix(
    *,
    occurrence: OccurrenceSnapshot,
    taxonomy: TaxonomySnapshot,
    import_report: ImportReport,
) -> tuple[_IdentityField, ...]:
    """Every field present in at least two of the three bundle schemas.
    ``taxonomy.json`` does not carry ``retrieved_at``/``dataset_license``/
    ``citation``, so those rows compare only occurrence vs. report; the two
    mapping-version rows each compare one snapshot vs. the report's
    correspondingly-named field."""
    return (
        _IdentityField(
            "dataset_id",
            (occurrence.dataset_id, taxonomy.dataset_id, import_report.dataset_id),
        ),
        _IdentityField(
            "source_sha256",
            (occurrence.source_sha256, taxonomy.source_sha256, import_report.source_sha256),
        ),
        _IdentityField(
            "source",
            (occurrence.source, taxonomy.source, import_report.source),
        ),
        _IdentityField(
            "retrieved_at",
            (occurrence.retrieved_at, None, import_report.retrieved_at),
        ),
        _IdentityField(
            "dataset_license",
            (occurrence.dataset_license, None, import_report.dataset_license),
        ),
        _IdentityField(
            "citation",
            (occurrence.citation, None, import_report.citation),
        ),
        _IdentityField(
            "occurrence_mapping_version",
            (occurrence.mapping_version, None, import_report.occurrence_mapping_version),
        ),
        _IdentityField(
            "taxonomy_mapping_version",
            (None, taxonomy.mapping_version, import_report.taxonomy_mapping_version),
        ),
    )


def _mismatched_field_labels(fields: tuple[_IdentityField, ...]) -> list[str]:
    """Pure comparison, no I/O: a field mismatches iff its non-``None``
    values disagree with each other."""
    return [field.label for field in fields if len(_distinct_non_none(field.values)) > 1]


def authenticate_bundle(
    *,
    occurrence: OccurrenceSnapshot,
    occurrence_file_sha256: str,
    taxonomy: TaxonomySnapshot,
    taxonomy_file_sha256: str,
    import_report: ImportReport,
) -> None:
    """Raises :class:`BundleIntegrityError` if the three bundle files do not
    authenticate as one consistent bundle. Must run before any output or
    temp file is created."""
    occurrence_checksum = _find_checksum_entry_by_filename(import_report, OCCURRENCES_FILENAME)
    if occurrence_checksum != occurrence_file_sha256:
        raise BundleIntegrityError(
            CODE_OCCURRENCE_CHECKSUM_MISMATCH,
            f"{OCCURRENCES_FILENAME} sha256 does not match the checksum recorded in "
            "import-report.json",
        )

    taxonomy_checksum = _find_checksum_entry_by_filename(import_report, TAXONOMY_FILENAME)
    if taxonomy_checksum != taxonomy_file_sha256:
        raise BundleIntegrityError(
            CODE_TAXONOMY_CHECKSUM_MISMATCH,
            f"{TAXONOMY_FILENAME} sha256 does not match the checksum recorded in "
            "import-report.json",
        )

    fields = _identity_matrix(occurrence=occurrence, taxonomy=taxonomy, import_report=import_report)
    mismatched = _mismatched_field_labels(fields)
    if mismatched:
        raise BundleIntegrityError(
            CODE_BUNDLE_METADATA_MISMATCH,
            "bundle metadata mismatch across occurrences.json/taxonomy.json/"
            "import-report.json for field(s): " + ", ".join(mismatched),
        )
