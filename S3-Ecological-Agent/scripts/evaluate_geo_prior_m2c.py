"""Run the single, locked M2-C evaluation on the spatial ``test`` split's
942 S1-scoped observations.

Re-validates the already-authorised S1 evaluation bundle against the
*current* spatial split identity (never trusts a stale validation), loads
the frozen geographic-prior configuration and checkpoint selected by
``scripts/train_geo_prior.py`` on the ``validation`` split only, then reports
S1-only, geographic-only, and fixed-fusion metrics separately over the
locked test observations. Calls
``s3_ecological.experiments.s1_bundle.validate_s1_evaluation_bundle`` and
``s3_ecological.fusion.soft_fusion.fuse`` (via ``geo_prior_metrics``)
unmodified.

This produces one experimental result for FlyTech S3 Milestone 2-C. It is
not a production readiness claim and not a biosecurity or biological-efficacy
conclusion.

Torch-only: run via ``data/local/m2/s1/venv/Scripts/python.exe``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from geo_prior_model import EncodingParams, FCNet, convert_loc_to_tensor, encode_loc_time
from s3_ecological.experiments.geo_prior_dataset import load_manifest
from s3_ecological.experiments.geo_prior_metrics import (
    GeoFusionCandidate,
    bootstrap_confidence_interval,
    fuse_predictions,
    summarize,
    top_candidate_id,
)
from s3_ecological.experiments.s1_bundle import (
    S1BundleValidationError,
    validate_s1_evaluation_bundle,
)
from s3_ecological.schemas.experiment import SplitName
from s3_ecological.settings import S3Settings

CLASS_NAMES = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")
AUTHORISATION_REFERENCE = "owner-approval-m2-2026-09-08"
BOOTSTRAP_SEED = 42
BOOTSTRAP_RESAMPLES = 2000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_usable_date(event_date: str) -> bool:
    """Same convention as ``scripts/train_geo_prior.py::_has_usable_date`` -
    kept as an independent copy rather than a cross-script import, matching
    this project's existing self-contained-script convention (see
    ``scripts/generate_tf4_s1_outputs.py``)."""
    if not event_date:
        return False
    try:
        datetime.strptime(event_date[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _day_of_year_fraction(event_date: str) -> float:
    parsed = datetime.strptime(event_date[:10], "%Y-%m-%d")
    day_of_year = parsed.timetuple().tm_yday
    return (day_of_year / 365.0) * 2.0 - 1.0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _test_source_record_ids(spatial_split_manifest_path: Path) -> set[str]:
    manifest = load_manifest(spatial_split_manifest_path)
    return {
        row.source_record_id
        for row in manifest.rows
        if row.split is SplitName.TEST and row.source_record_id is not None
    }


def _compute_geo_support(
    records: list[dict[str, Any]], *, model: FCNet, params: EncodingParams, device: torch.device
) -> list[list[float] | None]:
    """One raw per-genus sigmoid score list per record, or ``None`` when the
    frozen configuration needs date features and this record has no usable
    ``observed_at`` - matching this codebase's ``geo_support`` semantics
    (:mod:`s3_ecological.priors.geo_nearest_distance`): ``None`` means "no
    usable evidence", never a substituted zero."""
    result: list[list[float] | None] = [None] * len(records)
    if params.use_date_feats:
        usable_positions = [
            index
            for index, record in enumerate(records)
            if _has_usable_date(record["observed_at"] or "")
        ]
    else:
        usable_positions = list(range(len(records)))
    if not usable_positions:
        return result

    subset = [records[index] for index in usable_positions]
    lon_lat = np.array(
        [[record["longitude"], record["latitude"]] for record in subset], dtype=np.float32
    )
    loc_norm = convert_loc_to_tensor(lon_lat, device=device)
    date_tensor = None
    if params.use_date_feats:
        date_values = np.array(
            [_day_of_year_fraction(record["observed_at"]) for record in subset], dtype=np.float32
        )
        date_tensor = torch.from_numpy(date_values).to(device)
    loc_feat = encode_loc_time(loc_norm, date_tensor, params=params)

    model.eval()
    with torch.inference_mode():
        scores = model(loc_feat).cpu().tolist()
    for position, score in zip(usable_positions, scores, strict=True):
        result[position] = score
    return result


def _metrics_block(
    truth: list[int], predicted: list[int], *, label: str
) -> dict[str, Any]:
    summary = summarize(truth, predicted, class_count=len(CLASS_NAMES))
    accuracy_ci = bootstrap_confidence_interval(
        truth, predicted, class_count=len(CLASS_NAMES),
        metric="accuracy", seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES,
    )
    macro_f1_ci = bootstrap_confidence_interval(
        truth, predicted, class_count=len(CLASS_NAMES),
        metric="macro_f1", seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES,
    )
    return {
        "label": label,
        "observation_count": len(truth),
        "accuracy": summary["accuracy"],
        "accuracy_95ci": list(accuracy_ci),
        "macro_precision": summary["macro_precision"],
        "macro_recall": summary["macro_recall"],
        "macro_f1": summary["macro_f1"],
        "macro_f1_95ci": list(macro_f1_ci),
        "per_genus": [
            {"genus": name, **summary["per_class"][index]}
            for index, name in enumerate(CLASS_NAMES)
        ],
        "confusion_matrix": summary["confusion_matrix"],
        "confusion_matrix_genus_order": list(CLASS_NAMES),
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings = S3Settings()

    manifest = load_manifest(args.spatial_split_manifest)
    test_source_record_ids = _test_source_record_ids(args.spatial_split_manifest)
    try:
        validate_s1_evaluation_bundle(
            manifest_path=args.s1_bundle_manifest,
            expected_authorisation_reference=AUTHORISATION_REFERENCE,
            expected_spatial_split_identity=manifest.split_identity,
            test_source_record_ids=test_source_record_ids,
            settings=settings,
        )
    except S1BundleValidationError as exc:
        raise SystemExit(
            f"S1 bundle failed re-validation against the current spatial split identity: {exc}"
        ) from exc

    bundle = json.loads(args.s1_bundle_manifest.read_text(encoding="utf-8"))
    bundle_dir = args.s1_bundle_manifest.parent
    predictions_path = bundle_dir / bundle["artifacts"]["predictions_file"]
    ground_truth_path = bundle_dir / bundle["artifacts"]["ground_truth_file"]

    predictions = _load_jsonl(predictions_path)
    ground_truth = {row["observation_id"]: row for row in _load_jsonl(ground_truth_path)}
    if set(row["observation_id"] for row in predictions) != set(ground_truth):
        raise SystemExit("prediction and ground-truth observation ids differ after re-validation")

    selected_configuration = json.loads(args.selected_configuration.read_text(encoding="utf-8"))
    frozen_config = selected_configuration["frozen_config"]
    params = EncodingParams(use_date_feats=frozen_config["use_date_feats"])
    checkpoint = torch.load(
        selected_configuration["checkpoint_path"], map_location="cpu", weights_only=True
    )
    checkpoint_sha256 = sha256_file(Path(selected_configuration["checkpoint_path"]))
    if checkpoint_sha256 != selected_configuration["checkpoint_sha256"]:
        raise SystemExit("checkpoint file no longer matches the frozen selected_configuration hash")

    device = torch.device("cpu")
    model = FCNet(
        num_inputs=checkpoint["num_inputs"],
        num_classes=len(CLASS_NAMES),
        num_filts=frozen_config["num_filts"],
    ).to(device)
    model.load_state_dict(checkpoint["state_dict"])

    records = [
        {
            "observation_id": row["observation_id"],
            "latitude": row["location"]["latitude"],
            "longitude": row["location"]["longitude"],
            "observed_at": row.get("observed_at"),
            "visual_candidates": row["visual_candidates"],
        }
        for row in predictions
    ]
    geo_support_by_record = _compute_geo_support(records, model=model, params=params, device=device)

    genus_index = {name: index for index, name in enumerate(CLASS_NAMES)}
    truth_indices: list[int] = []
    s1_only_predicted: list[int] = []
    fusion_predicted: list[int] = []
    geo_only_truth: list[int] = []
    geo_only_predicted: list[int] = []
    excluded_missing_date = 0

    for record, geo_scores in zip(records, geo_support_by_record, strict=True):
        truth_name = ground_truth[record["observation_id"]]["ground_truth_name"]
        truth_index = genus_index[truth_name]
        truth_indices.append(truth_index)

        candidates_in_order = record["visual_candidates"]
        if [candidate["name"] for candidate in candidates_in_order] != list(CLASS_NAMES):
            raise SystemExit(
                f"observation {record['observation_id']} candidate order does not match "
                "the canonical TF4 genus order"
            )

        visual_probabilities = [
            candidate["visual_probability"] for candidate in candidates_in_order
        ]
        s1_only_predicted.append(
            max(range(len(CLASS_NAMES)), key=lambda i: visual_probabilities[i])
        )

        if geo_scores is None:
            excluded_missing_date += 1
        else:
            usable_geo_scores = geo_scores
            geo_only_truth.append(truth_index)
            geo_only_predicted.append(
                max(range(len(CLASS_NAMES)), key=lambda i: usable_geo_scores[i])
            )

        geo_support_values: list[float | None] = (
            [None] * len(CLASS_NAMES) if geo_scores is None else list(geo_scores)
        )

        fusion_candidates = [
            GeoFusionCandidate(
                candidate_id=candidates_in_order[index]["candidate_id"],
                resolved_taxon_id=None,
                visual_probability_raw=visual_probabilities[index],
                geo_support=geo_support_values[index],
            )
            for index in range(len(CLASS_NAMES))
        ]
        outputs = fuse_predictions(
            fusion_candidates,
            fusion_epsilon=settings.fusion_epsilon,
            fusion_weight_geo=settings.fusion_weight_geo,
            fusion_weight_environment=settings.fusion_weight_environment,
        )
        winner_candidate_id = top_candidate_id(fusion_candidates, outputs)
        winner_index = next(
            index
            for index, candidate in enumerate(candidates_in_order)
            if candidate["candidate_id"] == winner_candidate_id
        )
        fusion_predicted.append(winner_index)

    report = {
        "schema_version": "1.0.0",
        "purpose": "M2-C locked spatial-test evaluation: S1-only, geographic-only, fixed-fusion",
        "identity": (
            "Experimental FlyTech S3 Milestone 2-C result; not a production readiness or "
            "biosecurity/biological-efficacy claim"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "authorisation_reference": AUTHORISATION_REFERENCE,
        "spatial_split_identity": manifest.split_identity,
        "observation_count": len(records),
        "genus_order": list(CLASS_NAMES),
        "s1_bundle_manifest_sha256": sha256_file(args.s1_bundle_manifest),
        "geo_prior_frozen_configuration": {
            "config": frozen_config,
            "checkpoint_sha256": checkpoint_sha256,
            "selection_rationale": selected_configuration["selection_rationale"],
            "validation_result": selected_configuration["validation_result"],
        },
        "fusion_constants": {
            "fusion_epsilon": settings.fusion_epsilon,
            "fusion_weight_geo": settings.fusion_weight_geo,
            "fusion_weight_environment": settings.fusion_weight_environment,
        },
        "geo_only_excluded_missing_date": excluded_missing_date,
        "s1_only": _metrics_block(truth_indices, s1_only_predicted, label="s1_only"),
        "geo_only": _metrics_block(geo_only_truth, geo_only_predicted, label="geo_only"),
        "fusion": _metrics_block(truth_indices, fusion_predicted, label="fusion"),
        "limitations": [
            "Small Anastrepha support (31 of 942 test observations) makes its per-genus metrics "
            "high-variance; treat the Anastrepha row in every confusion matrix with caution.",
            "Ground-truth labels are iNaturalist research-grade community identifications, not "
            "expert-verified biosecurity determinations.",
            "The S1 visual classifier is a closed four-genus softmax with no unknown-taxon class.",
            "The geographic prior's spatial scope is a global, label-only training signal (no "
            "environmental or seasonal-range covariates beyond the location/date encoding).",
            "This evaluation is a single locked run on the spatial test split; it is not a "
            "production readiness or biosecurity/biological-efficacy claim.",
        ],
    }
    output_path = args.output_dir
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / "m2c_locked_test_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path)}, sort_keys=True))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spatial-split-manifest",
        type=Path,
        default=Path("data/local/m2/readiness/spatial-split-manifest.json"),
    )
    parser.add_argument(
        "--s1-bundle-manifest",
        type=Path,
        default=Path("data/local/m2/s1/outputs/fold-0/s1_bundle_manifest.json"),
    )
    parser.add_argument(
        "--selected-configuration",
        type=Path,
        default=Path("data/local/m2/geo_prior/training/selected_configuration.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/local/m2/geo_prior/evaluation")
    )
    return parser.parse_args()


def main() -> int:
    evaluate(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
