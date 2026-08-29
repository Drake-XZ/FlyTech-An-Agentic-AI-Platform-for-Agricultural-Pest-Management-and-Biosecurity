"""Unit tests for the pre-Milestone 2 experiment config/manifest/report
Pydantic schemas (schemas/experiment.py). No file I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from s3_ecological.schemas.experiment import (
    AuthorisationDeclaration,
    AuthorisationStatus,
    GeoExperimentConfig,
    GeoExperimentReadinessReport,
    GeographicScopeMode,
    ImportReportIdentity,
    OccurrenceSnapshotIdentity,
    ReadinessStatus,
    S1InputStatus,
    SpatialSplitConfig,
    SpatialSplitManifest,
    TaxonomySnapshotIdentity,
)

_TZ_AWARE_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _minimal_config_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "experiment_id": "test-experiment",
        "generated_at": _TZ_AWARE_NOW,
        "occurrence_snapshot_path": "occurrences.json",
        "taxonomy_snapshot_path": "taxonomy.json",
        "import_report_path": "import-report.json",
    }
    kwargs.update(overrides)
    return kwargs


def test_geo_experiment_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        GeoExperimentConfig(**_minimal_config_kwargs(unexpected_field="x"))


def test_geo_experiment_config_rejects_naive_generated_at():
    with pytest.raises(ValidationError, match="timezone"):
        GeoExperimentConfig(**_minimal_config_kwargs(generated_at=datetime(2026, 8, 29)))


def test_geo_experiment_config_defaults_to_the_four_tf4_genera():
    config = GeoExperimentConfig(**_minimal_config_kwargs())
    assert config.target_taxa == ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]


def test_geo_experiment_config_rejects_empty_target_taxa():
    with pytest.raises(ValidationError):
        GeoExperimentConfig(**_minimal_config_kwargs(target_taxa=[]))


def test_authorisation_declaration_rejects_authorised_without_required_fields():
    with pytest.raises(ValidationError, match="authorisation_reference"):
        AuthorisationDeclaration(status=AuthorisationStatus.AUTHORISED)


def test_authorisation_declaration_rejects_blank_required_field():
    with pytest.raises(ValidationError, match="purpose"):
        AuthorisationDeclaration(
            status=AuthorisationStatus.AUTHORISED,
            authorisation_reference="ref",
            purpose="   ",
            approving_role="role",
        )


def test_authorisation_declaration_accepts_authorised_with_all_fields():
    declaration = AuthorisationDeclaration(
        status=AuthorisationStatus.AUTHORISED,
        authorisation_reference="ref",
        purpose="purpose",
        approving_role="role",
    )
    assert declaration.status is AuthorisationStatus.AUTHORISED


def test_authorisation_declaration_defaults_to_unknown_with_no_fields_required():
    declaration = AuthorisationDeclaration()
    assert declaration.status is AuthorisationStatus.UNKNOWN


def test_spatial_split_config_rejects_unsupported_block_strategy():
    with pytest.raises(ValidationError, match="unsupported block_strategy"):
        SpatialSplitConfig(block_strategy="h3_v1")


@pytest.mark.parametrize(
    "ratios",
    [
        {"train_ratio": 0.5, "validation_ratio": 0.3, "test_ratio": 0.3},
        {"train_ratio": 0.5, "validation_ratio": 0.2, "test_ratio": 0.2},
    ],
)
def test_spatial_split_config_rejects_ratios_not_summing_to_one(
    ratios: dict[str, float],
):
    with pytest.raises(ValidationError, match="must equal 1.0"):
        SpatialSplitConfig.model_validate(ratios)


def test_spatial_split_config_accepts_ratio_sum_within_tolerance():
    config = SpatialSplitConfig(train_ratio=0.6 + 1e-10, validation_ratio=0.2, test_ratio=0.2)
    assert config.train_ratio == pytest.approx(0.6, abs=1e-9)


def test_spatial_split_config_rejects_negative_ratio():
    with pytest.raises(ValidationError, match="non-negative"):
        SpatialSplitConfig(train_ratio=-0.1, validation_ratio=0.9, test_ratio=0.2)


@pytest.mark.parametrize("grid_size_degrees", [0.0, -1.0, 10.1])
def test_spatial_split_config_rejects_out_of_range_grid_size(grid_size_degrees: float):
    with pytest.raises(ValidationError, match="grid_size_degrees"):
        SpatialSplitConfig(grid_size_degrees=grid_size_degrees)


def test_spatial_split_config_accepts_boundary_grid_size_of_ten():
    config = SpatialSplitConfig(grid_size_degrees=10.0)
    assert config.grid_size_degrees == 10.0


def test_geo_experiment_config_forwards_settings_overrides_verbatim():
    config = GeoExperimentConfig(
        **_minimal_config_kwargs(settings_overrides={"max_coordinate_uncertainty_m": 1000.0})
    )
    assert config.settings_overrides == {"max_coordinate_uncertainty_m": 1000.0}


def test_geo_experiment_config_rejects_unsupported_schema_version():
    with pytest.raises(ValidationError):
        GeoExperimentConfig(**_minimal_config_kwargs(schema_version="1.0.0"))


def test_geo_experiment_config_default_geographic_scope_mode_is_label_only():
    config = GeoExperimentConfig(**_minimal_config_kwargs())
    assert config.geographic_scope_mode is GeographicScopeMode.LABEL_ONLY


def test_geo_experiment_config_rejects_unsupported_geographic_scope_mode():
    with pytest.raises(ValidationError):
        GeoExperimentConfig(**_minimal_config_kwargs(geographic_scope_mode="region_filtered"))


def test_geo_experiment_config_rejects_whitespace_only_experiment_id():
    with pytest.raises(ValidationError, match="experiment_id"):
        GeoExperimentConfig(**_minimal_config_kwargs(experiment_id="   "))


def test_geo_experiment_config_rejects_whitespace_only_geographic_scope():
    with pytest.raises(ValidationError, match="geographic_scope"):
        GeoExperimentConfig(**_minimal_config_kwargs(geographic_scope="   "))


def test_geo_experiment_config_trims_experiment_id_and_geographic_scope():
    config = GeoExperimentConfig(
        **_minimal_config_kwargs(experiment_id="  padded-id  ", geographic_scope="  global  ")
    )
    assert config.experiment_id == "padded-id"
    assert config.geographic_scope == "global"


def test_geo_experiment_config_rejects_blank_target_taxon_entry():
    with pytest.raises(ValidationError, match="blank"):
        GeoExperimentConfig(**_minimal_config_kwargs(target_taxa=["Bactrocera", "   "]))


def test_geo_experiment_config_rejects_duplicate_target_taxa_after_trimming():
    with pytest.raises(ValidationError, match="duplicate"):
        GeoExperimentConfig(
            **_minimal_config_kwargs(target_taxa=["Bactrocera", " Bactrocera "])
        )


def test_geo_experiment_config_trims_only_surrounding_whitespace_in_target_taxa():
    config = GeoExperimentConfig(
        **_minimal_config_kwargs(target_taxa=["  Bactrocera  ", "Ceratitis"])
    )
    assert config.target_taxa == ["Bactrocera", "Ceratitis"]


def test_geo_experiment_config_accepts_unicode_scientific_name_unchanged():
    # Only surrounding whitespace may be stripped - spelling, case, and
    # non-ASCII characters (e.g. a diacritic) must survive exactly.
    config = GeoExperimentConfig(
        **_minimal_config_kwargs(target_taxa=["Anastrepha", "Bactroceránfoo"])
    )
    assert "Bactroceránfoo" in config.target_taxa


def _minimal_occurrence_identity(**overrides: object) -> OccurrenceSnapshotIdentity:
    kwargs: dict[str, object] = {
        "dataset_id": "test-dataset",
        "source": "gbif",
        "source_sha256": "a" * 64,
        "snapshot_key": "key",
        "dataset_license": "CC-BY 4.0",
        "citation": "Test citation",
        "retrieved_at": "2026-08-28T00:00:00+10:00",
        "mapping_version": "occurrence-mapping-v1",
        "file_sha256": "b" * 64,
    }
    kwargs.update(overrides)
    return OccurrenceSnapshotIdentity.model_validate(kwargs)


def _minimal_taxonomy_identity(**overrides: object) -> TaxonomySnapshotIdentity:
    kwargs: dict[str, object] = {
        "dataset_id": "test-dataset",
        "source": "gbif",
        "source_sha256": "a" * 64,
        "mapping_version": "taxonomy-mapping-v1",
        "file_sha256": "c" * 64,
    }
    kwargs.update(overrides)
    return TaxonomySnapshotIdentity.model_validate(kwargs)


def _minimal_import_report_identity(**overrides: object) -> ImportReportIdentity:
    kwargs: dict[str, object] = {
        "dataset_id": "test-dataset",
        "source_sha256": "a" * 64,
        "importer_version": "s3-ecological-importer-0.1.0",
        "file_sha256": "d" * 64,
    }
    kwargs.update(overrides)
    return ImportReportIdentity.model_validate(kwargs)


def _minimal_manifest_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "experiment_id": "test-experiment",
        "created_at": _TZ_AWARE_NOW,
        "occurrence_snapshot": _minimal_occurrence_identity(),
        "taxonomy_snapshot": _minimal_taxonomy_identity(),
        "import_report": _minimal_import_report_identity(),
        "configuration_digest": "e" * 64,
        "effective_cleaning_settings": {},
        "target_taxa": ["Bactrocera"],
        "geographic_scope": "global",
        "geographic_scope_mode": GeographicScopeMode.LABEL_ONLY,
        "block_strategy": "latitude_longitude_grid_v0.1",
        "block_strategy_version": "v0.1",
        "grid_size_degrees": 1.0,
        "train_ratio": 0.6,
        "validation_ratio": 0.2,
        "test_ratio": 0.2,
        "seed": 42,
        "split_identity": "f" * 64,
        "rows": [],
        "excluded_records": [],
    }
    kwargs.update(overrides)
    return kwargs


def test_spatial_split_manifest_rejects_unsupported_schema_version():
    with pytest.raises(ValidationError):
        SpatialSplitManifest(**_minimal_manifest_kwargs(schema_version="1.0.0"))


def test_spatial_split_manifest_accepts_current_schema_version():
    manifest = SpatialSplitManifest(**_minimal_manifest_kwargs())
    assert manifest.schema_version == "1.1.0"
    assert manifest.geographic_scope_mode is GeographicScopeMode.LABEL_ONLY


def _minimal_report_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "experiment_id": "test-experiment",
        "generated_at": _TZ_AWARE_NOW,
        "occurrence_data_status": ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING,
        "s1_input_status": S1InputStatus.MISSING,
        "overall_milestone_2_status": ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA,
        "reason_codes": [],
        "authorisation": AuthorisationDeclaration(),
        "configuration_digest": "e" * 64,
        "effective_cleaning_settings": {},
        "geographic_scope_mode": GeographicScopeMode.LABEL_ONLY,
        "occurrence_snapshot": _minimal_occurrence_identity(),
        "taxonomy_snapshot": _minimal_taxonomy_identity(),
        "import_report": _minimal_import_report_identity(),
        "usable_record_count": 0,
        "excluded_record_count": 0,
        "counts_by_target_taxon": {},
        "counts_by_source": {},
        "counts_by_block": {},
        "counts_by_split": {},
        "counts_by_quality_flag": {},
        "counts_by_cleaning_action": {},
        "counts_by_exclusion_flag": {},
        "counts_by_event_year": {},
        "undated_usable_record_count": 0,
        "earliest_usable_event_date": None,
        "latest_usable_event_date": None,
        "missing_target_taxa": [],
        "warnings": [],
        "spatial_split_manifest_path": "spatial-split-manifest.json",
        "spatial_split_manifest_sha256": "f" * 64,
    }
    kwargs.update(overrides)
    return kwargs


def test_readiness_report_rejects_unsupported_schema_version():
    with pytest.raises(ValidationError):
        GeoExperimentReadinessReport(**_minimal_report_kwargs(schema_version="1.0.0"))


def test_readiness_report_accepts_current_schema_version():
    report = GeoExperimentReadinessReport(**_minimal_report_kwargs())
    assert report.schema_version == "2.0.0"
    assert report.geographic_scope_mode is GeographicScopeMode.LABEL_ONLY
