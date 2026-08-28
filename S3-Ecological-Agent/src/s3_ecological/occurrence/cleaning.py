"""Occurrence cleaning (EarlyDesign.md sections 11.1-11.3, Profile v0.1 step 1).

Cleaning never deletes a record: every input record is retained as
traceable evidence with quality flags and cleaning actions, and only a
subset is marked ``usable_for_distance`` for the v0.1 geographic baseline.
Records excluded from the distance calculation still appear in
``EvidenceRecord`` output (evidence/records.py) so a reviewer can see why a
record was not used.

Taxonomy resolution is not re-checked here: a record only reaches this
module because an :class:`OccurrenceProvider` already queried it by a
resolved ``taxon_id`` (EarlyDesign.md section 11.2 step 1, "taxonomy is
resolved").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.settings import S3Settings

# Quality flags (EarlyDesign.md section 10, "quality_flags" column).
FLAG_INVALID_COORDINATES = "invalid_coordinates"
FLAG_ZERO_COORDINATES = "zero_coordinates"
FLAG_UNKNOWN_COORDINATE_UNCERTAINTY = "unknown_coordinate_uncertainty"
FLAG_COORDINATE_UNCERTAINTY_EXCEEDS_THRESHOLD = "coordinate_uncertainty_exceeds_threshold"
FLAG_KNOWN_CENTROID = "known_centroid_coordinates"
FLAG_CAPTIVE_OR_CULTIVATED = "captive_or_cultivated"
FLAG_DUPLICATE_SOURCE_RECORD = "duplicate_source_record"
FLAG_INVALID_EVENT_DATE = "invalid_event_date"

# Cleaning actions (EarlyDesign.md section 10, "cleaning_actions" column).
ACTION_EXCLUDED_INVALID_COORDINATES = "excluded_invalid_coordinates"
ACTION_EXCLUDED_UNKNOWN_UNCERTAINTY = "excluded_unknown_coordinate_uncertainty"
ACTION_EXCLUDED_UNCERTAINTY_THRESHOLD = "excluded_coordinate_uncertainty_exceeds_threshold"
ACTION_EXCLUDED_CENTROID = "excluded_known_centroid"
ACTION_EXCLUDED_CAPTIVE = "excluded_captive_or_cultivated"
ACTION_EXCLUDED_DUPLICATE = "excluded_duplicate_source_record"

# Coordinate match tolerance for the configured-centroid check, in decimal
# degrees (~11 m at the equator) - tight enough to only match a deliberately
# configured centroid, not nearby genuine occurrences.
_CENTROID_MATCH_TOLERANCE_DEG = 0.0001


@dataclass(frozen=True)
class CleanedOccurrence:
    """One occurrence record after cleaning, with its full evidence trail."""

    record: RawOccurrenceRecord
    usable_for_distance: bool
    quality_flags: list[str] = field(default_factory=list)
    cleaning_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CleaningReport:
    """All cleaned records for one taxon query, in input order."""

    cleaned: list[CleanedOccurrence]

    @property
    def usable(self) -> list[CleanedOccurrence]:
        """Records usable for the v0.1 nearest-distance baseline."""
        return [item for item in self.cleaned if item.usable_for_distance]


def clean_occurrences(
    records: Sequence[RawOccurrenceRecord], settings: S3Settings
) -> CleaningReport:
    """Apply the Profile v0.1 minimum cleaning checks to raw occurrence records.

    Exclusion from ``usable_for_distance`` is limited to the criteria listed
    in EarlyDesign.md section 12.1 step 1 (invalid/missing coordinates,
    unknown or excessive coordinate uncertainty, a configured centroid,
    captive/cultivated status, or an exact duplicate). Zero coordinates and
    implausible event dates are flagged for reviewer visibility only, since
    the spec instructs flagging them (section 11.3) but does not list them
    among the usability exclusions, and a golden acceptance fixture
    deliberately uses ``(0, 0)`` as a synthetic observation location.
    """
    seen_duplicate_keys: set[tuple[object, ...]] = set()
    cleaned: list[CleanedOccurrence] = []

    for record in records:
        quality_flags: list[str] = []
        cleaning_actions: list[str] = []
        usable = True

        duplicate_key = _duplicate_key(record)
        if duplicate_key in seen_duplicate_keys:
            quality_flags.append(FLAG_DUPLICATE_SOURCE_RECORD)
            cleaning_actions.append(ACTION_EXCLUDED_DUPLICATE)
            usable = False
        else:
            seen_duplicate_keys.add(duplicate_key)

        if usable and not _has_valid_coordinates(record):
            quality_flags.append(FLAG_INVALID_COORDINATES)
            cleaning_actions.append(ACTION_EXCLUDED_INVALID_COORDINATES)
            usable = False

        if usable and record.latitude == 0.0 and record.longitude == 0.0:
            quality_flags.append(FLAG_ZERO_COORDINATES)

        coordinate_uncertainty_m = record.coordinate_uncertainty_m
        if usable and coordinate_uncertainty_m is None:
            quality_flags.append(FLAG_UNKNOWN_COORDINATE_UNCERTAINTY)
            cleaning_actions.append(ACTION_EXCLUDED_UNKNOWN_UNCERTAINTY)
            usable = False
        elif (
            usable
            and coordinate_uncertainty_m is not None
            and coordinate_uncertainty_m > settings.max_coordinate_uncertainty_m
        ):
            quality_flags.append(FLAG_COORDINATE_UNCERTAINTY_EXCEEDS_THRESHOLD)
            cleaning_actions.append(ACTION_EXCLUDED_UNCERTAINTY_THRESHOLD)
            usable = False

        if usable and _matches_known_centroid(record, settings.known_centroid_coordinates):
            quality_flags.append(FLAG_KNOWN_CENTROID)
            cleaning_actions.append(ACTION_EXCLUDED_CENTROID)
            usable = False

        if usable and record.is_captive_or_cultivated:
            quality_flags.append(FLAG_CAPTIVE_OR_CULTIVATED)
            cleaning_actions.append(ACTION_EXCLUDED_CAPTIVE)
            usable = False

        if not _has_plausible_event_date(record.event_date):
            quality_flags.append(FLAG_INVALID_EVENT_DATE)

        cleaned.append(
            CleanedOccurrence(
                record=record,
                usable_for_distance=usable,
                quality_flags=quality_flags,
                cleaning_actions=cleaning_actions,
            )
        )

    return CleaningReport(cleaned=cleaned)


def _duplicate_key(record: RawOccurrenceRecord) -> tuple[object, ...]:
    """Identify exact-duplicate source records (EarlyDesign.md section 11.3)."""
    if record.source_record_id is not None:
        return ("id", record.source, record.source_record_id)
    return (
        "coords",
        record.source,
        record.taxon_id,
        record.latitude,
        record.longitude,
        record.event_date,
    )


def _has_valid_coordinates(record: RawOccurrenceRecord) -> bool:
    if record.latitude is None or record.longitude is None:
        return False
    return -90.0 <= record.latitude <= 90.0 and -180.0 <= record.longitude <= 180.0


def _matches_known_centroid(
    record: RawOccurrenceRecord, known_centroids: Sequence[tuple[float, float]]
) -> bool:
    if record.latitude is None or record.longitude is None:
        return False
    return any(
        abs(record.latitude - centroid_lat) < _CENTROID_MATCH_TOLERANCE_DEG
        and abs(record.longitude - centroid_lon) < _CENTROID_MATCH_TOLERANCE_DEG
        for centroid_lat, centroid_lon in known_centroids
    )


def _has_plausible_event_date(event_date: str | None) -> bool:
    """Accept ``YYYY``, ``YYYY-MM``, or ``YYYY-MM-DD`` without inventing fields.

    EarlyDesign.md section 11.3 requires normalizing time "without inventing
    missing day/month values", so a year-only or year-month date is valid,
    not merely tolerated.
    """
    if event_date is None:
        return True
    parts = event_date.split("-")
    try:
        if len(parts) == 1:
            date(int(parts[0]), 1, 1)
        elif len(parts) == 2:
            date(int(parts[0]), int(parts[1]), 1)
        elif len(parts) == 3:
            date(int(parts[0]), int(parts[1]), int(parts[2]))
        else:
            return False
    except ValueError:
        return False
    return True
