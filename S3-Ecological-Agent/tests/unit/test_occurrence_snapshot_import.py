"""Unit tests for the offline occurrence snapshot importer (Milestone 1.5).

All fixtures under ``tests/fixtures/importer/`` are small, hand-written
synthetic rows - never a real GBIF/ALA export - so these tests exercise the
field-mapping and error-handling rules without any real occurrence data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import pytest

from s3_ecological.ingestion.occurrence_snapshot import (
    ImportFatalError,
    import_occurrence_snapshot,
)
from s3_ecological.schemas.snapshot import ImportStatus, OccurrenceSnapshot, TaxonomySnapshot

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


def _import_gbif(output_dir: Path, **overrides):
    kwargs = {
        "input_path": FIXTURES_DIR / "gbif_small.csv",
        "source": "gbif",
        "query_parameters_path": None,
        "output_dir": output_dir,
        **_COMMAND_METADATA,
    }
    kwargs.update(overrides)
    return import_occurrence_snapshot(**kwargs)


def test_gbif_csv_happy_path_accepts_every_row_and_writes_bundle(tmp_path):
    report = _import_gbif(tmp_path)

    assert report.status == ImportStatus.COMPLETED
    assert report.input_record_count == 5
    assert report.accepted_record_count == 5
    assert report.rejected_record_count == 0
    assert report.rejections == []

    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    taxonomy = json.loads((tmp_path / "taxonomy.json").read_text(encoding="utf-8"))
    assert len(occurrences["records"]) == 5
    assert occurrences["dataset_id"] == "test-dataset"
    expected_key = f"test-dataset:{occurrences['source_sha256'][:12]}:dwc-occurrence-v1"
    assert occurrences["snapshot_key"] == expected_key
    assert taxonomy["source_sha256"] == occurrences["source_sha256"]


def test_taxon_id_is_namespaced_with_the_source_prefix(tmp_path):
    _import_gbif(tmp_path)
    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    for record in occurrences["records"]:
        assert record["taxon_id"].startswith("gbif:")
        assert not record["taxon_id"].startswith("gbif:gbif:")


def test_generated_record_id_is_used_when_no_id_header_is_present(tmp_path):
    _import_gbif(tmp_path)
    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    ceratitis = next(
        r for r in occurrences["records"] if r["scientific_name_raw"] == "Ceratitis capitata"
    )
    assert ceratitis["source_record_id"].startswith("generated:")
    assert len(ceratitis["source_record_id"]) == len("generated:") + 64


def test_generated_record_id_does_not_depend_on_row_position(tmp_path):
    lines = (FIXTURES_DIR / "gbif_small.csv").read_text(encoding="utf-8").splitlines()
    header, data_rows = lines[0], lines[1:]
    reordered = tmp_path / "reordered.csv"
    reordered.write_text("\n".join([header, *reversed(data_rows)]) + "\n", encoding="utf-8")

    original_dir, reordered_dir = tmp_path / "original", tmp_path / "reordered_out"
    _import_gbif(original_dir)
    import_occurrence_snapshot(
        input_path=reordered,
        source="gbif",
        query_parameters_path=None,
        output_dir=reordered_dir,
        **_COMMAND_METADATA,
    )

    def _ceratitis_id(directory: Path) -> str:
        occurrences = json.loads((directory / "occurrences.json").read_text(encoding="utf-8"))
        record = next(
            r for r in occurrences["records"] if r["scientific_name_raw"] == "Ceratitis capitata"
        )
        return record["source_record_id"]

    assert _ceratitis_id(original_dir) == _ceratitis_id(reordered_dir)


def test_partial_date_falls_back_to_year_month_or_year_alone(tmp_path):
    _import_gbif(tmp_path)
    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    ceratitis = next(
        r for r in occurrences["records"] if r["scientific_name_raw"] == "Ceratitis capitata"
    )
    assert ceratitis["event_date"] == "2020-07"


def test_unrecognized_boolean_is_a_mapping_warning_not_a_rejection(tmp_path):
    report = _import_gbif(tmp_path)
    assert report.rejected_record_count == 0
    assert len(report.mapping_warnings) == 1
    warning = report.mapping_warnings[0]
    assert warning.code == "unrecognized_boolean"

    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    ludens = next(
        r for r in occurrences["records"] if r["scientific_name_raw"] == "Anastrepha ludens"
    )
    assert ludens["is_captive_or_cultivated"] is None


def test_two_distinct_taxon_ids_sharing_a_name_are_kept_separate_and_marked_ambiguous(tmp_path):
    _import_gbif(tmp_path)
    taxonomy = json.loads((tmp_path / "taxonomy.json").read_text(encoding="utf-8"))
    dorsalis_items = [t for t in taxonomy["taxa"] if t["scientific_name"] == "Bactrocera dorsalis"]
    assert len(dorsalis_items) == 2
    assert {tuple(item["taxon_ids"].values())[0] for item in dorsalis_items} == {
        "gbif:145433",
        "gbif:999999",
    }
    assert all(item["ambiguous"] for item in dorsalis_items)

    rhagoletis_items = [
        t for t in taxonomy["taxa"] if t["scientific_name"] == "Rhagoletis pomonella"
    ]
    assert len(rhagoletis_items) == 1
    assert rhagoletis_items[0]["ambiguous"] is False


def test_ala_tsv_happy_path_maps_ala_specific_headers(tmp_path):
    report = import_occurrence_snapshot(
        input_path=FIXTURES_DIR / "ala_small.tsv",
        source="ala",
        query_parameters_path=None,
        output_dir=tmp_path,
        **_COMMAND_METADATA,
    )
    assert report.status == ImportStatus.COMPLETED
    assert report.accepted_record_count == 3
    assert report.delimiter == "\t"

    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    tryoni = next(
        r for r in occurrences["records"] if r["scientific_name_raw"] == "Bactrocera tryoni"
    )
    assert tryoni["taxon_id"] == "ala:urn:lsid:biodiversity.org.au:apni.taxon:12345"
    cerasi = next(
        r for r in occurrences["records"] if r["scientific_name_raw"] == "Rhagoletis cerasi"
    )
    assert cerasi["source_record_id"].startswith("generated:")
    assert cerasi["event_date"] == "2021"


def test_malformed_rows_alone_are_all_rejected_and_the_import_is_fatal(tmp_path):
    with pytest.raises(ImportFatalError, match="zero accepted records"):
        import_occurrence_snapshot(
            input_path=FIXTURES_DIR / "malformed_rows.csv",
            source="generic_dwc",
            query_parameters_path=None,
            output_dir=tmp_path,
            **_COMMAND_METADATA,
        )


def test_malformed_rows_each_produce_their_documented_rejection_code(tmp_path):
    # malformed_rows.csv alone is all-rejected (fatal, no report). Adding one
    # trailing well-formed row lets the import succeed with rejections, so
    # the report's per-row codes can be inspected directly.
    combined = tmp_path / "combined.csv"
    malformed_lines = (
        (FIXTURES_DIR / "malformed_rows.csv").read_text(encoding="utf-8").splitlines()
    )
    good_row = (
        "generic:900,Bactrocera dorsalis,Bactrocera dorsalis,generic:taxon-900,species,"
        "10.0,20.0,50,2020-01-01,HumanObservation,CC-BY 4.0,,false,false"
    )
    combined.write_text("\n".join([*malformed_lines, good_row]) + "\n", encoding="utf-8")

    report = import_occurrence_snapshot(
        input_path=combined,
        source="generic_dwc",
        query_parameters_path=None,
        output_dir=tmp_path,
        **_COMMAND_METADATA,
    )
    assert report.status == ImportStatus.COMPLETED_WITH_REJECTIONS
    assert report.accepted_record_count == 1
    assert report.rejected_record_count == 6
    codes_by_row = {rejection.row_number: rejection.code for rejection in report.rejections}
    assert codes_by_row == {
        1: "missing_scientific_name",
        2: "missing_taxon_id",
        3: "invalid_numeric_value",
        4: "negative_coordinate_uncertainty",
        5: "non_finite_numeric_value",
        6: "invalid_record_schema",
    }
    assert (tmp_path / "occurrences.json").exists()
    assert (tmp_path / "import-report.json").exists()


def test_missing_required_scientific_name_header_is_fatal(tmp_path):
    bad_input = tmp_path / "bad.csv"
    bad_input.write_text("occurrenceID,taxonKey\nrec-1,145433\n", encoding="utf-8")
    with pytest.raises(ImportFatalError, match="scientificName"):
        import_occurrence_snapshot(
            input_path=bad_input,
            source="gbif",
            query_parameters_path=None,
            output_dir=tmp_path,
            **_COMMAND_METADATA,
        )


def test_unsupported_extension_source_combination_is_fatal(tmp_path):
    bad_input = tmp_path / "data.txt"
    bad_input.write_text("scientificName,taxonKey\n", encoding="utf-8")
    with pytest.raises(ImportFatalError, match="unsupported extension"):
        import_occurrence_snapshot(
            input_path=bad_input,
            source="gbif",
            query_parameters_path=None,
            output_dir=tmp_path,
            **_COMMAND_METADATA,
        )


def test_retrieved_at_without_timezone_is_fatal(tmp_path):
    with pytest.raises(ImportFatalError, match="timezone"):
        _import_gbif(tmp_path, retrieved_at="2026-08-28T00:00:00")


def test_empty_dataset_id_is_fatal(tmp_path):
    with pytest.raises(ImportFatalError, match="dataset-id"):
        _import_gbif(tmp_path, dataset_id="   ")


def test_secret_like_query_parameter_key_is_rejected(tmp_path):
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"api_key": "abc123"}), encoding="utf-8")
    with pytest.raises(ImportFatalError, match="secret"):
        _import_gbif(tmp_path, query_parameters_path=params_path)


def test_query_parameters_are_recorded_on_every_record(tmp_path):
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"country": "AU", "year": 2024}), encoding="utf-8")
    _import_gbif(tmp_path, query_parameters_path=params_path)

    occurrences = json.loads((tmp_path / "occurrences.json").read_text(encoding="utf-8"))
    assert occurrences["query_parameters"] == {"country": "AU", "year": 2024}
    assert all(
        r["query_parameters"] == {"country": "AU", "year": 2024} for r in occurrences["records"]
    )


def test_existing_output_without_overwrite_is_fatal_and_overwrite_replaces_it(tmp_path):
    _import_gbif(tmp_path)
    with pytest.raises(ImportFatalError, match="already exists"):
        _import_gbif(tmp_path)

    report = _import_gbif(tmp_path, overwrite=True)
    assert report.status == ImportStatus.COMPLETED


def test_repeated_import_of_identical_input_produces_byte_identical_output(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    _import_gbif(first_dir)
    _import_gbif(second_dir)

    first_occurrences = (first_dir / "occurrences.json").read_bytes()
    second_occurrences = (second_dir / "occurrences.json").read_bytes()
    assert first_occurrences == second_occurrences

    first_taxonomy = (first_dir / "taxonomy.json").read_bytes()
    second_taxonomy = (second_dir / "taxonomy.json").read_bytes()
    assert first_taxonomy == second_taxonomy


def test_output_file_checksums_in_report_match_the_written_bytes(tmp_path):
    report = _import_gbif(tmp_path)
    occurrences_bytes = (tmp_path / "occurrences.json").read_bytes()
    taxonomy_bytes = (tmp_path / "taxonomy.json").read_bytes()

    import hashlib

    occurrences_sha256 = report.output_files["occurrences"].sha256
    assert occurrences_sha256 == hashlib.sha256(occurrences_bytes).hexdigest()
    taxonomy_sha256 = report.output_files["taxonomy"].sha256
    assert taxonomy_sha256 == hashlib.sha256(taxonomy_bytes).hexdigest()


def test_output_bundle_validates_against_the_pydantic_snapshot_schemas(tmp_path):
    _import_gbif(tmp_path)
    occurrences_text = (tmp_path / "occurrences.json").read_text(encoding="utf-8")
    OccurrenceSnapshot.model_validate_json(occurrences_text)
    taxonomy_text = (tmp_path / "taxonomy.json").read_text(encoding="utf-8")
    TaxonomySnapshot.model_validate_json(taxonomy_text)


def test_canonical_source_reimports_a_previous_occurrences_json_unchanged(tmp_path):
    first_dir = tmp_path / "first"
    _import_gbif(first_dir)

    second_dir = tmp_path / "second"
    report = import_occurrence_snapshot(
        input_path=first_dir / "occurrences.json",
        source="canonical",
        query_parameters_path=None,
        output_dir=second_dir,
        **_COMMAND_METADATA,
    )
    assert report.status == ImportStatus.COMPLETED
    assert report.accepted_record_count == 5

    first_payload = json.loads((first_dir / "occurrences.json").read_text(encoding="utf-8"))
    second_payload = json.loads((second_dir / "occurrences.json").read_text(encoding="utf-8"))
    assert first_payload["records"] == second_payload["records"]


def test_canonical_source_rejects_metadata_that_does_not_match_the_command_line(tmp_path):
    first_dir = tmp_path / "first"
    _import_gbif(first_dir)

    with pytest.raises(ImportFatalError, match="does not match"):
        import_occurrence_snapshot(
            input_path=first_dir / "occurrences.json",
            source="canonical",
            query_parameters_path=None,
            output_dir=tmp_path / "second",
            dataset_id="a-different-dataset-id",
            retrieved_at=_COMMAND_METADATA["retrieved_at"],
            dataset_license=_COMMAND_METADATA["dataset_license"],
            citation=_COMMAND_METADATA["citation"],
        )
