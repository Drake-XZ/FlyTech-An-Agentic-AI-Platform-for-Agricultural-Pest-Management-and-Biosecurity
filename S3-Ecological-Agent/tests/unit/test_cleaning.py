"""Unit tests for occurrence cleaning (EarlyDesign.md sections 11.1-11.3)."""

from __future__ import annotations

from typing import Any

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.occurrence.cleaning import (
    FLAG_CAPTIVE_OR_CULTIVATED,
    FLAG_COORDINATE_UNCERTAINTY_EXCEEDS_THRESHOLD,
    FLAG_DUPLICATE_SOURCE_RECORD,
    FLAG_INVALID_COORDINATES,
    FLAG_INVALID_EVENT_DATE,
    FLAG_KNOWN_CENTROID,
    FLAG_UNKNOWN_COORDINATE_UNCERTAINTY,
    FLAG_ZERO_COORDINATES,
    clean_occurrences,
)
from s3_ecological.settings import S3Settings


def _record(**overrides: Any) -> RawOccurrenceRecord:
    defaults: dict[str, Any] = dict(
        source="test",
        source_record_id="rec-1",
        scientific_name_raw="Bactrocera",
        taxon_id="fixture:bactrocera",
        latitude=0.0,
        longitude=0.0,
        coordinate_uncertainty_m=100.0,
        event_date="2026-01-01",
        is_captive_or_cultivated=False,
    )
    defaults.update(overrides)
    return RawOccurrenceRecord(**defaults)


def test_valid_record_is_usable_with_no_flags():
    report = clean_occurrences([_record(latitude=10.0, longitude=20.0)], S3Settings())
    assert report.cleaned[0].usable_for_distance is True
    assert report.cleaned[0].quality_flags == []


def test_invalid_coordinates_are_excluded_but_retained():
    report = clean_occurrences([_record(latitude=200.0, longitude=20.0)], S3Settings())
    cleaned = report.cleaned[0]
    assert cleaned.usable_for_distance is False
    assert FLAG_INVALID_COORDINATES in cleaned.quality_flags
    assert len(report.cleaned) == 1


def test_missing_latitude_is_treated_as_invalid_coordinates():
    report = clean_occurrences([_record(latitude=None, longitude=None)], S3Settings())
    assert report.cleaned[0].usable_for_distance is False
    assert FLAG_INVALID_COORDINATES in report.cleaned[0].quality_flags


def test_zero_coordinates_are_flagged_but_still_usable():
    report = clean_occurrences([_record(latitude=0.0, longitude=0.0)], S3Settings())
    cleaned = report.cleaned[0]
    assert FLAG_ZERO_COORDINATES in cleaned.quality_flags
    assert cleaned.usable_for_distance is True


def test_missing_coordinate_uncertainty_excludes_record():
    report = clean_occurrences(
        [_record(latitude=10.0, longitude=20.0, coordinate_uncertainty_m=None)], S3Settings()
    )
    cleaned = report.cleaned[0]
    assert cleaned.usable_for_distance is False
    assert FLAG_UNKNOWN_COORDINATE_UNCERTAINTY in cleaned.quality_flags


def test_excessive_coordinate_uncertainty_excludes_record():
    settings = S3Settings(max_coordinate_uncertainty_m=1000.0)
    report = clean_occurrences(
        [_record(latitude=10.0, longitude=20.0, coordinate_uncertainty_m=5000.0)], settings
    )
    cleaned = report.cleaned[0]
    assert cleaned.usable_for_distance is False
    assert FLAG_COORDINATE_UNCERTAINTY_EXCEEDS_THRESHOLD in cleaned.quality_flags


def test_known_centroid_match_excludes_record():
    settings = S3Settings(known_centroid_coordinates=[(10.0, 20.0)])
    report = clean_occurrences([_record(latitude=10.0, longitude=20.0)], settings)
    cleaned = report.cleaned[0]
    assert cleaned.usable_for_distance is False
    assert FLAG_KNOWN_CENTROID in cleaned.quality_flags


def test_captive_or_cultivated_excludes_record():
    report = clean_occurrences(
        [_record(latitude=10.0, longitude=20.0, is_captive_or_cultivated=True)], S3Settings()
    )
    cleaned = report.cleaned[0]
    assert cleaned.usable_for_distance is False
    assert FLAG_CAPTIVE_OR_CULTIVATED in cleaned.quality_flags


def test_duplicate_source_record_id_excludes_second_occurrence():
    records = [
        _record(latitude=10.0, longitude=20.0, source_record_id="dup-1"),
        _record(latitude=11.0, longitude=21.0, source_record_id="dup-1"),
    ]
    report = clean_occurrences(records, S3Settings())
    assert report.cleaned[0].usable_for_distance is True
    assert report.cleaned[1].usable_for_distance is False
    assert FLAG_DUPLICATE_SOURCE_RECORD in report.cleaned[1].quality_flags


def test_implausible_event_date_is_flagged_but_not_excluded():
    report = clean_occurrences(
        [_record(latitude=10.0, longitude=20.0, event_date="not-a-date")], S3Settings()
    )
    cleaned = report.cleaned[0]
    assert FLAG_INVALID_EVENT_DATE in cleaned.quality_flags
    assert cleaned.usable_for_distance is True


def test_year_only_and_year_month_event_dates_are_plausible():
    report = clean_occurrences(
        [
            _record(latitude=10.0, longitude=20.0, event_date="2026", source_record_id="a"),
            _record(latitude=10.0, longitude=20.0, event_date="2026-06", source_record_id="b"),
        ],
        S3Settings(),
    )
    assert all(FLAG_INVALID_EVENT_DATE not in item.quality_flags for item in report.cleaned)


def test_missing_event_date_is_plausible():
    report = clean_occurrences(
        [_record(latitude=10.0, longitude=20.0, event_date=None)], S3Settings()
    )
    assert FLAG_INVALID_EVENT_DATE not in report.cleaned[0].quality_flags


def test_cleaning_report_usable_property_filters_excluded_records():
    records = [
        _record(latitude=10.0, longitude=20.0, source_record_id="ok"),
        _record(latitude=200.0, longitude=20.0, source_record_id="bad"),
    ]
    report = clean_occurrences(records, S3Settings())
    assert len(report.cleaned) == 2
    assert len(report.usable) == 1
    assert report.usable[0].record.source_record_id == "ok"


def test_excluded_records_are_never_dropped_from_the_report():
    records = [
        _record(latitude=None, longitude=None, source_record_id=f"rec-{i}") for i in range(3)
    ]
    report = clean_occurrences(records, S3Settings())
    assert len(report.cleaned) == 3
    assert report.usable == []
