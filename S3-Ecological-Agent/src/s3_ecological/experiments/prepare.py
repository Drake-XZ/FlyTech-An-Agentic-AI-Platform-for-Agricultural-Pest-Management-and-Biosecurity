"""Orchestration for the offline `prepare-geo-experiment` command
(DesignSuggestionLog.md, "Proposed command" and "Processing sequence").

This module owns all file I/O: loading and validating the config, reading
and checksumming the Milestone 1.5 bundle, and atomically writing the two
output artifacts. All spatial-block/split math lives in
:mod:`s3_ecological.experiments.spatial_split`, and all status/reason-code
classification lives in :mod:`s3_ecological.experiments.readiness` - both
are pure and file-I/O-free so they can be unit tested without a filesystem.

Deliberate layout deviation from the design suggestion's illustrative
sketch: this orchestration lives in a third module, `prepare.py`, rather
than being folded into `readiness.py` or `spatial_split.py` (see
`WorkLog.md` for the recorded reason - it keeps file I/O out of both pure
modules, matching the design suggestion's own "isolate file I/O from pure
logic" requirement).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from s3_ecological.experiments.readiness import (
    REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED,
    combine_reason_codes,
    compute_occurrence_data_status,
    compute_overall_status,
    evaluate_authorisation,
    evaluate_data_quality,
    evaluate_s1_input,
)
from s3_ecological.experiments.spatial_split import (
    LatitudeLongitudeGridV0,
    OccurrenceForSplit,
    SplitRatios,
    assign_records_to_splits,
    compute_split_identity,
)
from s3_ecological.occurrence.cleaning import FLAG_INVALID_EVENT_DATE, clean_occurrences
from s3_ecological.providers.factory import validate_local_snapshot_bundle
from s3_ecological.schemas.experiment import (
    DataNature,
    ExcludedOccurrenceEntry,
    GeoExperimentConfig,
    GeoExperimentReadinessReport,
    ImportReportIdentity,
    OccurrenceSnapshotIdentity,
    SpatialSplitManifest,
    SplitAssignmentRow,
    SplitName,
    TaxonomySnapshotIdentity,
)
from s3_ecological.schemas.snapshot import ImportReport, OccurrenceSnapshot, TaxonomySnapshot
from s3_ecological.settings import S3Settings

_MANIFEST_FILENAME = "spatial-split-manifest.json"
_REPORT_FILENAME = "readiness-report.json"


class GeoExperimentFatalError(Exception):
    """A config, schema, checksum, I/O, or bundle-consistency failure that
    must stop the command before any artifact is written (exit code 1)."""


def prepare_geo_experiment(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> GeoExperimentReadinessReport:
    """Run the full offline readiness/spatial-split build and return the
    validated readiness report. Never trains a model, calibrates a fusion
    weight or risk threshold, or claims a biological performance result."""
    config = _load_config(Path(config_path))
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    manifest_path = output_path / _MANIFEST_FILENAME
    report_path = output_path / _REPORT_FILENAME
    if not overwrite:
        existing = [p.name for p in (manifest_path, report_path) if p.exists()]
        if existing:
            raise GeoExperimentFatalError(
                "refusing to overwrite existing artifact(s) without --overwrite: "
                + ", ".join(existing)
            )

    occurrence_snapshot, occurrence_file_sha256 = _load_snapshot(
        config.occurrence_snapshot_path, OccurrenceSnapshot
    )
    taxonomy_snapshot, taxonomy_file_sha256 = _load_snapshot(
        config.taxonomy_snapshot_path, TaxonomySnapshot
    )
    import_report, import_report_file_sha256 = _load_snapshot(
        config.import_report_path, ImportReport
    )

    if (
        import_report.dataset_id != occurrence_snapshot.dataset_id
        or import_report.source_sha256 != occurrence_snapshot.source_sha256
    ):
        raise GeoExperimentFatalError(
            "import-report.json does not share dataset_id/source_sha256 with occurrences.json"
        )

    settings_overrides: dict[str, Any] = dict(config.settings_overrides)
    settings_overrides.update(
        {
            "occurrence_provider": "local_snapshot",
            "occurrence_snapshot_path": str(Path(config.occurrence_snapshot_path)),
            "taxonomy_provider": "local_snapshot",
            "taxonomy_snapshot_path": str(Path(config.taxonomy_snapshot_path)),
        }
    )
    try:
        settings = S3Settings.load(overrides=settings_overrides)
    except ValidationError as exc:
        raise GeoExperimentFatalError(f"invalid effective settings: {exc}") from exc

    try:
        validate_local_snapshot_bundle(settings)
    except ValueError as exc:
        raise GeoExperimentFatalError(f"snapshot bundle consistency check failed: {exc}") from exc

    genus_by_taxon_id = _genus_by_taxon_id(taxonomy_snapshot)
    target_taxa_set = set(config.target_taxa)
    in_scope_records = [
        record
        for record in occurrence_snapshot.records
        if genus_by_taxon_id.get(record.taxon_id) in target_taxa_set
    ]

    cleaning_report = clean_occurrences(in_scope_records, settings)
    usable = cleaning_report.usable
    excluded = [item for item in cleaning_report.cleaned if not item.usable_for_distance]

    split_records: list[OccurrenceForSplit] = []
    for item in usable:
        latitude, longitude = item.record.latitude, item.record.longitude
        if latitude is None or longitude is None:
            raise GeoExperimentFatalError(
                "cleaner marked a record usable_for_distance without coordinates"
            )
        split_records.append(
            OccurrenceForSplit(
                source=item.record.source,
                source_record_id=item.record.source_record_id,
                taxon_id=item.record.taxon_id,
                latitude=latitude,
                longitude=longitude,
            )
        )

    strategy = LatitudeLongitudeGridV0(grid_size_degrees=config.spatial_split.grid_size_degrees)
    ratios = SplitRatios(
        train=config.spatial_split.train_ratio,
        validation=config.spatial_split.validation_ratio,
        test=config.spatial_split.test_ratio,
    )
    split_result = assign_records_to_splits(
        split_records, strategy=strategy, ratios=ratios, seed=config.spatial_split.seed
    )
    split_identity = compute_split_identity(
        strategy=strategy, ratios=ratios, seed=config.spatial_split.seed
    )

    rows = [
        SplitAssignmentRow(
            source=assignment.occurrence.source,
            source_record_id=assignment.occurrence.source_record_id,
            taxon_id=assignment.occurrence.taxon_id,
            block_id=assignment.block_id,
            split=assignment.split,
        )
        for assignment in split_result.assignments
    ]
    rows.sort(
        key=lambda row: (
            row.split.value,
            row.block_id,
            row.taxon_id,
            row.source,
            row.source_record_id or "",
        )
    )

    excluded_entries = [
        ExcludedOccurrenceEntry(
            source=item.record.source,
            source_record_id=item.record.source_record_id,
            taxon_id=item.record.taxon_id,
            quality_flags=list(item.quality_flags),
            cleaning_actions=list(item.cleaning_actions),
        )
        for item in excluded
    ]
    excluded_entries.sort(key=lambda e: (e.taxon_id, e.source, e.source_record_id or ""))

    counts_by_target_taxon = {taxon: 0 for taxon in config.target_taxa}
    counts_by_source: dict[str, int] = {}
    for item in usable:
        genus = genus_by_taxon_id.get(item.record.taxon_id)
        if genus in counts_by_target_taxon:
            counts_by_target_taxon[genus] += 1
        counts_by_source[item.record.source] = counts_by_source.get(item.record.source, 0) + 1

    counts_by_exclusion_flag: dict[str, int] = {}
    for item in excluded:
        for action in item.cleaning_actions:
            counts_by_exclusion_flag[action] = counts_by_exclusion_flag.get(action, 0) + 1

    required_splits = [
        split
        for split, ratio in (
            (SplitName.TRAIN, config.spatial_split.train_ratio),
            (SplitName.VALIDATION, config.spatial_split.validation_ratio),
            (SplitName.TEST, config.spatial_split.test_ratio),
        )
        if ratio > 0
    ]

    earliest_date, latest_date = _earliest_and_latest_event_dates(usable)
    missing_target_taxa = [
        taxon for taxon in config.target_taxa if counts_by_target_taxon.get(taxon, 0) == 0
    ]

    data_nature_reasons = (
        [REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED]
        if config.data_nature is DataNature.SYNTHETIC_ENGINEERING_FIXTURE
        else []
    )
    authorisation_reasons = evaluate_authorisation(config.authorisation)
    s1_input_status, s1_reasons = evaluate_s1_input(
        s1_evaluation_input_path=config.s1_evaluation_input_path, data_nature=config.data_nature
    )
    data_quality_reasons = evaluate_data_quality(
        usable_record_count=len(usable),
        counts_by_target_taxon=counts_by_target_taxon,
        target_taxa=config.target_taxa,
        counts_by_block=split_result.counts_by_block,
        counts_by_split=split_result.counts_by_split,
        required_splits=required_splits,
    )
    occurrence_data_status = compute_occurrence_data_status(
        data_nature=config.data_nature,
        authorisation_reasons=authorisation_reasons,
        data_quality_reasons=data_quality_reasons,
    )
    overall_status = compute_overall_status(
        occurrence_data_status=occurrence_data_status, s1_input_status=s1_input_status
    )
    reason_codes = combine_reason_codes(
        data_nature_reasons, authorisation_reasons, s1_reasons, data_quality_reasons
    )

    warnings = _build_warnings(
        data_nature=config.data_nature,
        missing_target_taxa=missing_target_taxa,
        single_block=len(split_result.counts_by_block) <= 1 and bool(usable),
        s1_missing=s1_input_status.value == "missing",
    )

    configuration_digest = _configuration_digest(config, settings)
    occurrence_identity = OccurrenceSnapshotIdentity(
        dataset_id=occurrence_snapshot.dataset_id,
        source=occurrence_snapshot.source,
        source_sha256=occurrence_snapshot.source_sha256,
        snapshot_key=occurrence_snapshot.snapshot_key,
        dataset_license=occurrence_snapshot.dataset_license,
        citation=occurrence_snapshot.citation,
        retrieved_at=occurrence_snapshot.retrieved_at,
        mapping_version=occurrence_snapshot.mapping_version,
        file_sha256=occurrence_file_sha256,
    )
    taxonomy_identity = TaxonomySnapshotIdentity(
        dataset_id=taxonomy_snapshot.dataset_id,
        source=taxonomy_snapshot.source,
        source_sha256=taxonomy_snapshot.source_sha256,
        mapping_version=taxonomy_snapshot.mapping_version,
        file_sha256=taxonomy_file_sha256,
    )
    import_report_identity = ImportReportIdentity(
        dataset_id=import_report.dataset_id,
        source_sha256=import_report.source_sha256,
        importer_version=import_report.importer_version,
        file_sha256=import_report_file_sha256,
    )

    effective_cleaning_settings = settings.model_dump(mode="json")

    manifest = SpatialSplitManifest(
        experiment_id=config.experiment_id,
        created_at=config.generated_at,
        occurrence_snapshot=occurrence_identity,
        taxonomy_snapshot=taxonomy_identity,
        import_report=import_report_identity,
        configuration_digest=configuration_digest,
        effective_cleaning_settings=effective_cleaning_settings,
        target_taxa=list(config.target_taxa),
        geographic_scope=config.geographic_scope,
        block_strategy=strategy.name,
        block_strategy_version=strategy.version,
        grid_size_degrees=config.spatial_split.grid_size_degrees,
        train_ratio=config.spatial_split.train_ratio,
        validation_ratio=config.spatial_split.validation_ratio,
        test_ratio=config.spatial_split.test_ratio,
        seed=config.spatial_split.seed,
        split_identity=split_identity,
        rows=rows,
        excluded_records=excluded_entries,
    )
    manifest_bytes = _serialize(manifest)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_tmp = _write_temp(manifest_path, manifest_bytes)

    report = GeoExperimentReadinessReport(
        experiment_id=config.experiment_id,
        generated_at=config.generated_at,
        occurrence_data_status=occurrence_data_status,
        s1_input_status=s1_input_status,
        overall_milestone_2_status=overall_status,
        reason_codes=reason_codes,
        authorisation=config.authorisation,
        configuration_digest=configuration_digest,
        effective_cleaning_settings=effective_cleaning_settings,
        occurrence_snapshot=occurrence_identity,
        taxonomy_snapshot=taxonomy_identity,
        import_report=import_report_identity,
        usable_record_count=len(usable),
        excluded_record_count=len(excluded),
        counts_by_target_taxon=counts_by_target_taxon,
        counts_by_source=counts_by_source,
        counts_by_block=split_result.counts_by_block,
        counts_by_split=split_result.counts_by_split,
        counts_by_exclusion_flag=counts_by_exclusion_flag,
        earliest_usable_event_date=earliest_date,
        latest_usable_event_date=latest_date,
        missing_target_taxa=missing_target_taxa,
        warnings=warnings,
        spatial_split_manifest_path=_MANIFEST_FILENAME,
        spatial_split_manifest_sha256=manifest_sha256,
    )
    report_bytes = _serialize(report)
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    report_tmp = _write_temp(report_path, report_bytes)

    _verify_and_commit(manifest_tmp, manifest_path, manifest_sha256)
    _verify_and_commit(report_tmp, report_path, report_sha256)

    SpatialSplitManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    return GeoExperimentReadinessReport.model_validate(
        json.loads(report_path.read_text(encoding="utf-8"))
    )


def _load_config(path: Path) -> GeoExperimentConfig:
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except OSError as exc:
        raise GeoExperimentFatalError(f"cannot read config '{path}': {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise GeoExperimentFatalError(f"invalid TOML in config '{path}': {exc}") from exc
    try:
        return GeoExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        raise GeoExperimentFatalError(f"invalid geo-experiment config '{path}': {exc}") from exc


def _load_snapshot(path_str: str, model: type[BaseModel]) -> tuple[Any, str]:
    path = Path(path_str)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise GeoExperimentFatalError(f"cannot read required input '{path}': {exc}") from exc
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise GeoExperimentFatalError(f"invalid JSON in '{path}': {exc}") from exc
    try:
        return model.model_validate(payload), file_sha256
    except ValidationError as exc:
        raise GeoExperimentFatalError(f"invalid schema in '{path}': {exc}") from exc


def _genus_by_taxon_id(taxonomy_snapshot: TaxonomySnapshot) -> dict[str, str]:
    """The first whitespace-delimited token of each taxon's scientific name,
    since every taxonomy fixture/import used so far is species-level (e.g.
    "Bactrocera dorsalis")."""
    genus_by_taxon_id: dict[str, str] = {}
    for item in taxonomy_snapshot.taxa:
        genus = item.scientific_name.split()[0]
        for taxon_id in item.taxon_ids.values():
            genus_by_taxon_id[taxon_id] = genus
    return genus_by_taxon_id


def _earliest_and_latest_event_dates(usable: list[Any]) -> tuple[str | None, str | None]:
    dated = [
        (item.record.event_date, _event_date_sort_key(item.record.event_date))
        for item in usable
        if item.record.event_date is not None and FLAG_INVALID_EVENT_DATE not in item.quality_flags
    ]
    if not dated:
        return None, None
    earliest = min(dated, key=lambda pair: pair[1])[0]
    latest = max(dated, key=lambda pair: pair[1])[0]
    return earliest, latest


def _event_date_sort_key(value: str) -> tuple[int, int, int]:
    parts = value.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return (year, month, day)


def _build_warnings(
    *,
    data_nature: DataNature,
    missing_target_taxa: list[str],
    single_block: bool,
    s1_missing: bool,
) -> list[str]:
    warnings = [
        "latitude_longitude_grid_v0.1 cells are equal-angle, not equal-area, and are "
        "not a production ecological-region definition."
    ]
    if data_nature is DataNature.SYNTHETIC_ENGINEERING_FIXTURE:
        warnings.append(
            "This run consumes a synthetic engineering fixture; results are for "
            "interface/engineering validation only, not a real ecological or "
            "biosecurity finding."
        )
    if missing_target_taxa:
        warnings.append(
            "No usable occurrences for target genera: " + ", ".join(missing_target_taxa) + "."
        )
    if single_block:
        warnings.append(
            "All usable occurrences fall in a single spatial block; spatial holdout "
            "evaluation is not meaningful yet."
        )
    if s1_missing:
        warnings.append(
            "No S1 identification output was supplied; Milestone 2 fusion evaluation "
            "cannot run yet."
        )
    return warnings


def _configuration_digest(config: GeoExperimentConfig, settings: S3Settings) -> str:
    payload = {
        "geo_experiment_config": config.model_dump(mode="json"),
        "effective_cleaning_settings": settings.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _serialize(model: BaseModel) -> bytes:
    """Deterministic UTF-8 JSON: stable (field-declaration) key order, fixed
    indentation, trailing newline - matches the Milestone 1.5 importer's
    convention so identical inputs always produce identical bytes."""
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
            raise GeoExperimentFatalError(
                f"checksum verification failed for '{final_path.name}' after write"
            )
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
