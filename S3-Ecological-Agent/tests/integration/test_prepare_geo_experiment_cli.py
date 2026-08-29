"""Integration tests for the ``prepare-geo-experiment`` CLI subcommand
(DesignSuggestionLog.md "Temporal + CLI/documentation coverage" - "CLI
exit-code tests"). Exercises ``s3_ecological.cli.main`` end to end through
``argparse``, covering the 0/1/2 exit-code contract described in
``cli.py``'s ``_run_prepare_geo_experiment``. Fully offline, synthetic
fixtures only - see tests/integration/test_prepare_geo_experiment.py for the
underlying bundle-tampering and rollback coverage this file does not repeat.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from s3_ecological.cli import main
from s3_ecological.ingestion.occurrence_snapshot import import_occurrence_snapshot

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "importer"

_COMMAND_METADATA: dict[str, Any] = {
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
# Four rows, one per default target genus, deliberately placed (with
# grid_size_degrees=1.0, seed=42) in four distinct grid blocks that are not
# all assigned to the same split - unlike gbif_small.csv (which is missing
# Ceratitis coverage and only fills two splits), this bundle produces zero
# data-quality reason codes, i.e. a genuinely clean run.
_CLEAN_RUN_CSV_ROWS = [
    "generic:401,Anastrepha ludens,Anastrepha ludens,generic:taxon-401,species,"
    "-40,-40,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false",
    "generic:402,Bactrocera dorsalis,Bactrocera dorsalis,generic:taxon-402,species,"
    "-40,-32,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false",
    "generic:403,Ceratitis capitata,Ceratitis capitata,generic:taxon-403,species,"
    "-40,-26,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false",
    "generic:404,Rhagoletis pomonella,Rhagoletis pomonella,generic:taxon-404,species,"
    "-40,-38,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false",
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
    grid_size_degrees: float = 1.0,
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
    content = f"""
schema_version = "1.1.0"
experiment_id = "{experiment_id}"
generated_at = 2026-08-29T00:00:00+10:00
occurrence_snapshot_path = "{(bundle_dir / "occurrences.json").as_posix()}"
taxonomy_snapshot_path = "{(bundle_dir / "taxonomy.json").as_posix()}"
import_report_path = "{(bundle_dir / "import-report.json").as_posix()}"
target_taxa = [{taxa_toml}]
geographic_scope = "global"
data_nature = "{data_nature}"

[authorisation]
status = "{authorisation_status}"
{authorisation_extra}
[spatial_split]
block_strategy = "latitude_longitude_grid_v0.1"
grid_size_degrees = {grid_size_degrees}
train_ratio = 0.6
validation_ratio = 0.2
test_ratio = 0.2
seed = 42

[settings_overrides]
"""
    path.write_text(content, encoding="utf-8")
    return path


def _import_clean_bundle(output_dir: Path) -> None:
    csv_path = output_dir.parent / "clean_run.csv"
    csv_path.write_text(
        "\n".join([_SINGLE_BLOCK_CSV_HEADER, *_CLEAN_RUN_CSV_ROWS]) + "\n", encoding="utf-8"
    )
    _import_bundle(output_dir, input_path=csv_path, source="generic_dwc")


def test_cli_exit_code_is_zero_for_a_clean_synthetic_run(tmp_path, capsys):
    bundle_dir = tmp_path / "bundle"
    _import_clean_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_milestone_2_status"] == "engineering_fixture_only"
    assert (output_dir / "spatial-split-manifest.json").exists()
    assert (output_dir / "readiness-report.json").exists()


def test_cli_exit_code_is_zero_for_missing_authorised_s1_smoke(tmp_path, capsys):
    # A blocked-on-S1 run is a correctly-reported, non-fatal, non-data-quality
    # outcome - it must exit 0, not be silently treated as fully clean and not
    # treated as fatal.
    bundle_dir = tmp_path / "bundle"
    _import_clean_bundle(bundle_dir)
    config_path = _write_config(
        tmp_path / "config.toml",
        bundle_dir=bundle_dir,
        data_nature="real_world_data",
        authorisation_status="authorised",
    )
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_milestone_2_status"] == "not_run_missing_authorised_data"
    assert payload["s1_input_status"] == "missing"
    assert "missing_authorised_s1_outputs" in payload["reason_codes"]


def test_cli_exit_code_is_two_when_a_data_quality_reason_is_present(tmp_path, capsys):
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
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "single_block_only" in payload["reason_codes"]


def test_cli_exit_code_is_one_on_fatal_error_and_writes_no_output(tmp_path, capsys):
    bundle_dir = tmp_path / "bundle"
    # No bundle imported: the input files simply do not exist.
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "prepare-geo-experiment:" in captured.err
    assert captured.out == ""
    assert not output_dir.exists() or not any(output_dir.iterdir())


def test_cli_overwrite_flag_is_required_to_replace_existing_output(tmp_path, capsys):
    bundle_dir = tmp_path / "bundle"
    _import_clean_bundle(bundle_dir)
    config_path = _write_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    output_dir = tmp_path / "out"

    first_exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert first_exit_code == 0
    capsys.readouterr()

    second_exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert second_exit_code == 1
    assert "overwrite" in capsys.readouterr().err

    third_exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
            "--overwrite",
        ]
    )
    assert third_exit_code == 0
    capsys.readouterr()
