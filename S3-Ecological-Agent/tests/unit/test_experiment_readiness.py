"""Unit tests for the pure readiness-status/reason-code evaluators
(DesignSuggestionLog.md "Required output artifacts" status semantics and
"S1 boundary"). No file I/O - see
tests/integration/test_prepare_geo_experiment.py for the end-to-end tests.
"""

from __future__ import annotations

from s3_ecological.experiments.readiness import (
    REASON_AUTHORISATION_NOT_GRANTED,
    REASON_AUTHORISATION_UNKNOWN,
    REASON_EMPTY_REQUIRED_SPLIT,
    REASON_MISSING_AUTHORISED_S1_OUTPUTS,
    REASON_MISSING_TARGET_TAXON_COVERAGE,
    REASON_NO_USABLE_OCCURRENCE_RECORDS,
    REASON_S1_OUTPUTS_SUPPLIED_BUT_NOT_VALIDATED,
    REASON_SINGLE_BLOCK_ONLY,
    REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED,
    combine_reason_codes,
    compute_occurrence_data_status,
    compute_overall_status,
    evaluate_authorisation,
    evaluate_data_quality,
    evaluate_s1_input,
)
from s3_ecological.schemas.experiment import (
    AuthorisationDeclaration,
    AuthorisationStatus,
    DataNature,
    ReadinessStatus,
    S1InputStatus,
    SplitName,
)


def test_evaluate_authorisation_authorised_yields_no_reasons():
    declaration = AuthorisationDeclaration(
        status=AuthorisationStatus.AUTHORISED,
        authorisation_reference="ref",
        purpose="purpose",
        approving_role="role",
    )
    assert evaluate_authorisation(declaration) == []


def test_evaluate_authorisation_not_authorised_and_unknown():
    assert evaluate_authorisation(
        AuthorisationDeclaration(status=AuthorisationStatus.NOT_AUTHORISED)
    ) == [REASON_AUTHORISATION_NOT_GRANTED]
    assert evaluate_authorisation(AuthorisationDeclaration()) == [REASON_AUTHORISATION_UNKNOWN]


def test_evaluate_s1_input_missing_path():
    status, reasons = evaluate_s1_input(
        s1_evaluation_input_path=None, data_nature=DataNature.REAL_WORLD_DATA
    )
    assert status is S1InputStatus.MISSING
    assert reasons == [REASON_MISSING_AUTHORISED_S1_OUTPUTS]


def test_evaluate_s1_input_synthetic_fixture_overrides_supplied_path():
    status, reasons = evaluate_s1_input(
        s1_evaluation_input_path="some/path.json",
        data_nature=DataNature.SYNTHETIC_ENGINEERING_FIXTURE,
    )
    assert status is S1InputStatus.ENGINEERING_FIXTURE_ONLY
    assert reasons == [REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED]


def test_evaluate_s1_input_supplied_path_on_real_data_is_unvalidated():
    status, reasons = evaluate_s1_input(
        s1_evaluation_input_path="some/path.json", data_nature=DataNature.REAL_WORLD_DATA
    )
    assert status is S1InputStatus.UNVALIDATED
    assert reasons == [REASON_S1_OUTPUTS_SUPPLIED_BUT_NOT_VALIDATED]


def test_evaluate_data_quality_no_usable_records_short_circuits():
    reasons = evaluate_data_quality(
        usable_record_count=0,
        counts_by_target_taxon={"Bactrocera": 0},
        target_taxa=["Bactrocera"],
        counts_by_block={},
        counts_by_split={},
        required_splits=[SplitName.TRAIN, SplitName.VALIDATION, SplitName.TEST],
    )
    assert reasons == [REASON_NO_USABLE_OCCURRENCE_RECORDS]


def test_evaluate_data_quality_reports_every_applicable_reason():
    reasons = evaluate_data_quality(
        usable_record_count=5,
        counts_by_target_taxon={"Bactrocera": 5, "Ceratitis": 0},
        target_taxa=["Bactrocera", "Ceratitis"],
        counts_by_block={"block-1": 5},
        counts_by_split={"train": 5},
        required_splits=[SplitName.TRAIN, SplitName.VALIDATION, SplitName.TEST],
    )
    assert reasons == [
        REASON_MISSING_TARGET_TAXON_COVERAGE,
        REASON_SINGLE_BLOCK_ONLY,
        REASON_EMPTY_REQUIRED_SPLIT,
    ]


def test_evaluate_data_quality_clean_input_yields_no_reasons():
    reasons = evaluate_data_quality(
        usable_record_count=6,
        counts_by_target_taxon={"Bactrocera": 6},
        target_taxa=["Bactrocera"],
        counts_by_block={"block-1": 3, "block-2": 3},
        counts_by_split={"train": 2, "validation": 2, "test": 2},
        required_splits=[SplitName.TRAIN, SplitName.VALIDATION, SplitName.TEST],
    )
    assert reasons == []


def test_occurrence_data_status_synthetic_fixture_always_wins():
    status = compute_occurrence_data_status(
        data_nature=DataNature.SYNTHETIC_ENGINEERING_FIXTURE,
        authorisation_reasons=[],
        data_quality_reasons=[],
    )
    assert status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY


def test_occurrence_data_status_missing_authorisation_before_data_quality():
    status = compute_occurrence_data_status(
        data_nature=DataNature.REAL_WORLD_DATA,
        authorisation_reasons=[REASON_AUTHORISATION_UNKNOWN],
        data_quality_reasons=[REASON_SINGLE_BLOCK_ONLY],
    )
    assert status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA


def test_occurrence_data_status_data_quality_reason_alone():
    status = compute_occurrence_data_status(
        data_nature=DataNature.REAL_WORLD_DATA,
        authorisation_reasons=[],
        data_quality_reasons=[REASON_SINGLE_BLOCK_ONLY],
    )
    assert status is ReadinessStatus.NOT_READY_DATA_QUALITY


def test_occurrence_data_status_clean_authorised_real_data_is_ready():
    status = compute_occurrence_data_status(
        data_nature=DataNature.REAL_WORLD_DATA, authorisation_reasons=[], data_quality_reasons=[]
    )
    assert status is ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING


def test_overall_status_engineering_fixture_beats_missing_s1():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.ENGINEERING_FIXTURE_ONLY,
        s1_input_status=S1InputStatus.MISSING,
    )
    assert status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY


def test_overall_status_engineering_fixture_s1_only_also_wins():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING,
        s1_input_status=S1InputStatus.ENGINEERING_FIXTURE_ONLY,
    )
    assert status is ReadinessStatus.ENGINEERING_FIXTURE_ONLY


def test_overall_status_missing_authorised_data_before_data_quality():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA,
        s1_input_status=S1InputStatus.AVAILABLE_AUTHORISED,
    )
    assert status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA


def test_overall_status_s1_not_available_forces_not_run_even_when_data_is_ready():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING,
        s1_input_status=S1InputStatus.UNVALIDATED,
    )
    assert status is ReadinessStatus.NOT_RUN_MISSING_AUTHORISED_DATA


def test_overall_status_data_quality_reason_when_s1_available():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.NOT_READY_DATA_QUALITY,
        s1_input_status=S1InputStatus.AVAILABLE_AUTHORISED,
    )
    assert status is ReadinessStatus.NOT_READY_DATA_QUALITY


def test_overall_status_fully_ready_only_when_everything_is_clean():
    status = compute_overall_status(
        occurrence_data_status=ReadinessStatus.READY_FOR_GEO_PRIOR_ENGINEERING,
        s1_input_status=S1InputStatus.AVAILABLE_AUTHORISED,
    )
    assert status is ReadinessStatus.READY_FOR_APPROVED_MILESTONE_2_EXPERIMENT


def test_combine_reason_codes_dedupes_preserving_first_seen_order():
    combined = combine_reason_codes(
        ["a", "b"], ["b", "c"], ["a", "d"],
    )
    assert combined == ["a", "b", "c", "d"]
