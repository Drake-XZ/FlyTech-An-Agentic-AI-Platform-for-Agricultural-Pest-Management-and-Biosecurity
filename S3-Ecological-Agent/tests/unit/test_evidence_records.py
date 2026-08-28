"""Unit tests for evidence-record construction and provenance (EarlyDesign.md section 10)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from s3_ecological.evidence.records import build_evidence_records, evidence_id_for_occurrence
from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.occurrence.cleaning import clean_occurrences
from s3_ecological.settings import S3Settings

RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _record(**overrides: Any) -> RawOccurrenceRecord:
    defaults: dict[str, Any] = dict(
        source="test",
        source_record_id="rec-1",
        scientific_name_raw="Bactrocera",
        taxon_id="fixture:bactrocera",
        latitude=10.0,
        longitude=20.0,
        coordinate_uncertainty_m=100.0,
        event_date="2026-01-01",
    )
    defaults.update(overrides)
    return RawOccurrenceRecord(**defaults)


def test_evidence_id_is_stable_for_the_same_record():
    record = _record()
    assert evidence_id_for_occurrence(record) == evidence_id_for_occurrence(record)


def test_evidence_id_uses_source_record_id_when_present():
    record = _record(source="gbif", source_record_id="123")
    assert evidence_id_for_occurrence(record) == "occurrence:gbif:123"


def test_evidence_id_falls_back_to_content_key_without_source_record_id():
    record = _record(source_record_id=None, dataset_id="dataset-a")
    evidence_id = evidence_id_for_occurrence(record)
    assert evidence_id.startswith("occurrence:test:dataset-a:")
    assert "10.0:20.0:2026-01-01" in evidence_id


def test_evidence_id_is_independent_of_position_in_a_filtered_subset():
    full = [
        _record(source_record_id="a"),
        _record(source_record_id="b"),
        _record(source_record_id="c"),
    ]
    filtered = [full[2], full[0]]
    assert evidence_id_for_occurrence(filtered[1]) == evidence_id_for_occurrence(full[0])


def test_build_evidence_records_includes_excluded_records():
    records = [
        _record(source_record_id="ok"),
        _record(source_record_id="bad", latitude=None, longitude=None),
    ]
    report = clean_occurrences(records, S3Settings())
    evidence = build_evidence_records(report.cleaned, RETRIEVED_AT)
    assert len(evidence) == 2
    evidence_ids = {item.evidence_id for item in evidence}
    assert "occurrence:test:ok" in evidence_ids
    assert "occurrence:test:bad" in evidence_ids


def test_build_evidence_records_preserves_quality_flags():
    records = [_record(source_record_id="bad", latitude=None, longitude=None)]
    report = clean_occurrences(records, S3Settings())
    evidence = build_evidence_records(report.cleaned, RETRIEVED_AT)
    assert evidence[0].quality_flags
    assert evidence[0].retrieved_at == RETRIEVED_AT


def test_build_evidence_records_on_empty_input_returns_empty_list():
    report = clean_occurrences([], S3Settings())
    assert build_evidence_records(report.cleaned, RETRIEVED_AT) == []
