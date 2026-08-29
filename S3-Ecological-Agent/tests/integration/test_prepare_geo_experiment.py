"""Integration tests for the offline `prepare-geo-experiment` orchestration
(DesignSuggestionLog.md "2026-08-29 17:16 Australia/Sydney"). Every input is
a small, hand-written synthetic fixture - never real GBIF/ALA data - and no
test makes a network call (there is no network client anywhere in this
code path).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict

import pytest

from s3_ecological.experiments.prepare import GeoExperimentFatalError, prepare_geo_experiment
from s3_ecological.experiments.readiness import (
    REASON_MISSING_AUTHORISED_S1_OUTPUTS,
    REASON_NO_USABLE_OCCURRENCE_RECORDS,
    REASON_SINGLE_BLOCK_ONLY,
)
from s3_ecological.ingestion.occurrence_snapshot import import_occurrence_snapshot
from s3_ecological.schemas.experiment import (
    GeoExperimentReadinessReport,
    ReadinessStatus,
    S1InputStatus,
    SpatialSplitManifest,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "importer"

class _CommandMetadata(TypedDict):
    dataset_id: str
    retrieved_at: str
    dataset_license: str
    citation: str


_COMMAND_METADATA: _CommandMetadata = {
    "dataset_id": "test-dataset",
    "retrieved_at": "2026-08-28T00:00:00+10:00",
    "dataset_license": "CC-BY 4.0",
    "citation": "Test citation, test-dataset",
}

_SINGLE_BLOCK_CSV_HEADER = (
    "occurrenceID,scientificName,acceptedScientificName,taxonID,taxonRank,"
    "decimalLatitude,decimalLongitude,coordinateUncertaintyInMeters,eventDate,"
    "basisOfRecord,license,mediaLicense,isCaptive,isCultivated"
)
_SINGLE_BLOCK_CSV_ROWS = [
    "generic:101,Bactrocera dorsalis,Bactrocera dorsalis,generic:taxon-101,species,"
    "10.1,20.1,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false",
    "generic:102,Ceratitis capitata,Ceratitis capitata,generic:taxon-102,species,"
    "10.2,20.2,50,2020-06-01,HumanObservation,CC-BY 4.0,,false,false",
]


def _import_bundle(output_dir: Path, *, input_path: Path | None = None, source: str = "gbif"):
    return import_occurrence_snapshot(
        input_path=input_path or (FIXTURES_DIR / "gbif_small.csv"),
        source=source,
        query_parameters_path=None,
        output_dir=output_dir,
        **_COMMAND_METADATA,
    )


def _write_config(
    path: Path,
    *,
    bundle_dir: Path,
    experiment_id: str = "test-experiment",
    target_taxa: list[str] | None = None,
    data_nature: str = "synthetic_engineering_fixture",
    authorisation_status: str = "unknown",
    s1_evaluation_input_path: str | None = None,
    grid_size_degrees: float = 1.0,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int = 42,
) -> Path:
    default_taxa = ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]
    taxa_toml = ", ".join(
        f'"{t}"' for t in (target_taxa if target_taxa is not None else default_taxa)
    )
    authorisation_extra = (
        'authorisation_reference = "ref"\npurpose = "test"\napproving_role = "role"\n'
        if authorisation_status == "authorised"
        else ""
    )
    s1_line = (
        f's1_evaluation_input_path = "{Path(s1_evaluation_input_path).as_posix()}"\n'
        if s1_evaluation_input_path
        else ""
    )
    content = f"""
schema_version = "1.0.0"
experiment_id = "{experiment_id}"
generated_at = 2026-08-29T00:00:00+10:00
occurrence_snapshot_path = "{(bundle_dir / "occurrences.json").as_posix()}"
taxonomy_snapshot_path = "{(bundle_dir / "taxonomy.json").as_posix()}"
import_report_path = "{(bundle_dir / "import-report.json").as_posix()}"
target_taxa = [{taxa_toml}]
geographic_scope = "global"
data_nature = "{data_nature}"
{s1_line}
[authorisation]
status = "{authorisation_status}"
{authorisation_extra}
[spatial_split]
block_strategy = "latitude_longitude_grid_v0.1"
grid_size_degrees = {grid_size_degrees}
train_ratio = {train_ratio}
validation_ratio = {validation_ratio}
test_ratio = {test_ratio}
seed = {seed}

[settings_overrides]
"""
    path.write_text(content, encoding="utf-8")
    return path


def test_synthetic_fixture_reports_engineering_fixture_only_and_keeps_blocks_whole(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        data_nature="synthetic_engineering_fixture",
        grid_size_degrees=2.0,
    )

    report = prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")

    assert report.overall_milestone_2_status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY
    assert report.occurrence_data_status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY
    assert "No model was trained" in report.statement

    manifest_path = tmp_path / "out" / "spatial-split-manifest.json"
    manifest = SpatialSplitManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    splits_by_block: dict[str, set[str]] = {}
    for row in manifest.rows:
        splits_by_block.setdefault(row.block_id, set()).add(row.split.value)
    assert all(len(splits) == 1 for splits in splits_by_block.values())


def test_no_network_client_is_reachable_from_the_experiments_package():
    import ast
    from importlib import resources

    package_root = Path(str(resources.files("s3_ecological"))) / "experiments"
    forbidden = {"httpx", "requests", "urllib3", "aiohttp"}
    for path in sorted(package_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        overlap = imported & forbidden
        assert not overlap, f"{path} imports a network client: {overlap}"


def test_missing_s1_input_forces_not_run_even_with_clean_authorised_data(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        data_nature="real_world_data",
        authorisation_status="authorised",
        grid_size_degrees=2.0,
    )

    report = prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")

    assert report.s1_input_status is S1InputStatus.MISSING
    assert report.overall_milestone_2_status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA
    assert REASON_MISSING_AUTHORISED_S1_OUTPUTS in report.reason_codes


def test_unknown_authorisation_forces_not_run_missing_authorised_data(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        data_nature="real_world_data",
        authorisation_status="unknown",
        grid_size_degrees=2.0,
    )

    report = prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")

    assert report.occurrence_data_status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA
    assert report.overall_milestone_2_status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA


def test_no_usable_records_when_target_taxa_do_not_match_the_bundle(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        target_taxa=["Drosophila"],
        data_nature="real_world_data",
        authorisation_status="authorised",
    )

    report = prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")

    assert report.usable_record_count == 0
    assert report.missing_target_taxa == ["Drosophila"]
    assert REASON_NO_USABLE_OCCURRENCE_RECORDS in report.reason_codes
    assert report.occurrence_data_status is ReadinessStatus.NOT_READY_DATA_QUALITY


def test_single_block_reason_when_all_usable_records_share_one_cell(tmp_path):
    csv_path = tmp_path / "single_block.csv"
    csv_path.write_text(
        "\n".join([_SINGLE_BLOCK_CSV_HEADER, *_SINGLE_BLOCK_CSV_ROWS]) + "\n", encoding="utf-8"
    )
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir, input_path=csv_path, source="generic_dwc")

    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        target_taxa=["Bactrocera", "Ceratitis"],
        data_nature="real_world_data",
        authorisation_status="authorised",
    )

    report = prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")

    assert REASON_SINGLE_BLOCK_ONLY in report.reason_codes
    assert report.occurrence_data_status is ReadinessStatus.NOT_READY_DATA_QUALITY
    assert len(report.counts_by_block) == 1


def test_existing_output_without_overwrite_is_fatal_and_overwrite_replaces_it(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    prepare_geo_experiment(config_path=config_path, output_dir=output_dir)
    with pytest.raises(GeoExperimentFatalError, match="overwrite"):
        prepare_geo_experiment(config_path=config_path, output_dir=output_dir)

    report = prepare_geo_experiment(config_path=config_path, output_dir=output_dir, overwrite=True)
    assert report.experiment_id == "test-experiment"


def test_repeated_run_of_identical_input_produces_byte_identical_output(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)

    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    prepare_geo_experiment(config_path=config_path, output_dir=first_dir)
    prepare_geo_experiment(config_path=config_path, output_dir=second_dir)

    for filename in ("spatial-split-manifest.json", "readiness-report.json"):
        assert (first_dir / filename).read_bytes() == (second_dir / filename).read_bytes()


def test_manifest_and_report_checksums_and_pydantic_validation(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    report = prepare_geo_experiment(config_path=config_path, output_dir=output_dir)

    manifest_bytes = (output_dir / "spatial-split-manifest.json").read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == report.spatial_split_manifest_sha256
    SpatialSplitManifest.model_validate_json(manifest_bytes)
    GeoExperimentReadinessReport.model_validate_json(
        (output_dir / "readiness-report.json").read_bytes()
    )
    assert report.configuration_digest == json.loads(manifest_bytes)["configuration_digest"]


def test_dataset_id_mismatch_between_bundle_files_is_fatal(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    occurrences_path = bundle_dir / "occurrences.json"
    payload = json.loads(occurrences_path.read_text(encoding="utf-8"))
    payload["dataset_id"] = "a-different-dataset-id"
    occurrences_path.write_text(json.dumps(payload), encoding="utf-8")

    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)

    with pytest.raises(GeoExperimentFatalError, match="dataset_id"):
        prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")


def test_missing_input_file_is_fatal(tmp_path):
    bundle_dir = tmp_path / "bundle"
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)

    with pytest.raises(GeoExperimentFatalError, match="cannot read"):
        prepare_geo_experiment(config_path=config_path, output_dir=tmp_path / "out")


def test_effective_cleaning_settings_and_configuration_digest_are_recorded_in_both_artifacts(
    tmp_path,
):
    bundle_dir = tmp_path / "bundle"
    _import_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    report = prepare_geo_experiment(config_path=config_path, output_dir=output_dir)
    manifest = SpatialSplitManifest.model_validate_json(
        (output_dir / "spatial-split-manifest.json").read_bytes()
    )

    assert report.configuration_digest == manifest.configuration_digest
    assert report.effective_cleaning_settings == manifest.effective_cleaning_settings
    assert report.effective_cleaning_settings["occurrence_provider"] == "local_snapshot"
