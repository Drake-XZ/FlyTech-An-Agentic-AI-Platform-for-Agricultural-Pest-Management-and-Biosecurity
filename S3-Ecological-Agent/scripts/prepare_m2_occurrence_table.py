"""Offline, deterministic conversion of the committed M2 GBIF/ALA JSONL
resources into an importer-compatible Darwin Core CSV table plus a
machine-readable conversion report (DesignSuggestionLog.md, "2026-09-08
Australia/Sydney - Suggested next increment: M2-A authorised occurrence
preparation and readiness run", "Required implementation order" steps 2-5).

This script is data preparation only. It:

- reads only the already-committed local files under ``data/external/m2/
  gbif/*.jsonl`` and ``data/external/m2/ala/*.jsonl`` (or paths given via
  ``--gbif-dir``/``--ala-dir``);
- makes no network request, no LLM call, and no call to any FlyTech agent
  or model;
- never trains, calibrates, or evaluates anything;
- never reimplements ``s3_ecological.occurrence.cleaning.clean_occurrences``:
  coordinate quality/usability decisions remain that function's sole
  authority. This script only maps provider fields to the Milestone 1.5
  importer's Darwin Core contract and performs pre-import, cross-provider
  identity deduplication - a different concern from ecological cleaning.

Determinism contract
---------------------

Given the same input files and the same CLI configuration, the emitted CSV
bytes are always identical: every value taken from the input JSON is passed
through unmodified except for two explicit, documented mapping
transformations (ALA epoch-millisecond ``eventDate`` -> ISO date; provider
name prefixed onto ``occurrenceID``/``taxonID`` for cross-provider
recoverability - see the module docstring in
``s3_ecological.ingestion.occurrence_snapshot`` for why the second
transformation is necessary), and the final row order is a sort by the
already-provider-prefixed ``occurrenceID`` cell, not by input file order or
line number. Reordering the lines within an input JSONL file, or reordering
the ``--gbif-dir``/``--ala-dir`` genus files themselves, must not change the
emitted CSV bytes. Volatile fields (``generated_at``, ``run_id``) live only
in the conversion report, never in the CSV.

Field mapping
-------------

GBIF (per-record JSON keys, GBIF occurrence-download API shape):

- ``occurrenceID`` else ``gbifID`` -> provider record identity
- ``acceptedTaxonKey`` else ``taxonKey`` else ``taxonID`` -> provider taxon id
  (same fallback order the existing importer already uses for
  ``--source gbif``)
- ``scientificName``, ``acceptedScientificName``, ``taxonRank`` -> passed
  through verbatim
- ``decimalLatitude``, ``decimalLongitude``, ``coordinateUncertaintyInMeters``
  -> passed through verbatim (the existing importer re-parses and validates
  these; this script does not re-validate them a second time)
- ``eventDate`` (already an ISO-ish string for this provider) -> passed
  through verbatim; ``year``/``month``/``day`` used only when ``eventDate``
  is absent
- ``basisOfRecord``, ``license`` -> passed through verbatim
- ``media[0].license`` -> ``mediaLicense`` (first image's licence only, if
  any images are attached)
- ``http://unknown.org/captive_cultivated`` -> ``isCaptive``: ``"wild"`` maps
  to ``false``; ``null`` or any other value maps to blank (unknown), never
  guessed

ALA (per-record JSON keys, ALA biocache-download JSON shape):

- ``uuid`` -> provider record identity (always present in the committed ALA
  files, unlike ``occurrenceID``, which is only present for
  iNaturalist-sourced ALA records)
- ``acceptedConceptID`` else ``taxonConceptID`` else ``taxonID`` -> provider
  taxon id
- ``scientificName``, ``taxonRank`` -> passed through verbatim (ALA records
  in this dataset carry no distinct ``acceptedScientificName``; the accepted
  name column is filled with ``scientificName`` in that case, exactly the
  same fallback the existing importer already applies)
- ``decimalLatitude``, ``decimalLongitude``, ``coordinateUncertaintyInMeters``
  -> passed through verbatim when present (roughly half of the committed ALA
  records carry no coordinate pair at all; this script never invents one)
- ``eventDate`` -> **converted**: ALA's iNaturalist-sourced records encode
  this as epoch milliseconds (an integer), not an ISO string. This script
  converts it to a plain ``YYYY-MM-DD`` date via pure integer arithmetic
  (``datetime(1970,1,1,UTC) + timedelta(milliseconds=value)``, never
  ``datetime.fromtimestamp``, which raises ``OSError`` for the pre-1970
  values present in this dataset on some platforms). Falls back to
  ``year``/``month`` when ``eventDate`` is absent or not an integer.
- ``basisOfRecord``, ``license`` -> passed through verbatim
- no media-licence or captive/cultivated field exists in the committed ALA
  records, so both are always left blank for ALA-derived rows

Provider and record identity preservation
------------------------------------------

The Milestone 1.5 importer (see ``s3_ecological/ingestion/occurrence_snapshot.py``)
namespaces the *taxon id* it is given with the ``--source`` value
(``generic_dwc:`` here) but does **not** namespace ``source_record_id``. Since
this script merges two providers into one ``--source generic_dwc`` import, it
must itself prefix both the taxon id and the record id with the record's
originating provider name (``gbif:`` / ``ala:``) before the importer ever sees
them, or two providers' identities could collide or become unrecoverable.
This is why every emitted ``occurrenceID``/``taxonID`` cell in the CSV is of
the form ``<provider>:<original id>`` - a deliberate, documented provenance
mechanism, not a bug, and not a second taxonomy authority: the resulting
taxonomy/occurrence ``taxon_id`` becomes ``generic_dwc:<provider>:<original
provider taxon id>`` after import, fully reversible by string-splitting on
the first two ``:`` separators.

Deduplication (versioned comparison profile ``m2-dedup-v0.1``)
-----------------------------------------------------------------

Three explicit tiers, all reported, never silently dropped:

1. **Exact duplicate** - two rows from the *same* provider share the same
   provider record identity (``occurrenceID``/``gbifID`` for GBIF, ``uuid``
   for ALA). Only one is kept; the deterministic tie-break (independent of
   input file order) is the lexicographically smallest fully-mapped row
   tuple.
2. **Probable cross-provider duplicate** - two rows from *different*
   providers are very likely the same underlying observation, judged by
   either (a) a shared iNaturalist observation id embedded in the raw
   ``occurrenceID`` URL of both providers' records (a strong, specimen-level
   identity signal - both GBIF and ALA re-publish iNaturalist research-grade
   observations under this shared URL), or (b) the same normalized accepted
   scientific name, coordinates rounded to ``coordinate_round_decimals``
   (default 3 decimal degrees, roughly 111 m at the equator - a fixed,
   documented bucket precision, not a fuzzy tolerance search) decimal
   degrees, and matching event dates (calendar day). Only the non-canonical
   row is dropped; ``canonical_provider_precedence`` (default
   ``["gbif", "ala"]``) breaks the tie deterministically.
3. **Ambiguous match** - the same coordinate+name bucket as (2b) but the
   event dates disagree, or one or both sides lack an event date. Both rows
   are *kept* and emitted; the pairing is recorded in the report under
   ``duplicate_details.ambiguous_cross_provider_matches`` so a reviewer can
   resolve it, exactly as the task requires ("ambiguous matches must not be
   silently dropped").

Known limitation, stated plainly: this is a bucketed exact-precision match,
not an O(n*m) fuzzy nearest-neighbour search across the full ~46k-record
dataset - a deliberately bounded-cost choice for this offline preparation
script, recorded here as a data-preparation parameter, not a scientific
calibration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

TOOL_VERSION = "prepare-m2-occurrence-table-v0.1.0"
CONVERSION_PROFILE_VERSION = "m2-occurrence-conversion-v0.1"
DEDUP_PROFILE_VERSION = "m2-dedup-v0.1"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GBIF_DIR = REPO_ROOT / "data" / "external" / "m2" / "gbif"
DEFAULT_ALA_DIR = REPO_ROOT / "data" / "external" / "m2" / "ala"
DEFAULT_GENERA = ("anastrepha", "bactrocera", "ceratitis", "rhagoletis")
TF4_GENERA = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")

_CANONICAL_PROVIDER_PRECEDENCE = ("gbif", "ala")
_DEFAULT_COORDINATE_ROUND_DECIMALS = 3

_CSV_HEADER = [
    "occurrenceID",
    "scientificName",
    "acceptedScientificName",
    "taxonID",
    "taxonRank",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "eventDate",
    "basisOfRecord",
    "license",
    "mediaLicense",
    "isCaptive",
    "isCultivated",
    "provider",
]

_GBIF_TAXON_ID_HEADERS = ("acceptedTaxonKey", "taxonKey", "taxonID")
_GBIF_RECORD_ID_HEADERS = ("occurrenceID", "gbifID")
_ALA_TAXON_ID_HEADERS = ("acceptedConceptID", "taxonConceptID", "taxonID")
_ALA_RECORD_ID_HEADERS = ("uuid",)

_INATURALIST_URL_PREFIX = "inaturalist.org/observations/"


class ConversionFatalError(Exception):
    """A missing input file, malformed configuration, or output-write
    failure that must stop the run before any output file is written."""


@dataclass
class _Row:
    """One mapped occurrence, prior to deduplication."""

    provider: str
    genus_file: str
    source_file_relpath: str
    source_line_number: int
    provider_record_id: str
    inaturalist_obs_id: str | None
    scientific_name: str | None
    accepted_name: str | None
    taxon_id_raw: str | None
    rank: str | None
    latitude: Any
    longitude: Any
    coordinate_uncertainty_m: Any
    event_date: str | None
    basis_of_record: str | None
    license: str | None
    media_license: str | None
    is_captive: str
    mapping_warnings: list[str] = field(default_factory=list)

    def csv_row(self) -> list[str]:
        occurrence_id = f"{self.provider}:{self.provider_record_id}"
        taxon_id = f"{self.provider}:{self.taxon_id_raw}" if self.taxon_id_raw else ""
        return [
            occurrence_id,
            self.scientific_name or "",
            self.accepted_name or self.scientific_name or "",
            taxon_id,
            self.rank or "",
            _format_number(self.latitude),
            _format_number(self.longitude),
            _format_number(self.coordinate_uncertainty_m),
            self.event_date or "",
            self.basis_of_record or "",
            self.license or "",
            self.media_license or "",
            self.is_captive,
            "",
            self.provider,
        ]

    def sort_key(self) -> tuple[str, ...]:
        return tuple(str(v) for v in self.csv_row())

    def resolved_genus(self) -> str | None:
        name = self.accepted_name or self.scientific_name
        if not name:
            return None
        token = name.split()
        return token[0] if token else None

    def report_identity(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "genus_file": self.genus_file,
            "source_file": self.source_file_relpath,
            "source_line_number": self.source_line_number,
            "provider_record_id": self.provider_record_id,
            "scientific_name": self.scientific_name,
            "accepted_name": self.accepted_name,
        }


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int | float):
        return repr(value)
    return str(value)


def _first_present(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = rec.get(key)
        if value is not None and value != "":
            return value
    return None


def _extract_inaturalist_id(raw_occurrence_id: Any) -> str | None:
    if not isinstance(raw_occurrence_id, str):
        return None
    marker = raw_occurrence_id.find(_INATURALIST_URL_PREFIX)
    if marker == -1:
        return None
    tail = raw_occurrence_id[marker + len(_INATURALIST_URL_PREFIX) :]
    digits = "".join(ch for ch in tail.split("?")[0].split("/")[0] if ch.isdigit())
    return digits or None


def _normalize_name(name: str) -> str:
    folded = unicodedata.normalize("NFKC", name).strip().casefold()
    return " ".join(folded.split())


def _gbif_event_date(rec: dict[str, Any]) -> str | None:
    direct = rec.get("eventDate")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return _year_month_day_fallback(rec.get("year"), rec.get("month"), rec.get("day"))


def _ala_event_date(rec: dict[str, Any], warnings: list[str]) -> str | None:
    raw = rec.get("eventDate")
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        try:
            resolved = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=raw)).date()
        except OverflowError:
            warnings.append(f"unrepresentable ALA epoch-millisecond eventDate '{raw}'")
        else:
            return resolved.isoformat()
    elif isinstance(raw, str) and raw.strip():
        # Defensive: not observed in the committed data, but pass through an
        # already-ISO-shaped string verbatim rather than discarding it.
        return raw.strip()
    return _year_month_day_fallback(rec.get("year"), rec.get("month"), rec.get("day"))


def _year_month_day_fallback(year: Any, month: Any, day: Any) -> str | None:
    if year is None or year == "":
        return None
    year_str = str(int(year)) if isinstance(year, int | float) else str(year).strip()
    if not year_str.isdigit():
        return None
    month_str = str(month).strip() if month is not None else ""
    if not month_str.isdigit():
        return year_str
    day_str = str(day).strip() if day is not None else ""
    if not day_str.isdigit():
        return f"{year_str}-{int(month_str):02d}"
    return f"{year_str}-{int(month_str):02d}-{int(day_str):02d}"


def _parse_gbif_record(
    rec: dict[str, Any], *, genus_file: str, source_file_relpath: str, line_number: int
) -> _Row:
    warnings: list[str] = []
    record_id = _first_present(rec, _GBIF_RECORD_ID_HEADERS)
    taxon_id = _first_present(rec, _GBIF_TAXON_ID_HEADERS)

    media_license = None
    media = rec.get("media")
    if isinstance(media, list) and media and isinstance(media[0], dict):
        media_license = media[0].get("license")

    captive_raw = rec.get("http://unknown.org/captive_cultivated")
    is_captive = ""
    if captive_raw == "wild":
        is_captive = "false"
    elif captive_raw not in (None, ""):
        is_captive = ""
        warnings.append(f"unrecognized captive_cultivated value '{captive_raw}'")

    raw_occurrence_id = rec.get("occurrenceID")

    return _Row(
        provider="gbif",
        genus_file=genus_file,
        source_file_relpath=source_file_relpath,
        source_line_number=line_number,
        provider_record_id=str(record_id) if record_id is not None else "",
        inaturalist_obs_id=_extract_inaturalist_id(raw_occurrence_id),
        scientific_name=rec.get("scientificName"),
        accepted_name=rec.get("acceptedScientificName") or rec.get("scientificName"),
        taxon_id_raw=str(taxon_id) if taxon_id is not None else None,
        rank=rec.get("taxonRank"),
        latitude=rec.get("decimalLatitude"),
        longitude=rec.get("decimalLongitude"),
        coordinate_uncertainty_m=rec.get("coordinateUncertaintyInMeters"),
        event_date=_gbif_event_date(rec),
        basis_of_record=rec.get("basisOfRecord"),
        license=rec.get("license"),
        media_license=media_license,
        is_captive=is_captive,
        mapping_warnings=warnings,
    )


def _parse_ala_record(
    rec: dict[str, Any], *, genus_file: str, source_file_relpath: str, line_number: int
) -> _Row:
    warnings: list[str] = []
    record_id = _first_present(rec, _ALA_RECORD_ID_HEADERS)
    taxon_id = _first_present(rec, _ALA_TAXON_ID_HEADERS)
    raw_occurrence_id = rec.get("occurrenceID")

    return _Row(
        provider="ala",
        genus_file=genus_file,
        source_file_relpath=source_file_relpath,
        source_line_number=line_number,
        provider_record_id=str(record_id) if record_id is not None else "",
        inaturalist_obs_id=_extract_inaturalist_id(raw_occurrence_id),
        scientific_name=rec.get("scientificName"),
        accepted_name=rec.get("acceptedScientificName") or rec.get("scientificName"),
        taxon_id_raw=str(taxon_id) if taxon_id is not None else None,
        rank=rec.get("taxonRank"),
        latitude=rec.get("decimalLatitude"),
        longitude=rec.get("decimalLongitude"),
        coordinate_uncertainty_m=rec.get("coordinateUncertaintyInMeters"),
        event_date=_ala_event_date(rec, warnings),
        basis_of_record=rec.get("basisOfRecord") or rec.get("raw_basisOfRecord"),
        license=rec.get("license"),
        media_license=None,
        is_captive="",
        mapping_warnings=warnings,
    )


@dataclass
class _InputFileResult:
    provider: str
    genus_file: str
    relative_path: str
    sha256: str
    record_count: int
    unparseable_line_count: int
    rows: list[_Row]


def _read_jsonl_file(
    path: Path, *, provider: str, genus_file: str, parse_fn: Any
) -> _InputFileResult:
    if not path.exists():
        raise ConversionFatalError(f"required input file does not exist: {path}")

    relative_path = _relpath_or_str(path)
    hasher = hashlib.sha256()
    rows: list[_Row] = []
    record_count = 0
    unparseable_line_count = 0

    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            hasher.update(raw_line)
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                unparseable_line_count += 1
                continue
            if not isinstance(rec, dict):
                unparseable_line_count += 1
                continue
            record_count += 1
            rows.append(
                parse_fn(
                    rec,
                    genus_file=genus_file,
                    source_file_relpath=relative_path,
                    line_number=line_number,
                )
            )

    return _InputFileResult(
        provider=provider,
        genus_file=genus_file,
        relative_path=relative_path,
        sha256=hasher.hexdigest(),
        record_count=record_count,
        unparseable_line_count=unparseable_line_count,
        rows=rows,
    )


@dataclass
class _DedupOutcome:
    kept_rows: list[_Row]
    exact_duplicates: list[dict[str, Any]]
    probable_duplicates: list[dict[str, Any]]
    ambiguous_matches: list[dict[str, Any]]


def _dedupe(
    rows: list[_Row],
    *,
    coordinate_round_decimals: int,
    canonical_provider_precedence: tuple[str, ...],
) -> _DedupOutcome:
    exact_duplicates: list[dict[str, Any]] = []

    # --- Tier 1: exact same-provider duplicates -------------------------
    by_provider_identity: dict[tuple[str, str], list[_Row]] = {}
    for row in rows:
        if not row.provider_record_id:
            continue
        by_provider_identity.setdefault((row.provider, row.provider_record_id), []).append(row)

    survivors: list[_Row] = []
    dropped_ids: set[int] = set()
    for (provider, record_id), group in by_provider_identity.items():
        if len(group) == 1:
            survivors.append(group[0])
            continue
        ordered = sorted(group, key=lambda r: r.sort_key())
        kept = ordered[0]
        survivors.append(kept)
        for extra in ordered[1:]:
            dropped_ids.add(id(extra))
            exact_duplicates.append(
                {
                    "reason": "same_provider_identical_record_identity",
                    "provider": provider,
                    "provider_record_id": record_id,
                    "kept": kept.report_identity(),
                    "dropped": extra.report_identity(),
                }
            )

    # Rows without a usable provider_record_id (should not occur in the
    # committed data, but handled defensively) always survive tier 1.
    for row in rows:
        if not row.provider_record_id:
            survivors.append(row)

    def _rank(row: _Row) -> int:
        try:
            return canonical_provider_precedence.index(row.provider)
        except ValueError:
            return len(canonical_provider_precedence)

    # --- Tier 2a: cross-provider match via shared iNaturalist id --------
    by_inat_id: dict[str, list[_Row]] = {}
    for row in survivors:
        if row.inaturalist_obs_id:
            by_inat_id.setdefault(row.inaturalist_obs_id, []).append(row)

    resolved_ids: set[int] = set()
    probable_duplicates: list[dict[str, Any]] = []
    ambiguous_matches: list[dict[str, Any]] = []
    kept_after_tier2: list[_Row] = []

    for inat_id, group in by_inat_id.items():
        providers_present = {r.provider for r in group}
        if len(providers_present) < 2:
            continue
        ordered = sorted(group, key=lambda r: (_rank(r), r.sort_key()))
        canonical = ordered[0]
        for extra in ordered[1:]:
            resolved_ids.add(id(extra))
            probable_duplicates.append(
                {
                    "reason": "shared_inaturalist_observation_id",
                    "inaturalist_observation_id": inat_id,
                    "kept": canonical.report_identity(),
                    "dropped": extra.report_identity(),
                }
            )
        resolved_ids.add(id(canonical))
        kept_after_tier2.append(canonical)

    for row in survivors:
        if id(row) not in resolved_ids:
            kept_after_tier2.append(row)

    # --- Tier 2b/3: coordinate + accepted-name bucket -------------------
    buckets: dict[tuple[str, float, float], list[_Row]] = {}
    passthrough: list[_Row] = []
    for row in kept_after_tier2:
        name = row.accepted_name or row.scientific_name
        if not name or row.latitude is None or row.longitude is None:
            passthrough.append(row)
            continue
        if not isinstance(row.latitude, int | float) or not isinstance(
            row.longitude, int | float
        ):
            passthrough.append(row)
            continue
        key = (
            _normalize_name(name),
            round(float(row.latitude), coordinate_round_decimals),
            round(float(row.longitude), coordinate_round_decimals),
        )
        buckets.setdefault(key, []).append(row)

    final_kept: list[_Row] = list(passthrough)
    bucket_resolved: set[int] = set()

    for _key, group in buckets.items():
        providers_present = {r.provider for r in group}
        if len(providers_present) < 2:
            final_kept.extend(group)
            continue

        dates = {r.event_date for r in group if r.event_date}
        all_have_dates = all(r.event_date for r in group)
        dates_agree = all_have_dates and len(dates) == 1

        if dates_agree:
            ordered = sorted(group, key=lambda r: (_rank(r), r.sort_key()))
            canonical = ordered[0]
            final_kept.append(canonical)
            for extra in ordered[1:]:
                probable_duplicates.append(
                    {
                        "reason": "coordinate_and_accepted_name_bucket_matching_date",
                        "kept": canonical.report_identity(),
                        "dropped": extra.report_identity(),
                    }
                )
        else:
            final_kept.extend(group)
            ambiguous_matches.append(
                {
                    "reason": (
                        "event_date_mismatch"
                        if dates and len(dates) > 1
                        else "missing_event_date_on_one_or_more_sides"
                    ),
                    "members": [r.report_identity() for r in group],
                }
            )
        bucket_resolved.update(id(r) for r in group)

    return _DedupOutcome(
        kept_rows=final_kept,
        exact_duplicates=exact_duplicates,
        probable_duplicates=probable_duplicates,
        ambiguous_matches=ambiguous_matches,
    )


def convert(
    *,
    gbif_dir: Path,
    ala_dir: Path,
    genera: tuple[str, ...],
    output_csv: Path,
    output_report: Path,
    coordinate_round_decimals: int = _DEFAULT_COORDINATE_ROUND_DECIMALS,
    canonical_provider_precedence: tuple[str, ...] = _CANONICAL_PROVIDER_PRECEDENCE,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Run the full offline conversion and write both output files.

    Returns the conversion report as a plain dict (also written to
    ``output_report``). Raises :class:`ConversionFatalError` before any
    output file is written if a required input is missing.
    """
    generated_at = generated_at or datetime.now(UTC)

    input_results: list[_InputFileResult] = []
    for genus in genera:
        input_results.append(
            _read_jsonl_file(
                gbif_dir / f"{genus}.jsonl",
                provider="gbif",
                genus_file=genus,
                parse_fn=_parse_gbif_record,
            )
        )
        input_results.append(
            _read_jsonl_file(
                ala_dir / f"{genus}.jsonl",
                provider="ala",
                genus_file=genus,
                parse_fn=_parse_ala_record,
            )
        )

    all_rows: list[_Row] = []
    all_mapping_warnings: list[dict[str, Any]] = []
    for result in input_results:
        for row in result.rows:
            all_rows.append(row)
            for warning in row.mapping_warnings:
                all_mapping_warnings.append(
                    {
                        "provider": row.provider,
                        "source_file": row.source_file_relpath,
                        "source_line_number": row.source_line_number,
                        "provider_record_id": row.provider_record_id,
                        "message": warning,
                    }
                )

    outcome = _dedupe(
        all_rows,
        coordinate_round_decimals=coordinate_round_decimals,
        canonical_provider_precedence=canonical_provider_precedence,
    )

    emitted_rows = sorted(outcome.kept_rows, key=lambda r: r.sort_key())

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    csv_bytes = _render_csv(emitted_rows)
    output_csv.write_bytes(csv_bytes)
    output_csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()

    counts_by_provider: dict[str, int] = {}
    counts_by_target_taxon: dict[str, int] = dict.fromkeys(TF4_GENERA, 0)
    other_genus_count = 0
    license_summary: dict[str, int] = {}
    for row in emitted_rows:
        counts_by_provider[row.provider] = counts_by_provider.get(row.provider, 0) + 1
        genus = row.resolved_genus()
        if genus in counts_by_target_taxon:
            counts_by_target_taxon[genus] += 1
        else:
            other_genus_count += 1
        license_key = row.license or "(blank)"
        license_summary[license_key] = license_summary.get(license_key, 0) + 1

    total_input_records = sum(r.record_count for r in input_results)
    total_unparseable = sum(r.unparseable_line_count for r in input_results)

    report: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "conversion_profile_version": CONVERSION_PROFILE_VERSION,
        "dedup_profile_version": DEDUP_PROFILE_VERSION,
        "generated_at": generated_at.isoformat(),
        "statement": (
            "No model was trained, no fusion weight or risk threshold was "
            "calibrated, and clean_occurrences was not reimplemented. This "
            "report only reconciles offline field-mapping and pre-import "
            "deduplication counts."
        ),
        "config": {
            "gbif_dir": _relpath_or_str(gbif_dir),
            "ala_dir": _relpath_or_str(ala_dir),
            "genera": list(genera),
            "coordinate_round_decimals": coordinate_round_decimals,
            "canonical_provider_precedence": list(canonical_provider_precedence),
            "output_csv": _relpath_or_str(output_csv),
            "output_report": _relpath_or_str(output_report),
        },
        "inputs": [
            {
                "provider": r.provider,
                "genus_file": r.genus_file,
                "relative_path": r.relative_path,
                "sha256": r.sha256,
                "record_count": r.record_count,
                "unparseable_line_count": r.unparseable_line_count,
            }
            for r in input_results
        ],
        "output": {
            "relative_path": _relpath_or_str(output_csv),
            "sha256": output_csv_sha256,
            "record_count": len(emitted_rows),
            "format": "csv",
        },
        "reconciliation": {
            "total_input_records": total_input_records,
            "total_unparseable_input_lines": total_unparseable,
            "emitted_records": len(emitted_rows),
            "exact_duplicates_removed": len(outcome.exact_duplicates),
            "probable_cross_provider_duplicates_removed": len(outcome.probable_duplicates),
            "ambiguous_cross_provider_matches_flagged": sum(
                len(m["members"]) for m in outcome.ambiguous_matches
            ),
            "reconciles": (
                total_input_records
                == len(emitted_rows)
                + len(outcome.exact_duplicates)
                + len(outcome.probable_duplicates)
            ),
        },
        "counts_by_provider": counts_by_provider,
        "counts_by_target_taxon": counts_by_target_taxon,
        "other_genus_emitted_count": other_genus_count,
        "license_summary": license_summary,
        "field_mapping_warnings": all_mapping_warnings,
        "duplicate_details": {
            "exact_duplicates": outcome.exact_duplicates,
            "probable_cross_provider_duplicates": outcome.probable_duplicates,
            "ambiguous_cross_provider_matches": outcome.ambiguous_matches,
        },
    }

    output_report.parent.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    output_report.write_bytes(report_json.encode("utf-8"))

    return report


def _relpath_or_str(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _render_csv(rows: list[_Row]) -> bytes:
    import io

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_HEADER)
    for row in rows:
        writer.writerow(row.csv_row())
    return buffer.getvalue().encode("utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert committed local GBIF/ALA M2 JSONL exports into an "
            "importer-compatible generic_dwc CSV table plus a conversion "
            "report. Offline only: makes no network request."
        )
    )
    parser.add_argument("--gbif-dir", default=str(DEFAULT_GBIF_DIR))
    parser.add_argument("--ala-dir", default=str(DEFAULT_ALA_DIR))
    parser.add_argument("--genera", nargs="+", default=list(DEFAULT_GENERA))
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument(
        "--coordinate-round-decimals", type=int, default=_DEFAULT_COORDINATE_ROUND_DECIMALS
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = convert(
            gbif_dir=Path(args.gbif_dir),
            ala_dir=Path(args.ala_dir),
            genera=tuple(args.genera),
            output_csv=Path(args.output_csv),
            output_report=Path(args.output_report),
            coordinate_round_decimals=args.coordinate_round_decimals,
        )
    except ConversionFatalError as exc:
        print(f"prepare_m2_occurrence_table: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report["reconciliation"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
