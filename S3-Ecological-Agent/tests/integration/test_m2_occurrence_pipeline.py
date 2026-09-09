"""Offline, end-to-end integration test for the M2-A pipeline
(DesignSuggestionLog.md "2026-09-08 Australia/Sydney - Suggested next
increment: M2-A authorised occurrence preparation and readiness run"):

    small GBIF/ALA JSONL fixtures
        -> scripts/prepare_m2_occurrence_table.py (conversion + dedup)
        -> s3_ecological.cli import-occurrences (Milestone 1.5 bundle)
        -> s3_ecological.cli prepare-geo-experiment (readiness gate)

Entirely offline and synthetic (small fixtures constructed for this test,
not the real committed M2 data - the real data is exercised manually and
recorded in WorkLog.md, not replayed inside the test suite). No S1 output is
supplied, so the expected, correct outcome is the honest blocked status
``not_run_missing_authorised_data`` with reason code
``missing_authorised_s1_outputs`` - this is the required, non-fabricated
result, not a test failure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from s3_ecological.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_m2_occurrence_table.py"


def _load_conversion_module():
    spec = importlib.util.spec_from_file_location("prepare_m2_occurrence_table", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m2 = _load_conversion_module()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _build_fixture_sources(tmp_path: Path) -> tuple[Path, Path]:
    gbif_dir = tmp_path / "gbif"
    ala_dir = tmp_path / "ala"

    # One record per TF4 genus per provider, placed in four distinct
    # 1-degree grid blocks (matching the pattern used by
    # tests/integration/test_prepare_geo_experiment_cli.py's
    # _CLEAN_RUN_CSV_ROWS) so the split assignment is not degenerate.
    gbif_records = {
        "anastrepha": [
            {
                "occurrenceID": "https://example.org/gbif/an-1",
                "acceptedTaxonKey": 101,
                "scientificName": "Anastrepha ludens",
                "acceptedScientificName": "Anastrepha ludens",
                "taxonRank": "SPECIES",
                "decimalLatitude": -40.0,
                "decimalLongitude": -40.0,
                "coordinateUncertaintyInMeters": 50,
                "eventDate": "2020-01-01",
                "basisOfRecord": "HUMAN_OBSERVATION",
                "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
            }
        ],
        "bactrocera": [
            {
                "occurrenceID": "https://example.org/gbif/ba-1",
                "acceptedTaxonKey": 102,
                "scientificName": "Bactrocera dorsalis",
                "acceptedScientificName": "Bactrocera dorsalis",
                "taxonRank": "SPECIES",
                "decimalLatitude": -40.0,
                "decimalLongitude": -32.0,
                "coordinateUncertaintyInMeters": 50,
                "eventDate": "2020-01-01",
                "basisOfRecord": "HUMAN_OBSERVATION",
                "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
            }
        ],
        "ceratitis": [
            {
                "occurrenceID": "https://example.org/gbif/ce-1",
                "acceptedTaxonKey": 103,
                "scientificName": "Ceratitis capitata",
                "acceptedScientificName": "Ceratitis capitata",
                "taxonRank": "SPECIES",
                "decimalLatitude": -40.0,
                "decimalLongitude": -26.0,
                "coordinateUncertaintyInMeters": 50,
                "eventDate": "2020-01-01",
                "basisOfRecord": "HUMAN_OBSERVATION",
                "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
            }
        ],
        "rhagoletis": [
            {
                "occurrenceID": "https://example.org/gbif/rh-1",
                "acceptedTaxonKey": 104,
                "scientificName": "Rhagoletis pomonella",
                "acceptedScientificName": "Rhagoletis pomonella",
                "taxonRank": "SPECIES",
                "decimalLatitude": -40.0,
                "decimalLongitude": -38.0,
                "coordinateUncertaintyInMeters": 50,
                "eventDate": "2020-01-01",
                "basisOfRecord": "HUMAN_OBSERVATION",
                "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
            }
        ],
    }

    ala_records = {
        "anastrepha": [
            {
                "uuid": "ala-an-1",
                "taxonID": "ala-taxon-an",
                "scientificName": "Anastrepha fraterculus",
                "taxonRank": "species",
                "decimalLatitude": -39.0,
                "decimalLongitude": -41.0,
                "eventDate": 1_577_836_800_000,  # 2020-01-01
                "license": "CC-BY",
            }
        ],
        "bactrocera": [],
        "ceratitis": [],
        "rhagoletis": [],
    }

    for genus, records in gbif_records.items():
        _write_jsonl(gbif_dir / f"{genus}.jsonl", records)
    for genus, records in ala_records.items():
        _write_jsonl(ala_dir / f"{genus}.jsonl", records)

    return gbif_dir, ala_dir


def _write_m2_config(
    path: Path, *, bundle_dir: Path, authorisation_status: str = "unknown"
) -> Path:
    content = f"""
schema_version = "1.1.0"
experiment_id = "m2-pipeline-test"
generated_at = 2026-09-08T00:00:00+10:00
occurrence_snapshot_path = "{(bundle_dir / "occurrences.json").as_posix()}"
taxonomy_snapshot_path = "{(bundle_dir / "taxonomy.json").as_posix()}"
import_report_path = "{(bundle_dir / "import-report.json").as_posix()}"
target_taxa = ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]
geographic_scope = "global"
geographic_scope_mode = "label_only"
data_nature = "real_world_data"

[authorisation]
status = "{authorisation_status}"

[spatial_split]
block_strategy = "latitude_longitude_grid_v0.1"
grid_size_degrees = 1.0
train_ratio = 0.6
validation_ratio = 0.2
test_ratio = 0.2
seed = 42

[settings_overrides]
"""
    path.write_text(content, encoding="utf-8")
    return path


def test_full_offline_pipeline_reports_missing_s1_honestly(tmp_path):
    gbif_dir, ala_dir = _build_fixture_sources(tmp_path)

    conversion_csv = tmp_path / "conversion" / "occurrences.csv"
    conversion_report_path = tmp_path / "conversion" / "report.json"
    conversion_report = m2.convert(
        gbif_dir=gbif_dir,
        ala_dir=ala_dir,
        genera=("anastrepha", "bactrocera", "ceratitis", "rhagoletis"),
        output_csv=conversion_csv,
        output_report=conversion_report_path,
    )
    assert conversion_report["reconciliation"]["reconciles"] is True
    assert conversion_report["reconciliation"]["total_input_records"] == 5
    assert conversion_report["reconciliation"]["emitted_records"] == 5

    bundle_dir = tmp_path / "bundle"
    import_exit_code = main(
        [
            "import-occurrences",
            "--input",
            str(conversion_csv),
            "--source",
            "generic_dwc",
            "--dataset-id",
            "m2-pipeline-test-bundle",
            "--retrieved-at",
            "2026-09-08T00:00:00Z",
            "--dataset-license",
            "Mixed - see per-record license field",
            "--citation",
            "Synthetic M2 pipeline test fixture, not real occurrence data",
            "--output-dir",
            str(bundle_dir),
        ]
    )
    assert import_exit_code == 0
    import_report = json.loads((bundle_dir / "import-report.json").read_text(encoding="utf-8"))
    assert import_report["rejected_record_count"] == 0
    assert import_report["accepted_record_count"] == 5

    config_path = _write_m2_config(tmp_path / "config.toml", bundle_dir=bundle_dir)
    readiness_dir = tmp_path / "readiness"
    readiness_exit_code = main(
        [
            "prepare-geo-experiment",
            "--config",
            str(config_path),
            "--output-dir",
            str(readiness_dir),
        ]
    )

    # missing_authorised_s1_outputs is not a data-quality reason code, so the
    # documented exit-code contract is 0, not 2 - a blocked-on-S1 run is a
    # correct, non-fatal outcome that must not be reported as a data defect.
    assert readiness_exit_code == 0

    readiness_report = json.loads(
        (readiness_dir / "readiness-report.json").read_text(encoding="utf-8")
    )
    assert readiness_report["overall_milestone_2_status"] == "not_run_missing_authorised_data"
    assert readiness_report["s1_input_status"] == "missing"
    assert "missing_authorised_s1_outputs" in readiness_report["reason_codes"]
    assert readiness_report["missing_target_taxa"] == []
    assert set(readiness_report["counts_by_target_taxon"].keys()) == {
        "Anastrepha",
        "Bactrocera",
        "Ceratitis",
        "Rhagoletis",
    }

    manifest = json.loads(
        (readiness_dir / "spatial-split-manifest.json").read_text(encoding="utf-8")
    )
    block_to_splits: dict[str, set[str]] = {}
    for row in manifest["rows"]:
        block_to_splits.setdefault(row["block_id"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in block_to_splits.values())


def test_full_offline_pipeline_is_reproducible_byte_identical(tmp_path):
    gbif_dir, ala_dir = _build_fixture_sources(tmp_path)

    def _run(output_root: Path) -> bytes:
        conversion_csv = output_root / "occurrences.csv"
        m2.convert(
            gbif_dir=gbif_dir,
            ala_dir=ala_dir,
            genera=("anastrepha", "bactrocera", "ceratitis", "rhagoletis"),
            output_csv=conversion_csv,
            output_report=output_root / "report.json",
        )
        return conversion_csv.read_bytes()

    first = _run(tmp_path / "run1")
    second = _run(tmp_path / "run2")
    assert first == second
