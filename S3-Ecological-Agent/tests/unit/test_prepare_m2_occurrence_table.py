"""Unit tests for ``scripts/prepare_m2_occurrence_table.py`` (M2-A: see
DesignSuggestionLog.md "2026-09-08 Australia/Sydney - Suggested next
increment: M2-A authorised occurrence preparation and readiness run",
"Required tests and verification"). Offline, no network access, no S1/model
dependency - this module only exercises the standalone field-mapping and
deduplication tool.

The script lives under ``scripts/`` (not the ``s3_ecological`` package), so
it is loaded here via ``importlib`` rather than a normal import.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import socket
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_m2_occurrence_table.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prepare_m2_occurrence_table", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses introspects sys.modules[cls.__module__], so the module must
    # be registered before exec_module runs the @dataclass decorators.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m2 = _load_module()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _run_convert(tmp_path: Path, *, gbif: dict, ala: dict, genera=("bactrocera",), **kwargs):
    gbif_dir = tmp_path / "gbif"
    ala_dir = tmp_path / "ala"
    for genus, records in gbif.items():
        _write_jsonl(gbif_dir / f"{genus}.jsonl", records)
    for genus in genera:
        if genus not in gbif:
            _write_jsonl(gbif_dir / f"{genus}.jsonl", [])
    for genus, records in ala.items():
        _write_jsonl(ala_dir / f"{genus}.jsonl", records)
    for genus in genera:
        if genus not in ala:
            _write_jsonl(ala_dir / f"{genus}.jsonl", [])

    output_csv = tmp_path / "out" / "occurrences.csv"
    output_report = tmp_path / "out" / "report.json"
    report = m2.convert(
        gbif_dir=gbif_dir,
        ala_dir=ala_dir,
        genera=genera,
        output_csv=output_csv,
        output_report=output_report,
        **kwargs,
    )
    return report, output_csv, output_report


# --------------------------------------------------------------------- #
# Field mapping
# --------------------------------------------------------------------- #


def test_gbif_field_mapping_preserves_identity_and_licence(tmp_path):
    gbif_record = {
        "occurrenceID": "https://www.inaturalist.org/observations/111",
        "acceptedTaxonKey": 12345,
        "taxonKey": 999,
        "scientificName": "Bactrocera dorsalis",
        "acceptedScientificName": "Bactrocera dorsalis",
        "taxonRank": "SPECIES",
        "decimalLatitude": -10.5,
        "decimalLongitude": 130.25,
        "coordinateUncertaintyInMeters": 50,
        "eventDate": "2021-05-01",
        "basisOfRecord": "HUMAN_OBSERVATION",
        "license": "http://creativecommons.org/licenses/by-nc/4.0/legalcode",
        "media": [{"license": "http://creativecommons.org/licenses/by-nc/4.0/"}],
        "http://unknown.org/captive_cultivated": "wild",
    }
    report, output_csv, _ = _run_convert(tmp_path, gbif={"bactrocera": [gbif_record]}, ala={})

    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    row = rows[0]
    assert row["occurrenceID"] == "gbif:https://www.inaturalist.org/observations/111"
    assert row["taxonID"] == "gbif:12345"  # acceptedTaxonKey takes priority over taxonKey
    assert row["scientificName"] == "Bactrocera dorsalis"
    assert row["license"] == "http://creativecommons.org/licenses/by-nc/4.0/legalcode"
    assert row["mediaLicense"] == "http://creativecommons.org/licenses/by-nc/4.0/"
    assert row["isCaptive"] == "false"
    assert report["counts_by_provider"] == {"gbif": 1}


def test_ala_field_mapping_epoch_millisecond_event_date(tmp_path):
    ala_record = {
        "uuid": "aaaa-bbbb",
        "taxonConceptID": "https://biodiversity.org.au/afd/taxa/xyz",
        "scientificName": "Ceratitis capitata",
        "taxonRank": "species",
        "decimalLatitude": -33.8,
        "decimalLongitude": 151.2,
        "eventDate": 1_609_459_200_000,  # 2021-01-01T00:00:00Z
        "license": "CC-BY",
    }
    report, output_csv, _ = _run_convert(
        tmp_path, gbif={}, ala={"ceratitis": [ala_record]}, genera=("ceratitis",)
    )
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    row = rows[0]
    assert row["occurrenceID"] == "ala:aaaa-bbbb"
    assert row["taxonID"] == "ala:https://biodiversity.org.au/afd/taxa/xyz"
    assert row["eventDate"] == "2021-01-01"
    assert row["license"] == "CC-BY"
    assert report["counts_by_provider"] == {"ala": 1}


def test_ala_field_mapping_negative_epoch_millisecond_event_date_pre_1970(tmp_path):
    # A real example from the committed ALA data: eventDate=-378691200000.
    # datetime.fromtimestamp() raises OSError for negative values on some
    # platforms (observed on Windows); the conversion must use pure
    # timedelta arithmetic instead, which is platform independent.
    ala_record = {
        "uuid": "cccc-dddd",
        "taxonID": "some-taxon",
        "scientificName": "Rhagoletis pomonella",
        "eventDate": -378_691_200_000,
        "license": "CC-BY 4.0 (Int)",
    }
    report, output_csv, _ = _run_convert(
        tmp_path, gbif={}, ala={"rhagoletis": [ala_record]}, genera=("rhagoletis",)
    )
    rows = _read_csv_rows(output_csv)
    assert rows[0]["eventDate"] == "1958-01-01"
    assert report["reconciliation"]["reconciles"] is True


def test_ala_record_without_coordinates_is_passed_through_blank(tmp_path):
    ala_record = {
        "uuid": "no-coords",
        "taxonID": "t1",
        "scientificName": "Anastrepha fraterculus",
    }
    _report, output_csv, _ = _run_convert(
        tmp_path, gbif={}, ala={"anastrepha": [ala_record]}, genera=("anastrepha",)
    )
    rows = _read_csv_rows(output_csv)
    assert rows[0]["decimalLatitude"] == ""
    assert rows[0]["decimalLongitude"] == ""


def test_missing_scientific_name_and_taxon_id_are_not_rejected_by_this_script(tmp_path):
    # This script must not reimplement the importer's own row validation
    # (missing_scientific_name / missing_taxon_id); it leaves that decision
    # to import_occurrence_snapshot downstream.
    record = {"occurrenceID": "https://example/1"}
    report, output_csv, _ = _run_convert(tmp_path, gbif={"bactrocera": [record]}, ala={})
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    assert rows[0]["scientificName"] == ""
    assert rows[0]["taxonID"] == ""
    assert report["reconciliation"]["reconciles"] is True


def test_unrecognized_captive_cultivated_value_is_recorded_as_warning_not_error(tmp_path):
    record = {
        "occurrenceID": "https://example/2",
        "scientificName": "Bactrocera dorsalis",
        "taxonKey": 1,
        "http://unknown.org/captive_cultivated": "captive",
    }
    report, output_csv, _ = _run_convert(tmp_path, gbif={"bactrocera": [record]}, ala={})
    rows = _read_csv_rows(output_csv)
    assert rows[0]["isCaptive"] == ""
    assert len(report["field_mapping_warnings"]) == 1
    assert "captive" in report["field_mapping_warnings"][0]["message"]


# --------------------------------------------------------------------- #
# Determinism / ordering
# --------------------------------------------------------------------- #


def test_output_is_byte_identical_when_input_lines_are_reordered(tmp_path):
    records = [
        {
            "occurrenceID": f"https://example/{i}",
            "taxonKey": i,
            "scientificName": "Bactrocera dorsalis",
            "decimalLatitude": float(i),
            "decimalLongitude": float(i),
            "eventDate": "2020-01-01",
        }
        for i in range(5)
    ]

    _report_a, csv_a, _ = _run_convert(
        tmp_path / "forward", gbif={"bactrocera": records}, ala={}
    )
    _report_b, csv_b, _ = _run_convert(
        tmp_path / "reversed", gbif={"bactrocera": list(reversed(records))}, ala={}
    )

    assert csv_a.read_bytes() == csv_b.read_bytes()


def test_genus_file_order_does_not_affect_output(tmp_path):
    gbif = {
        "bactrocera": [
            {
                "occurrenceID": "https://example/b1",
                "taxonKey": 1,
                "scientificName": "Bactrocera dorsalis",
                "decimalLatitude": 1.0,
                "decimalLongitude": 1.0,
            }
        ],
        "ceratitis": [
            {
                "occurrenceID": "https://example/c1",
                "taxonKey": 2,
                "scientificName": "Ceratitis capitata",
                "decimalLatitude": 2.0,
                "decimalLongitude": 2.0,
            }
        ],
    }
    genera = ("bactrocera", "ceratitis")
    _report_a, csv_a, _ = _run_convert(tmp_path / "a", gbif=gbif, ala={}, genera=genera)
    _report_b, csv_b, _ = _run_convert(
        tmp_path / "b", gbif=gbif, ala={}, genera=tuple(reversed(genera))
    )
    assert csv_a.read_bytes() == csv_b.read_bytes()


# --------------------------------------------------------------------- #
# Deduplication
# --------------------------------------------------------------------- #


def test_exact_same_provider_duplicate_is_removed_and_reported(tmp_path):
    record = {
        "occurrenceID": "https://example/dup",
        "taxonKey": 1,
        "scientificName": "Bactrocera dorsalis",
        "decimalLatitude": 1.0,
        "decimalLongitude": 1.0,
    }
    report, output_csv, _ = _run_convert(
        tmp_path, gbif={"bactrocera": [dict(record), dict(record)]}, ala={}
    )
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    assert report["reconciliation"]["exact_duplicates_removed"] == 1
    assert report["reconciliation"]["total_input_records"] == 2
    assert report["reconciliation"]["reconciles"] is True
    assert len(report["duplicate_details"]["exact_duplicates"]) == 1


def test_probable_cross_provider_duplicate_via_shared_inaturalist_id(tmp_path):
    gbif_record = {
        "occurrenceID": "https://www.inaturalist.org/observations/9999",
        "taxonKey": 1,
        "scientificName": "Bactrocera dorsalis",
        "decimalLatitude": 1.0,
        "decimalLongitude": 1.0,
        "eventDate": "2020-01-01",
    }
    ala_record = {
        "occurrenceID": "https://www.inaturalist.org/observations/9999",
        "uuid": "ala-uuid-1",
        "taxonID": "t1",
        "scientificName": "Bactrocera dorsalis",
        "decimalLatitude": 1.0,
        "decimalLongitude": 1.0,
        "eventDate": 1_577_836_800_000,  # 2020-01-01
    }
    report, output_csv, _ = _run_convert(
        tmp_path, gbif={"bactrocera": [gbif_record]}, ala={"bactrocera": [ala_record]}
    )
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    assert rows[0]["provider"] == "gbif"  # canonical_provider_precedence = (gbif, ala)
    assert report["reconciliation"]["probable_cross_provider_duplicates_removed"] == 1
    detail = report["duplicate_details"]["probable_cross_provider_duplicates"][0]
    assert detail["reason"] == "shared_inaturalist_observation_id"


def test_probable_cross_provider_duplicate_via_coordinate_name_date_bucket(tmp_path):
    gbif_record = {
        "occurrenceID": "https://example/g1",
        "taxonKey": 1,
        "scientificName": "Ceratitis capitata",
        "decimalLatitude": -33.8123,
        "decimalLongitude": 151.2001,
        "eventDate": "2019-03-15",
    }
    ala_record = {
        "uuid": "ala-uuid-2",
        "taxonID": "t2",
        "scientificName": "Ceratitis capitata",
        "decimalLatitude": -33.8124,  # rounds to same 3-decimal bucket
        "decimalLongitude": 151.2002,
        "eventDate": 1_552_608_000_000,  # 2019-03-15
    }
    report, output_csv, _ = _run_convert(
        tmp_path,
        gbif={"ceratitis": [gbif_record]},
        ala={"ceratitis": [ala_record]},
        genera=("ceratitis",),
    )
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1
    assert report["reconciliation"]["probable_cross_provider_duplicates_removed"] == 1


def test_ambiguous_cross_provider_match_is_kept_and_reported_not_dropped(tmp_path):
    gbif_record = {
        "occurrenceID": "https://example/g2",
        "taxonKey": 1,
        "scientificName": "Ceratitis capitata",
        "decimalLatitude": 10.0011,
        "decimalLongitude": 20.0011,
        "eventDate": "2019-03-15",
    }
    ala_record = {
        "uuid": "ala-uuid-3",
        "taxonID": "t3",
        "scientificName": "Ceratitis capitata",
        "decimalLatitude": 10.0012,  # rounds to the same 3-decimal bucket
        "decimalLongitude": 20.0012,
        "eventDate": 1_552_694_400_000,  # 2019-03-16 - disagrees with GBIF date
    }
    report, output_csv, _ = _run_convert(
        tmp_path,
        gbif={"ceratitis": [gbif_record]},
        ala={"ceratitis": [ala_record]},
        genera=("ceratitis",),
    )
    rows = _read_csv_rows(output_csv)
    # Ambiguous matches are never silently dropped: both rows survive.
    assert len(rows) == 2
    assert report["reconciliation"]["probable_cross_provider_duplicates_removed"] == 0
    assert report["reconciliation"]["ambiguous_cross_provider_matches_flagged"] == 2
    ambiguous = report["duplicate_details"]["ambiguous_cross_provider_matches"]
    assert len(ambiguous) == 1
    assert ambiguous[0]["reason"] == "event_date_mismatch"


def test_count_reconciliation_holds_with_mixed_dedup_outcomes(tmp_path):
    gbif_records = [
        {
            "occurrenceID": "https://example/g-exact",
            "taxonKey": 1,
            "scientificName": "Rhagoletis pomonella",
            "decimalLatitude": 1.0,
            "decimalLongitude": 1.0,
        },
        {
            "occurrenceID": "https://example/g-exact",  # exact dup, same provider
            "taxonKey": 1,
            "scientificName": "Rhagoletis pomonella",
            "decimalLatitude": 1.0,
            "decimalLongitude": 1.0,
        },
        {
            "occurrenceID": "https://example/g-unique",
            "taxonKey": 2,
            "scientificName": "Rhagoletis pomonella",
            "decimalLatitude": 5.0,
            "decimalLongitude": 5.0,
        },
    ]
    ala_records = [
        {
            "uuid": "ala-unique",
            "taxonID": "t9",
            "scientificName": "Rhagoletis pomonella",
            "decimalLatitude": 9.0,
            "decimalLongitude": 9.0,
        }
    ]
    report, output_csv, _ = _run_convert(
        tmp_path,
        gbif={"rhagoletis": gbif_records},
        ala={"rhagoletis": ala_records},
        genera=("rhagoletis",),
    )
    reconciliation = report["reconciliation"]
    rows = _read_csv_rows(output_csv)
    assert len(rows) == 3
    assert reconciliation["total_input_records"] == 4
    assert reconciliation["emitted_records"] == 3
    assert reconciliation["exact_duplicates_removed"] == 1
    assert reconciliation["reconciles"] is True


# --------------------------------------------------------------------- #
# Provenance / integrity
# --------------------------------------------------------------------- #


def test_input_and_output_sha256_are_recorded(tmp_path):
    record = {
        "occurrenceID": "https://example/sha",
        "taxonKey": 1,
        "scientificName": "Bactrocera dorsalis",
    }
    report, output_csv, output_report = _run_convert(
        tmp_path, gbif={"bactrocera": [record]}, ala={}
    )
    assert len(report["inputs"]) == 2  # one gbif + one ala file for the single genus
    for entry in report["inputs"]:
        assert len(entry["sha256"]) == 64
    assert len(report["output"]["sha256"]) == 64
    import hashlib

    assert report["output"]["sha256"] == hashlib.sha256(output_csv.read_bytes()).hexdigest()
    assert output_report.exists()


def test_unparseable_json_line_is_counted_not_fatal(tmp_path):
    gbif_dir = tmp_path / "gbif"
    ala_dir = tmp_path / "ala"
    gbif_dir.mkdir(parents=True)
    ala_dir.mkdir(parents=True)
    (gbif_dir / "bactrocera.jsonl").write_text(
        '{"occurrenceID": "https://example/ok", "taxonKey": 1, '
        '"scientificName": "Bactrocera dorsalis"}\n'
        "not-json\n",
        encoding="utf-8",
    )
    (ala_dir / "bactrocera.jsonl").write_text("", encoding="utf-8")

    report = m2.convert(
        gbif_dir=gbif_dir,
        ala_dir=ala_dir,
        genera=("bactrocera",),
        output_csv=tmp_path / "out.csv",
        output_report=tmp_path / "report.json",
    )
    gbif_input = next(i for i in report["inputs"] if i["provider"] == "gbif")
    assert gbif_input["record_count"] == 1
    assert gbif_input["unparseable_line_count"] == 1


def test_missing_input_file_raises_fatal_error_before_writing_output(tmp_path):
    gbif_dir = tmp_path / "gbif"
    ala_dir = tmp_path / "ala"
    gbif_dir.mkdir()
    ala_dir.mkdir()
    # No genus files created at all.
    output_csv = tmp_path / "out.csv"
    output_report = tmp_path / "report.json"

    try:
        m2.convert(
            gbif_dir=gbif_dir,
            ala_dir=ala_dir,
            genera=("bactrocera",),
            output_csv=output_csv,
            output_report=output_report,
        )
        raised = False
    except m2.ConversionFatalError:
        raised = True

    assert raised
    assert not output_csv.exists()
    assert not output_report.exists()


# --------------------------------------------------------------------- #
# No network access
# --------------------------------------------------------------------- #


def test_conversion_makes_no_network_call(tmp_path, monkeypatch):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("prepare_m2_occurrence_table must not open network sockets")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)

    record = {
        "occurrenceID": "https://example/offline",
        "taxonKey": 1,
        "scientificName": "Bactrocera dorsalis",
    }
    report, _output_csv, _ = _run_convert(tmp_path, gbif={"bactrocera": [record]}, ala={})
    assert report["reconciliation"]["reconciles"] is True


def test_module_imports_no_network_or_model_libraries():
    # Defensive static check: the module source must not reference any HTTP
    # client, model runtime, or agent-framework import.
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden_tokens = [
        "import requests",
        "import httpx",
        "import urllib.request",
        "import torch",
        "pydantic_ai",
        "openai",
        "anthropic",
    ]
    for token in forbidden_tokens:
        assert token not in source, f"unexpected dependency found: {token}"


def test_cli_main_writes_csv_and_report(tmp_path, capsys):
    gbif_dir = tmp_path / "gbif"
    ala_dir = tmp_path / "ala"
    _write_jsonl(
        gbif_dir / "bactrocera.jsonl",
        [
            {
                "occurrenceID": "https://example/cli",
                "taxonKey": 1,
                "scientificName": "Bactrocera dorsalis",
            }
        ],
    )
    _write_jsonl(ala_dir / "bactrocera.jsonl", [])
    output_csv = tmp_path / "out.csv"
    output_report = tmp_path / "report.json"

    exit_code = m2.main(
        [
            "--gbif-dir",
            str(gbif_dir),
            "--ala-dir",
            str(ala_dir),
            "--genera",
            "bactrocera",
            "--output-csv",
            str(output_csv),
            "--output-report",
            str(output_report),
        ]
    )

    assert exit_code == 0
    assert output_csv.exists()
    assert output_report.exists()
    printed = json.loads(capsys.readouterr().out)
    assert printed["reconciles"] is True


def test_cli_main_returns_one_on_missing_input(tmp_path, capsys):
    exit_code = m2.main(
        [
            "--gbif-dir",
            str(tmp_path / "does-not-exist-gbif"),
            "--ala-dir",
            str(tmp_path / "does-not-exist-ala"),
            "--genera",
            "bactrocera",
            "--output-csv",
            str(tmp_path / "out.csv"),
            "--output-report",
            str(tmp_path / "report.json"),
        ]
    )
    assert exit_code == 1
    assert "prepare_m2_occurrence_table" in capsys.readouterr().err
