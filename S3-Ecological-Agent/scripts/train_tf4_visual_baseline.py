"""Train the isolated FlyTech reproduction of the TF4 EfficientNet-B2 baseline.

The resulting model is a temporary external S1 input producer for Milestone 2.
It is not the unavailable checkpoint reported by Shen et al. and it is not an
S3 runtime component.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import EfficientNet_B2_Weights, efficientnet_b2

MODEL_NAME = "efficientnet_b2"
MODEL_VERSION = "flytech-reproduced-tf4-efficientnet-b2-v0.1"
IMAGE_SIZE = 260
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


class ManifestDataset(Dataset[tuple[torch.Tensor, int, dict[str, str]]]):
    def __init__(
        self,
        rows: list[dict[str, str]],
        *,
        root: Path,
        class_names: list[str],
        transform: Callable[[Image.Image], torch.Tensor],
        label_field: str,
    ) -> None:
        self.rows = rows
        self.root = root
        self.class_to_index = {name: index for index, name in enumerate(class_names)}
        self.transform = transform
        self.label_field = label_field

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int, dict[str, str]]:
        row = self.rows[index]
        with Image.open(self.root / row["relative_path"]) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, self.class_to_index[row[self.label_field]], row


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _metrics(truth: list[int], predicted: list[int], class_count: int) -> dict[str, Any]:
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for actual, guess in zip(truth, predicted, strict=True):
        matrix[actual][guess] += 1
    f1_scores: list[float] = []
    recalls: list[float] = []
    precisions: list[float] = []
    for index in range(class_count):
        true_positive = matrix[index][index]
        false_positive = sum(matrix[row][index] for row in range(class_count)) - true_positive
        false_negative = sum(matrix[index]) - true_positive
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
    return {
        "accuracy": sum(matrix[index][index] for index in range(class_count)) / len(truth),
        "macro_precision": sum(precisions) / class_count,
        "macro_recall": sum(recalls) / class_count,
        "macro_f1": sum(f1_scores) / class_count,
        "confusion_matrix": matrix,
    }


def _evaluate(
    model: nn.Module,
    loader: DataLoader[Any],
    loss_function: nn.Module,
    device: torch.device,
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    model.eval()
    loss_sum = 0.0
    truth: list[int] = []
    predicted: list[int] = []
    predictions: list[dict[str, Any]] = []
    with torch.inference_mode():
        for inputs, labels, metadata in loader:
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            logits = model(inputs)
            loss_sum += float(loss_function(logits, labels)) * labels.shape[0]
            probabilities = torch.softmax(logits, dim=1).cpu()
            guesses = probabilities.argmax(dim=1)
            truth.extend(labels.cpu().tolist())
            predicted.extend(guesses.tolist())
            for row_index in range(labels.shape[0]):
                predictions.append(
                    {
                        "observation_id": metadata["observation_id"][row_index],
                        "truth_index": int(labels[row_index].cpu()),
                        "predicted_index": int(guesses[row_index]),
                        "probabilities": probabilities[row_index].tolist(),
                    }
                )
    return loss_sum / len(truth), _metrics(truth, predicted, 4), predictions


def _train_epoch(
    model: nn.Module,
    loader: DataLoader[Any],
    loss_function: nn.Module,
    optimizer: torch.optim.Optimizer,
    scaler: Any,
    device: torch.device,
) -> float:
    model.train()
    loss_sum = 0.0
    sample_count = 0
    use_amp = device.type == "cuda"
    for inputs, labels, _metadata in loader:
        inputs = inputs.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
            logits = model(inputs)
            loss = loss_function(logits, labels)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        loss_sum += float(loss.detach()) * labels.shape[0]
        sample_count += labels.shape[0]
    return loss_sum / sample_count


def _save_validation_predictions(
    path: Path, predictions: list[dict[str, Any]], class_names: list[str]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "observation_id",
            "ground_truth_genus",
            "predicted_genus",
            *[f"probability_{name}" for name in class_names],
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in predictions:
            output = {
                "observation_id": row["observation_id"],
                "ground_truth_genus": class_names[row["truth_index"]],
                "predicted_genus": class_names[row["predicted_index"]],
            }
            output.update(
                {
                    f"probability_{name}": f"{probability:.10f}"
                    for name, probability in zip(class_names, row["probabilities"], strict=True)
                }
            )
            writer.writerow(output)


def train(args: argparse.Namespace) -> dict[str, Any]:
    seed_everything(args.seed)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_csv(args.training_manifest)
    class_names = ["Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis"]
    if {row["genus"] for row in rows} != set(class_names):
        raise ValueError("training manifest must contain exactly the four TF4 genera")
    validation_rows = [row for row in rows if int(row["fold"]) == args.validation_fold]
    training_rows = [row for row in rows if int(row["fold"]) != args.validation_fold]

    training_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    evaluation_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    train_dataset = ManifestDataset(
        training_rows,
        root=args.dataset_root,
        class_names=class_names,
        transform=training_transform,
        label_field="genus",
    )
    validation_dataset = ManifestDataset(
        validation_rows,
        root=args.dataset_root,
        class_names=class_names,
        transform=evaluation_transform,
        label_field="genus",
    )
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
        num_workers=args.workers,
        pin_memory=True,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.require_cuda and device.type != "cuda":
        raise RuntimeError("CUDA is required by this run but is unavailable")
    model = efficientnet_b2(weights=EfficientNet_B2_Weights.IMAGENET1K_V1)
    classifier_head = model.classifier[1]
    if not isinstance(classifier_head, nn.Linear):
        raise TypeError("unexpected EfficientNet classifier head")
    model.classifier[1] = nn.Linear(classifier_head.in_features, len(class_names))
    model.to(device)

    counts = Counter(row["genus"] for row in training_rows)
    class_weights = torch.tensor(
        [len(training_rows) / (len(class_names) * counts[name]) for name in class_names],
        dtype=torch.float32,
        device=device,
    )
    loss_function = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.GradScaler(device.type, enabled=device.type == "cuda")

    best_f1 = -math.inf
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, Any]] = []
    checkpoint_path = output_dir / "tf4_efficientnet_b2_best.pt"
    for epoch in range(1, args.epochs + 1):
        train_loss = _train_epoch(model, train_loader, loss_function, optimizer, scaler, device)
        validation_loss, metrics, _ = _evaluate(model, validation_loader, loss_function, device)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "learning_rate": optimizer.param_groups[0]["lr"],
            **{key: value for key, value in metrics.items() if key != "confusion_matrix"},
        }
        history.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
        if metrics["macro_f1"] > best_f1:
            best_f1 = metrics["macro_f1"]
            best_epoch = epoch
            stale_epochs = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_name": MODEL_NAME,
                    "model_version": MODEL_VERSION,
                    "class_names": class_names,
                    "image_size": IMAGE_SIZE,
                    "normalization_mean": MEAN,
                    "normalization_std": STD,
                    "validation_fold": args.validation_fold,
                    "training_manifest_sha256": sha256_file(args.training_manifest),
                    "epoch": epoch,
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1
        scheduler.step()
        if stale_epochs >= args.patience:
            break

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    validation_loss, validation_metrics, validation_predictions = _evaluate(
        model, validation_loader, loss_function, device
    )
    predictions_path = output_dir / "tf4_internal_validation_predictions.csv"
    _save_validation_predictions(predictions_path, validation_predictions, class_names)
    report = {
        "schema_version": "1.0.0",
        "model_version": MODEL_VERSION,
        "identity": "FlyTech reproduced TF4 baseline; not the original Shen et al. checkpoint",
        "created_at": datetime.now(UTC).isoformat(),
        "authorisation_reference": "owner-approval-m2-2026-09-08",
        "purpose": "non-commercial M2 temporary S1 input production",
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "software": {
            "python_torch": torch.__version__,
            "torchvision": torchvision.__version__,
        },
        "architecture": MODEL_NAME,
        "initialisation": "torchvision EfficientNet_B2 IMAGENET1K_V1",
        "class_names": class_names,
        "image_size": IMAGE_SIZE,
        "normalization": {"mean": MEAN, "std": STD},
        "training": {
            "seed": args.seed,
            "validation_fold": args.validation_fold,
            "training_count": len(training_rows),
            "validation_count": len(validation_rows),
            "batch_size": args.batch_size,
            "maximum_epochs": args.epochs,
            "patience": args.patience,
            "best_epoch": best_epoch,
            "optimizer": "AdamW",
            "learning_rate": args.learning_rate,
            "weight_decay": 1e-4,
            "loss": "class-weighted cross entropy",
            "augmentation": "resize 260x260, horizontal flip p=0.5, mild color jitter",
            "history": history,
        },
        "internal_validation": {"loss": validation_loss, **validation_metrics},
        "artifacts": {
            "training_manifest_sha256": sha256_file(args.training_manifest),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "validation_predictions_sha256": sha256_file(predictions_path),
        },
        "limitations": [
            "Public TF4 materials omit the original checkpoint and full training recipe.",
            "Only the configured fold is held out in this initial reproduction run.",
            "Internal TF4 validation is not the M2 spatial-holdout evaluation.",
            "The closed-set four-genus softmax cannot detect taxa outside TF4.",
        ],
    }
    report_path = output_dir / "tf4_training_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "best_macro_f1": best_f1}, sort_keys=True))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--training-manifest",
        type=Path,
        default=Path("data/local/m2/s1/prepared/tf4_training_manifest.csv"),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/local/m2/s1/tf4/processed_data"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/m2/s1/training/fold-0"))
    parser.add_argument("--validation-fold", type=int, default=0, choices=range(10))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--require-cuda", action="store_true")
    return parser.parse_args()


def main() -> int:
    train(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
