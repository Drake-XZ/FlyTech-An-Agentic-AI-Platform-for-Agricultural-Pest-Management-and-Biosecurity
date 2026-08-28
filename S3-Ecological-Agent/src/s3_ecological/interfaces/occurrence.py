"""Occurrence provider interface (EarlyDesign.md sections 7.3, 11.2).

The same interface must serve the in-memory fixture provider, the
local-snapshot provider, and a future live GBIF/ALA adapter without any
change to cleaning, priors, fusion, or risk logic (EarlyDesign.md section
6.4).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.common import ToolResult


class OccurrenceQuery(BaseModel):
    """Input to ``query_occurrences`` (EarlyDesign.md section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    taxon_id: str = Field(min_length=1)
    region: dict[str, float] | None = None
    time_range: tuple[date, date] | None = None
    quality_filters: dict[str, Any] | None = None


class RawOccurrenceRecord(BaseModel):
    """An occurrence record as returned by a provider, before cleaning.

    Fields mirror the evidence provenance requirements of section 10 so a
    provider never has to invent data during cleaning - anything the
    cleaned record needs must already exist here.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_record_id: str | None = None
    dataset_id: str | None = None
    source_url: str | None = None
    scientific_name_raw: str
    taxon_id: str
    latitude: float | None = None
    longitude: float | None = None
    coordinate_uncertainty_m: float | None = None
    event_date: str | None = None
    basis_of_record: str | None = None
    license: str | None = None
    media_license: str | None = None
    is_captive_or_cultivated: bool | None = None
    query_parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot_or_cache_key: str | None = None


@runtime_checkable
class OccurrenceProvider(Protocol):
    """Interface every occurrence source (fixture, snapshot, or live) must implement."""

    def query(self, query: OccurrenceQuery) -> ToolResult[list[RawOccurrenceRecord]]:
        """Return raw (uncleaned) occurrence records for one taxon."""
        ...
