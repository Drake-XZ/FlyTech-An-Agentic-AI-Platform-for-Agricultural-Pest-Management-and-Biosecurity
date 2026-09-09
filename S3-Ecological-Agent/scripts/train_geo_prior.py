"""Train the FlyTech reproduction of the `geo_prior` presence-only
geographic prior over a small, pre-declared configuration grid, fitting
every candidate on the spatial ``train`` split only and selecting exactly one
frozen configuration using the spatial ``validation`` split's genus macro-F1
only.

The resulting model is an independent reproduction for FlyTech S3 Milestone
2-C. It is not a release of Mac Aodha, Cole & Perona's original `geo_prior`
checkpoint (none is published - see
``research/third_party/geo_prior/FlyTech_VENDORING.md``) and it is not an S3
runtime component. Consumes the CSV manifests written by
``scripts/prepare_geo_prior_dataset.py``; never reads the locked spatial
``test`` split.

Torch-only: run via ``data/local/m2/s1/venv/Scripts/python.exe``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from geo_prior_model import (
    BalancedSampler,
    EncodingParams,
    FCNet,
    convert_loc_to_tensor,
    embedding_loss,
    encode_loc_time,
    num_input_feats,
    seed_everything,
)
from s3_ecological.experiments.geo_prior_metrics import accuracy, confusion_matrix, macro_f1

MODEL_NAME = "geo_prior_fcnet"
MODEL_VERSION = "flytech-reproduced-geo-prior-fcnet-v0.1"
UPSTREAM_REPOSITORY = "https://github.com/macaodha/geo_prior"
UPSTREAM_COMMIT = "257dc7e30f3cc6bf02fbec55ee878724d077fe61"
CLASS_NAMES = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")

CONFIG_GRID: list[dict[str, Any]] = [
    {"num_filts": 64, "use_date_feats": False},
    {"num_filts": 64, "use_date_feats": True},
    {"num_filts": 256, "use_date_feats": False},
    {"num_filts": 256, "use_date_feats": True},
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _config_id(config: dict[str, Any]) -> str:
    return f"filts{config['num_filts']}_date{config['use_date_feats']}"


def _day_of_year_fraction(event_date: str) -> float:
    """Normalises a ``YYYY-MM-DD``-prefixed date string to ``[-1, 1]`` via
    its fraction of a 365-day year. This project's occurrence records carry
    no other calendar convention, so this fixed 365-day denominator (rather
    than a per-year leap-aware count) is a documented, deliberate
    simplification - it is not part of the vendored upstream code, which
    leaves the date-encoding convention to the caller's dataset loader."""
    parsed = datetime.strptime(event_date[:10], "%Y-%m-%d")
    day_of_year = parsed.timetuple().tm_yday
    return (day_of_year / 365.0) * 2.0 - 1.0


def _has_usable_date(event_date: str) -> bool:
    """True only for a full ``YYYY-MM-DD``-prefixed date. Some real GBIF/ALA
    records carry a year-only or year-month event_date (e.g. ``"2013"``,
    ``"2013-04"``) - these cannot yield a day-of-year and are treated the
    same as a missing date for date-aware configs."""
    if not event_date:
        return False
    try:
        datetime.strptime(event_date[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _filter_dated(
    records: list[dict[str, str]], *, require_event_date: bool
) -> list[dict[str, str]]:
    if not require_event_date:
        return records
    return [record for record in records if _has_usable_date(record["event_date"])]


def _encode(
    records: list[dict[str, str]], *, params: EncodingParams, device: torch.device
) -> tuple[torch.Tensor, torch.Tensor]:
    lon_lat = np.array(
        [[float(record["longitude"]), float(record["latitude"])] for record in records],
        dtype=np.float32,
    )
    loc_norm = convert_loc_to_tensor(lon_lat, device=device)
    date_tensor = None
    if params.use_date_feats:
        date_values = np.array(
            [_day_of_year_fraction(record["event_date"]) for record in records], dtype=np.float32
        )
        date_tensor = torch.from_numpy(date_values).to(device)
    loc_feat = encode_loc_time(loc_norm, date_tensor, params=params)
    class_index = {name: index for index, name in enumerate(CLASS_NAMES)}
    loc_class = torch.tensor(
        [class_index[record["genus"]] for record in records], dtype=torch.long, device=device
    )
    return loc_feat, loc_class


def _train_one_config(
    config: dict[str, Any],
    *,
    train_records: list[dict[str, str]],
    validation_records: list[dict[str, str]],
    args: argparse.Namespace,
    device: torch.device,
    output_dir: Path,
) -> dict[str, Any]:
    seed_everything(args.seed)
    params = EncodingParams(use_date_feats=config["use_date_feats"])

    require_event_date = config["use_date_feats"]
    scoped_train = _filter_dated(train_records, require_event_date=require_event_date)
    scoped_validation = _filter_dated(validation_records, require_event_date=require_event_date)

    loc_feat_train, loc_class_train = _encode(scoped_train, params=params, device=device)
    loc_feat_validation, loc_class_validation = _encode(
        scoped_validation, params=params, device=device
    )

    model = FCNet(
        num_inputs=num_input_feats(params),
        num_classes=len(CLASS_NAMES),
        num_filts=config["num_filts"],
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=args.lr_decay)

    sampler = BalancedSampler(
        [int(label) for label in loc_class_train.cpu().tolist()],
        args.max_per_class,
        rng=random.Random(args.seed),
    )

    best_macro_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, Any]] = []
    config_dir = output_dir / _config_id(config)
    config_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config_dir / "checkpoint.pt"

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_indices = sampler.sample_epoch()
        loss_sum = 0.0
        batch_count = 0
        for start in range(0, len(epoch_indices), args.batch_size):
            batch_positions = torch.tensor(
                epoch_indices[start : start + args.batch_size], dtype=torch.long, device=device
            )
            optimizer.zero_grad(set_to_none=True)
            loss = embedding_loss(
                model,
                loc_feat=loc_feat_train[batch_positions],
                loc_class=loc_class_train[batch_positions],
                num_classes=len(CLASS_NAMES),
                device=device,
                params=params,
            )
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach())
            batch_count += 1
        scheduler.step()

        model.eval()
        with torch.inference_mode():
            validation_scores = model(loc_feat_validation)
        validation_predicted = validation_scores.argmax(dim=1).cpu().tolist()
        validation_truth = loc_class_validation.cpu().tolist()
        matrix = confusion_matrix(
            validation_truth, validation_predicted, class_count=len(CLASS_NAMES)
        )
        validation_macro_f1 = macro_f1(matrix)
        validation_accuracy = accuracy(validation_truth, validation_predicted)

        row = {
            "epoch": epoch,
            "train_loss": loss_sum / batch_count,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "validation_accuracy": validation_accuracy,
            "validation_macro_f1": validation_macro_f1,
        }
        history.append(row)
        print(json.dumps({"config": _config_id(config), **row}, sort_keys=True), flush=True)

        if validation_macro_f1 > best_macro_f1:
            best_macro_f1 = validation_macro_f1
            best_epoch = epoch
            stale_epochs = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_name": MODEL_NAME,
                    "model_version": MODEL_VERSION,
                    "config": config,
                    "num_inputs": num_input_feats(params),
                    "class_names": list(CLASS_NAMES),
                    "epoch": epoch,
                    "seed": args.seed,
                    "validation_macro_f1": validation_macro_f1,
                    "validation_accuracy": validation_accuracy,
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1
        if stale_epochs >= args.patience:
            break

    return {
        "config": config,
        "config_id": _config_id(config),
        "train_count": len(scoped_train),
        "validation_count": len(scoped_validation),
        "train_count_excluded_undated": len(train_records) - len(scoped_train),
        "validation_count_excluded_undated": len(validation_records) - len(scoped_validation),
        "best_epoch": best_epoch,
        "epochs_run": len(history),
        "best_validation_macro_f1": best_macro_f1,
        "best_validation_accuracy": history[best_epoch - 1]["validation_accuracy"],
        "history": history,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
    }


def _select_winner(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Selection rule (fixed, applied only to validation-set genus macro-F1):
    highest ``best_validation_macro_f1``; ties broken by smaller
    ``num_filts``, then by preferring the date-feature-free config -
    i.e. by preferring the structurally simpler candidate."""

    def sort_key(candidate: dict[str, Any]) -> tuple[float, int, bool]:
        return (
            -candidate["best_validation_macro_f1"],
            candidate["config"]["num_filts"],
            candidate["config"]["use_date_feats"],
        )

    return sorted(candidates, key=sort_key)[0]


def train(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.force_cpu else "cpu")

    train_records = _read_csv(args.train_manifest)
    validation_records = _read_csv(args.validation_manifest)
    if {record["genus"] for record in train_records} - set(CLASS_NAMES):
        raise ValueError(
            "train manifest contains a genus outside the frozen four-class label space"
        )

    dataset_report: dict[str, Any] | None = None
    if args.dataset_report is not None and args.dataset_report.exists():
        dataset_report = json.loads(args.dataset_report.read_text(encoding="utf-8"))

    only_config_id = getattr(args, "only_config_id", None)
    if only_config_id is None:
        config_grid = CONFIG_GRID
    else:
        config_grid = [config for config in CONFIG_GRID if _config_id(config) == only_config_id]
        if not config_grid:
            raise ValueError(
                f"--only-config-id {only_config_id!r} does not match any entry in CONFIG_GRID "
                f"(known ids: {[_config_id(config) for config in CONFIG_GRID]})"
            )

    candidates = [
        _train_one_config(
            config,
            train_records=train_records,
            validation_records=validation_records,
            args=args,
            device=device,
            output_dir=output_dir,
        )
        for config in config_grid
    ]
    winner = _select_winner(candidates)

    candidate_table_path = output_dir / "candidate_table.json"
    candidate_table = {
        "schema_version": "1.0.0",
        "purpose": "M2-C geographic-prior validation-set configuration selection",
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "environment": {
            "torch": torch.__version__,
            "numpy": np.__version__,
            "device": str(device),
            "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        },
        "seed": args.seed,
        "train_manifest_sha256": sha256_file(args.train_manifest),
        "validation_manifest_sha256": sha256_file(args.validation_manifest),
        "dataset_report": dataset_report,
        "selection_rule": (
            "highest best_validation_macro_f1 (genus macro-F1 on the spatial validation split "
            "only); ties broken by smaller num_filts, then by preferring use_date_feats=False"
        ),
        "candidates": candidates,
        "selected_config_id": winner["config_id"],
    }
    candidate_table_path.write_text(
        json.dumps(candidate_table, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    selected_configuration_path = output_dir / "selected_configuration.json"
    selected_configuration = {
        "schema_version": "1.0.0",
        "identity": (
            "FlyTech reproduced geo_prior FCNet; not the original Mac Aodha et al. checkpoint "
            "(none is published upstream)"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "frozen_config": winner["config"],
        "frozen_config_id": winner["config_id"],
        "checkpoint_path": winner["checkpoint_path"],
        "checkpoint_sha256": winner["checkpoint_sha256"],
        "selection_rationale": candidate_table["selection_rule"],
        "validation_result": {
            "best_epoch": winner["best_epoch"],
            "best_validation_macro_f1": winner["best_validation_macro_f1"],
            "best_validation_accuracy": winner["best_validation_accuracy"],
            "train_count": winner["train_count"],
            "validation_count": winner["validation_count"],
        },
        "seed": args.seed,
        "train_manifest_sha256": candidate_table["train_manifest_sha256"],
        "validation_manifest_sha256": candidate_table["validation_manifest_sha256"],
        "spatial_split_identity": (dataset_report or {}).get("spatial_split_identity"),
    }
    selected_configuration_path.write_text(
        json.dumps(selected_configuration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "candidate_table": str(candidate_table_path),
                "selected_configuration": str(selected_configuration_path),
                "selected_config_id": winner["config_id"],
                "best_validation_macro_f1": winner["best_validation_macro_f1"],
            },
            sort_keys=True,
        )
    )
    return selected_configuration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-manifest",
        type=Path,
        default=Path("data/local/m2/geo_prior/dataset/train_manifest.csv"),
    )
    parser.add_argument(
        "--validation-manifest",
        type=Path,
        default=Path("data/local/m2/geo_prior/dataset/validation_manifest.csv"),
    )
    parser.add_argument(
        "--dataset-report",
        type=Path,
        default=Path("data/local/m2/geo_prior/dataset/dataset_report.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/m2/geo_prior/training"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--max-per-class", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--lr-decay", type=float, default=0.98)
    parser.add_argument("--force-cpu", action="store_true")
    parser.add_argument(
        "--only-config-id",
        type=str,
        default=None,
        help=(
            "Restrict training to a single CONFIG_GRID entry by its config_id "
            "(e.g. filts256_dateTrue), instead of the full 4-config grid search. "
            "Used by the M2-D robustness audit to fit the already-selected frozen "
            "recipe on a new spatial partition without repeating hyperparameter search."
        ),
    )
    return parser.parse_args()


def main() -> int:
    train(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
