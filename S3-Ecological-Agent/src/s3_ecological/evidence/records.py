"""Evidence record construction and provenance (EarlyDesign.md section 10)."""

from __future__ import annotations

from datetime import datetime

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.occurrence.cleaning import CleanedOccurrence
from s3_ecological.schemas.response import EvidenceRecord


def evidence_id_for_occurrence(record: RawOccurrenceRecord) -> str:
    """Stable, content-addressed evidence id for one occurrence record.

    Prefers the source's own record id when present. Falls back to a key
    built from the record's own content (not its position in a list), so
    the same record always gets the same id whether it appears in a
    provider's full result set or in a filtered subset such as
    ``CleaningReport.usable`` (EarlyDesign.md section 10,
    ``supporting_evidence_ids`` must resolve to a real evidence entry).
    """
    if record.source_record_id is not None:
        return f"occurrence:{record.source}:{record.source_record_id}"
    dataset = record.dataset_id or record.snapshot_or_cache_key or "unknown-dataset"
    content_key = f"{record.latitude}:{record.longitude}:{record.event_date}"
    return f"occurrence:{record.source}:{dataset}:{content_key}"


def build_evidence_records(
    cleaned: list[CleanedOccurrence], retrieved_at: datetime
) -> list[EvidenceRecord]:
    """Build one traceable :class:`EvidenceRecord` per input occurrence record.

    Every record is included, not only the usable ones - an excluded record
    is still evidence that a reviewer can inspect (EarlyDesign.md section
    11.2 step 1, "retain excluded ... records as traceable evidence").
    """
    return [
        EvidenceRecord(
            evidence_id=evidence_id_for_occurrence(item.record),
            source=item.record.source,
            source_record_id=item.record.source_record_id,
            dataset_id=item.record.dataset_id,
            source_url=item.record.source_url,
            retrieved_at=retrieved_at,
            scientific_name_raw=item.record.scientific_name_raw,
            taxon_id=item.record.taxon_id,
            latitude=item.record.latitude,
            longitude=item.record.longitude,
            coordinate_uncertainty_m=item.record.coordinate_uncertainty_m,
            event_date=item.record.event_date,
            basis_of_record=item.record.basis_of_record,
            license=item.record.license,
            media_license=item.record.media_license,
            quality_flags=item.quality_flags,
            cleaning_actions=item.cleaning_actions,
            query_parameters=item.record.query_parameters,
            snapshot_or_cache_key=item.record.snapshot_or_cache_key,
        )
        for item in cleaned
    ]
