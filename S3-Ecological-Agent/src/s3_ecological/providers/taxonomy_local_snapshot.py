"""Local-snapshot taxonomy provider (Milestone 1.5: offline occurrence
snapshot ingestion, EarlyDesign.md section 6.4).

Resolves submitted names against a ``taxonomy.json`` bundle produced by
:mod:`s3_ecological.ingestion.occurrence_snapshot`, through the same
:class:`TaxonomyProvider` interface as :class:`~s3_ecological.providers.
taxonomy_fixture.FixtureTaxonomyProvider`. Reads exactly one local file at
construction time; never performs network I/O and never falls back to the
fixture taxonomy on a miss.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from s3_ecological.interfaces.taxonomy import TaxonomyProvider, TaxonomyQuery, TaxonomyResolution
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus
from s3_ecological.schemas.response import ResolvedTaxon
from s3_ecological.schemas.snapshot import TaxonomySnapshot, TaxonomySnapshotItem

PROVIDER_NAME = "local_snapshot"


def _normalize(name: str) -> str:
    """Same normalization rule the importer uses to detect name collisions:
    Unicode NFKC, trim, collapse internal whitespace, case-fold."""
    folded = unicodedata.normalize("NFKC", name).strip().casefold()
    return " ".join(folded.split())


def _resolved_taxon(taxon: TaxonomySnapshotItem, *, ambiguous: bool = False) -> ResolvedTaxon:
    """Re-key the persisted ``{import-source: id}`` mapping to this
    provider's own name.

    ``taxon_ids`` on disk is keyed by where the id came from (``gbif``,
    ``ala``, ``generic_dwc``, or a canonical record's own namespace prefix)
    so the bundle is self-describing on its own. The pipeline instead looks
    up ``ResolvedTaxon.taxon_ids`` by ``settings.taxonomy_provider``
    (``"local_snapshot"``), exactly as :mod:`taxonomy_fixture` keys its
    entries by ``"fixture"`` - so this provider remaps the key, not the
    value, when handing a taxon to the pipeline.
    """
    namespaced_id = next(iter(taxon.taxon_ids.values()))
    return ResolvedTaxon(
        scientific_name=taxon.scientific_name,
        rank=taxon.rank or "unknown",
        taxon_ids={PROVIDER_NAME: namespaced_id},
        synonym_of=taxon.synonym_of,
        ambiguous=ambiguous or taxon.ambiguous,
    )


class LocalSnapshotTaxonomyProvider(TaxonomyProvider):
    """Taxonomy provider backed by one ``taxonomy.json`` snapshot file on disk."""

    def __init__(self, snapshot_path: str | Path) -> None:
        self.snapshot_path = Path(snapshot_path)
        payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.snapshot = TaxonomySnapshot.model_validate(payload)
        self.dataset_id = self.snapshot.dataset_id
        self.source_sha256 = self.snapshot.source_sha256

        self._indices_by_normalized_name: dict[str, list[int]] = {}
        for index, taxon in enumerate(self.snapshot.taxa):
            for name in (taxon.scientific_name, *taxon.submitted_names):
                self._indices_by_normalized_name.setdefault(_normalize(name), []).append(index)

    def resolve(self, query: TaxonomyQuery) -> ToolResult[TaxonomyResolution]:
        indices = sorted(set(self._indices_by_normalized_name.get(_normalize(query.name), [])))

        if not indices:
            resolution = TaxonomyResolution(submitted_name=query.name, resolved_taxon=None)
            return ToolResult(
                status=ToolStatus.PARTIAL,
                data=resolution,
                warnings=[
                    Issue(
                        code=IssueCode.TAXON_NOT_FOUND,
                        message=f"'{query.name}' did not match any taxon in this local snapshot",
                        component="taxonomy",
                        retryable=False,
                    )
                ],
            )

        if len(indices) == 1:
            taxon = self.snapshot.taxa[indices[0]]
            resolution = TaxonomyResolution(
                submitted_name=query.name, resolved_taxon=_resolved_taxon(taxon)
            )
            return ToolResult(status=ToolStatus.SUCCESS, data=resolution)

        candidates = [self.snapshot.taxa[index].scientific_name for index in indices]
        best_guess = _resolved_taxon(self.snapshot.taxa[indices[0]], ambiguous=True)
        resolution = TaxonomyResolution(
            submitted_name=query.name, resolved_taxon=best_guess, candidate_matches=candidates
        )
        return ToolResult(status=ToolStatus.PARTIAL, data=resolution)
