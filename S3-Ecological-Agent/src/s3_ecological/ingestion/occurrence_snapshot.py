"""Offline occurrence snapshot importer (EarlyDesign.md "Next implementation
increment: offline occurrence snapshot ingestion", Milestone 1.5).

Converts a user-supplied GBIF, ALA, generic Darwin Core CSV/TSV export, or a
previously produced canonical JSON snapshot, into a deterministic local
bundle of ``occurrences.json`` + ``taxonomy.json`` + ``import-report.json``.
No network access, no credentials, and no dependency on the optional
``agent``/``api`` extras. The importer never scores, ranks, or assesses risk
- those responsibilities stay in :mod:`s3_ecological.orchestration.pipeline`
and the deterministic core it calls.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from s3_ecological.interfaces.occurrence import RawOccurrenceRecord
from s3_ecological.schemas.snapshot import (
    ImportRejection,
    ImportReport,
    ImportStatus,
    OccurrenceSnapshot,
    OutputFileChecksum,
    TaxonomySnapshot,
    TaxonomySnapshotItem,
)

IMPORTER_VERSION = "s3-ecological-importer-0.1.0"

SUPPORTED_SOURCES = frozenset({"gbif", "ala", "generic_dwc", "canonical"})

_OCCURRENCES_FILENAME = "occurrences.json"
_TAXONOMY_FILENAME = "taxonomy.json"
_REPORT_FILENAME = "import-report.json"

_OCCURRENCE_MAPPING_VERSION = "dwc-occurrence-v1"
_TAXONOMY_MAPPING_VERSION = "dwc-taxonomy-v1"
_CANONICAL_MAPPING_VERSION = "canonical-v1"

# Ordered fallback header lists per source profile (EarlyDesign.md field
# mapping table). Order matters: the first present, non-empty header wins.
_TAXON_ID_HEADERS: dict[str, list[str]] = {
    "gbif": ["acceptedTaxonKey", "taxonKey", "taxonID"],
    "ala": ["acceptedConceptID", "taxonConceptID", "taxonID"],
    "generic_dwc": ["taxonID"],
}
_RECORD_ID_HEADERS: dict[str, list[str]] = {
    "gbif": ["occurrenceID", "gbifID"],
    "ala": ["occurrenceID", "id"],
    "generic_dwc": ["occurrenceID", "id"],
}
_ACCEPTED_NAME_HEADERS = ["acceptedScientificName", "scientificName"]
_RAW_NAME_HEADER = "scientificName"
_RANK_HEADER = "taxonRank"
_LATITUDE_HEADER = "decimalLatitude"
_LONGITUDE_HEADER = "decimalLongitude"
_UNCERTAINTY_HEADER = "coordinateUncertaintyInMeters"
_EVENT_DATE_HEADER = "eventDate"
_YEAR_HEADER, _MONTH_HEADER, _DAY_HEADER = "year", "month", "day"
_BASIS_HEADER = "basisOfRecord"
_LICENSE_HEADER = "license"
_MEDIA_LICENSE_HEADER = "mediaLicense"
_CAPTIVE_HEADERS = ["isCaptive", "isCultivated"]

_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}

# Substrings that mark a `--query-parameters-json` key as secret-like and
# therefore rejected outright (EarlyDesign.md: "keys with secret-like names
# such as token, password, or api_key are rejected").
_SECRET_KEY_SUBSTRINGS = ("token", "password", "apikey", "api_key", "secret")

_ROW_REJECTION_CODES = (
    "missing_scientific_name",
    "missing_taxon_id",
    "invalid_numeric_value",
    "negative_coordinate_uncertainty",
    "non_finite_numeric_value",
    "invalid_record_schema",
)


class ImportFatalError(Exception):
    """Raised for any failure that must abort the import with no bundle written.

    Every fatal condition in EarlyDesign.md's "Failure semantics" section
    (missing/unreadable/non-UTF-8 input, unsupported extension/source
    combination, a missing required header, invalid command metadata, a
    canonical JSON schema failure, an existing target without
    ``--overwrite``, zero accepted records, an unwritable output directory,
    or a checksum-verification failure) raises this. The CLI catches it,
    prints a concise message to stderr, and exits ``1``.
    """


def _normalize_name(name: str) -> str:
    """Unicode-normalize, trim, collapse whitespace, and case-fold a taxon name."""
    folded = unicodedata.normalize("NFKC", name).strip().casefold()
    return " ".join(folded.split())


def _validate_command_metadata(
    dataset_id: str, retrieved_at: str, dataset_license: str, citation: str
) -> None:
    if not dataset_id.strip():
        raise ImportFatalError("--dataset-id must not be empty")
    if not dataset_license.strip():
        raise ImportFatalError("--dataset-license must not be empty")
    if not citation.strip():
        raise ImportFatalError("--citation must not be empty")
    try:
        parsed = datetime.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise ImportFatalError(
            f"--retrieved-at '{retrieved_at}' is not a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ImportFatalError(
            f"--retrieved-at '{retrieved_at}' must include a timezone offset or 'Z'"
        )


def _load_query_parameters(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ImportFatalError(f"cannot read --query-parameters-json file '{path}': {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportFatalError(f"--query-parameters-json is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImportFatalError("--query-parameters-json must contain a single JSON object")
    for key in payload:
        lowered = key.lower()
        if any(marker in lowered for marker in _SECRET_KEY_SUBSTRINGS):
            raise ImportFatalError(
                f"--query-parameters-json key '{key}' looks like a secret and is rejected"
            )
    return payload


def _resolve_format(input_path: Path, source: str) -> str | None:
    """Return the delimiter for ``input_path`` (``None`` for canonical JSON).

    Delimiters are chosen from the file extension alone, never inferred from
    content, per EarlyDesign.md ("Do not infer delimiters").
    """
    suffix = input_path.suffix.lower()

    if source == "canonical":
        if suffix != ".json":
            raise ImportFatalError("--source canonical requires a .json input file")
        return None

    if suffix == ".csv":
        return ","
    if suffix == ".tsv" or input_path.name == "occurrence.txt":
        return "\t"
    raise ImportFatalError(
        f"unsupported extension/source combination: '{input_path.name}' with --source '{source}'"
    )


def _read_input(input_path: Path) -> tuple[bytes, str]:
    try:
        raw_bytes = input_path.read_bytes()
    except OSError as exc:
        raise ImportFatalError(f"cannot read input file '{input_path}': {exc}") from exc
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportFatalError(f"input file '{input_path}' is not valid UTF-8: {exc}") from exc
    return raw_bytes, text


def _field_mapping_for_source(source: str) -> dict[str, list[str]]:
    if source == "canonical":
        return {}
    return {
        "source_record_id": _RECORD_ID_HEADERS[source],
        "scientific_name_raw": [_RAW_NAME_HEADER],
        "accepted_name": _ACCEPTED_NAME_HEADERS,
        "taxon_id": _TAXON_ID_HEADERS[source],
        "rank": [_RANK_HEADER],
        "latitude": [_LATITUDE_HEADER],
        "longitude": [_LONGITUDE_HEADER],
        "coordinate_uncertainty_m": [_UNCERTAINTY_HEADER],
        "event_date": [_EVENT_DATE_HEADER, _YEAR_HEADER, _MONTH_HEADER, _DAY_HEADER],
        "basis_of_record": [_BASIS_HEADER],
        "license": [_LICENSE_HEADER],
        "media_license": [_MEDIA_LICENSE_HEADER],
        "is_captive_or_cultivated": _CAPTIVE_HEADERS,
    }


@dataclass
class _RowError:
    code: str
    field: str | None
    message: str


@dataclass
class _TaxonAccumulator:
    scientific_name: str | None = None
    rank: str | None = None
    submitted_names: set[str] = field(default_factory=set)


def _first_present(row: dict[str, str | None], headers: list[str]) -> str | None:
    for header in headers:
        value = row.get(header)
        if value:
            return value
    return None


def _parse_optional_float(
    value: str | None, field_name: str
) -> tuple[float | None, list[_RowError]]:
    if value is None:
        return None, []
    try:
        parsed = float(value)
    except ValueError:
        message = f"'{field_name}' value '{value}' is not numeric"
        return None, [_RowError("invalid_numeric_value", field_name, message)]
    if not math.isfinite(parsed):
        message = f"'{field_name}' value '{value}' is not finite"
        return None, [_RowError("non_finite_numeric_value", field_name, message)]
    return parsed, []


def _parse_uncertainty(value: str | None) -> tuple[float | None, list[_RowError]]:
    parsed, errors = _parse_optional_float(value, _UNCERTAINTY_HEADER)
    if errors or parsed is None:
        return parsed, errors
    if parsed < 0:
        return None, [
            _RowError(
                "negative_coordinate_uncertainty",
                _UNCERTAINTY_HEADER,
                f"'{_UNCERTAINTY_HEADER}' value '{value}' is negative",
            )
        ]
    return parsed, []


def _resolve_event_date(row: dict[str, str | None]) -> str | None:
    direct = row.get(_EVENT_DATE_HEADER)
    if direct:
        return direct
    year = row.get(_YEAR_HEADER)
    if not year:
        return None
    month = row.get(_MONTH_HEADER)
    if not month or not month.isdigit():
        return year
    day = row.get(_DAY_HEADER)
    if not day or not day.isdigit():
        return f"{year}-{int(month):02d}"
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _parse_optional_bool(value: str | None) -> tuple[bool | None, str | None]:
    """Return (value, warning). A non-empty, unrecognized spelling becomes
    ``(None, warning)`` rather than a row rejection (EarlyDesign.md rule 10)."""
    if value is None:
        return None, None
    lowered = value.lower()
    if lowered in _BOOL_TRUE:
        return True, None
    if lowered in _BOOL_FALSE:
        return False, None
    return None, f"unrecognized boolean value '{value}'"


def _namespace_taxon_id(source: str, raw_taxon_id: str) -> str:
    prefix = f"{source}:"
    return raw_taxon_id if raw_taxon_id.startswith(prefix) else f"{prefix}{raw_taxon_id}"


def _generated_record_id(headers: list[str], row: dict[str, str | None]) -> str:
    """Deterministic fallback id: sha256 of every trimmed header -> trimmed
    value or null, sorted by key. Never includes row position, so
    reordering rows never changes an id (EarlyDesign.md rule 3)."""
    payload = {header: row.get(header) for header in headers}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"generated:{digest}"


def _row_dict(headers: list[str], raw_row: list[str]) -> dict[str, str | None]:
    return {header: (cell.strip() or None) for header, cell in zip(headers, raw_row, strict=True)}


def _parse_headers(text: str, delimiter: str, source: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise ImportFatalError("input file has no header row") from exc
    headers = [h.strip() for h in raw_headers]

    duplicates = sorted(h for h, count in Counter(headers).items() if count > 1)
    if duplicates:
        raise ImportFatalError(f"duplicate headers after trimming: {duplicates}")
    if _RAW_NAME_HEADER not in headers:
        raise ImportFatalError(f"missing required header '{_RAW_NAME_HEADER}'")
    if not any(header in headers for header in _TAXON_ID_HEADERS[source]):
        raise ImportFatalError(
            f"no supported taxon-id header for source '{source}'; expected one of "
            f"{_TAXON_ID_HEADERS[source]}"
        )
    return headers, list(reader)


@dataclass
class _DelimitedImportResult:
    records: list[RawOccurrenceRecord]
    rejections: list[ImportRejection]
    mapping_warnings: list[ImportRejection]
    counts_by_rejection_code: dict[str, int]
    counts_by_taxon_id: dict[str, int]
    taxa: list[TaxonomySnapshotItem]
    input_record_count: int


def _import_delimited(
    *,
    text: str,
    delimiter: str,
    source: str,
    dataset_id: str,
    dataset_license: str,
    query_parameters: dict[str, Any],
    snapshot_key: str,
) -> _DelimitedImportResult:
    headers, data_rows = _parse_headers(text, delimiter, source)

    records: list[RawOccurrenceRecord] = []
    rejections: list[ImportRejection] = []
    mapping_warnings: list[ImportRejection] = []
    counts_by_code: dict[str, int] = {}
    counts_by_taxon: dict[str, int] = {}
    accumulators: dict[str, _TaxonAccumulator] = {}

    for offset, raw_row in enumerate(data_rows):
        row_number = offset + 1
        errors: list[_RowError] = []

        if len(raw_row) != len(headers):
            errors.append(
                _RowError(
                    "invalid_record_schema",
                    None,
                    f"row has {len(raw_row)} fields, expected {len(headers)}",
                )
            )
            _record_rejection(rejections, counts_by_code, row_number, errors)
            continue

        row = _row_dict(headers, raw_row)

        scientific_name_raw = row.get(_RAW_NAME_HEADER)
        if not scientific_name_raw:
            errors.append(
                _RowError(
                    "missing_scientific_name",
                    _RAW_NAME_HEADER,
                    "scientificName is missing or empty",
                )
            )

        raw_taxon_id = _first_present(row, _TAXON_ID_HEADERS[source])
        if not raw_taxon_id:
            errors.append(
                _RowError(
                    "missing_taxon_id",
                    _TAXON_ID_HEADERS[source][0],
                    "no supported source taxon id field is present",
                )
            )

        latitude, lat_errors = _parse_optional_float(row.get(_LATITUDE_HEADER), _LATITUDE_HEADER)
        errors.extend(lat_errors)
        longitude, lon_errors = _parse_optional_float(row.get(_LONGITUDE_HEADER), _LONGITUDE_HEADER)
        errors.extend(lon_errors)
        uncertainty, unc_errors = _parse_uncertainty(row.get(_UNCERTAINTY_HEADER))
        errors.extend(unc_errors)

        if errors:
            _record_rejection(rejections, counts_by_code, row_number, errors)
            continue

        assert scientific_name_raw is not None
        assert raw_taxon_id is not None

        accepted_name = _first_present(row, _ACCEPTED_NAME_HEADERS) or scientific_name_raw
        rank = row.get(_RANK_HEADER)
        event_date = _resolve_event_date(row)
        basis_of_record = row.get(_BASIS_HEADER)
        license_value = row.get(_LICENSE_HEADER) or dataset_license
        media_license = row.get(_MEDIA_LICENSE_HEADER)
        is_captive, bool_warning = _parse_optional_bool(_first_present(row, _CAPTIVE_HEADERS))
        if bool_warning:
            mapping_warnings.append(
                ImportRejection(
                    row_number=row_number,
                    code="unrecognized_boolean",
                    field="isCaptive/isCultivated",
                    message=bool_warning,
                )
            )

        source_record_id = _first_present(row, _RECORD_ID_HEADERS[source])
        if source_record_id is None:
            source_record_id = _generated_record_id(headers, row)

        namespaced_taxon_id = _namespace_taxon_id(source, raw_taxon_id)

        try:
            record = RawOccurrenceRecord(
                source=source,
                source_record_id=source_record_id,
                dataset_id=dataset_id,
                scientific_name_raw=scientific_name_raw,
                taxon_id=namespaced_taxon_id,
                latitude=latitude,
                longitude=longitude,
                coordinate_uncertainty_m=uncertainty,
                event_date=event_date,
                basis_of_record=basis_of_record,
                license=license_value,
                media_license=media_license,
                is_captive_or_cultivated=is_captive,
                query_parameters=query_parameters,
                snapshot_or_cache_key=snapshot_key,
            )
        except ValidationError as exc:
            message = f"record failed schema validation ({exc.error_count()} error(s))"
            _record_rejection(
                rejections,
                counts_by_code,
                row_number,
                [_RowError("invalid_record_schema", None, message)],
            )
            continue

        records.append(record)
        counts_by_taxon[namespaced_taxon_id] = counts_by_taxon.get(namespaced_taxon_id, 0) + 1

        accumulator = accumulators.setdefault(namespaced_taxon_id, _TaxonAccumulator())
        accumulator.submitted_names.add(scientific_name_raw)
        if accumulator.scientific_name is None:
            accumulator.scientific_name = accepted_name
        if accumulator.rank is None and rank:
            accumulator.rank = rank

    taxa = _build_taxonomy_items(accumulators, id_key_fn=lambda _taxon_id: source)

    return _DelimitedImportResult(
        records=records,
        rejections=rejections,
        mapping_warnings=mapping_warnings,
        counts_by_rejection_code=counts_by_code,
        counts_by_taxon_id=counts_by_taxon,
        taxa=taxa,
        input_record_count=len(data_rows),
    )


def _record_rejection(
    rejections: list[ImportRejection],
    counts_by_code: dict[str, int],
    row_number: int,
    errors: list[_RowError],
) -> None:
    for error in errors:
        counts_by_code[error.code] = counts_by_code.get(error.code, 0) + 1
    primary = errors[0]
    message = "; ".join(error.message for error in errors)
    rejections.append(
        ImportRejection(
            row_number=row_number, code=primary.code, field=primary.field, message=message
        )
    )


def _build_taxonomy_items(
    accumulators: dict[str, _TaxonAccumulator], *, id_key_fn: Any
) -> list[TaxonomySnapshotItem]:
    items: list[TaxonomySnapshotItem] = []
    for taxon_id, accumulator in accumulators.items():
        submitted_sorted = sorted(
            accumulator.submitted_names, key=lambda n: (_normalize_name(n), n)
        )
        scientific_name = accumulator.scientific_name or submitted_sorted[0]
        items.append(
            TaxonomySnapshotItem(
                submitted_names=submitted_sorted,
                scientific_name=scientific_name,
                rank=accumulator.rank,
                taxon_ids={id_key_fn(taxon_id): taxon_id},
                ambiguous=False,
            )
        )
    items.sort(key=lambda item: next(iter(item.taxon_ids.values())))
    _mark_ambiguous(items)
    return items


def _mark_ambiguous(items: list[TaxonomySnapshotItem]) -> None:
    """Flag items that share a normalized name with another item in the same
    bundle - the importer keeps them as separate entries (EarlyDesign.md:
    "Multiple accepted taxa for one normalized submitted name must remain
    ambiguous")."""
    name_to_indices: dict[str, set[int]] = {}
    for index, item in enumerate(items):
        for name in (item.scientific_name, *item.submitted_names):
            name_to_indices.setdefault(_normalize_name(name), set()).add(index)
    ambiguous_indices = {
        index for indices in name_to_indices.values() if len(indices) > 1 for index in indices
    }
    for index in ambiguous_indices:
        items[index] = items[index].model_copy(update={"ambiguous": True})


def _import_canonical(
    *,
    text: str,
    dataset_id: str,
    retrieved_at: str,
    dataset_license: str,
    citation: str,
) -> tuple[list[RawOccurrenceRecord], list[TaxonomySnapshotItem]]:
    """Re-import a previously written ``occurrences.json`` unchanged.

    ``--source canonical`` is a CLI selector, not a value the file's own
    ``source`` field is compared against: a canonical bundle re-imports a
    file whose ``source`` still records where its records originally came
    from (``"gbif"``, ``"ala"``, ...), and that field is carried through to
    the new bundle unchanged - only dataset_id/retrieved_at/dataset_license/
    citation must match the current command line.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportFatalError(f"canonical input is not valid JSON: {exc}") from exc

    try:
        canonical = OccurrenceSnapshot.model_validate(payload)
    except ValidationError as exc:
        raise ImportFatalError(
            f"canonical JSON schema failure: {exc.error_count()} error(s)"
        ) from exc

    mismatches = []
    if canonical.dataset_id != dataset_id:
        mismatches.append(f"dataset_id '{canonical.dataset_id}' != '{dataset_id}'")
    if canonical.retrieved_at != retrieved_at:
        mismatches.append(f"retrieved_at '{canonical.retrieved_at}' != '{retrieved_at}'")
    if canonical.dataset_license != dataset_license:
        mismatches.append(f"dataset_license '{canonical.dataset_license}' != '{dataset_license}'")
    if canonical.citation != citation:
        mismatches.append(f"citation '{canonical.citation}' != '{citation}'")
    if mismatches:
        raise ImportFatalError(
            "canonical input metadata does not match the command metadata: " + "; ".join(mismatches)
        )

    accumulators: dict[str, _TaxonAccumulator] = {}
    for record in canonical.records:
        accumulator = accumulators.setdefault(record.taxon_id, _TaxonAccumulator())
        accumulator.submitted_names.add(record.scientific_name_raw)
        if accumulator.scientific_name is None:
            accumulator.scientific_name = record.scientific_name_raw

    def _id_key(taxon_id: str) -> str:
        return taxon_id.split(":", 1)[0] if ":" in taxon_id else taxon_id

    taxa = _build_taxonomy_items(accumulators, id_key_fn=_id_key)
    return list(canonical.records), taxa


def _serialize(model: BaseModel) -> bytes:
    """Deterministic UTF-8 JSON: stable (field-declaration) key order, fixed
    indentation, trailing newline. Identical model content always produces
    identical bytes."""
    data = model.model_dump(mode="json")
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_temp(final_path: Path, data: bytes) -> Path:
    fd, tmp_name = tempfile.mkstemp(
        dir=final_path.parent, prefix=f".{final_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name)


def _verify_and_commit(tmp_path: Path, final_path: Path, expected_sha256: str) -> None:
    try:
        readback = tmp_path.read_bytes()
        if hashlib.sha256(readback).hexdigest() != expected_sha256:
            raise ImportFatalError(
                f"checksum verification failed for '{final_path.name}' after write"
            )
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def import_occurrence_snapshot(
    *,
    input_path: str | Path,
    source: str,
    dataset_id: str,
    retrieved_at: str,
    dataset_license: str,
    citation: str,
    query_parameters_path: str | Path | None,
    output_dir: str | Path,
    overwrite: bool = False,
) -> ImportReport:
    """Import one offline occurrence export into a local snapshot bundle.

    Writes ``occurrences.json``, ``taxonomy.json``, and
    ``import-report.json`` into ``output_dir`` and returns the report. Raises
    :class:`ImportFatalError` (no bundle written) for any condition listed in
    EarlyDesign.md's "Failure semantics" section; a non-fatal completion with
    row rejections is reflected in the returned report's
    ``rejected_record_count`` and ``status``, not by raising.
    """
    started_at = datetime.now(UTC)
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if source not in SUPPORTED_SOURCES:
        raise ImportFatalError(
            f"unsupported --source '{source}'; expected one of {sorted(SUPPORTED_SOURCES)}"
        )
    _validate_command_metadata(dataset_id, retrieved_at, dataset_license, citation)
    query_parameters = _load_query_parameters(query_parameters_path)
    delimiter = _resolve_format(input_path, source)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImportFatalError(f"output directory '{output_dir}' is not writable: {exc}") from exc

    for filename in (_OCCURRENCES_FILENAME, _TAXONOMY_FILENAME, _REPORT_FILENAME):
        if (output_dir / filename).exists() and not overwrite:
            raise ImportFatalError(
                f"'{output_dir / filename}' already exists; pass --overwrite to replace it"
            )

    raw_bytes, text = _read_input(input_path)
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    if source == "canonical":
        mapping_version = _CANONICAL_MAPPING_VERSION
        taxonomy_mapping_version = _CANONICAL_MAPPING_VERSION
        snapshot_key = f"{dataset_id}:{source_sha256[:12]}:{mapping_version}"
        records, taxa = _import_canonical(
            text=text,
            dataset_id=dataset_id,
            retrieved_at=retrieved_at,
            dataset_license=dataset_license,
            citation=citation,
        )
        rejections: list[ImportRejection] = []
        mapping_warnings: list[ImportRejection] = []
        counts_by_code: dict[str, int] = {}
        counts_by_taxon = {
            record.taxon_id: sum(1 for r in records if r.taxon_id == record.taxon_id)
            for record in records
        }
        input_record_count = len(records)
        field_mapping: dict[str, list[str]] = {}
    else:
        assert delimiter is not None
        mapping_version = _OCCURRENCE_MAPPING_VERSION
        taxonomy_mapping_version = _TAXONOMY_MAPPING_VERSION
        snapshot_key = f"{dataset_id}:{source_sha256[:12]}:{mapping_version}"
        result = _import_delimited(
            text=text,
            delimiter=delimiter,
            source=source,
            dataset_id=dataset_id,
            dataset_license=dataset_license,
            query_parameters=query_parameters,
            snapshot_key=snapshot_key,
        )
        records = result.records
        taxa = result.taxa
        rejections = result.rejections
        mapping_warnings = result.mapping_warnings
        counts_by_code = result.counts_by_rejection_code
        counts_by_taxon = result.counts_by_taxon_id
        input_record_count = result.input_record_count
        field_mapping = _field_mapping_for_source(source)

    if not records:
        raise ImportFatalError("zero accepted records; nothing to import")

    occurrence_snapshot = OccurrenceSnapshot(
        dataset_id=dataset_id,
        source=source,
        retrieved_at=retrieved_at,
        dataset_license=dataset_license,
        citation=citation,
        source_sha256=source_sha256,
        mapping_version=mapping_version,
        snapshot_key=snapshot_key,
        query_parameters=query_parameters,
        records=records,
    )
    taxonomy_snapshot = TaxonomySnapshot(
        dataset_id=dataset_id,
        source=source,
        source_sha256=source_sha256,
        mapping_version=taxonomy_mapping_version,
        taxa=taxa,
    )

    occurrence_bytes = _serialize(occurrence_snapshot)
    taxonomy_bytes = _serialize(taxonomy_snapshot)
    occurrence_sha256 = hashlib.sha256(occurrence_bytes).hexdigest()
    taxonomy_sha256 = hashlib.sha256(taxonomy_bytes).hexdigest()

    occurrences_path = output_dir / _OCCURRENCES_FILENAME
    taxonomy_path = output_dir / _TAXONOMY_FILENAME
    report_path = output_dir / _REPORT_FILENAME

    occ_tmp = _write_temp(occurrences_path, occurrence_bytes)
    tax_tmp = _write_temp(taxonomy_path, taxonomy_bytes)

    completed_at = datetime.now(UTC)
    status = ImportStatus.COMPLETED_WITH_REJECTIONS if rejections else ImportStatus.COMPLETED

    report = ImportReport(
        dataset_id=dataset_id,
        source=source,
        retrieved_at=retrieved_at,
        dataset_license=dataset_license,
        citation=citation,
        query_parameters=query_parameters,
        importer_version=IMPORTER_VERSION,
        occurrence_mapping_version=mapping_version,
        taxonomy_mapping_version=taxonomy_mapping_version,
        input_filename=input_path.name,
        source_sha256=source_sha256,
        started_at=started_at,
        completed_at=completed_at,
        encoding="utf-8",
        delimiter=delimiter,
        input_record_count=input_record_count,
        accepted_record_count=len(records),
        rejected_record_count=len(rejections),
        counts_by_taxon_id=counts_by_taxon,
        counts_by_rejection_code=counts_by_code,
        field_mapping=field_mapping,
        rejections=rejections,
        mapping_warnings=mapping_warnings,
        output_files={
            "occurrences": OutputFileChecksum(
                filename=_OCCURRENCES_FILENAME, sha256=occurrence_sha256
            ),
            "taxonomy": OutputFileChecksum(filename=_TAXONOMY_FILENAME, sha256=taxonomy_sha256),
        },
        status=status,
    )
    report_bytes = _serialize(report)
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    report_tmp = _write_temp(report_path, report_bytes)

    _verify_and_commit(occ_tmp, occurrences_path, occurrence_sha256)
    _verify_and_commit(tax_tmp, taxonomy_path, taxonomy_sha256)
    _verify_and_commit(report_tmp, report_path, report_sha256)

    return report
