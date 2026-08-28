"""Taxonomy provider interface (EarlyDesign.md sections 7.3, 11.1).

Any taxonomy source - a fixture, a local snapshot, or a future live GBIF/ALA
adapter - implements :class:`TaxonomyProvider`. Domain logic (``taxonomy/``)
depends only on this Protocol, never on a concrete provider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from s3_ecological.schemas.common import ToolResult
from s3_ecological.schemas.response import ResolvedTaxon


class TaxonomyQuery(BaseModel):
    """Input to ``resolve_taxonomy`` (EarlyDesign.md section 7.3)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    rank: str | None = None


class TaxonomyResolution(BaseModel):
    """Output of a single taxonomy resolution.

    ``candidate_matches`` lists alternative accepted names considered when
    ``resolved_taxon.ambiguous`` is True, so a caller can see why the match
    was uncertain instead of a silent best guess (EarlyDesign.md section
    11.1: "do not silently merge taxa when the match is uncertain").
    """

    model_config = ConfigDict(extra="forbid")

    submitted_name: str
    resolved_taxon: ResolvedTaxon | None
    candidate_matches: list[str] = Field(default_factory=list)


@runtime_checkable
class TaxonomyProvider(Protocol):
    """Interface every taxonomy source (fixture, snapshot, or live) must implement."""

    def resolve(self, query: TaxonomyQuery) -> ToolResult[TaxonomyResolution]:
        """Resolve a submitted name to a stable, versioned taxon identity."""
        ...
