"""Fixture-backed taxonomy provider.

Covers the four TF4 genera named in EarlyDesign.md section 6.1 plus two
edge cases used by the unit/golden tests: a historical synonym (``Dacus``,
long used in older literature for several ``Bactrocera`` species) and a
deliberately ambiguous rank-mismatched name, so ambiguity handling is
exercised without needing a live taxonomy backend.
"""

from __future__ import annotations

from s3_ecological.interfaces.taxonomy import TaxonomyProvider, TaxonomyQuery, TaxonomyResolution
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus
from s3_ecological.schemas.response import ResolvedTaxon

_TF4_GENERA: dict[str, ResolvedTaxon] = {
    "anastrepha": ResolvedTaxon(
        scientific_name="Anastrepha", rank="genus", taxon_ids={"fixture": "fixture:anastrepha"}
    ),
    "bactrocera": ResolvedTaxon(
        scientific_name="Bactrocera", rank="genus", taxon_ids={"fixture": "fixture:bactrocera"}
    ),
    "ceratitis": ResolvedTaxon(
        scientific_name="Ceratitis", rank="genus", taxon_ids={"fixture": "fixture:ceratitis"}
    ),
    "rhagoletis": ResolvedTaxon(
        scientific_name="Rhagoletis", rank="genus", taxon_ids={"fixture": "fixture:rhagoletis"}
    ),
}

# Maps a lower-cased synonym name to the lower-cased accepted-name key above.
_SYNONYMS: dict[str, str] = {
    "dacus": "bactrocera",
}

# Names that deliberately resolve ambiguously (e.g. a species-rank name with
# no species-level entry in this genus-only fixture taxonomy). Maps the
# lower-cased submitted name to the list of accepted names it could plausibly
# match.
_AMBIGUOUS_MATCHES: dict[str, list[str]] = {
    "anastrepha sp.": ["Anastrepha"],
}


class FixtureTaxonomyProvider(TaxonomyProvider):
    """Deterministic, in-memory taxonomy resolution for the TF4 genera."""

    def resolve(self, query: TaxonomyQuery) -> ToolResult[TaxonomyResolution]:
        lookup_name = query.name.strip().lower()

        if lookup_name in _AMBIGUOUS_MATCHES:
            candidate_names = _AMBIGUOUS_MATCHES[lookup_name]
            best_guess = _TF4_GENERA[candidate_names[0].lower()].model_copy(
                update={"ambiguous": True}
            )
            resolution = TaxonomyResolution(
                submitted_name=query.name,
                resolved_taxon=best_guess,
                candidate_matches=candidate_names,
            )
            return ToolResult(status=ToolStatus.PARTIAL, data=resolution)

        if lookup_name in _SYNONYMS:
            accepted = _TF4_GENERA[_SYNONYMS[lookup_name]].model_copy(
                update={"synonym_of": query.name}
            )
            resolution = TaxonomyResolution(submitted_name=query.name, resolved_taxon=accepted)
            return ToolResult(status=ToolStatus.SUCCESS, data=resolution)

        if lookup_name in _TF4_GENERA:
            resolution = TaxonomyResolution(
                submitted_name=query.name, resolved_taxon=_TF4_GENERA[lookup_name]
            )
            return ToolResult(status=ToolStatus.SUCCESS, data=resolution)

        resolution = TaxonomyResolution(submitted_name=query.name, resolved_taxon=None)
        return ToolResult(
            status=ToolStatus.PARTIAL,
            data=resolution,
            warnings=[
                Issue(
                    code=IssueCode.TAXON_NOT_FOUND,
                    message=(
                        f"'{query.name}' did not match any known taxon in this fixture taxonomy"
                    ),
                    component="taxonomy",
                    retryable=False,
                )
            ],
        )
