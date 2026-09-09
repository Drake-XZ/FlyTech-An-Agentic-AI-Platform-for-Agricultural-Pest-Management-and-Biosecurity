"""Validation boundary for an authorised, recorded S1 evaluation bundle.

This module validates outputs produced outside S3.  It neither implements nor
trains a visual model.  A path is accepted only when its provenance, checksums,
candidate semantics, labels, and spatial-test membership all reconcile.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from s3_ecological.orchestration.validation import validate_candidate_probabilities
from s3_ecological.schemas.request import ObservationRequest
from s3_ecological.settings import S3Settings

_OBSERVATION_ID_PATTERN = re.compile(r"inaturalist\.org/observations/(\d+)", re.IGNORECASE)


class S1BundleValidationError(ValueError):
    """The supplied S1 evaluation bundle is not safe to use for M2."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise S1BundleValidationError(f"{label} must be an object")
    return value


def _require_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise S1BundleValidationError(f"{label}.{key} must be non-empty text")
    return value


def _artifact_path(
    bundle_dir: Path, artifacts: dict[str, Any], file_key: str, hash_key: str
) -> Path:
    filename = _require_text(artifacts, file_key, "artifacts")
    if Path(filename).name != filename:
        raise S1BundleValidationError(f"artifacts.{file_key} must be a direct child filename")
    path = bundle_dir / filename
    if not path.is_file():
        raise S1BundleValidationError(f"referenced S1 artifact does not exist: {filename}")
    expected_hash = _require_text(artifacts, hash_key, "artifacts").lower()
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        raise S1BundleValidationError(
            f"SHA-256 mismatch for {filename}: expected {expected_hash}, got {actual_hash}"
        )
    return path


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return _require_mapping(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S1BundleValidationError(f"cannot read valid JSON from {path}: {exc}") from exc


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise S1BundleValidationError(f"blank line in {label} at line {line_number}")
                rows.append(_require_mapping(json.loads(line), f"{label}[{line_number}]"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S1BundleValidationError(f"cannot read valid JSONL from {path}: {exc}") from exc
    return rows


def _test_observation_ids(source_record_ids: set[str]) -> set[str]:
    result: set[str] = set()
    for value in source_record_ids:
        match = _OBSERVATION_ID_PATTERN.search(value)
        if match:
            result.add(match.group(1))
    return result


def validate_s1_evaluation_bundle(
    *,
    manifest_path: str | Path,
    expected_authorisation_reference: str,
    expected_spatial_split_identity: str,
    test_source_record_ids: set[str],
    settings: S3Settings,
) -> None:
    """Validate a real S1 bundle or raise :class:`S1BundleValidationError`."""
    path = Path(manifest_path)
    bundle = _load_json(path, "S1 bundle")
    if bundle.get("schema_version") != "1.0.0":
        raise S1BundleValidationError("unsupported S1 bundle schema_version")
    if bundle.get("status") != "available_authorised":
        raise S1BundleValidationError("S1 bundle status must be available_authorised")

    authorisation = _require_mapping(bundle.get("authorisation"), "authorisation")
    if _require_text(authorisation, "reference", "authorisation") != (
        expected_authorisation_reference
    ):
        raise S1BundleValidationError("S1 and occurrence authorisation references differ")
    _require_text(authorisation, "purpose", "authorisation")
    _require_text(authorisation, "approving_role", "authorisation")

    scope = _require_mapping(bundle.get("evaluation_scope"), "evaluation_scope")
    if scope.get("spatial_split") != "test":
        raise S1BundleValidationError("S1 evaluation scope must be the spatial test split")
    if scope.get("spatial_split_identity") != expected_spatial_split_identity:
        raise S1BundleValidationError("S1 bundle spatial split identity does not match this run")
    for key in (
        "tf4_training_observation_overlap",
        "tf4_sha256_overlap",
        "no_derivatives_images",
    ):
        if scope.get(key) != 0:
            raise S1BundleValidationError(f"evaluation_scope.{key} must be zero")
    if scope.get("one_image_per_observation") is not True:
        raise S1BundleValidationError("S1 evaluation must use one image per observation")

    semantics = _require_mapping(bundle.get("candidate_semantics"), "candidate_semantics")
    label_space = semantics.get("label_space")
    if not isinstance(label_space, list) or not all(isinstance(name, str) for name in label_space):
        raise S1BundleValidationError("candidate_semantics.label_space must be text list")
    if label_space != ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]:
        raise S1BundleValidationError("S1 bundle must use the ordered TF4 genus label space")
    if semantics.get("probabilities") != "raw closed-set softmax over the four TF4 genera":
        raise S1BundleValidationError("unsupported S1 probability semantics")
    if semantics.get("candidate_set_complete") is not True:
        raise S1BundleValidationError("this bundle profile requires complete TF4 candidate sets")
    if semantics.get("unknown_class_supported") is not False:
        raise S1BundleValidationError("this closed-set bundle must not claim an unknown class")

    artifacts = _require_mapping(bundle.get("artifacts"), "artifacts")
    bundle_dir = path.parent
    predictions_path = _artifact_path(
        bundle_dir, artifacts, "predictions_file", "predictions_sha256"
    )
    labels_path = _artifact_path(bundle_dir, artifacts, "ground_truth_file", "ground_truth_sha256")
    evaluation_manifest_path = _artifact_path(
        bundle_dir, artifacts, "evaluation_manifest_file", "evaluation_manifest_sha256"
    )
    crosswalk_path = _artifact_path(
        bundle_dir, artifacts, "taxonomy_crosswalk_file", "taxonomy_crosswalk_sha256"
    )
    preparation_report_path = _artifact_path(
        bundle_dir, artifacts, "preparation_report_file", "preparation_report_sha256"
    )

    crosswalk = _load_json(crosswalk_path, "taxonomy crosswalk")
    classes = crosswalk.get("classes")
    if not isinstance(classes, list) or len(classes) != 4:
        raise S1BundleValidationError("taxonomy crosswalk must contain four classes")
    ordered_classes = sorted(classes, key=lambda row: row.get("class_index", -1))
    candidate_id_by_name = {
        _require_text(row, "name", "crosswalk class"): _require_text(
            row, "candidate_id", "crosswalk class"
        )
        for row in ordered_classes
    }
    if list(candidate_id_by_name) != label_space:
        raise S1BundleValidationError("taxonomy crosswalk order does not match label space")

    preparation = _load_json(preparation_report_path, "TF4 preparation report")
    if preparation.get("authorisation_reference") != expected_authorisation_reference:
        raise S1BundleValidationError("preparation report authorisation does not match")
    preparation_evaluation = _require_mapping(preparation.get("evaluation"), "evaluation")
    if preparation_evaluation.get("spatial_split_identity") != expected_spatial_split_identity:
        raise S1BundleValidationError("preparation report spatial split identity does not match")
    if preparation_evaluation.get("manifest_sha256") != _sha256_file(evaluation_manifest_path):
        raise S1BundleValidationError("preparation report evaluation manifest hash does not match")

    prediction_payloads = _load_jsonl(predictions_path, "predictions")
    label_payloads = _load_jsonl(labels_path, "ground truth")
    expected_count = scope.get("observation_count")
    if not isinstance(expected_count, int) or expected_count <= 0:
        raise S1BundleValidationError("evaluation_scope.observation_count must be positive")
    if len(prediction_payloads) != expected_count or len(label_payloads) != expected_count:
        raise S1BundleValidationError("S1 artifact counts do not match observation_count")

    producer = _require_mapping(bundle.get("producer"), "producer")
    model_version = _require_text(producer, "model_version", "producer")
    allowed_test_ids = _test_observation_ids(test_source_record_ids)
    predictions_by_id: dict[str, ObservationRequest] = {}
    for index, payload in enumerate(prediction_payloads, start=1):
        try:
            request = ObservationRequest.model_validate(payload)
        except ValidationError as exc:
            raise S1BundleValidationError(f"invalid prediction at line {index}: {exc}") from exc
        if request.schema_version != "1.0.0":
            raise S1BundleValidationError("prediction uses an unsupported request schema")
        if request.observation_id in predictions_by_id:
            raise S1BundleValidationError(f"duplicate prediction id {request.observation_id}")
        if request.observation_id not in allowed_test_ids:
            raise S1BundleValidationError(
                f"prediction {request.observation_id} is not in the spatial test split"
            )
        issues = validate_candidate_probabilities(request, settings)
        if issues:
            raise S1BundleValidationError(issues[0].message)
        if not request.candidate_set_complete or request.omitted_probability_mass != 0:
            raise S1BundleValidationError(
                "prediction does not use closed TF4 completeness semantics"
            )
        if [candidate.name for candidate in request.visual_candidates] != label_space:
            raise S1BundleValidationError("prediction candidate order differs from TF4 label space")
        for candidate in request.visual_candidates:
            if candidate.candidate_id != candidate_id_by_name[candidate.name]:
                raise S1BundleValidationError("prediction candidate id differs from crosswalk")
            if candidate.model_version != model_version:
                raise S1BundleValidationError(
                    "prediction model version differs from bundle producer"
                )
        predictions_by_id[request.observation_id] = request

    labels_by_id: dict[str, dict[str, Any]] = {}
    for label in label_payloads:
        item_id = _require_text(label, "observation_id", "ground truth row")
        if item_id in labels_by_id:
            raise S1BundleValidationError(f"duplicate ground-truth id {item_id}")
        if label.get("schema_version") != "1.0.0" or label.get("spatial_split") != "test":
            raise S1BundleValidationError("ground-truth schema or split is invalid")
        truth_name = _require_text(label, "ground_truth_name", "ground truth row")
        if label.get("ground_truth_candidate_id") != candidate_id_by_name.get(truth_name):
            raise S1BundleValidationError("ground-truth candidate does not match crosswalk")
        if "-nd/" in _require_text(label, "media_license", "ground truth row").lower():
            raise S1BundleValidationError("ground truth includes a no-derivatives image")
        labels_by_id[item_id] = label
    if set(predictions_by_id) != set(labels_by_id):
        raise S1BundleValidationError("prediction and ground-truth observation ids differ")

    with evaluation_manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        manifest_rows = list(csv.DictReader(handle))
    if {row.get("observation_id") for row in manifest_rows} != set(predictions_by_id):
        raise S1BundleValidationError("evaluation manifest observation ids do not reconcile")
    for row in manifest_rows:
        item_id = row["observation_id"]
        if row.get("spatial_split") != "test":
            raise S1BundleValidationError("evaluation manifest contains a non-test row")
        if int(row.get("minimum_tf4_dhash_distance", "0")) <= int(
            scope.get("tf4_dhash_distance_limit", 5)
        ):
            raise S1BundleValidationError(
                "evaluation manifest contains a perceptual near-duplicate"
            )
        if row.get("sha256") != labels_by_id[item_id].get("image_sha256"):
            raise S1BundleValidationError("evaluation image hash differs from ground truth")

    actual_counts = Counter(label["ground_truth_name"] for label in label_payloads)
    if scope.get("counts_by_genus") != {name: actual_counts[name] for name in label_space}:
        raise S1BundleValidationError("evaluation counts_by_genus do not reconcile")
