"""Download the bounded public-data subset used to prepare Milestone 2.

This research utility is not reachable from the S3 runtime. It keeps source
records and media licences alongside downloads and can resume image downloads.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GBIF_API = "https://api.gbif.org/v1/occurrence/search"
ALA_API = "https://biocache-ws.ala.org.au/ws/occurrences/search"
INAT_DATASET_KEY = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
TAXA = {
    "Anastrepha": 1624988,
    "Bactrocera": 1626510,
    "Ceratitis": 8776023,
    "Rhagoletis": 1622544,
}
USER_AGENT = "FlyTech-S3-M2-resource-preparation/0.1"


def request_json(url: str, attempts: int = 5) -> dict[str, Any]:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def download_pages(
    *,
    url: str,
    params: dict[str, str],
    page_size: int,
    records_key: str,
    total_key: str,
    offset_key: str,
    limit_key: str,
    destination: Path,
    max_records: int | None = None,
    page_workers: int = 16,
) -> dict[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".jsonl.partial")
    first_params = {**params, offset_key: "0", limit_key: str(page_size)}
    first_payload = request_json(f"{url}?{urllib.parse.urlencode(first_params)}")
    total = int(first_payload[total_key])
    if destination.exists():
        with destination.open(encoding="utf-8") as existing:
            count = sum(1 for _ in existing)
        print(f"  {destination.stem}: cached {count:,}/{total:,}", flush=True)
        return {"downloaded": count, "source_total": total}
    download_total = min(total, max_records) if max_records is not None else total
    first_records = first_payload.get(records_key, [])
    downloaded = len(first_records)

    def fetch_page(offset: int) -> tuple[int, list[dict[str, Any]]]:
        requested = min(page_size, download_total - offset)
        page_params = {**params, offset_key: str(offset), limit_key: str(requested)}
        payload = request_json(f"{url}?{urllib.parse.urlencode(page_params)}")
        return offset, payload.get(records_key, [])

    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        for record in first_records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
        offsets = list(range(page_size, download_total, page_size))
        with concurrent.futures.ThreadPoolExecutor(max_workers=page_workers) as executor:
            futures = [executor.submit(fetch_page, offset) for offset in offsets]
            for page_number, future in enumerate(
                concurrent.futures.as_completed(futures), start=1
            ):
                _, records = future.result()
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                    handle.write("\n")
                downloaded += len(records)
                if page_number % 8 == 0 or page_number == len(futures):
                    print(
                        f"  {destination.stem}: {downloaded:,}/{download_total:,} "
                        f"(source total {total:,})",
                        flush=True,
                    )
    os.replace(partial, destination)
    return {"downloaded": downloaded, "source_total": total}


def download_gbif(root: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for genus, taxon_key in TAXA.items():
        print(f"GBIF {genus}", flush=True)
        counts[genus] = download_pages(
            url=GBIF_API,
            params={"taxon_key": str(taxon_key), "has_coordinate": "true"},
            page_size=300,
            records_key="results",
            total_key="count",
            offset_key="offset",
            limit_key="limit",
            destination=root / "gbif" / f"{genus.lower()}.jsonl",
            max_records=10_000,
        )
    return counts


def download_ala(root: Path) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for genus in TAXA:
        print(f"ALA {genus}", flush=True)
        counts[genus] = download_pages(
            url=ALA_API,
            params={"q": f"genus:{genus}", "fq": "spatiallyValid:true"},
            page_size=100,
            records_key="occurrences",
            total_key="totalRecords",
            offset_key="start",
            limit_key="pageSize",
            destination=root / "ala" / f"{genus.lower()}.jsonl",
            max_records=10_000,
            page_workers=4,
        )
    return counts


def download_inat_metadata(
    root: Path,
) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]]]:
    counts: dict[str, dict[str, int]] = {}
    jobs: list[dict[str, Any]] = []
    for genus, taxon_key in TAXA.items():
        destination = root / "inaturalist" / "metadata" / f"{genus.lower()}.jsonl"
        print(f"iNaturalist metadata {genus}", flush=True)
        counts[genus] = download_pages(
            url=GBIF_API,
            params={
                "dataset_key": INAT_DATASET_KEY,
                "taxon_key": str(taxon_key),
                "has_coordinate": "true",
                "media_type": "StillImage",
            },
            page_size=300,
            records_key="results",
            total_key="count",
            offset_key="offset",
            limit_key="limit",
            destination=destination,
            page_workers=8,
        )
        with destination.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                media = next(
                    (
                        item
                        for item in record.get("media", [])
                        if item.get("type") == "StillImage" and item.get("identifier")
                    ),
                    None,
                )
                if media is None:
                    continue
                original_url = str(media["identifier"])
                media_extension = Path(
                    urllib.parse.urlparse(original_url).path
                ).suffix.lower() or ".jpg"
                jobs.append(
                    {
                        "genus": genus,
                        "gbif_key": record.get("key"),
                        "occurrence_id": record.get("occurrenceID"),
                        "scientific_name": record.get("scientificName"),
                        "event_date": record.get("eventDate"),
                        "latitude": record.get("decimalLatitude"),
                        "longitude": record.get("decimalLongitude"),
                        "record_license": record.get("license"),
                        "media_license": media.get("license"),
                        "creator": media.get("creator"),
                        "rights_holder": media.get("rightsHolder"),
                        "source_url": media.get("references"),
                        "download_url": (
                            original_url.rsplit("/", 1)[0] + f"/medium{media_extension}"
                        ),
                        "media_extension": media_extension,
                        "photo_id": original_url.rstrip("/").split("/")[-2],
                    }
                )
    return counts, jobs


def download_one_image(root: Path, job: dict[str, Any]) -> dict[str, Any]:
    filename = f"{job['gbif_key']}_{job['photo_id']}{job['media_extension']}"
    destination = root / "inaturalist" / "images_medium" / str(job["genus"]).lower() / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + ".partial")
        request = urllib.request.Request(
            str(job["download_url"]), headers={"User-Agent": USER_AGENT}
        )
        for attempt in range(5):
            try:
                with (
                    urllib.request.urlopen(request, timeout=90) as response,
                    partial.open("wb") as handle,
                ):
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                os.replace(partial, destination)
                break
            except urllib.error.HTTPError as exc:
                partial.unlink(missing_ok=True)
                if exc.code in {400, 401, 403, 404} or attempt == 4:
                    raise
                time.sleep(2**attempt)
            except (urllib.error.URLError, TimeoutError):
                partial.unlink(missing_ok=True)
                if attempt == 4:
                    raise
                time.sleep(2**attempt)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {
        **job,
        "local_path": destination.relative_to(root).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": digest,
    }


def download_images(root: Path, jobs: list[dict[str, Any]], workers: int) -> tuple[int, int]:
    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    print(f"iNaturalist medium images: {len(jobs):,}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_one_image, root, job): job for job in jobs}
        for number, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            try:
                completed.append(future.result())
            except Exception as exc:
                failed.append({**futures[future], "error": str(exc)})
            if number % 250 == 0 or number == len(jobs):
                print(f"  images: {number:,}/{len(jobs):,}; failed={len(failed):,}", flush=True)
    completed.sort(key=lambda item: (str(item["genus"]), str(item["gbif_key"])))
    fields = list(completed[0]) if completed else list(jobs[0]) + ["local_path", "bytes", "sha256"]
    index_path = root / "inaturalist" / "image_index.csv"
    with index_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(completed)
    (root / "inaturalist" / "image_failures.json").write_text(
        json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return len(completed), len(failed)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path, summary: dict[str, Any]) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    summary.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "sources": {
                "gbif_api": GBIF_API,
                "ala_api": ALA_API,
                "inaturalist_dataset_key": INAT_DATASET_KEY,
            },
            "metadata_files": [
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for path in files
                if "images_medium" not in path.parts and path.name != "download-manifest.json"
            ],
        }
    )
    (root / "download-manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--image-workers", type=int, default=12)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"gbif_counts": download_gbif(root)}
    summary["ala_counts"] = download_ala(root)
    inat_counts, jobs = download_inat_metadata(root)
    summary["inaturalist_counts"] = inat_counts
    summary["inaturalist_image_candidates"] = len(jobs)
    if not args.skip_images:
        downloaded, failed = download_images(root, jobs, max(1, args.image_workers))
        summary["inaturalist_images_downloaded"] = downloaded
        summary["inaturalist_images_failed"] = failed
    write_manifest(root, summary)
    print(f"Completed: {root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
