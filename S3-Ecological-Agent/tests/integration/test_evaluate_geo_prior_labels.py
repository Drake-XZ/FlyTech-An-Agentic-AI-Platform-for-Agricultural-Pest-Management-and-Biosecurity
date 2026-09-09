"""Torch-gated tests for ``scripts/evaluate_geo_prior_m2c.py``'s M2-D
additions (DesignSuggestionLog.md "M2-D robustness, ablation, and
generalisation audit").

Skipped entirely under the main venv (no torch dependency there). Run for
real via (from the repo root):

    data/local/m2/s1/venv/Scripts/python.exe -m pytest \
        tests/integration/test_evaluate_geo_prior_labels.py -q

Uses a tiny synthetic spatial-split manifest, S1 bundle, and geo_prior
checkpoint - never real M2 data. Covers two things:

1. The default invocation (no ``--report-label``/``--report-filename``)
   must keep producing the exact M2-C ``purpose``/``identity`` text and the
   ``m2c_locked_test_report.json`` filename - a regression guard proving the
   new, additive CLI flags do not change M2-C's own behaviour.
2. A custom ``--report-label``/``--report-filename`` changes only those two
   report fields and the output filename; a record with no usable
   ``observed_at`` under the date-aware frozen config is excluded from
   ``geo_only`` but still produces ``s1_only``/``fusion`` predictions (no
   fabricated date, matching ``_compute_geo_support``'s documented
   semantics).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


geo_prior_model = _load_module("geo_prior_model")
evaluate_geo_prior_m2c = _load_module("evaluate_geo_prior_m2c")

from s3_ecological.schemas.experiment import (  # noqa: E402
    GeographicScopeMode,
    ImportReportIdentity,
    OccurrenceSnapshotIdentity,
    SpatialSplitManifest,
    SplitAssignmentRow,
    SplitName,
    TaxonomySnapshotIdentity,
)

_PLACEHOLDER_SHA256 = "0" * 64
CLASSES = ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]
CANDIDATE_IDS = {name: f"taxon:{index}" for index, name in enumerate(CLASSES)}
MODEL_VERSION = "s1-test-model"
AUTHORISATION_REFERENCE = evaluate_geo_prior_m2c.AUTHORISATION_REFERENCE


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _write_spatial_split_manifest(
    path: Path, *, split_identity: str, observation_ids: list[str]
) -> None:
    rows = [
        SplitAssignmentRow(
            source="test",
            source_record_id=f"gbif:https://www.inaturalist.org/observations/{observation_id}",
            taxon_id="t:test",
            block_id="block-1",
            split=SplitName.TEST,
        )
        for observation_id in observation_ids
    ]
    manifest = SpatialSplitManifest(
        experiment_id="m2d-fixture",
        created_at=datetime(2026, 9, 9, tzinfo=UTC),
        occurrence_snapshot=OccurrenceSnapshotIdentity(
            dataset_id="test-dataset",
            source="generic_dwc",
            source_sha256=_PLACEHOLDER_SHA256,
            snapshot_key="test-key",
            dataset_license="CC-BY 4.0",
            citation="test citation",
            retrieved_at="2026-09-09T00:00:00+10:00",
            mapping_version="generic_dwc-v0.1",
            file_sha256=_PLACEHOLDER_SHA256,
        ),
        taxonomy_snapshot=TaxonomySnapshotIdentity(
            dataset_id="test-dataset",
            source="generic_dwc",
            source_sha256=_PLACEHOLDER_SHA256,
            mapping_version="generic_dwc-v0.1",
            file_sha256=_PLACEHOLDER_SHA256,
        ),
        import_report=ImportReportIdentity(
            dataset_id="test-dataset",
            source_sha256=_PLACEHOLDER_SHA256,
            importer_version="test-importer-v0.1",
            file_sha256=_PLACEHOLDER_SHA256,
        ),
        configuration_digest=_PLACEHOLDER_SHA256,
        effective_cleaning_settings={},
        target_taxa=CLASSES,
        geographic_scope="global",
        geographic_scope_mode=GeographicScopeMode.LABEL_ONLY,
        block_strategy="latitude_longitude_grid_v0.1",
        block_strategy_version="v0.1",
        grid_size_degrees=1.0,
        train_ratio=0.6,
        validation_ratio=0.2,
        test_ratio=0.2,
        seed=42,
        split_identity=split_identity,
        rows=rows,
        excluded_records=[],
    )
    path.write_text(manifest.model_dump_json(), encoding="utf-8")


def _write_s1_bundle(tmp_path: Path, *, split_identity: str, observations: list[dict]) -> Path:
    predictions = []
    labels = []
    evaluation_rows = []
    for observation in observations:
        image_sha256 = hashlib.sha256(observation["observation_id"].encode("utf-8")).hexdigest()
        predictions.append(
            {
                "schema_version": "1.0.0",
                "observation_id": observation["observation_id"],
                "source": "test",
                "candidate_set_complete": True,
                "omitted_probability_mass": 0.0,
                "observed_at": observation["observed_at"],
                "location": {
                    "latitude": observation["latitude"],
                    "longitude": observation["longitude"],
                    "coordinate_uncertainty_m": None,
                },
                "visual_candidates": [
                    {
                        "candidate_id": CANDIDATE_IDS[name],
                        "name": name,
                        "rank": "genus",
                        "visual_probability": 0.7 if name == observation["genus"] else 0.1,
                        "model_version": MODEL_VERSION,
                    }
                    for name in CLASSES
                ],
                "context": None,
                "other_agent_evidence": [],
            }
        )
        labels.append(
            {
                "schema_version": "1.0.0",
                "observation_id": observation["observation_id"],
                "ground_truth_candidate_id": CANDIDATE_IDS[observation["genus"]],
                "ground_truth_name": observation["genus"],
                "ground_truth_rank": "genus",
                "label_source": "fixture",
                "spatial_split": "test",
                "image_sha256": image_sha256,
                "media_license": "https://creativecommons.org/licenses/by/4.0/",
            }
        )
        evaluation_rows.append(
            {
                "observation_id": observation["observation_id"],
                "spatial_split": "test",
                "minimum_tf4_dhash_distance": "6",
                "sha256": image_sha256,
            }
        )

    predictions_path = tmp_path / "predictions.jsonl"
    labels_path = tmp_path / "labels.jsonl"
    _jsonl(predictions_path, predictions)
    _jsonl(labels_path, labels)

    evaluation_path = tmp_path / "evaluation.csv"
    with evaluation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["observation_id", "spatial_split", "minimum_tf4_dhash_distance", "sha256"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(evaluation_rows)

    crosswalk_path = tmp_path / "crosswalk.json"
    crosswalk_path.write_text(
        json.dumps(
            {
                "classes": [
                    {"class_index": index, "name": name, "candidate_id": CANDIDATE_IDS[name]}
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
                "authorisation_reference": AUTHORISATION_REFERENCE,
                "evaluation": {
                    "spatial_split_identity": split_identity,
                    "manifest_sha256": _sha(evaluation_path),
                },
            }
        ),
        encoding="utf-8",
    )

    counts_by_genus = {name: 0 for name in CLASSES}
    for observation in observations:
        counts_by_genus[observation["genus"]] += 1

    bundle = {
        "schema_version": "1.0.0",
        "status": "available_authorised",
        "authorisation": {
            "reference": AUTHORISATION_REFERENCE,
            "purpose": "test",
            "approving_role": "owner",
        },
        "producer": {"model_version": MODEL_VERSION},
        "candidate_semantics": {
            "label_space": CLASSES,
            "probabilities": "raw closed-set softmax over the four TF4 genera",
            "candidate_set_complete": True,
            "unknown_class_supported": False,
        },
        "evaluation_scope": {
            "spatial_split": "test",
            "spatial_split_identity": split_identity,
            "observation_count": len(observations),
            "counts_by_genus": counts_by_genus,
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
    bundle_path = tmp_path / "s1_bundle_manifest.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle_path


def _write_selected_configuration(tmp_path: Path) -> Path:
    params = geo_prior_model.EncodingParams(use_date_feats=True)
    num_inputs = geo_prior_model.num_input_feats(params)
    torch.manual_seed(0)
    model = geo_prior_model.FCNet(num_inputs=num_inputs, num_classes=len(CLASSES), num_filts=8)
    checkpoint_path = tmp_path / "checkpoint.pt"
    torch.save({"num_inputs": num_inputs, "state_dict": model.state_dict()}, checkpoint_path)

    selected_configuration = {
        "frozen_config": {"num_filts": 8, "use_date_feats": True},
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": _sha(checkpoint_path),
        "selection_rationale": "synthetic fixture for the M2-D evaluate() integration test",
        "validation_result": {
            "best_epoch": 1,
            "best_validation_macro_f1": 0.5,
            "best_validation_accuracy": 0.5,
            "train_count": 4,
            "validation_count": 2,
        },
    }
    selected_configuration_path = tmp_path / "selected_configuration.json"
    selected_configuration_path.write_text(json.dumps(selected_configuration), encoding="utf-8")
    return selected_configuration_path


def test_default_invocation_matches_m2c_report_text_and_filename(tmp_path):
    split_identity = "m2d-fixture-split-default"
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_spatial_split_manifest(
        manifest_path, split_identity=split_identity, observation_ids=["201", "202", "203"]
    )
    bundle_path = _write_s1_bundle(
        tmp_path,
        split_identity=split_identity,
        observations=[
            {
                "observation_id": "201",
                "genus": "Anastrepha",
                "latitude": 10.0,
                "longitude": 20.0,
                "observed_at": "2020-01-15T00:00:00",
            },
            {
                "observation_id": "202",
                "genus": "Bactrocera",
                "latitude": -10.0,
                "longitude": -20.0,
                "observed_at": None,
            },
            {
                "observation_id": "203",
                "genus": "Ceratitis",
                "latitude": 30.0,
                "longitude": 40.0,
                "observed_at": "2020-03-15T00:00:00",
            },
        ],
    )
    selected_configuration_path = _write_selected_configuration(tmp_path)

    args = argparse.Namespace(
        spatial_split_manifest=manifest_path,
        s1_bundle_manifest=bundle_path,
        selected_configuration=selected_configuration_path,
        output_dir=tmp_path / "evaluation_default",
        report_label=None,
        report_filename=None,
    )
    report = evaluate_geo_prior_m2c.evaluate(args)

    assert report["purpose"] == (
        "M2-C locked spatial-test evaluation: S1-only, geographic-only, fixed-fusion"
    )
    assert report["identity"] == (
        "Experimental FlyTech S3 Milestone 2-C result; not a production readiness or "
        "biosecurity/biological-efficacy claim"
    )
    assert (args.output_dir / "m2c_locked_test_report.json").is_file()

    assert report["observation_count"] == 3
    assert report["geo_only_excluded_missing_date"] == 1
    assert report["s1_only"]["observation_count"] == 3
    assert report["fusion"]["observation_count"] == 3
    assert report["geo_only"]["observation_count"] == 2


def test_report_label_and_filename_change_only_those_fields(tmp_path):
    split_identity = "m2d-fixture-split-custom"
    manifest_path = tmp_path / "spatial-split-manifest.json"
    _write_spatial_split_manifest(
        manifest_path, split_identity=split_identity, observation_ids=["301", "302"]
    )
    bundle_path = _write_s1_bundle(
        tmp_path,
        split_identity=split_identity,
        observations=[
            {
                "observation_id": "301",
                "genus": "Rhagoletis",
                "latitude": -30.0,
                "longitude": -40.0,
                "observed_at": "2020-04-15T00:00:00",
            },
            {
                "observation_id": "302",
                "genus": "Anastrepha",
                "latitude": 11.0,
                "longitude": 21.0,
                "observed_at": "2020-05-15T00:00:00",
            },
        ],
    )
    selected_configuration_path = _write_selected_configuration(tmp_path)

    args = argparse.Namespace(
        spatial_split_manifest=manifest_path,
        s1_bundle_manifest=bundle_path,
        selected_configuration=selected_configuration_path,
        output_dir=tmp_path / "evaluation_custom",
        report_label="M2-D (grid0_5_seed42)",
        report_filename="m2d_locked_test_report.json",
    )
    report = evaluate_geo_prior_m2c.evaluate(args)

    assert report["purpose"] == (
        "M2-D (grid0_5_seed42) spatial-test evaluation: S1-only, geographic-only, fixed-fusion"
    )
    assert report["identity"] == (
        "Experimental FlyTech S3 M2-D (grid0_5_seed42) result; not a production readiness or "
        "biosecurity/biological-efficacy claim"
    )
    assert report["schema_version"] == "1.0.0"
    assert report["authorisation_reference"] == AUTHORISATION_REFERENCE
    assert report["spatial_split_identity"] == split_identity

    assert (args.output_dir / "m2d_locked_test_report.json").is_file()
    assert not (args.output_dir / "m2c_locked_test_report.json").exists()

    assert report["geo_only_excluded_missing_date"] == 0
    assert report["geo_only"]["observation_count"] == 2
