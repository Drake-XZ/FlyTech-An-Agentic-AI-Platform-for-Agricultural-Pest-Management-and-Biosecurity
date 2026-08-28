"""Profile-dependent request validation (EarlyDesign.md section 8, section 6
fusion-semantics bullets).

Structural validation (types, ranges, raw ``candidate_id`` uniqueness) lives
in ``schemas.request`` and is enforced unconditionally by Pydantic. The
checks here need a versioned, configurable tolerance from ``S3Settings``,
so they are kept out of that framework-neutral schema module.
"""

from __future__ import annotations

from s3_ecological.schemas.common import Issue
from s3_ecological.schemas.enums import IssueCode
from s3_ecological.schemas.request import ObservationRequest
from s3_ecological.settings import S3Settings


def validate_schema_version(
    request: ObservationRequest, supported_versions: frozenset[str]
) -> list[Issue]:
    """Reject a request declaring a schema version this build does not implement."""
    if request.schema_version not in supported_versions:
        return [
            Issue(
                code=IssueCode.UNSUPPORTED_SCHEMA_VERSION,
                message=(
                    f"schema_version '{request.schema_version}' is not supported; "
                    f"supported versions are {sorted(supported_versions)}"
                ),
                component="orchestration.validation",
                retryable=False,
            )
        ]
    return []


def validate_candidate_probabilities(
    request: ObservationRequest, settings: S3Settings
) -> list[Issue]:
    """Enforce the candidate-set-completeness probability rules (section 8).

    ``candidate_set_complete=true`` requires the raw probabilities to sum to
    1 within ``probability_sum_tolerance``. ``candidate_set_complete=false``
    only requires the sum to be at most 1 (within the same tolerance);
    omitted mass may be unknown.
    """
    total = sum(candidate.visual_probability for candidate in request.visual_candidates)
    tolerance = settings.probability_sum_tolerance

    if request.candidate_set_complete:
        if abs(total - 1.0) > tolerance:
            return [
                _invalid_input(
                    f"candidate_set_complete=true requires visual_probability values to "
                    f"sum to 1 within tolerance {tolerance}, got {total}"
                )
            ]
        return []

    if total > 1.0 + tolerance:
        return [
            _invalid_input(
                f"candidate_set_complete=false requires visual_probability values to "
                f"sum to at most 1 within tolerance {tolerance}, got {total}"
            )
        ]
    return []


def validate_no_duplicate_resolved_taxa(
    resolved_taxon_id_by_candidate: dict[str, str | None]
) -> list[Issue]:
    """Reject two submitted candidates that resolve to the same taxon.

    Two different raw names (a synonym and its accepted name, for example)
    can describe the same taxon; the raw ``candidate_id`` uniqueness check
    in ``schemas.request`` cannot catch that because it only sees the raw
    names, so this runs after taxonomy resolution.
    """
    seen_candidate_by_taxon_id: dict[str, str] = {}
    issues: list[Issue] = []
    for candidate_id, taxon_id in resolved_taxon_id_by_candidate.items():
        if taxon_id is None:
            continue
        earlier_candidate_id = seen_candidate_by_taxon_id.get(taxon_id)
        if earlier_candidate_id is not None:
            issues.append(
                Issue(
                    code=IssueCode.DUPLICATE_CANDIDATE,
                    message=(
                        f"candidates '{earlier_candidate_id}' and '{candidate_id}' both "
                        f"resolve to taxon '{taxon_id}'"
                    ),
                    component="orchestration.validation",
                    retryable=False,
                )
            )
        else:
            seen_candidate_by_taxon_id[taxon_id] = candidate_id
    return issues


def _invalid_input(message: str) -> Issue:
    return Issue(
        code=IssueCode.INVALID_INPUT,
        message=message,
        component="orchestration.validation",
        retryable=False,
    )
