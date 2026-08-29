"""Pure record-counting helpers for the offline pre-Milestone 2 readiness
builder (DesignSuggestionLog.md, "2026-08-29 20:18 Australia/Sydney -
Suggested hardening increment: readiness integrity and contract
corrections", "Separate quality flags from cleaning actions" and "Temporal
coverage counts").

``quality_flags`` (every observation about a record, including usable ones)
and ``cleaning_actions`` (only the subset that actually excluded a record)
are two distinct vocabularies on :class:`CleanedOccurrence`
(``occurrence/cleaning.py``, unchanged). This module counts each separately
instead of conflating them.

``counts_by_event_year``/``undated_usable_record_count`` are purely
descriptive breakdowns of when usable records were observed - they carry no
seasonality, environmental-suitability, or biological-evidence meaning.
"""

from __future__ import annotations

from collections.abc import Sequence

from s3_ecological.occurrence.cleaning import FLAG_INVALID_EVENT_DATE, CleanedOccurrence

_EVENT_YEAR_LENGTH = 4


def counts_by_quality_flag(cleaned: Sequence[CleanedOccurrence]) -> dict[str, int]:
    """Every ``quality_flags`` value across all in-scope records (usable and
    excluded). A value repeated within one record's own ``quality_flags``
    counts once for that record."""
    counts: dict[str, int] = {}
    for item in cleaned:
        for flag in dict.fromkeys(item.quality_flags):
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))


def counts_by_cleaning_action(excluded: Sequence[CleanedOccurrence]) -> dict[str, int]:
    """Real cleaning/exclusion actions only, over excluded records - this is
    what ``counts_by_exclusion_flag`` should have measured all along (it was
    populated from ``cleaning_actions`` despite its name promising
    ``quality_flags``). A value repeated within one record's own
    ``cleaning_actions`` counts once for that record."""
    counts: dict[str, int] = {}
    for item in excluded:
        for action in dict.fromkeys(item.cleaning_actions):
            counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _valid_event_year(item: CleanedOccurrence) -> str | None:
    """The record's 4-digit event year, if its event date is present, not
    flagged ``FLAG_INVALID_EVENT_DATE``, and its leading ``-``-delimited
    token is exactly 4 digits. ``None`` otherwise."""
    event_date = item.record.event_date
    if event_date is None or FLAG_INVALID_EVENT_DATE in item.quality_flags:
        return None
    year_token = event_date.split("-", 1)[0]
    if len(year_token) == _EVENT_YEAR_LENGTH and year_token.isdigit():
        return year_token
    return None


def counts_by_event_year(usable: Sequence[CleanedOccurrence]) -> dict[str, int]:
    """Usable records only, keyed by valid 4-digit event year, ascending."""
    counts: dict[str, int] = {}
    for item in usable:
        year = _valid_event_year(item)
        if year is not None:
            counts[year] = counts.get(year, 0) + 1
    return dict(sorted(counts.items()))


def undated_usable_record_count(usable: Sequence[CleanedOccurrence]) -> int:
    """Usable records with no valid event year (missing or invalid date)."""
    return sum(1 for item in usable if _valid_event_year(item) is None)
