"""Tests for the authorised external-S1 evaluation bundle boundary."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from s3_ecological.experiments.readiness import evaluate_s1_input
from s3_ecological.experiments.s1_bundle import (
    S1BundleValidationError,
    validate_s1_evaluation_bundle,
)
from s3_ecological.schemas.experiment import DataNature, S1InputStatus
from s3_ecological.settings import S3Settings

CLASSES = ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]
IDS = {name: f"taxon:{index}" for index, name in enumerate(CLASSES)}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_bundle(tmp_path: Path, *, split_identity: str = "split-id") -> Path:
    image_sha = "a" * 64
    prediction = {
        "schema_version": "1.0.0",
        "observation_id": "123",
        "source": "test",
        "candidate_set_complete": True,
        "omitted_probability_mass": 0.0,
        "observed_at": "2026-01-01T00:00:00",
        "location": {
            "latitude": -33.0,
            "longitude": 151.0,
            "coordinate_uncertainty_m": None,
        },
        "visual_candidates": [
            {
                "candidate_id": IDS[name],
                "name": name,
                "rank": "genus",
                "visual_probability": 0.25,
                "model_version": "test-model",
            }
            for name in CLASSES
        ],
        "context": None,
        "other_agent_evidence": [],
    }
    label = {
        "schema_version": "1.0.0",
        "observation_id": "123",
        "ground_truth_candidate_id": IDS["Anastrepha"],
        "ground_truth_name": "Anastrepha",
        "ground_truth_rank": "genus",
        "label_source": "fixture",
        "spatial_split": "test",
        "image_sha256": image_sha,
        "media_license": "https://creativecommons.org/licenses/by/4.0/",
    }
    predictions_path = tmp_path / "predictions.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    _jsonl(predictions_path, [prediction])
    _jsonl(labels_path, [label])

    evaluation_path = tmp_path / "evaluation.csv"
    with evaluation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "observation_id",
                "spatial_split",
                "minimum_tf4_dhash_distance",
                "sha256",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "observation_id": "123",
                "spatial_split": "test",
                "minimum_tf4_dhash_distance": "6",
                "sha256": image_sha,
            }
        )

    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "classes": [
                    {"class_index": index, "name": name, "candidate_id": IDS[name]}
                    for index, name in enumerate(CLASSES)
                ]
            }
        ),
        encoding="utf-8",
    )
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(
        json.dumps(
            {
                "authorisation_reference": "owner-ref",
                "evaluation": {
                    "spatial_split_identity": split_identity,
                    "manifest_sha256": _sha(evaluation_path),
                },
            }
        ),
        encoding="utf-8",
    )
    bundle = {
        "schema_version": "1.0.0",
        "status": "available_authorised",
        "authorisation": {
            "reference": "owner-ref",
            "purpose": "test",
            "approving_role": "owner",
        },
        "producer": {"model_version": "test-model"},
        "candidate_semantics": {
            "label_space": CLASSES,
            "probabilities": "raw closed-set softmax over the four TF4 genera",
            "candidate_set_complete": True,
            "unknown_class_supported": False,
        },
        "evaluation_scope": {
            "spatial_split": "test",
            "spatial_split_identity": split_identity,
            "observation_count": 1,
            "counts_by_genus": {
                "Anastrepha": 1,
                "Bactrocera": 0,
                "Ceratitis": 0,
                "Rhagoletis": 0,
            },
            "one_image_per_observation": True,
            "tf4_training_observation_overlap": 0,
            "tf4_sha256_overlap": 0,
            "tf4_dhash_distance_limit": 5,
            "no_derivatives_images": 0,
        },
        "artifacts": {
            "predictions_file": predictions_path.name,
            "predictions_sha256": _sha(predictions_path),
            "ground_truth_file": labels_path.name,
            "ground_truth_sha256": _sha(labels_path),
            "evaluation_manifest_file": evaluation_path.name,
            "evaluation_manifest_sha256": _sha(evaluation_path),
            "taxonomy_crosswalk_file": crosswalk_path.name,
            "taxonomy_crosswalk_sha256": _sha(crosswalk_path),
            "preparation_report_file": preparation_path.name,
            "preparation_report_sha256": _sha(preparation_path),
        },
    }
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle_path


def test_valid_authorised_s1_bundle_is_accepted(tmp_path: Path):
    bundle_path = _write_bundle(tmp_path)
    validate_s1_evaluation_bundle(
        manifest_path=bundle_path,
        expected_authorisation_reference="owner-ref",
        expected_spatial_split_identity="split-id",
        test_source_record_ids={"gbif:https://www.inaturalist.org/observations/123"},
        settings=S3Settings(),
    )
    status, reasons = evaluate_s1_input(
        s1_evaluation_input_path=str(bundle_path),
        data_nature=DataNature.REAL_WORLD_DATA,
        validated_s1_input=True,
    )
    assert status is S1InputStatus.AVAILABLE_AUTHORISED
    assert reasons == []


def test_tampered_artifact_is_rejected(tmp_path: Path):
    bundle_path = _write_bundle(tmp_path)
    (tmp_path / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(S1BundleValidationError, match="SHA-256 mismatch"):
        validate_s1_evaluation_bundle(
            manifest_path=bundle_path,
            expected_authorisation_reference="owner-ref",
            expected_spatial_split_identity="split-id",
            test_source_record_ids={"gbif:https://www.inaturalist.org/observations/123"},
            settings=S3Settings(),
        )


def test_wrong_spatial_split_identity_is_rejected(tmp_path: Path):
    bundle_path = _write_bundle(tmp_path)
    with pytest.raises(S1BundleValidationError, match="spatial split identity"):
        validate_s1_evaluation_bundle(
            manifest_path=bundle_path,
            expected_authorisation_reference="owner-ref",
            expected_spatial_split_identity="different-split",
            test_source_record_ids={"gbif:https://www.inaturalist.org/observations/123"},
            settings=S3Settings(),
        )


def test_m2d_partition_s1_bundle_is_rejected_for_a_different_partition(tmp_path: Path):
    """M2-D robustness audit: each new spatial partition must regenerate its
    own S1 bundle. A bundle declaring one partition's real identity must be
    rejected when a different partition's identity is expected."""
    from s3_ecological.experiments.spatial_split import (
        LatitudeLongitudeGridV0,
        SplitRatios,
        compute_split_identity,
    )

    ratios = SplitRatios(0.60, 0.20, 0.20)
    reference_identity = compute_split_identity(
        strategy=LatitudeLongitudeGridV0(1.0), ratios=ratios, seed=42
    )
    other_identity = compute_split_identity(
        strategy=LatitudeLongitudeGridV0(0.5), ratios=ratios, seed=42
    )
    assert reference_identity != other_identity

    bundle_path = _write_bundle(tmp_path, split_identity=reference_identity)
    with pytest.raises(S1BundleValidationError, match="spatial split identity"):
        validate_s1_evaluation_bundle(
            manifest_path=bundle_path,
            expected_authorisation_reference="owner-ref",
            expected_spatial_split_identity=other_identity,
            test_source_record_ids={"gbif:https://www.inaturalist.org/observations/123"},
            settings=S3Settings(),
        )
