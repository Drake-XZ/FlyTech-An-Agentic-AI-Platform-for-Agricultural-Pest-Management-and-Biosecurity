"""Orchestration for the offline `prepare-geo-experiment` command
(DesignSuggestionLog.md, "Proposed command" and "Processing sequence").

This module owns all file I/O: loading and validating the config, reading
and checksumming the Milestone 1.5 bundle, and atomically writing the two
output artifacts. Bundle authentication lives in
:mod:`s3_ecological.experiments.bundle_integrity`, the two-file atomic
commit/rollback lives in :mod:`s3_ecological.experiments.atomic_output_pair`,
record-counting lives in :mod:`s3_ecological.experiments.record_counts`, all
spatial-block/split math lives in
:mod:`s3_ecological.experiments.spatial_split`, and all status/reason-code
classification lives in :mod:`s3_ecological.experiments.readiness` - all four
are pure and file-I/O-free so they can be unit tested without a filesystem.

Deliberate layout deviation from the design suggestion's illustrative
sketch: this orchestration lives in a separate module, `prepare.py`, rather
than being folded into `readiness.py` or `spatial_split.py` (see
`WorkLog.md` for the recorded reason - it keeps file I/O out of the pure
modules, matching the design suggestion's own "isolate file I/O from pure
logic" requirement).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from s3_ecological.experiments.atomic_output_pair import (
    AtomicPairCommitError,
    StagedOutput,
    commit_pair_atomically,
)
from s3_ecological.experiments.bundle_integrity import BundleIntegrityError, authenticate_bundle
from s3_ecological.experiments.readiness import (
    REASON_SYNTHETIC_ENGINEERING_FIXTURE_DECLARED,
    combine_reason_codes,
    compute_occurrence_data_status,
    compute_overall_status,
    evaluate_authorisation,
    evaluate_data_quality,
    evaluate_geographic_scope,
    evaluate_s1_input,
)
from s3_ecological.experiments.record_counts import (
    counts_by_cleaning_action,
    counts_by_event_year,
    counts_by_quality_flag,
    undated_usable_record_count,
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
    must stop the command before any artifact is written (exit code 1).

    ``code`` is populated with a stable machine-readable code (e.g. one of
    ``bundle_integrity``'s ``CODE_*`` constants) when the failure originates
    from a component that provides one; it is ``None`` for failures that do
    not have a dedicated code (invalid TOML, unreadable file, and so on).
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


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

    occurrence_snapshot, occurrence_file_sha256 = _load_snapshot(
        config.occurrence_snapshot_path, OccurrenceSnapshot
    )
    taxonomy_snapshot, taxonomy_file_sha256 = _load_snapshot(
        config.taxonomy_snapshot_path, TaxonomySnapshot
    )
    import_report, import_report_file_sha256 = _load_snapshot(
        config.import_report_path, ImportReport
    )

    try:
        authenticate_bundle(
            occurrence=occurrence_snapshot,
            occurrence_file_sha256=occurrence_file_sha256,
            taxonomy=taxonomy_snapshot,
            taxonomy_file_sha256=taxonomy_file_sha256,
            import_report=import_report,
        )
    except BundleIntegrityError as exc:
        raise GeoExperimentFatalError(str(exc), code=exc.code) from exc

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

    quality_flag_counts = counts_by_quality_flag(cleaning_report.cleaned)
    cleaning_action_counts = counts_by_cleaning_action(excluded)
    event_year_counts = counts_by_event_year(usable)
    undated_usable = undated_usable_record_count(usable)

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
    geographic_scope_reasons = evaluate_geographic_scope(config.geographic_scope_mode)
    occurrence_data_status = compute_occurrence_data_status(
        data_nature=config.data_nature,
        authorisation_reasons=authorisation_reasons,
        data_quality_reasons=data_quality_reasons,
    )
    overall_status = compute_overall_status(
        occurrence_data_status=occurrence_data_status, s1_input_status=s1_input_status
    )
    reason_codes = combine_reason_codes(
        data_nature_reasons,
        authorisation_reasons,
        s1_reasons,
        data_quality_reasons,
        geographic_scope_reasons,
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
        geographic_scope_mode=config.geographic_scope_mode,
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
        geographic_scope_mode=config.geographic_scope_mode,
        occurrence_snapshot=occurrence_identity,
        taxonomy_snapshot=taxonomy_identity,
        import_report=import_report_identity,
        usable_record_count=len(usable),
        excluded_record_count=len(excluded),
        counts_by_target_taxon=counts_by_target_taxon,
        counts_by_source=counts_by_source,
        counts_by_block=split_result.counts_by_block,
        counts_by_split=split_result.counts_by_split,
        counts_by_quality_flag=quality_flag_counts,
        counts_by_cleaning_action=cleaning_action_counts,
        counts_by_exclusion_flag=cleaning_action_counts,
        counts_by_event_year=event_year_counts,
        undated_usable_record_count=undated_usable,
        earliest_usable_event_date=earliest_date,
        latest_usable_event_date=latest_date,
        missing_target_taxa=missing_target_taxa,
        warnings=warnings,
        spatial_split_manifest_path=_MANIFEST_FILENAME,
        spatial_split_manifest_sha256=manifest_sha256,
    )
    report_bytes = _serialize(report)
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()

    try:
        commit_pair_atomically(
            StagedOutput(final_path=manifest_path, data=manifest_bytes, sha256=manifest_sha256),
            StagedOutput(final_path=report_path, data=report_bytes, sha256=report_sha256),
            overwrite=overwrite,
            verify_committed=_verify_committed_output_pair,
        )
    except AtomicPairCommitError as exc:
        raise GeoExperimentFatalError(str(exc)) from exc

    SpatialSplitManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    return GeoExperimentReadinessReport.model_validate(
        json.loads(report_path.read_text(encoding="utf-8"))
    )


def _verify_committed_output_pair(manifest_bytes: bytes, report_bytes: bytes) -> None:
    """Post-commit cross-check between the two just-written files. Raising
    here triggers ``commit_pair_atomically``'s rollback of both files - this
    function must never mutate either argument or touch the filesystem."""
    try:
        manifest = SpatialSplitManifest.model_validate_json(manifest_bytes)
        report = GeoExperimentReadinessReport.model_validate_json(report_bytes)
    except ValidationError as exc:
        raise ValueError(f"post-commit schema validation failed: {exc}") from exc

    mismatched_fields = [
        label
        for label, matches in (
            ("experiment_id", manifest.experiment_id == report.experiment_id),
            (
                "configuration_digest",
                manifest.configuration_digest == report.configuration_digest,
            ),
            (
                "geographic_scope_mode",
                manifest.geographic_scope_mode == report.geographic_scope_mode,
            ),
            ("occurrence_snapshot", manifest.occurrence_snapshot == report.occurrence_snapshot),
            ("taxonomy_snapshot", manifest.taxonomy_snapshot == report.taxonomy_snapshot),
            ("import_report", manifest.import_report == report.import_report),
        )
        if not matches
    ]
    if mismatched_fields:
        raise ValueError(
            "manifest/report identity mismatch after commit: " + ", ".join(mismatched_fields)
        )

    if report.spatial_split_manifest_sha256 != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError(
            "report.spatial_split_manifest_sha256 does not match the committed manifest"
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
