"""Provider factory (EarlyDesign.md section 6.4: "place provider selection
behind dependency injection or a factory so a live adapter can be added
later without changing taxonomy, cleaning, fusion, risk, or evidence
logic").
"""

from __future__ import annotations

from s3_ecological.interfaces.occurrence import OccurrenceProvider
from s3_ecological.interfaces.taxonomy import TaxonomyProvider
from s3_ecological.providers.occurrence_live_deferred import (
    LiveAlaOccurrenceProvider,
    LiveGbifOccurrenceProvider,
)
from s3_ecological.providers.occurrence_local_snapshot import LocalSnapshotOccurrenceProvider
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.settings import S3Settings


def build_taxonomy_provider(settings: S3Settings) -> TaxonomyProvider:
    """Select a taxonomy provider by name; only ``fixture`` exists today."""
    if settings.taxonomy_provider == "fixture":
        return FixtureTaxonomyProvider()
    raise ValueError(f"Unknown taxonomy_provider '{settings.taxonomy_provider}'")


def build_occurrence_provider(settings: S3Settings) -> OccurrenceProvider:
    """Select an occurrence provider by name from ``settings.occurrence_provider``.

    ``live_gbif``/``live_ala`` are accepted here without requiring
    credentials: the returned provider answers every query with
    ``provider_not_configured`` rather than raising at startup.
    """
    match settings.occurrence_provider:
        case "local_snapshot":
            if not settings.occurrence_snapshot_path:
                raise ValueError("occurrence_snapshot_path is required for local_snapshot provider")
            return LocalSnapshotOccurrenceProvider(settings.occurrence_snapshot_path)
        case "in_memory":
            return InMemoryOccurrenceProvider(records=[])
        case "live_gbif":
            return LiveGbifOccurrenceProvider(
                base_url=settings.gbif_base_url, api_key_env_var=settings.gbif_api_key_env_var
            )
        case "live_ala":
            return LiveAlaOccurrenceProvider(
                base_url=settings.ala_base_url, api_key_env_var=settings.ala_api_key_env_var
            )
        case "fixture" | _:
            from s3_ecological.providers.fixture_occurrences import (
                build_fixture_occurrence_provider,
            )

            return build_fixture_occurrence_provider()
