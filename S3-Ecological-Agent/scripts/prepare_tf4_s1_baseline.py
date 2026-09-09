"""Prepare leakage-audited manifests for the temporary TF4 visual baseline.

This is an isolated research utility.  It does not implement S1 inside the S3
runtime; it prepares inputs for a separately trained visual model whose output
may later be validated at the existing S1-to-S3 boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

TF4_CLASSES = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")
PROFILE_VERSION = "tf4-s1-preparation-v0.1"
FOLD_COUNT = 10
FOLD_SEED = 42
PERCEPTUAL_DISTANCE_LIMIT = 5
OBSERVATION_ID_PATTERN = re.compile(r"inaturalist\.org/observations/(\d+)", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def difference_hash(path: Path) -> int:
    """Return a deterministic 64-bit dHash for duplicate screening."""
    with Image.open(path) as image:
        resized = ImageOps.grayscale(image).resize((9, 8))
        pixels = list(resized.tobytes())
    value = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return value


def observation_id(value: str) -> str | None:
    match = OBSERVATION_ID_PATTERN.search(value)
    return match.group(1) if match else None


def is_no_derivatives_license(value: str) -> bool:
    normalised = value.lower().rstrip("/")
    return normalised.endswith("-nd") or "-nd/" in normalised or "/nd/" in normalised


def stable_fold(genus: str, item_id: str, index: int) -> int:
    """Assign balanced folds after deterministic within-class hash sorting."""
    del genus, item_id
    return index % FOLD_COUNT


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _load_taxonomy_crosswalk(path: Path) -> tuple[dict[str, str], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches: dict[str, list[dict[str, Any]]] = {name: [] for name in TF4_CLASSES}
    for taxon in payload.get("taxa", []):
        scientific_name = taxon.get("scientific_name")
        if scientific_name in matches and taxon.get("rank") == "genus":
            matches[scientific_name].append(taxon)

    crosswalk: dict[str, str] = {}
    for genus, entries in matches.items():
        if len(entries) != 1 or entries[0].get("ambiguous"):
            raise ValueError(
                f"expected one unambiguous genus entry for {genus}, found {len(entries)}"
            )
        identifiers = entries[0].get("taxon_ids", {})
        if not identifiers:
            raise ValueError(f"taxonomy entry for {genus} has no stable identifier")
        crosswalk[genus] = identifiers[sorted(identifiers)[0]]
    return crosswalk, sha256_file(path)


def _prepare_training_rows(tf4_root: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_class: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for genus in TF4_CLASSES:
        class_dir = tf4_root / genus
        if not class_dir.is_dir():
            raise ValueError(f"missing TF4 class directory: {class_dir}")
        records: list[dict[str, Any]] = []
        for image_path in sorted(class_dir.glob("*.jpg"), key=lambda item: item.name):
            item_id = image_path.stem
            if not item_id.isdigit():
                raise ValueError(f"TF4 filename is not an iNaturalist observation id: {image_path}")
            if item_id in seen_ids:
                raise ValueError(f"duplicate TF4 observation id: {item_id}")
            seen_ids.add(item_id)
            image_sha = sha256_file(image_path)
            records.append(
                {
                    "observation_id": item_id,
                    "genus": genus,
                    "relative_path": image_path.relative_to(tf4_root.parent).as_posix(),
                    "bytes": image_path.stat().st_size,
                    "sha256": image_sha,
                    "dhash64": f"{difference_hash(image_path):016x}",
                    "sort_key": hashlib.sha256(
                        f"{FOLD_SEED}:{genus}:{item_id}:{image_sha}".encode()
                    ).hexdigest(),
                }
            )
        if not records:
            raise ValueError(f"TF4 class contains no JPG images: {class_dir}")
        by_class[genus] = sorted(records, key=lambda row: row["sort_key"])

    output: list[dict[str, Any]] = []
    for genus in TF4_CLASSES:
        for index, row in enumerate(by_class[genus]):
            row = dict(row)
            row.pop("sort_key")
            row["fold"] = stable_fold(genus, row["observation_id"], index)
            output.append(row)
    output.sort(key=lambda row: (row["genus"], row["observation_id"]))
    return output, {genus: len(by_class[genus]) for genus in TF4_CLASSES}


def _test_observation_ids(spatial_manifest: Path) -> tuple[set[str], str, str]:
    payload = json.loads(spatial_manifest.read_text(encoding="utf-8"))
    result: set[str] = set()
    for row in payload.get("rows", []):
        if row.get("split") != "test":
            continue
        item_id = observation_id(row.get("source_record_id") or "")
        if item_id:
            result.add(item_id)
    return result, payload.get("split_identity", ""), sha256_file(spatial_manifest)


def _minimum_distance(value: int, reference_hashes: list[int]) -> int:
    return min((value ^ reference).bit_count() for reference in reference_hashes)


def _prepare_evaluation_rows(
    *,
    image_index: Path,
    test_ids: set[str],
    training_rows: list[dict[str, Any]],
    crosswalk: dict[str, str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    training_ids = {row["observation_id"] for row in training_rows}
    training_shas = {row["sha256"] for row in training_rows}
    training_hashes = [int(row["dhash64"], 16) for row in training_rows]
    image_root = image_index.parent.parent
    exclusions: Counter[str] = Counter()
    chosen: dict[str, dict[str, Any]] = {}

    with image_index.open(encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            item_id = observation_id(source.get("occurrence_id", ""))
            if not item_id or item_id not in test_ids:
                continue
            if item_id in training_ids:
                exclusions["tf4_observation_id_overlap"] += 1
                continue
            if is_no_derivatives_license(source.get("media_license", "")):
                exclusions["no_derivatives_license"] += 1
                continue
            genus_by_casefold = {name.casefold(): name for name in TF4_CLASSES}
            genus = genus_by_casefold.get(source.get("genus", "").casefold())
            if genus is None:
                exclusions["outside_tf4_label_space"] += 1
                continue
            source["genus"] = genus
            current = chosen.get(item_id)
            if current is None or source.get("photo_id", "") < current.get("photo_id", ""):
                if current is not None:
                    exclusions["additional_image_same_observation"] += 1
                chosen[item_id] = source
            else:
                exclusions["additional_image_same_observation"] += 1

    output: list[dict[str, Any]] = []
    for item_id, source in sorted(chosen.items()):
        image_path = image_root / source["local_path"]
        if not image_path.is_file():
            exclusions["missing_local_image"] += 1
            continue
        actual_sha = sha256_file(image_path)
        if source.get("sha256") and actual_sha != source["sha256"]:
            raise ValueError(f"image index SHA-256 mismatch: {image_path}")
        if actual_sha in training_shas:
            exclusions["exact_image_sha256_overlap"] += 1
            continue
        image_dhash = difference_hash(image_path)
        distance = _minimum_distance(image_dhash, training_hashes)
        if distance <= PERCEPTUAL_DISTANCE_LIMIT:
            exclusions["perceptual_near_duplicate"] += 1
            continue
        genus = source["genus"]
        output.append(
            {
                "observation_id": item_id,
                "photo_id": source["photo_id"],
                "candidate_id": crosswalk[genus],
                "ground_truth_genus": genus,
                "scientific_name": source["scientific_name"],
                "event_date": source["event_date"],
                "latitude": source["latitude"],
                "longitude": source["longitude"],
                "relative_path": source["local_path"],
                "media_license": source["media_license"],
                "sha256": actual_sha,
                "dhash64": f"{image_dhash:016x}",
                "minimum_tf4_dhash_distance": distance,
                "spatial_split": "test",
            }
        )
    return output, exclusions


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    training_rows, training_counts = _prepare_training_rows(args.tf4_root)
    crosswalk, taxonomy_sha = _load_taxonomy_crosswalk(args.taxonomy_snapshot)
    test_ids, split_identity, split_sha = _test_observation_ids(args.spatial_split_manifest)
    evaluation_rows, exclusions = _prepare_evaluation_rows(
        image_index=args.image_index,
        test_ids=test_ids,
        training_rows=training_rows,
        crosswalk=crosswalk,
    )

    training_manifest = output_dir / "tf4_training_manifest.csv"
    evaluation_manifest = output_dir / "s1_evaluation_manifest.csv"
    crosswalk_path = output_dir / "tf4_taxonomy_crosswalk.json"
    report_path = output_dir / "tf4_s1_preparation_report.json"
    _write_csv(
        training_manifest,
        ["observation_id", "genus", "relative_path", "bytes", "sha256", "dhash64", "fold"],
        training_rows,
    )
    _write_csv(
        evaluation_manifest,
        [
            "observation_id",
            "photo_id",
            "candidate_id",
            "ground_truth_genus",
            "scientific_name",
            "event_date",
            "latitude",
            "longitude",
            "relative_path",
            "media_license",
            "sha256",
            "dhash64",
            "minimum_tf4_dhash_distance",
            "spatial_split",
        ],
        evaluation_rows,
    )
    crosswalk_payload = {
        "schema_version": "1.0.0",
        "taxonomy_snapshot_sha256": taxonomy_sha,
        "rank": "genus",
        "classes": [
            {"class_index": index, "name": genus, "candidate_id": crosswalk[genus]}
            for index, genus in enumerate(TF4_CLASSES)
        ],
    }
    crosswalk_path.write_text(
        json.dumps(crosswalk_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evaluation_counts = Counter(row["ground_truth_genus"] for row in evaluation_rows)
    report = {
        "schema_version": "1.0.0",
        "profile_version": PROFILE_VERSION,
        "purpose": "temporary non-commercial M2 S1-input baseline preparation",
        "tf4_source": {
            "url": "https://drive.google.com/file/d/129XoNQFvoBGZ3Oor07dedT_MZnNuAdgf/view",
            "archive_sha256": sha256_file(args.tf4_archive),
            "archive_bytes": args.tf4_archive.stat().st_size,
            "upstream_repository": "https://github.com/Dukeshen1/Tephritid-Recognition",
            "upstream_commit": "99b0198e711d68fbc64214865183b23ea374c042",
        },
        "training": {
            "count": len(training_rows),
            "counts_by_genus": training_counts,
            "fold_count": FOLD_COUNT,
            "fold_seed": FOLD_SEED,
            "manifest_sha256": sha256_file(training_manifest),
        },
        "evaluation": {
            "count": len(evaluation_rows),
            "counts_by_genus": {genus: evaluation_counts[genus] for genus in TF4_CLASSES},
            "source_test_observation_count": len(test_ids),
            "spatial_split_identity": split_identity,
            "spatial_split_manifest_sha256": split_sha,
            "image_index_sha256": sha256_file(args.image_index),
            "manifest_sha256": sha256_file(evaluation_manifest),
        },
        "leakage_controls": {
            "one_image_per_observation": True,
            "excluded_if_tf4_observation_id_matches": True,
            "excluded_if_sha256_matches": True,
            "perceptual_hash": "64-bit difference hash over 9x8 grayscale resize",
            "excluded_if_dhash_hamming_distance_at_most": PERCEPTUAL_DISTANCE_LIMIT,
            "excluded_no_derivatives_media": True,
            "exclusions": dict(sorted(exclusions.items())),
        },
        "taxonomy_crosswalk_sha256": sha256_file(crosswalk_path),
        "authorisation_reference": "owner-approval-m2-2026-09-08",
        "limitations": [
            "TF4.zip contains no evaluation images despite its empty test directories.",
            "The public repository does not contain the original trained checkpoint.",
            "This preparation does not itself validate or authorise model predictions.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tf4-root",
        type=Path,
        default=Path("data/local/m2/s1/tf4/processed_data/train"),
    )
    parser.add_argument("--tf4-archive", type=Path, default=Path("data/local/m2/s1/source/TF4.zip"))
    parser.add_argument(
        "--image-index", type=Path, default=Path("data/external/m2/inaturalist/image_index.csv")
    )
    parser.add_argument(
        "--spatial-split-manifest",
        type=Path,
        default=Path("data/local/m2/readiness/spatial-split-manifest.json"),
    )
    parser.add_argument(
        "--taxonomy-snapshot",
        type=Path,
        default=Path("data/local/m2/bundle/taxonomy.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/local/m2/s1/prepared"))
    return parser.parse_args()


def main() -> int:
    report = prepare(parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
