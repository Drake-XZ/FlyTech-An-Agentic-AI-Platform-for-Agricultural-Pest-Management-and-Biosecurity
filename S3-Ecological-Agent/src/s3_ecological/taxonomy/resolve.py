"""Per-candidate taxonomy resolution (EarlyDesign.md section 7.2 step 1).

Orchestrates :class:`TaxonomyProvider` calls for a batch of submitted
candidate names. It never invents a resolution: a name the provider cannot
match stays unresolved (``resolved_taxon=None``) rather than being guessed
from a partial string match.
"""

from __future__ import annotations

from s3_ecological.interfaces.taxonomy import TaxonomyProvider, TaxonomyQuery, TaxonomyResolution
from s3_ecological.schemas.common import ToolResult


def resolve_candidate_names(
    names: list[str], provider: TaxonomyProvider
) -> dict[str, ToolResult[TaxonomyResolution]]:
    """Resolve each distinct submitted name once, in first-seen order.

    Duplicate submitted names (e.g. the same species suggested at two ranks
    by S1) are resolved only once and the result is shared, since taxonomy
    resolution is a pure function of the submitted name for a given
    provider snapshot.
    """
    results: dict[str, ToolResult[TaxonomyResolution]] = {}
    for name in names:
        if name in results:
            continue
        results[name] = provider.resolve(TaxonomyQuery(name=name))
    return results
