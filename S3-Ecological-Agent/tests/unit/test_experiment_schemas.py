"""Unit tests for the pre-Milestone 2 experiment config/manifest/report
Pydantic schemas (schemas/experiment.py). No file I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from s3_ecological.schemas.experiment import (
    AuthorisationDeclaration,
    AuthorisationStatus,
    GeoExperimentConfig,
    SpatialSplitConfig,
)

_TZ_AWARE_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _minimal_config_kwargs(**overrides):
    kwargs = {
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
def test_spatial_split_config_rejects_ratios_not_summing_to_one(ratios):
    with pytest.raises(ValidationError, match="must equal 1.0"):
        SpatialSplitConfig(**ratios)


def test_spatial_split_config_accepts_ratio_sum_within_tolerance():
    config = SpatialSplitConfig(train_ratio=0.6 + 1e-10, validation_ratio=0.2, test_ratio=0.2)
    assert config.train_ratio == pytest.approx(0.6, abs=1e-9)


def test_spatial_split_config_rejects_negative_ratio():
    with pytest.raises(ValidationError, match="non-negative"):
        SpatialSplitConfig(train_ratio=-0.1, validation_ratio=0.9, test_ratio=0.2)


@pytest.mark.parametrize("grid_size_degrees", [0.0, -1.0, 10.1])
def test_spatial_split_config_rejects_out_of_range_grid_size(grid_size_degrees):
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
