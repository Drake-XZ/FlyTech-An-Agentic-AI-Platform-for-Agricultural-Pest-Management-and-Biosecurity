"""In-memory occurrence provider.

Holds a fixed list of :class:`RawOccurrenceRecord` supplied at construction
time and filters by ``taxon_id``. Used directly by unit tests and as the
building block for :class:`~s3_ecological.providers.occurrence_local_snapshot.
LocalSnapshotOccurrenceProvider`, which just loads the same record shape from
a JSON file.
"""

from __future__ import annotations

from s3_ecological.interfaces.occurrence import (
    OccurrenceProvider,
    OccurrenceQuery,
    RawOccurrenceRecord,
)
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus


class InMemoryOccurrenceProvider(OccurrenceProvider):
    """Occurrence provider backed by an in-process list of raw records."""

    def __init__(self, records: list[RawOccurrenceRecord], dataset_id: str = "in-memory-v0.1"):
        self._records = list(records)
        self.dataset_id = dataset_id

    def query(self, query: OccurrenceQuery) -> ToolResult[list[RawOccurrenceRecord]]:
        matches = [record for record in self._records if record.taxon_id == query.taxon_id]
        if not matches:
            return ToolResult(
                status=ToolStatus.NO_RECORDS,
                data=[],
                warnings=[
                    Issue(
                        code=IssueCode.NO_RECORDS,
                        message=f"No occurrence records for taxon '{query.taxon_id}'",
                        component="occurrence",
                        retryable=False,
                    )
                ],
            )
        return ToolResult(status=ToolStatus.SUCCESS, data=matches)
