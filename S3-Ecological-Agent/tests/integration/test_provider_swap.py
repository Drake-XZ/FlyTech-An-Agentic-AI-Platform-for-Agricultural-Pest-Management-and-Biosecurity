"""Integration tests: swapping occurrence/taxonomy providers via the factory.

Cleaning, priors, fusion, and risk logic must behave identically regardless
of which concrete :class:`OccurrenceProvider` backs them (EarlyDesign.md
section 6.4).
"""

from __future__ import annotations

import json

import pytest

from s3_ecological.interfaces.occurrence import OccurrenceQuery, RawOccurrenceRecord
from s3_ecological.providers.factory import build_occurrence_provider, build_taxonomy_provider
from s3_ecological.providers.occurrence_local_snapshot import LocalSnapshotOccurrenceProvider
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.schemas.enums import ToolStatus
from s3_ecological.settings import S3Settings


def _record(taxon_id: str = "fixture:bactrocera") -> RawOccurrenceRecord:
    return RawOccurrenceRecord(
        source="test",
        source_record_id="rec-1",
        scientific_name_raw="Bactrocera",
        taxon_id=taxon_id,
        latitude=10.0,
        longitude=20.0,
        coordinate_uncertainty_m=100.0,
    )


def test_factory_builds_fixture_taxonomy_provider_by_default():
    provider = build_taxonomy_provider(S3Settings())
    assert isinstance(provider, FixtureTaxonomyProvider)


def test_factory_rejects_unknown_taxonomy_provider_name():
    with pytest.raises(ValueError, match="Unknown taxonomy_provider"):
        build_taxonomy_provider(S3Settings(taxonomy_provider="not_real"))


def test_factory_builds_fixture_occurrence_provider_by_default():
    provider = build_occurrence_provider(S3Settings())
    result = provider.query(OccurrenceQuery(taxon_id="fixture:bactrocera"))
    assert result.status in (ToolStatus.SUCCESS, ToolStatus.NO_RECORDS)


def test_factory_builds_in_memory_occurrence_provider_with_no_records():
    provider = build_occurrence_provider(S3Settings(occurrence_provider="in_memory"))
    result = provider.query(OccurrenceQuery(taxon_id="fixture:bactrocera"))
    assert result.status == ToolStatus.NO_RECORDS


def test_factory_builds_local_snapshot_provider_from_file(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"dataset_id": "test-snapshot", "records": [_record().model_dump(mode="json")]}),
        encoding="utf-8",
    )
    provider = build_occurrence_provider(
        S3Settings(
            occurrence_provider="local_snapshot", occurrence_snapshot_path=str(snapshot_path)
        )
    )
    result = provider.query(OccurrenceQuery(taxon_id="fixture:bactrocera"))
    assert result.status == ToolStatus.SUCCESS
    assert result.data is not None
    assert len(result.data) == 1


def test_factory_local_snapshot_without_path_raises_clear_error():
    with pytest.raises(ValueError, match="occurrence_snapshot_path"):
        build_occurrence_provider(S3Settings(occurrence_provider="local_snapshot"))


def test_factory_builds_live_gbif_provider_that_never_crashes_and_returns_provider_not_configured():
    provider = build_occurrence_provider(S3Settings(occurrence_provider="live_gbif"))
    result = provider.query(OccurrenceQuery(taxon_id="fixture:bactrocera"))
    assert result.status == ToolStatus.PROVIDER_NOT_CONFIGURED


def test_factory_builds_live_ala_provider_that_never_crashes_and_returns_provider_not_configured():
    provider = build_occurrence_provider(S3Settings(occurrence_provider="live_ala"))
    result = provider.query(OccurrenceQuery(taxon_id="fixture:bactrocera"))
    assert result.status == ToolStatus.PROVIDER_NOT_CONFIGURED


def test_in_memory_and_local_snapshot_providers_agree_on_the_same_records(tmp_path):
    record = _record()
    in_memory = InMemoryOccurrenceProvider([record])

    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"dataset_id": "test-snapshot", "records": [record.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    local_snapshot = LocalSnapshotOccurrenceProvider(snapshot_path)

    query = OccurrenceQuery(taxon_id="fixture:bactrocera")
    assert in_memory.query(query).data == local_snapshot.query(query).data
