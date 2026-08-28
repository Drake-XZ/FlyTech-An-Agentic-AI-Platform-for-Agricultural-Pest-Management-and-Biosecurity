"""Small synthetic occurrence dataset used as the zero-configuration default.

This is deliberately not the golden-acceptance snapshots under
``fixtures/golden/`` - those are crafted per-case to hit exact documented
values (EarlyDesign.md section 20.3). This dataset exists so
``S3Settings(occurrence_provider="fixture")`` (the library default) has
*something* to score against without any file path configuration, e.g. for
ad-hoc exploration with ``s3-ecological assess``.

Coordinates are synthetic and do not represent real specimen localities.
"""

from __future__ import annotations

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider

DATASET_ID = "fixture-occurrences-v0.1"

_RECORDS: list[RawOccurrenceRecord] = [
    RawOccurrenceRecord(
        source="fixture",
        source_record_id=f"fixture-occurrence-{index}",
        dataset_id=DATASET_ID,
        source_url=f"fixture://occurrences/fixture-occurrence-{index}",
        scientific_name_raw=genus,
        taxon_id=f"fixture:{genus.lower()}",
        latitude=latitude,
        longitude=longitude,
        coordinate_uncertainty_m=100.0,
        event_date="2026-08-01",
        basis_of_record="synthetic_fixture",
        license="CC0-1.0",
        media_license=None,
        is_captive_or_cultivated=False,
        query_parameters={"taxon_id": f"fixture:{genus.lower()}"},
        snapshot_or_cache_key=DATASET_ID,
    )
    for index, (genus, latitude, longitude) in enumerate(
        [
            ("Bactrocera", -35.1, 146.4),
            ("Bactrocera", -35.3, 146.6),
            ("Bactrocera", -34.9, 146.2),
            ("Anastrepha", -15.8, -47.9),
            ("Anastrepha", -16.0, -48.1),
            ("Anastrepha", -15.6, -47.7),
            ("Ceratitis", -33.9, 18.4),
            ("Ceratitis", -34.1, 18.6),
            ("Rhagoletis", 42.4, -71.1),
            ("Rhagoletis", 42.6, -71.3),
        ],
        start=1,
    )
]


def build_fixture_occurrence_provider() -> InMemoryOccurrenceProvider:
    """Return the default zero-configuration synthetic occurrence provider."""
    return InMemoryOccurrenceProvider(records=_RECORDS, dataset_id=DATASET_ID)
