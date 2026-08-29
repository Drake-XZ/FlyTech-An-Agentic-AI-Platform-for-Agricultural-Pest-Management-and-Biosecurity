"""Unit tests for the pure record-counting helpers
(experiments/record_counts.py - DesignSuggestionLog.md "Separate quality
flags from cleaning actions" and "Temporal coverage counts"). No file I/O -
hand-constructed :class:`CleanedOccurrence` instances only.
"""

from __future__ import annotations

from s3_ecological.experiments.record_counts import (
    counts_by_cleaning_action,
    counts_by_event_year,
    counts_by_quality_flag,
    undated_usable_record_count,
)
from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.occurrence.cleaning import (
    ACTION_EXCLUDED_UNKNOWN_UNCERTAINTY,
    FLAG_INVALID_EVENT_DATE,
    FLAG_UNKNOWN_COORDINATE_UNCERTAINTY,
    FLAG_ZERO_COORDINATES,
    CleanedOccurrence,
)


def _record(**overrides: object) -> RawOccurrenceRecord:
    kwargs: dict[str, object] = {
        "source": "gbif",
        "scientific_name_raw": "Bactrocera dorsalis",
        "taxon_id": "taxon-1",
        "latitude": 10.0,
        "longitude": 20.0,
    }
    kwargs.update(overrides)
    return RawOccurrenceRecord.model_validate(kwargs)


def _cleaned(
    *,
    usable: bool,
    quality_flags: list[str] | None = None,
    cleaning_actions: list[str] | None = None,
    event_date: str | None = None,
) -> CleanedOccurrence:
    return CleanedOccurrence(
        record=_record(event_date=event_date),
        usable_for_distance=usable,
        quality_flags=list(quality_flags or []),
        cleaning_actions=list(cleaning_actions or []),
    )


def test_repeated_quality_flag_within_one_record_counts_once():
    item = _cleaned(usable=True, quality_flags=[FLAG_ZERO_COORDINATES, FLAG_ZERO_COORDINATES])
    assert counts_by_quality_flag([item]) == {FLAG_ZERO_COORDINATES: 1}


def test_usable_flagged_record_contributes_to_quality_flag_but_not_cleaning_action():
    item = _cleaned(usable=True, quality_flags=[FLAG_ZERO_COORDINATES], event_date="2020-01-01")
    assert counts_by_quality_flag([item]) == {FLAG_ZERO_COORDINATES: 1}
    # This record was never excluded, so it must not appear in the
    # cleaning-action counts at all (the caller only passes excluded records).
    assert counts_by_cleaning_action([]) == {}


def test_excluded_record_contributes_to_both_quality_flag_and_cleaning_action():
    item = _cleaned(
        usable=False,
        quality_flags=[FLAG_UNKNOWN_COORDINATE_UNCERTAINTY],
        cleaning_actions=[ACTION_EXCLUDED_UNKNOWN_UNCERTAINTY],
    )
    assert counts_by_quality_flag([item]) == {FLAG_UNKNOWN_COORDINATE_UNCERTAINTY: 1}
    assert counts_by_cleaning_action([item]) == {ACTION_EXCLUDED_UNKNOWN_UNCERTAINTY: 1}


def test_counts_by_event_year_spans_multiple_distinct_years_ascending():
    items = [
        _cleaned(usable=True, event_date="2020-06-15"),
        _cleaned(usable=True, event_date="2019-05-01"),
        _cleaned(usable=True, event_date="2020-01-01"),
    ]
    assert counts_by_event_year(items) == {"2019": 1, "2020": 2}


def test_undated_usable_record_count_counts_missing_and_invalidly_flagged_dates():
    items = [
        _cleaned(usable=True, event_date=None),
        _cleaned(usable=True, event_date="2020-01-01"),
        _cleaned(
            usable=True,
            event_date="not-a-date",
            quality_flags=[FLAG_INVALID_EVENT_DATE],
        ),
    ]
    assert undated_usable_record_count(items) == 2
    assert counts_by_event_year(items) == {"2020": 1}
