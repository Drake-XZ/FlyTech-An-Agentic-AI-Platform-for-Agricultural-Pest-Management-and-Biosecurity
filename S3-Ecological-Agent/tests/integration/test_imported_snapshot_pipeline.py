"""End-to-end test: import a synthetic GBIF-shaped CSV, then run the
deterministic pipeline against the resulting local snapshot bundle
(Milestone 1.5, EarlyDesign.md "offline occurrence snapshot ingestion").

This never touches the network: ``import_occurrence_snapshot`` reads only
the on-disk fixture at ``tests/fixtures/importer/gbif_small.csv``, and both
``LocalSnapshotOccurrenceProvider``/``LocalSnapshotTaxonomyProvider`` read
only the files it just wrote under ``tmp_path``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from s3_ecological.ingestion.occurrence_snapshot import (
    ImportFatalError,
    import_occurrence_snapshot,
)
from s3_ecological.interfaces.taxonomy import TaxonomyQuery
from s3_ecological.orchestration.pipeline import run_assessment
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider, build_taxonomy_provider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.enums import AssessmentStatus
from s3_ecological.schemas.request import Location, ObservationRequest, VisualCandidate
from s3_ecological.schemas.snapshot import ImportStatus
from s3_ecological.settings import S3Settings
from s3_ecological.suitability.null_model import NullSuitabilityModel

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "importer"
GENERATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _import_gbif_fixture(output_dir: Path):
    return import_occurrence_snapshot(
        input_path=FIXTURES_DIR / "gbif_small.csv",
        source="gbif",
        dataset_id="integration-test-gbif",
        retrieved_at="2026-08-28T00:00:00+00:00",
        dataset_license="CC-BY 4.0",
        citation="Integration test synthetic fixture, not a real dataset.",
        query_parameters_path=None,
        output_dir=output_dir,
        overwrite=False,
    )


def _settings_for_bundle(output_dir: Path) -> S3Settings:
    return S3Settings(
        occurrence_provider="local_snapshot",
        occurrence_snapshot_path=str(output_dir / "occurrences.json"),
        taxonomy_provider="local_snapshot",
        taxonomy_snapshot_path=str(output_dir / "taxonomy.json"),
    )


def _request(name: str, location: Location | None) -> ObservationRequest:
    return ObservationRequest(
        schema_version="1.0.0",
        observation_id="obs-imported-snapshot",
        candidate_set_complete=True,
        visual_candidates=[
            VisualCandidate(candidate_id="c1", name=name, visual_probability=1.0)
        ],
        location=location,
    )


def test_import_then_assess_end_to_end(tmp_path: Path):
    output_dir = tmp_path / "snapshot"
    report = _import_gbif_fixture(output_dir)

    assert report.status is ImportStatus.COMPLETED
    assert report.rejected_record_count == 0
    assert report.accepted_record_count == 5
    assert (output_dir / "occurrences.json").exists()
    assert (output_dir / "taxonomy.json").exists()
    assert (output_dir / "import-report.json").exists()

    settings = _settings_for_bundle(output_dir)
    occurrence_provider = build_occurrence_provider(settings)
    taxonomy_provider = build_taxonomy_provider(settings)

    result = run_assessment(
        _request("Bactrocera dorsalis", Location(latitude=14.5, longitude=121.0)),
        settings=settings,
        taxonomy_provider=taxonomy_provider,
        occurrence_provider=occurrence_provider,
        geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
        suitability_model=NullSuitabilityModel(),
        risk_policy=DeterministicRiskPolicy(),
        analysis_id="integration-imported-snapshot",
        generated_at=GENERATED_AT,
    )

    assert result.status in (
        AssessmentStatus.COMPLETED,
        AssessmentStatus.COMPLETED_WITH_WARNINGS,
    )
    top = result.reranked_candidates[0]
    assert top.resolved_taxon is not None
    assert top.resolved_taxon.scientific_name == "Bactrocera dorsalis"
    assert top.resolved_taxon.taxon_ids["local_snapshot"]

    # The fixture deliberately carries two "Bactrocera dorsalis" rows under
    # distinct taxon ids (gbif:145433 and gbif:999999) - the importer must
    # keep them as two taxonomy items, never merge them, and mark both
    # ambiguous rather than silently picking a winner.
    assert top.resolved_taxon.ambiguous is True

    # Evidence provenance/licence/snapshot-key must come from the imported
    # bundle, not be invented by the pipeline.
    assert result.evidence, "expected at least one evidence record from the local snapshot"
    for evidence in result.evidence:
        assert evidence.source == "gbif"
        assert evidence.license == "CC-BY 4.0"

    occurrences_payload = json.loads((output_dir / "occurrences.json").read_text(encoding="utf-8"))
    assert result.data_snapshot_versions.get("gbif") == occurrences_payload["snapshot_key"]
    assert report.status is ImportStatus.COMPLETED


def test_ambiguous_taxon_is_not_silently_merged(tmp_path: Path):
    output_dir = tmp_path / "snapshot"
    _import_gbif_fixture(output_dir)
    settings = _settings_for_bundle(output_dir)
    taxonomy_provider = build_taxonomy_provider(settings)

    taxonomy_payload = json.loads((output_dir / "taxonomy.json").read_text(encoding="utf-8"))
    dorsalis_items = [
        item
        for item in taxonomy_payload["taxa"]
        if item["scientific_name"] == "Bactrocera dorsalis"
    ]
    assert len(dorsalis_items) == 2
    assert {item["taxon_ids"]["gbif"] for item in dorsalis_items} == {"gbif:145433", "gbif:999999"}
    assert all(item["ambiguous"] for item in dorsalis_items)

    resolution = taxonomy_provider.resolve(TaxonomyQuery(name="Bactrocera dorsalis"))
    assert resolution.data is not None
    assert resolution.data.resolved_taxon is not None
    assert resolution.data.resolved_taxon.ambiguous is True
    assert len(resolution.data.candidate_matches) == 2


def test_evidence_snapshot_key_matches_imported_bundle(tmp_path: Path):
    output_dir = tmp_path / "snapshot"
    report = _import_gbif_fixture(output_dir)
    settings = _settings_for_bundle(output_dir)
    occurrence_provider = build_occurrence_provider(settings)
    taxonomy_provider = build_taxonomy_provider(settings)

    result = run_assessment(
        _request("Bactrocera dorsalis", Location(latitude=14.5, longitude=121.0)),
        settings=settings,
        taxonomy_provider=taxonomy_provider,
        occurrence_provider=occurrence_provider,
        geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
        suitability_model=NullSuitabilityModel(),
        risk_policy=DeterministicRiskPolicy(),
        analysis_id="integration-snapshot-key",
        generated_at=GENERATED_AT,
    )

    occurrences_payload = json.loads((output_dir / "occurrences.json").read_text(encoding="utf-8"))
    expected_snapshot_key = occurrences_payload["snapshot_key"]
    assert result.data_snapshot_versions.get("gbif") == expected_snapshot_key
    assert expected_snapshot_key.startswith("integration-test-gbif:")
    assert report.status is ImportStatus.COMPLETED


def test_malformed_rows_all_rejected_is_fatal_and_writes_nothing(tmp_path: Path):
    """Every row in ``malformed_rows.csv`` triggers a different rejection code,
    so zero records are accepted - a fatal condition (EarlyDesign.md) that
    must raise rather than write a half-empty bundle.
    """
    output_dir = tmp_path / "snapshot"
    with pytest.raises(ImportFatalError, match="zero accepted records"):
        import_occurrence_snapshot(
            input_path=FIXTURES_DIR / "malformed_rows.csv",
            source="generic_dwc",
            dataset_id="integration-test-malformed",
            retrieved_at="2026-08-28T00:00:00+00:00",
            dataset_license="CC0 1.0",
            citation="Integration test synthetic fixture, not a real dataset.",
            query_parameters_path=None,
            output_dir=output_dir,
            overwrite=False,
        )

    assert not output_dir.exists() or not any(output_dir.iterdir())


def test_one_good_row_among_malformed_rows_yields_partial_bundle(tmp_path: Path):
    """Mixing one valid row into an otherwise-malformed file must still
    produce a bundle with the six documented rejection codes recorded, and
    the accepted row's data must be unaffected by its rejected neighbours.
    """
    mixed_csv = tmp_path / "mixed_rows.csv"
    lines = (FIXTURES_DIR / "malformed_rows.csv").read_text(encoding="utf-8").splitlines()
    header, rejected_rows = lines[0], lines[1:]
    good_row = (
        "generic:good,Good species,Good species,generic:taxon-good,species,10.0,20.0,50,"
        "2020-01-01,HumanObservation,CC-BY 4.0,,false,false"
    )
    mixed_csv.write_text("\n".join([header, good_row, *rejected_rows]) + "\n", encoding="utf-8")

    output_dir = tmp_path / "snapshot"
    report = import_occurrence_snapshot(
        input_path=mixed_csv,
        source="generic_dwc",
        dataset_id="integration-test-mixed",
        retrieved_at="2026-08-28T00:00:00+00:00",
        dataset_license="CC0 1.0",
        citation="Integration test synthetic fixture, not a real dataset.",
        query_parameters_path=None,
        output_dir=output_dir,
        overwrite=False,
    )

    assert report.status is ImportStatus.COMPLETED_WITH_REJECTIONS
    assert report.accepted_record_count == 1
    assert report.rejected_record_count == 6
    assert {rejection.code for rejection in report.rejections} == {
        "missing_scientific_name",
        "missing_taxon_id",
        "invalid_numeric_value",
        "negative_coordinate_uncertainty",
        "non_finite_numeric_value",
        "invalid_record_schema",
    }

    occurrences_payload = json.loads((output_dir / "occurrences.json").read_text(encoding="utf-8"))
    assert len(occurrences_payload["records"]) == 1
    assert occurrences_payload["records"][0]["scientific_name_raw"] == "Good species"
