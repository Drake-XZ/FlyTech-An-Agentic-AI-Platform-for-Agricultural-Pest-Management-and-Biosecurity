"""Generate temporary, schema-compatible S1 outputs from the TF4 reproduction.

Predictions and ground truth are deliberately written to separate JSONL files.
The bundle manifest records the closed TF4 label-space semantics and provenance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import efficientnet_b2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EvaluationDataset(Dataset[tuple[torch.Tensor, dict[str, str]]]):
    def __init__(self, rows: list[dict[str, str]], image_root: Path) -> None:
        self.rows = rows
        self.image_root = image_root
        self.transform = transforms.Compose(
            [
                transforms.Resize((260, 260)),
                transforms.ToTensor(),
                transforms.Normalize(
                    (0.485, 0.456, 0.406),
                    (0.229, 0.224, 0.225),
                ),
            ]
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, dict[str, str]]:
        row = self.rows[index]
        with Image.open(self.image_root / row["relative_path"]) as image:
            tensor = self.transform(image.convert("RGB"))
        if not isinstance(tensor, torch.Tensor):
            raise TypeError("image transform did not produce a tensor")
        return tensor, row


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _observed_at(value: str) -> str | None:
    if not value or "T" not in value:
        return None
    return value


def generate(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluation_rows = _read_csv(args.evaluation_manifest)
    crosswalk_payload = json.loads(args.taxonomy_crosswalk.read_text(encoding="utf-8"))
    preparation_report = json.loads(args.preparation_report.read_text(encoding="utf-8"))
    classes = sorted(crosswalk_payload["classes"], key=lambda row: row["class_index"])
    class_names = [row["name"] for row in classes]
    candidate_ids = {row["name"]: row["candidate_id"] for row in classes}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    if checkpoint["class_names"] != class_names:
        raise ValueError("checkpoint class order does not match taxonomy crosswalk")
    model = efficientnet_b2(weights=None)
    head = model.classifier[1]
    if not isinstance(head, nn.Linear):
        raise TypeError("unexpected EfficientNet classifier head")
    model.classifier[1] = nn.Linear(head.in_features, len(class_names))
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()

    dataset = EvaluationDataset(evaluation_rows, args.image_root)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=device.type == "cuda",
    )
    predictions: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    confusion = [[0 for _ in class_names] for _ in class_names]
    class_to_index = {name: index for index, name in enumerate(class_names)}
    with torch.inference_mode():
        for inputs, metadata in loader:
            probabilities = torch.softmax(model(inputs.to(device)), dim=1).cpu()
            for row_index in range(inputs.shape[0]):
                probability_row = probabilities[row_index].tolist()
                request = {
                    "schema_version": "1.0.0",
                    "observation_id": metadata["observation_id"][row_index],
                    "source": "iNaturalist research-grade via GBIF image snapshot",
                    "candidate_set_complete": True,
                    "omitted_probability_mass": 0.0,
                    "observed_at": _observed_at(metadata["event_date"][row_index]),
                    "location": {
                        "latitude": float(metadata["latitude"][row_index]),
                        "longitude": float(metadata["longitude"][row_index]),
                        "coordinate_uncertainty_m": None,
                    },
                    "visual_candidates": [
                        {
                            "candidate_id": candidate_ids[name],
                            "name": name,
                            "rank": "genus",
                            "visual_probability": probability,
                            "model_version": checkpoint["model_version"],
                        }
                        for name, probability in zip(class_names, probability_row, strict=True)
                    ],
                    "context": None,
                    "other_agent_evidence": [],
                }
                truth_name = metadata["ground_truth_genus"][row_index]
                truth_index = class_to_index[truth_name]
                predicted_index = int(probabilities[row_index].argmax())
                confusion[truth_index][predicted_index] += 1
                predictions.append(request)
                labels.append(
                    {
                        "schema_version": "1.0.0",
                        "observation_id": request["observation_id"],
                        "ground_truth_candidate_id": candidate_ids[truth_name],
                        "ground_truth_name": truth_name,
                        "ground_truth_rank": "genus",
                        "label_source": "iNaturalist research-grade identification",
                        "spatial_split": "test",
                        "spatial_split_identity": preparation_report["evaluation"][
                            "spatial_split_identity"
                        ],
                        "image_sha256": metadata["sha256"][row_index],
                        "media_license": metadata["media_license"][row_index],
                    }
                )

    shutil.copyfile(args.evaluation_manifest, output_dir / "s1_evaluation_manifest.csv")
    shutil.copyfile(args.taxonomy_crosswalk, output_dir / "tf4_taxonomy_crosswalk.json")
    shutil.copyfile(args.preparation_report, output_dir / "tf4_s1_preparation_report.json")
    predictions_path = output_dir / "s1_predictions.jsonl"
    labels_path = output_dir / "s1_ground_truth.jsonl"
    _write_jsonl(predictions_path, predictions)
    _write_jsonl(labels_path, labels)
    correct = sum(confusion[index][index] for index in range(len(class_names)))
    total = sum(sum(row) for row in confusion)
    per_class_f1: dict[str, float] = {}
    for index, name in enumerate(class_names):
        true_positive = confusion[index][index]
        false_positive = sum(row[index] for row in confusion) - true_positive
        false_negative = sum(confusion[index]) - true_positive
        denominator = 2 * true_positive + false_positive + false_negative
        per_class_f1[name] = 2 * true_positive / denominator if denominator else 0.0

    counts = Counter(row["ground_truth_genus"] for row in evaluation_rows)
    bundle = {
        "schema_version": "1.0.0",
        "bundle_id": "m2-temporary-s1-tf4-reproduction-v0.1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "available_authorised",
        "authorisation": {
            "reference": "owner-approval-m2-2026-09-08",
            "purpose": (
                "FlyTech S3 Milestone 2 temporary visual baseline and spatial-holdout evaluation"
            ),
            "approving_role": "project owner",
        },
        "producer": {
            "type": "isolated_research_visual_baseline",
            "model_version": checkpoint["model_version"],
            "identity": "FlyTech reproduced TF4 baseline; not the original paper checkpoint",
            "checkpoint_sha256": sha256_file(args.checkpoint),
        },
        "candidate_semantics": {
            "rank": "genus",
            "label_space": class_names,
            "candidate_set_complete": True,
            "probabilities": "raw closed-set softmax over the four TF4 genera",
            "unknown_class_supported": False,
            "warning": "complete only within TF4; not complete over all possible taxa",
        },
        "evaluation_scope": {
            "spatial_split": "test",
            "spatial_split_identity": preparation_report["evaluation"]["spatial_split_identity"],
            "observation_count": len(predictions),
            "counts_by_genus": {name: counts[name] for name in class_names},
            "one_image_per_observation": True,
            "tf4_training_observation_overlap": 0,
            "tf4_sha256_overlap": 0,
            "tf4_dhash_distance_limit": 5,
            "no_derivatives_images": 0,
        },
        "artifacts": {
            "predictions_file": predictions_path.name,
            "predictions_sha256": sha256_file(predictions_path),
            "ground_truth_file": labels_path.name,
            "ground_truth_sha256": sha256_file(labels_path),
            "evaluation_manifest_file": "s1_evaluation_manifest.csv",
            "evaluation_manifest_sha256": sha256_file(args.evaluation_manifest),
            "taxonomy_crosswalk_file": "tf4_taxonomy_crosswalk.json",
            "taxonomy_crosswalk_sha256": sha256_file(args.taxonomy_crosswalk),
            "preparation_report_file": "tf4_s1_preparation_report.json",
            "preparation_report_sha256": sha256_file(args.preparation_report),
        },
        "s1_only_diagnostic": {
            "accuracy": correct / total,
            "macro_f1": sum(per_class_f1.values()) / len(class_names),
            "per_class_f1": per_class_f1,
            "confusion_matrix": confusion,
            "not_final_m2_result": True,
        },
        "limitations": [
            "This closed-set baseline cannot detect taxa outside the four TF4 genera.",
            "Ground truth is iNaturalist research-grade, not expert re-identification for FlyTech.",
            "The Anastrepha spatial-test subset is small and class counts are imbalanced.",
            "This bundle must pass the S3 S1-bundle validator before readiness can be unblocked.",
        ],
    }
    bundle_path = output_dir / "s1_bundle_manifest.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/local/m2/s1/training/fold-0/tf4_efficientnet_b2_best.pt"),
    )
    parser.add_argument(
        "--evaluation-manifest",
        type=Path,
        default=Path("data/local/m2/s1/prepared/s1_evaluation_manifest.csv"),
    )
    parser.add_argument(
        "--taxonomy-crosswalk",
        type=Path,
        default=Path("data/local/m2/s1/prepared/tf4_taxonomy_crosswalk.json"),
    )
    parser.add_argument(
        "--preparation-report",
        type=Path,
        default=Path("data/local/m2/s1/prepared/tf4_s1_preparation_report.json"),
    )
    parser.add_argument("--image-root", type=Path, default=Path("data/external/m2"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/m2/s1/outputs/fold-0"))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    generate(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
