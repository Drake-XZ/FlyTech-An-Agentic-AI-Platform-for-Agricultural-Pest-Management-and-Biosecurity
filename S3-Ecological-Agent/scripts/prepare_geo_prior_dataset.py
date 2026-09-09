"""Prepare train/validation CSV manifests for M2-C geographic-prior training.

Torch-free CLI wrapper around
``s3_ecological.experiments.geo_prior_dataset``. Run via the **main** venv
(this script never imports torch). It writes only derived, non-sensitive CSV
manifests and a JSON report under gitignored ``data/local/``; it performs no
spatial-splitting logic of its own - the split is authoritative from the
already-computed spatial split manifest.

This is an isolated research utility. It does not modify the S1 bundle, the
S3 fusion runtime, or any Profile v0.1 setting.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from s3_ecological.experiments.geo_prior_dataset import (
    GeoPriorDatasetRecord,
    load_manifest,
    load_occurrence_snapshot,
    load_taxonomy_snapshot,
    load_train_records,
    load_validation_records,
)

CSV_FIELDS = [
    "source",
    "source_record_id",
    "taxon_id",
    "genus",
    "latitude",
    "longitude",
    "event_date",
]


def _write_csv(path: Path, records: list[GeoPriorDatasetRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "source": record.source,
                    "source_record_id": record.source_record_id,
                    "taxon_id": record.taxon_id,
                    "genus": record.genus,
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "event_date": record.event_date or "",
                }
            )


def _counts_by_genus(records: list[GeoPriorDatasetRecord]) -> dict[str, int]:
    return dict(sorted(Counter(record.genus for record in records).items()))


def _undated_count(records: list[GeoPriorDatasetRecord]) -> int:
    return sum(1 for record in records if not record.event_date)


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(args.spatial_split_manifest)
    occurrence_snapshot = load_occurrence_snapshot(args.occurrence_snapshot, manifest=manifest)
    taxonomy_snapshot = load_taxonomy_snapshot(args.taxonomy_snapshot, manifest=manifest)

    train_records = load_train_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
    )
    validation_records = load_validation_records(
        manifest=manifest,
        occurrence_snapshot=occurrence_snapshot,
        taxonomy_snapshot=taxonomy_snapshot,
    )

    train_manifest_path = output_dir / "train_manifest.csv"
    validation_manifest_path = output_dir / "validation_manifest.csv"
    _write_csv(train_manifest_path, train_records)
    _write_csv(validation_manifest_path, validation_records)

    report_path = output_dir / "dataset_report.json"
    report = {
        "schema_version": "1.0.0",
        "purpose": "M2-C geographic-prior train/validation dataset preparation",
        "spatial_split_identity": manifest.split_identity,
        "spatial_split_manifest_sha256": _sha256_of(args.spatial_split_manifest),
        "occurrence_snapshot_sha256": manifest.occurrence_snapshot.file_sha256,
        "taxonomy_snapshot_sha256": manifest.taxonomy_snapshot.file_sha256,
        "train": {
            "count": len(train_records),
            "counts_by_genus": _counts_by_genus(train_records),
            "undated_record_count": _undated_count(train_records),
            "manifest_sha256": _sha256_of(train_manifest_path),
        },
        "validation": {
            "count": len(validation_records),
            "counts_by_genus": _counts_by_genus(validation_records),
            "undated_record_count": _undated_count(validation_records),
            "manifest_sha256": _sha256_of(validation_manifest_path),
        },
        "limitations": [
            "The locked spatial test split is intentionally never read by this script - it is "
            "read only by scripts/evaluate_geo_prior_m2c.py, directly from the S1 bundle's own "
            "prediction rows.",
            "A date-aware training configuration must additionally filter to records with a "
            "non-empty event_date; this report's undated_record_count tells the caller how many "
            "records that filter would exclude from each split.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spatial-split-manifest",
        type=Path,
        default=Path("data/local/m2/readiness/spatial-split-manifest.json"),
    )
    parser.add_argument(
        "--occurrence-snapshot",
        type=Path,
        default=Path("data/local/m2/bundle/occurrences.json"),
    )
    parser.add_argument(
        "--taxonomy-snapshot",
        type=Path,
        default=Path("data/local/m2/bundle/taxonomy.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/local/m2/geo_prior/dataset")
    )
    return parser.parse_args()


def main() -> int:
    report = prepare(parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
