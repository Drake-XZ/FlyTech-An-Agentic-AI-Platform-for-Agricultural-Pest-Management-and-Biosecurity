"""Local-snapshot occurrence provider.

Loads a JSON snapshot file shaped as
``{"dataset_id": "...", "records": [RawOccurrenceRecord, ...]}`` and serves
it through the same :class:`OccurrenceProvider` interface as the in-memory
and future live adapters (EarlyDesign.md section 6.4). This is the
"local-file provider" required for offline development and demonstration.
"""

from __future__ import annotations

import json
from pathlib import Path

from s3_ecological.interfaces.occurrence import (
    OccurrenceProvider,
    OccurrenceQuery,
    RawOccurrenceRecord,
)
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider
from s3_ecological.schemas.common import ToolResult


class LocalSnapshotOccurrenceProvider(OccurrenceProvider):
    """Occurrence provider backed by a JSON snapshot file on disk."""

    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        records = [RawOccurrenceRecord.model_validate(item) for item in payload["records"]]
        self.dataset_id: str = payload.get("dataset_id", self.snapshot_path.stem)
        # Delegate the actual filtering to the in-memory provider: the two
        # adapters share identical query semantics, so re-implementing the
        # filter here would be duplicated logic for no behavioral benefit.
        self._delegate = InMemoryOccurrenceProvider(records, dataset_id=self.dataset_id)

    def query(self, query: OccurrenceQuery) -> ToolResult[list[RawOccurrenceRecord]]:
        return self._delegate.query(query)
