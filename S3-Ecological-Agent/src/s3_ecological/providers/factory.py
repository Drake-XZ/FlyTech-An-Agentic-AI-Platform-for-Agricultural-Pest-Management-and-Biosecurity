"""Provider factory (EarlyDesign.md section 6.4: "place provider selection
behind dependency injection or a factory so a live adapter can be added
later without changing taxonomy, cleaning, fusion, risk, or evidence
logic").
"""

from __future__ import annotations

import json
from pathlib import Path

from s3_ecological.interfaces.occurrence import OccurrenceProvider
from s3_ecological.interfaces.taxonomy import TaxonomyProvider
from s3_ecological.providers.occurrence_live_deferred import (
    LiveAlaOccurrenceProvider,
    LiveGbifOccurrenceProvider,
)
from s3_ecological.providers.occurrence_local_snapshot import LocalSnapshotOccurrenceProvider
from s3_ecological.providers.occurrence_memory import InMemoryOccurrenceProvider
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.providers.taxonomy_local_snapshot import LocalSnapshotTaxonomyProvider
from s3_ecological.settings import S3Settings


def validate_local_snapshot_bundle(settings: S3Settings) -> None:
    """Cross-check that the configured occurrence and taxonomy snapshot files
    form one consistent bundle (EarlyDesign.md, "Offline taxonomy provider").

    Only meaningful - and only ever called - when both
    ``occurrence_provider`` and ``taxonomy_provider`` are ``"local_snapshot"``;
    a legacy occurrence-only snapshot paired with a non-local taxonomy
    provider is never passed through here, so that combination keeps working
    unchanged. Reads both files directly (rather than through already-built
    provider instances) so this check has no dependency on which of the two
    builder functions runs first.
    """
    if not settings.occurrence_snapshot_path or not settings.taxonomy_snapshot_path:
        raise ValueError(
            "both occurrence_snapshot_path and taxonomy_snapshot_path are required "
            "to validate a local snapshot bundle"
        )

    occurrence_payload = json.loads(
        Path(settings.occurrence_snapshot_path).read_text(encoding="utf-8")
    )
    taxonomy_payload = json.loads(Path(settings.taxonomy_snapshot_path).read_text(encoding="utf-8"))

    occurrence_dataset_id = occurrence_payload.get("dataset_id")
    taxonomy_dataset_id = taxonomy_payload.get("dataset_id")
    if occurrence_dataset_id != taxonomy_dataset_id:
        raise ValueError(
            "occurrence/taxonomy local snapshot dataset_id mismatch: "
            f"'{occurrence_dataset_id}' != '{taxonomy_dataset_id}'"
        )

    occurrence_sha256 = occurrence_payload.get("source_sha256")
    taxonomy_sha256 = taxonomy_payload.get("source_sha256")
    if (
        occurrence_sha256 is not None
        and taxonomy_sha256 is not None
        and occurrence_sha256 != taxonomy_sha256
    ):
        raise ValueError(
            "occurrence/taxonomy local snapshot source_sha256 mismatch: "
            f"'{occurrence_sha256}' != '{taxonomy_sha256}'"
        )

    known_taxon_ids = {
        taxon_id
        for taxon in taxonomy_payload.get("taxa", [])
        for taxon_id in taxon.get("taxon_ids", {}).values()
    }
    unknown_taxon_ids = {
        record.get("taxon_id")
        for record in occurrence_payload.get("records", [])
        if record.get("taxon_id") not in known_taxon_ids
    }
    if unknown_taxon_ids:
        raise ValueError(
            "occurrence records reference taxon_id(s) not present in the taxonomy "
            f"snapshot: {sorted(unknown_taxon_ids)}"
        )


def build_taxonomy_provider(settings: S3Settings) -> TaxonomyProvider:
    """Select a taxonomy provider by name from ``settings.taxonomy_provider``."""
    if settings.taxonomy_provider == "fixture":
        return FixtureTaxonomyProvider()
    if settings.taxonomy_provider == "local_snapshot":
        if not settings.taxonomy_snapshot_path:
            raise ValueError("taxonomy_snapshot_path is required for local_snapshot provider")
        if settings.occurrence_provider == "local_snapshot":
            validate_local_snapshot_bundle(settings)
        return LocalSnapshotTaxonomyProvider(settings.taxonomy_snapshot_path)
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
            if settings.taxonomy_provider == "local_snapshot":
                validate_local_snapshot_bundle(settings)
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
