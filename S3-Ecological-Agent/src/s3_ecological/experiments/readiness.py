"""Pure readiness-status evaluation for the offline pre-Milestone 2 gate
(DesignSuggestionLog.md, "Required output artifacts" status semantics and
"S1 boundary"). No file I/O here - see
:mod:`s3_ecological.experiments.prepare` for orchestration.

This module never trains a model, scores anything, or calibrates a
threshold. It only classifies already-computed counts and declarations into
the fixed status vocabulary the design suggestion defines.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from s3_ecological.schemas.experiment import (
    AuthorisationDeclaration,
    AuthorisationStatus,
    DataNature,
    ReadinessStatus,
    S1InputStatus,
    SplitName,
)

REASON_AUTHORISATION_NOT_GRANTED = "authorisation_not_granted"
REASON_AUTHORISATION_UNKNOWN = "authorisation_unknown"
REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED = "synthetic_engineering_fixture_declared"
REASON_NO_USABLE_OCCURRENCE_RECORDS = "no_usable_occurrence_records"
REASON_MISSING_TARGET_TAXON_COVERAGE = "missing_target_taxon_coverage"
REASON_SINGLE_BLOCK_ONLY = "single_block_only"
REASON_EMPTY_REQUIRED_SPLIT = "empty_required_split"
REASON_MISSING_AUTHORISED_S1_OUTPUTS = "missing_authorised_s1_outputs"
REASON_S1_OUTPUTS_SUPPLIED_BUT_NOT_VALIDATED = "s1_outputs_supplied_but_not_validated_by_this_tool"


def evaluate_authorisation(declaration: AuthorisationDeclaration) -> list[str]:
    """Reason codes for a data-authorisation declaration that is not
    ``authorised``. A public licence is never treated as authorisation
    (EarlyDesign.md; the caller must never pass an inferred status here)."""
    if declaration.status is AuthorisationStatus.AUTHORISED:
        return []
    if declaration.status is AuthorisationStatus.NOT_AUTHORISED:
        return [REASON_AUTHORISATION_NOT_GRANTED]
    return [REASON_AUTHORISATION_UNKNOWN]


def evaluate_s1_input(
    *,
    s1_evaluation_input_path: str | None,
    data_nature: DataNature,
) -> tuple[S1InputStatus, list[str]]:
    """This increment does not implement S1 (DesignSuggestionLog.md "S1
    boundary"), so a supplied path is never validated here - it can only be
    reported as unvalidated, or as an engineering fixture when the whole
    input bundle is declared synthetic."""
    if s1_evaluation_input_path is None:
        return S1InputStatus.MISSING, [REASON_MISSING_AUTHORISED_S1_OUTPUTS]
    if data_nature is DataNature.SYNTHETIC_ENGINEERING_FIXTURE:
        return S1InputStatus.ENGINEERING_FIXTURE_ONLY, [
            REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED
        ]
    return S1InputStatus.UNVALIDATED, [REASON_S1_OUTPUTS_SUPPLIED_BUT_NOT_VALIDATED]


def evaluate_data_quality(
    *,
    usable_record_count: int,
    counts_by_target_taxon: Mapping[str, int],
    target_taxa: Sequence[str],
    counts_by_block: Mapping[str, int],
    counts_by_split: Mapping[str, int],
    required_splits: Sequence[SplitName],
) -> list[str]:
    """Reason codes describing why usable, authorised occurrence data is
    not yet enough to engineer a geographic prior on. Never moves a record
    between splits to fix these - only reports them."""
    reasons: list[str] = []
    if usable_record_count == 0:
        reasons.append(REASON_NO_USABLE_OCCURRENCE_RECORDS)
        return reasons

    if any(counts_by_target_taxon.get(taxon, 0) == 0 for taxon in target_taxa):
        reasons.append(REASON_MISSING_TARGET_TAXON_COVERAGE)

    if len(counts_by_block) <= 1:
        reasons.append(REASON_SINGLE_BLOCK_ONLY)

    if any(counts_by_split.get(split.value, 0) == 0 for split in required_splits):
        reasons.append(REASON_EMPTY_REQUIRED_SPLIT)

    return reasons


def compute_occurrence_data_status(
    *,
    data_nature: DataNature,
    authorisation_reasons: Sequence[str],
    data_quality_reasons: Sequence[str],
) -> ReadinessStatus:
    """Status for the occurrence bundle alone, independent of S1. A
    synthetic fixture always reports as a fixture, never as readiness -
    even if it would otherwise look clean and well authorised."""
    if data_nature is DataNature.SYNTHETIC_ENGINEERING_FIXTURE:
        return ReadinessStatus.ENGINEERING_FIXTURE_ONLY
    if authorisation_reasons:
        return ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA
    if data_quality_reasons:
        return ReadinessStatus.NOT_READY_DATA_QUALITY
    return ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING


def compute_overall_status(
    *,
    occurrence_data_status: ReadinessStatus,
    s1_input_status: S1InputStatus,
) -> ReadinessStatus:
    """The Milestone-2 gating status. Uses the safest applicable result and
    never reports ``ready_for_approved_milestone_2_experiment`` while S1
    outputs or an authorised evaluation label are absent
    (DesignSuggestionLog.md "Required output artifacts")."""
    if (
        occurrence_data_status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY
        or s1_input_status is S1InputStatus.ENGINEERING_FIXTURE_ONLY
    ):
        return ReadinessStatus.ENGINEERING_FIXTURE_ONLY

    if (
        occurrence_data_status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA
        or s1_input_status is not S1InputStatus.AVAILABLE_AUTHORISED
    ):
        return ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA

    if occurrence_data_status is ReadinessStatus.NOT_READY_DATA_QUALITY:
        return ReadinessStatus.NOT_READY_DATA_QUALITY

    return ReadinessStatus.READY_FOR_APPROVED_MILESTONE_2_EXPERIMENT


def combine_reason_codes(*reason_groups: Sequence[str]) -> list[str]:
    """Deduplicate while preserving first-seen order across groups, so the
    result is deterministic given deterministic inputs."""
    seen: dict[str, None] = {}
    for group in reason_groups:
        for reason in group:
            seen.setdefault(reason, None)
    return list(seen)
