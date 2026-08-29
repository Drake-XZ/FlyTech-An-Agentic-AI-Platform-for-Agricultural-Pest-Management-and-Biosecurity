"""Schemas for the offline pre-Milestone 2 data-readiness and spatial-split
builder (DesignSuggestionLog.md, "2026-08-29 17:16 Australia/Sydney -
Suggested next increment: offline pre-Milestone 2 data-readiness and
spatial-split builder", approved as a normative implementation requirement
on 2026-08-29 20:05 Australia/Sydney).

These are storage/configuration contracts for
``s3_ecological.experiments.prepare.prepare_geo_experiment`` - a preparation
gate that runs before Milestone 2 (EarlyDesign.md section 22), not the
Milestone 2 geographic-prior experiment itself. Nothing here trains a model,
calibrates a fusion weight or risk threshold, or claims a biological
accuracy result.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPERIMENT_CONFIG_SCHEMA_VERSION = "1.0.0"
SPATIAL_SPLIT_MANIFEST_SCHEMA_VERSION = "1.0.0"
READINESS_REPORT_SCHEMA_VERSION = "1.0.0"

# The four TF4 genera (Shen et al.; WEEK 4/FlyTech_S3_Resource_Map.md section
# 3.5). A configurable subset is accepted for engineering tests, but the
# readiness report always states which of these are absent.
DEFAULT_TARGET_TAXA: tuple[str, ...] = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")

_RATIO_SUM_TOLERANCE = 1e-9
_MIN_GRID_SIZE_DEGREES = 0.0
_MAX_GRID_SIZE_DEGREES = 10.0


class AuthorisationStatus(StrEnum):
    """Data-authorisation declaration values (design suggestion "Required
    local inputs"). Never inferred from public availability of a dataset."""

    AUTHORISED = "authorised"
    NOT_AUTHORISED = "not_authorised"
    UNKNOWN = "unknown"


class DataNature(StrEnum):
    """Whether the input bundle is real authorised data or a hand-written
    engineering fixture. Set explicitly by the operator/test, never
    inferred - this is independent of ``AuthorisationStatus`` because a
    synthetic fixture can be legitimately "authorised for use in tests" and
    still must never be reported as research readiness."""

    REAL_WORLD_DATA = "real_world_data"
    SYNTHETIC_ENGINEERING_FIXTURE = "synthetic_engineering_fixture"


class SplitName(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class ReadinessStatus(StrEnum):
    """Shared status vocabulary for ``occurrence_data_status`` and
    ``overall_milestone_2_status`` (design suggestion "Required output
    artifacts" - "Use these minimum status semantics")."""

    READY_FOR_GEO_PRIOR_ENGINEERING = "ready_for_geo_prior_engineering"
    NOT_RUN_MISSING_AUTHORISED_DATA = "not_run_missing_authorised_data"
    NOT_READY_DATA_QUALITY = "not_ready_data_quality"
    ENGINEERING_FIXTURE_ONLY = "engineering_fixture_only"
    READY_FOR_APPROVED_MILESTONE_2_EXPERIMENT = "ready_for_approved_milestone_2_experiment"


class S1InputStatus(StrEnum):
    """S1 is not implemented by this increment (design suggestion "S1
    boundary") - this enum only records why S1 input is or is not usable."""

    AVAILABLE_AUTHORISED = "available_authorised"
    MISSING = "missing"
    UNVALIDATED = "unvalidated"
    ENGINEERING_FIXTURE_ONLY = "engineering_fixture_only"


class AuthorisationDeclaration(BaseModel):
    """The project owner's (or an authorised supervisor's) explicit
    permission to use one occurrence dataset for the stated prototype
    experiment. A public licence is never silently converted into this
    declaration."""

    model_config = ConfigDict(extra="forbid")

    status: AuthorisationStatus = AuthorisationStatus.UNKNOWN
    authorisation_reference: str | None = None
    purpose: str | None = None
    approving_role: str | None = None

    @model_validator(mode="after")
    def _require_fields_when_authorised(self) -> AuthorisationDeclaration:
        if self.status != AuthorisationStatus.AUTHORISED:
            return self
        missing = [
            name
            for name, value in (
                ("authorisation_reference", self.authorisation_reference),
                ("purpose", self.purpose),
                ("approving_role", self.approving_role),
            )
            if not value or not value.strip()
        ]
        if missing:
            raise ValueError(
                "authorisation.status='authorised' requires non-empty fields: "
                + ", ".join(missing)
            )
        return self


class SpatialSplitConfig(BaseModel):
    """Spatial-block strategy and deterministic split parameters (design
    suggestion "Spatial split Profile v0.1"). Every default here is an
    explicitly uncalibrated reproducibility default, not a scientifically
    validated choice."""

    model_config = ConfigDict(extra="forbid")

    block_strategy: str = "latitude_longitude_grid_v0.1"
    grid_size_degrees: float = 1.0
    train_ratio: float = 0.60
    validation_ratio: float = 0.20
    test_ratio: float = 0.20
    seed: int = 42

    @model_validator(mode="after")
    def _validate_ratios_and_grid(self) -> SpatialSplitConfig:
        if self.block_strategy != "latitude_longitude_grid_v0.1":
            raise ValueError(f"unsupported block_strategy '{self.block_strategy}'")

        for name, value in (
            ("train_ratio", self.train_ratio),
            ("validation_ratio", self.validation_ratio),
            ("test_ratio", self.test_ratio),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative, got {value}")

        total = self.train_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > _RATIO_SUM_TOLERANCE:
            raise ValueError(
                "train_ratio + validation_ratio + test_ratio must equal 1.0 "
                f"(+/- {_RATIO_SUM_TOLERANCE}), got {total}"
            )

        if not math.isfinite(self.grid_size_degrees) or not (
            _MIN_GRID_SIZE_DEGREES < self.grid_size_degrees <= _MAX_GRID_SIZE_DEGREES
        ):
            raise ValueError(
                "grid_size_degrees must be finite and in (0, 10], got "
                f"{self.grid_size_degrees}"
            )
        return self


class GeoExperimentConfig(BaseModel):
    """Top-level ``prepare-geo-experiment`` TOML configuration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EXPERIMENT_CONFIG_SCHEMA_VERSION
    experiment_id: str = Field(min_length=1)
    generated_at: datetime

    occurrence_snapshot_path: str = Field(min_length=1)
    taxonomy_snapshot_path: str = Field(min_length=1)
    import_report_path: str = Field(min_length=1)

    target_taxa: list[str] = Field(default_factory=lambda: list(DEFAULT_TARGET_TAXA), min_length=1)
    geographic_scope: str = "global"
    data_nature: DataNature = DataNature.REAL_WORLD_DATA
    s1_evaluation_input_path: str | None = None

    authorisation: AuthorisationDeclaration = Field(default_factory=AuthorisationDeclaration)
    spatial_split: SpatialSplitConfig = Field(default_factory=SpatialSplitConfig)

    # Forwarded verbatim to `S3Settings.load(overrides=...)` so cleaning
    # thresholds stay governed by the one existing settings model (design
    # suggestion: "Load all cleaning-related configuration through the
    # existing S3Settings model").
    settings_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_timezone_aware_generated_at(self) -> GeoExperimentConfig:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone offset (RFC 3339)")
        return self


class OccurrenceSnapshotIdentity(BaseModel):
    """Provenance summary of the ``occurrences.json`` input file."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    source: str
    source_sha256: str
    snapshot_key: str
    dataset_license: str
    citation: str
    retrieved_at: str
    mapping_version: str
    file_sha256: str


class TaxonomySnapshotIdentity(BaseModel):
    """Provenance summary of the ``taxonomy.json`` input file."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    source: str
    source_sha256: str
    mapping_version: str
    file_sha256: str


class ImportReportIdentity(BaseModel):
    """Provenance summary of the ``import-report.json`` input file."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    source_sha256: str
    importer_version: str
    file_sha256: str


class SplitAssignmentRow(BaseModel):
    """One usable occurrence's block and split assignment."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_record_id: str | None
    taxon_id: str
    block_id: str
    split: SplitName


class ExcludedOccurrenceEntry(BaseModel):
    """One in-scope occurrence excluded from split assignment, with the
    existing cleaner's own flags/actions (never a re-derived reason)."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_record_id: str | None
    taxon_id: str
    quality_flags: list[str]
    cleaning_actions: list[str]


class SpatialSplitManifest(BaseModel):
    """``spatial-split-manifest.json`` (design suggestion "Required output
    artifacts")."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SPATIAL_SPLIT_MANIFEST_SCHEMA_VERSION
    experiment_id: str
    created_at: datetime

    occurrence_snapshot: OccurrenceSnapshotIdentity
    taxonomy_snapshot: TaxonomySnapshotIdentity
    import_report: ImportReportIdentity

    configuration_digest: str
    effective_cleaning_settings: dict[str, Any]

    target_taxa: list[str]
    geographic_scope: str

    block_strategy: str
    block_strategy_version: str
    grid_size_degrees: float
    train_ratio: float
    validation_ratio: float
    test_ratio: float
    seed: int
    split_identity: str

    rows: list[SplitAssignmentRow]
    excluded_records: list[ExcludedOccurrenceEntry]


class GeoExperimentReadinessReport(BaseModel):
    """``readiness-report.json`` (design suggestion "Required output
    artifacts"). Never embeds its own digest - the CLI prints that digest
    after the file is written."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = READINESS_REPORT_SCHEMA_VERSION
    experiment_id: str
    generated_at: datetime

    occurrence_data_status: ReadinessStatus
    s1_input_status: S1InputStatus
    overall_milestone_2_status: ReadinessStatus
    reason_codes: list[str]

    authorisation: AuthorisationDeclaration
    configuration_digest: str
    effective_cleaning_settings: dict[str, Any]

    occurrence_snapshot: OccurrenceSnapshotIdentity
    taxonomy_snapshot: TaxonomySnapshotIdentity
    import_report: ImportReportIdentity

    usable_record_count: int = Field(ge=0)
    excluded_record_count: int = Field(ge=0)

    counts_by_target_taxon: dict[str, int]
    counts_by_source: dict[str, int]
    counts_by_block: dict[str, int]
    counts_by_split: dict[str, int]
    counts_by_exclusion_flag: dict[str, int]

    earliest_usable_event_date: str | None
    latest_usable_event_date: str | None
    missing_target_taxa: list[str]

    warnings: list[str]
    statement: str = (
        "No model was trained, no fusion weight or risk threshold was calibrated, "
        "and no biological or biosecurity performance was measured by this run."
    )

    spatial_split_manifest_path: str
    spatial_split_manifest_sha256: str
