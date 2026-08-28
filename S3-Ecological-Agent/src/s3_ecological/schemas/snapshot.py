"""Versioned schemas for offline occurrence/taxonomy snapshot bundles and
their import report (EarlyDesign.md "Next implementation increment:
offline occurrence snapshot ingestion", Milestone 1.5).

These describe the on-disk interchange format produced by
``s3_ecological.ingestion.occurrence_snapshot`` - they are storage
contracts, not provider-facing Protocols. ``interfaces/occurrence.py`` and
``interfaces/taxonomy.py`` remain the only contracts a provider must
satisfy; a snapshot bundle is just one on-disk source those providers can
be built from (EarlyDesign.md section 6.4).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord

# Schema version for both `occurrences.json` and `taxonomy.json`. Bump this,
# and give the new shape a migration path, before changing either bundle's
# structure - existing bundles must never be silently reinterpreted.
SNAPSHOT_SCHEMA_VERSION = "1.0.0"

# Schema version for `import-report.json`, versioned independently of the
# snapshot bundle it describes.
REPORT_SCHEMA_VERSION = "1.0.0"


class OccurrenceSnapshot(BaseModel):
    """On-disk occurrence bundle (`occurrences.json`).

    Every ``records`` entry already validates as :class:`RawOccurrenceRecord`
    - the importer does not invent a parallel record shape, so this bundle
    can be read by :class:`~s3_ecological.providers.occurrence_local_snapshot.
    LocalSnapshotOccurrenceProvider` unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    retrieved_at: str = Field(min_length=1)
    dataset_license: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    mapping_version: str = Field(min_length=1)
    snapshot_key: str = Field(min_length=1)
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    records: list[RawOccurrenceRecord] = Field(default_factory=list)


class TaxonomySnapshotItem(BaseModel):
    """One resolvable taxon entry in a `taxonomy.json` bundle.

    ``taxon_ids`` is keyed by the *import source* (``gbif``/``ala``/
    ``generic_dwc``, or the namespace prefix already present on a canonical
    record's id) rather than by a runtime provider name - it describes where
    the id came from, independent of which :class:`TaxonomyProvider` later
    loads this file. ``ambiguous`` is set when two different items in the
    same bundle share a normalized name (submitted or accepted) - the
    importer never merges them into one entry.
    """

    model_config = ConfigDict(extra="forbid")

    submitted_names: list[str] = Field(min_length=1)
    scientific_name: str = Field(min_length=1)
    rank: str | None = None
    taxon_ids: dict[str, str] = Field(min_length=1)
    synonym_of: str | None = None
    ambiguous: bool = False


class TaxonomySnapshot(BaseModel):
    """On-disk taxonomy bundle (`taxonomy.json`), paired with one `occurrences.json`."""

    model_config = ConfigDict(extra="forbid")

    snapshot_schema_version: str = SNAPSHOT_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    mapping_version: str = Field(min_length=1)
    taxa: list[TaxonomySnapshotItem] = Field(default_factory=list)


class ImportRejection(BaseModel):
    """One rejected input row.

    A row may fail more than one check; those are folded into a single
    ``message`` rather than one item per check, so the row still counts as
    exactly one rejection (EarlyDesign.md: "one row may report multiple
    field errors but counts as one rejected row"). ``message`` never
    contains the original row's field values, only field names and check
    descriptions, so a rejection report is safe to share even when the
    source data itself is not.
    """

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1)
    code: str = Field(min_length=1)
    field: str | None = None
    message: str = Field(min_length=1)


class OutputFileChecksum(BaseModel):
    """Filename + checksum of one file written by the importer."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)


class ImportStatus(StrEnum):
    """Terminal, non-fatal outcome of one import run.

    A fatal failure never reaches this enum - it raises
    :class:`~s3_ecological.ingestion.occurrence_snapshot.ImportFatalError`
    before any report is constructed.
    """

    COMPLETED = "completed"
    COMPLETED_WITH_REJECTIONS = "completed_with_rejections"


class ImportReport(BaseModel):
    """Machine-readable provenance and outcome of one `import-occurrences` run."""

    model_config = ConfigDict(extra="forbid")

    report_schema_version: str = REPORT_SCHEMA_VERSION

    # Command metadata, duplicated from the CLI invocation for a
    # self-contained report.
    dataset_id: str
    source: str
    retrieved_at: str
    dataset_license: str
    citation: str
    query_parameters: dict[str, Any] = Field(default_factory=dict)

    importer_version: str
    occurrence_mapping_version: str
    taxonomy_mapping_version: str

    input_filename: str
    source_sha256: str
    started_at: datetime
    completed_at: datetime
    encoding: str
    delimiter: str | None

    input_record_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    rejected_record_count: int = Field(ge=0)
    counts_by_taxon_id: dict[str, int] = Field(default_factory=dict)
    counts_by_rejection_code: dict[str, int] = Field(default_factory=dict)

    field_mapping: dict[str, list[str]] = Field(default_factory=dict)
    rejections: list[ImportRejection] = Field(default_factory=list)
    mapping_warnings: list[ImportRejection] = Field(default_factory=list)

    output_files: dict[str, OutputFileChecksum] = Field(default_factory=dict)
    status: ImportStatus
