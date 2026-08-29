# Design Suggestion Log

**Document status:** Append-only design history, suggestions, decisions, and implementation-increment requirements

**Related specification:** [EarlyDesign.md](EarlyDesign.md)

## Purpose and Maintenance Policy

This file contains the design history that was previously stored under `Design Change Log` at the end of `EarlyDesign.md`. The log was renamed and separated for maintainability; the move does not change the meaning, authority, date, or implementation status of any existing entry.

Apply these rules:

- This file is **append-only** and is the sole location for future S3 design suggestions, approved design changes, superseding decisions, and newly proposed implementation increments.
- Add every new entry at the physical end of this file with an Australia/Sydney date and, when available, exact time.
- State whether a new entry is a suggestion, approved requirement, implemented change, superseded decision, or non-semantic correction.
- `EarlyDesign.md` remains the consolidated normative implementation specification. When an approved entry changes its requirements, update the affected section of `EarlyDesign.md`, update its document-level `Last updated` date, and record the same change here.
- An unapproved suggestion in this file does not silently override `EarlyDesign.md`. An entry explicitly recorded as an approved requirement or owner decision retains the authority stated in that entry.
- Existing entries must never be edited, reordered, or deleted. Direct in-place edits are allowed only for non-semantic spelling, rendering, formatting, or broken-link corrections that do not alter meaning, authority, results, or timestamps.
- Create an ADR under `docs/decisions/` when a change needs additional rationale, alternatives, evidence, compatibility analysis, or rollback guidance.
- Historical entries in `WorkLog.md` that use its former filename `Work.md` or refer to the former `Design Change Log` location remain unchanged because `WorkLog.md` is also append-only; this policy supersedes those location instructions from 29 August 2026 onward.

## Entries

### 2026-08-28 — Prototype Implementation Profile v0.1

Confirmed prototype-only scope; selected PydanticAI as a replaceable optional agent layer; kept the ecological core runnable without an LLM or live API; froze the first implementation defaults, contracts, risk precedence, error semantics, and fixture acceptance requirements.

### 2026-08-28 21:27 Australia/Sydney — Append-only documentation policy

- Moved the Design Change Log from the beginning of `EarlyDesign.md` to the end so its maintenance model matches `Work.md`.
- Preserved the original Prototype Implementation Profile v0.1 change record.
- Established that every future update to `EarlyDesign.md` must be documented by appending a new timestamped subsection at the physical end of the file.
- Reconfirmed that every future update to `Work.md` must likewise be recorded as a new timestamped section at the physical end of that file; existing entries must not be rewritten or deleted except for non-semantic rendering, spelling, formatting, or broken-link corrections that do not change their meaning.

### 2026-08-28 22:52 Australia/Sydney — Next implementation increment: offline occurrence snapshot ingestion

#### Decision and priority

The next S3 implementation task is **Milestone 1.5: offline occurrence snapshot ingestion**. Complete it before starting a learned geographic prior, environmental-suitability model, live GBIF/ALA adapter, FastAPI service, or external LLM integration.

Convert a user-supplied, previously downloaded occurrence export into a deterministic local snapshot bundle that the existing S3 pipeline can query with networking disabled. The bundle must contain:

1. a canonical occurrence snapshot;
2. a compatible local taxonomy snapshot, so candidate names resolve to the same identifiers used by occurrence records;
3. a machine-readable import report with provenance, checksums, mappings, counts, row-level rejections, and licence information.

This increment extends ingestion only. It must not change Profile v0.1 scoring, fusion, risk precedence, uncertainty, thresholds, or golden-fixture expectations.

#### Required outcome

A user must be able to place a small GBIF, ALA, or generic Darwin Core-compatible CSV/TSV export on disk, run one CLI command, and then use the generated snapshots with the existing `assess` command. Both commands must work with `S3_LLM_ENABLED=false`, no API key, no network, and no live provider.

```text
offline export -> validation/import -> occurrence + taxonomy + report
-> local providers -> existing cleaning -> existing geo support
-> existing fusion -> existing risk and review policy
```

The importer must never calculate ecological support, rerank candidates, or assign risk. Those responsibilities remain in the deterministic core.

#### Scope and non-goals

Required:

- local files only;
- UTF-8 CSV, UTF-8 TSV, and canonical JSON;
- source profiles `gbif`, `ala`, and `generic_dwc`;
- the four TF4 genera for acceptance tests;
- deterministic mapping, validation, ID namespacing, checksums, reports, and provider integration;
- transparent malformed-row handling;
- small synthetic importer fixtures committed to the repository.

Out of scope:

- HTTP, downloads, APIs, or credentials;
- direct extraction of a Darwin Core Archive ZIP; provide its occurrence table as CSV, TSV, or `occurrence.txt`;
- remote taxonomy lookup or silent taxon guessing;
- changes to formulas, thresholds, model training, or biological-performance claims;
- non-S3 agents, the orchestrator, or a UI;
- committing large or unapproved third-party datasets.

#### File boundaries

```text
src/s3_ecological/ingestion/{__init__.py,occurrence_snapshot.py}
src/s3_ecological/schemas/snapshot.py
src/s3_ecological/providers/taxonomy_local_snapshot.py
tests/fixtures/importer/{gbif_small.csv,ala_small.tsv,malformed_rows.csv}
tests/unit/test_occurrence_snapshot_import.py
tests/integration/test_imported_snapshot_pipeline.py
docs/data_cards/offline_occurrence_snapshot_v1.md
```

Extend `providers/occurrence_local_snapshot.py` as needed. Existing `RawOccurrenceRecord`, provider Protocols, `run_assessment`, `clean_occurrences`, geographic prior, fusion, and risk modules remain authoritative. Do not duplicate their logic.


#### CLI contract

Add:

```text
s3-ecological import-occurrences \
  --input <source.csv|source.tsv|occurrence.txt|canonical.json> \
  --source <gbif|ala|generic_dwc|canonical> \
  --dataset-id <non-empty-versioned-id> \
  --retrieved-at <ISO-8601 timestamp with timezone> \
  --dataset-license <non-empty licence identifier or URL> \
  --citation <non-empty source citation> \
  --query-parameters-json <optional-JSON-object-file> \
  --output-dir <directory>
```

The `python -m s3_ecological.cli` form must also work. Every option except `--query-parameters-json` is mandatory. `.csv` is comma-delimited; `.tsv` and `occurrence.txt` are tab-delimited. Do not infer delimiters. Reject retrieval timestamps without a timezone offset or `Z`.

`--query-parameters-json` is optional and defaults to `{}`. When supplied, its file must contain one JSON object; arrays, scalars, malformed JSON, and keys with secret-like names such as `token`, `password`, or `api_key` are rejected.

A `.json` input requires `--source canonical`, must validate as snapshot schema `1.0.0`, and is never silently upgraded from the legacy `{dataset_id, records}` shape. Its dataset ID, retrieval time, licence, citation, and source must exactly match the CLI metadata; a mismatch is fatal. Preserve each canonical record's already namespaced taxon ID and derive `taxonomy.json` deterministically from its records.

Create `occurrences.json`, `taxonomy.json`, and `import-report.json`. Refuse existing targets unless `--overwrite` is supplied. `--overwrite` may replace only those three exact files and must never clear a directory. Use same-directory temporary files and atomic replacement after validation.

| Exit | Meaning |
|---:|---|
| `0` | Completed with no rejected rows |
| `2` | Completed with accepted and rejected rows; report contains details |
| `1` | Fatal failure; no final bundle remains |

#### Versioned output schemas

Create Pydantic v2 models and export their JSON Schemas through `scripts/export_json_schemas.py`.

`occurrences.json` must contain:

```json
{
  "snapshot_schema_version": "1.0.0",
  "dataset_id": "gbif-tf4-demo-2026-08-28",
  "source": "gbif",
  "retrieved_at": "2026-08-28T10:00:00Z",
  "dataset_license": "CC BY 4.0",
  "citation": "User-supplied citation",
  "source_sha256": "64 lowercase hexadecimal characters",
  "mapping_version": "dwc-occurrence-v1",
  "snapshot_key": "deterministic value",
  "query_parameters": {},
  "records": []
}
```

Every record must validate as the existing `RawOccurrenceRecord`. Command metadata must populate each record's source, dataset ID, query parameters, and snapshot key; rows cannot override it.

`taxonomy.json` must contain:

```json
{
  "snapshot_schema_version": "1.0.0",
  "dataset_id": "gbif-tf4-demo-2026-08-28",
  "source": "gbif",
  "source_sha256": "the same source-file checksum",
  "mapping_version": "dwc-taxonomy-v1",
  "taxa": []
}
```

Each taxon must contain `submitted_names`, `scientific_name`, optional `rank`, `taxon_ids`, optional `synonym_of`, and `ambiguous`. Multiple accepted taxa for one normalized submitted name must remain ambiguous.

`import-report.json` must contain:

- report schema version and all command metadata;
- importer package version and mapping versions;
- input filename without its absolute path;
- source SHA-256, UTC start time, and UTC completion time;
- encoding and delimiter;
- input, accepted, and rejected record counts;
- counts by canonical taxon ID and rejection code;
- the exact source-to-canonical field mapping;
- one rejection item per rejected row with one-based data-row number, stable code, optional field name, and redacted message;
- output filenames and SHA-256 checksums;
- status `completed` or `completed_with_rejections`; fatal runs emit a concise stderr error and leave no report file.

Never copy a full rejected source row into the report.

#### Deterministic field mapping

Trim header names and string values. Header matching is case-sensitive after trimming. Empty strings become `null`. Use the first present, non-empty field in each ordered list:

| Canonical field | `gbif` | `ala` | `generic_dwc` |
|---|---|---|---|
| source record ID | `occurrenceID`, `gbifID` | `occurrenceID`, `id` | `occurrenceID`, `id` |
| raw scientific name | `scientificName` | `scientificName` | `scientificName` |
| accepted name | `acceptedScientificName`, `scientificName` | `acceptedScientificName`, `scientificName` | `acceptedScientificName`, `scientificName` |
| source taxon ID | `acceptedTaxonKey`, `taxonKey`, `taxonID` | `acceptedConceptID`, `taxonConceptID`, `taxonID` | `taxonID` |
| rank | `taxonRank` | `taxonRank` | `taxonRank` |
| latitude | `decimalLatitude` | `decimalLatitude` | `decimalLatitude` |
| longitude | `decimalLongitude` | `decimalLongitude` | `decimalLongitude` |
| uncertainty | `coordinateUncertaintyInMeters` | `coordinateUncertaintyInMeters` | `coordinateUncertaintyInMeters` |
| event date | `eventDate`, then date components | `eventDate`, then date components | `eventDate`, then date components |
| basis | `basisOfRecord` | `basisOfRecord` | `basisOfRecord` |
| record licence | `license` | `license` | `license` |
| media licence | `mediaLicense` | `mediaLicense` | `mediaLicense` |
| captive/cultivated | `isCaptive`, `isCultivated` | `isCaptive`, `isCultivated` | `isCaptive`, `isCultivated` |

Mapping rules:

1. `scientificName` and a source taxon ID are required for an accepted row.
2. Prefix the source taxon ID with `gbif:`, `ala:`, or `generic_dwc:`; do not double-prefix an already namespaced ID.
3. If source record ID is missing, use `generated:` plus the SHA-256 of a compact UTF-8 JSON object containing every trimmed header mapped to its trimmed value or `null`, with keys sorted lexicographically. Record that action. Never include row number because reordering must not change identity.
4. Command-level metadata is authoritative and cannot be replaced by row values.
5. Use row-level `license` when present; otherwise use `--dataset-license`.
6. Both coordinates may be blank and become `null`; the existing cleaner will retain but exclude that evidence from distance scoring.
7. Numeric out-of-range coordinates may be imported unchanged for the existing cleaner to flag. Reject non-empty non-numeric coordinates.
8. Uncertainty may be blank. A non-empty value must be finite and greater than or equal to zero.
9. Preserve `eventDate` after trimming. From components construct only `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` from contiguous available values. Never invent month or day.
10. Accepted Boolean spellings are case-insensitive `true`, `false`, `1`, `0`, `yes`, and `no`. An unrecognized non-empty value becomes `null` and creates a non-fatal mapping warning.
11. Preserve occurrence input order. Sort taxonomy items by canonical taxon ID and submitted names by normalized name.
12. Serialize as UTF-8 with stable key ordering, deterministic indentation, and a trailing newline. Identical input bytes and command metadata must produce byte-identical occurrence and taxonomy files.


#### Failure semantics

Fatal failures return exit code `1` and leave no final bundle:

- missing, unreadable, or non-UTF-8 input;
- unsupported extension/source combination;
- duplicate headers after trimming;
- missing `scientificName` header;
- no supported source taxon ID header;
- invalid command metadata;
- canonical JSON schema failure;
- an existing target without `--overwrite`;
- zero accepted records;
- unwritable output directory;
- output validation or checksum verification failure.

Stable row-rejection codes are `missing_scientific_name`, `missing_taxon_id`, `invalid_numeric_value`, `negative_coordinate_uncertainty`, `non_finite_numeric_value`, and `invalid_record_schema`.

One row may report multiple field errors but counts as one rejected row. Rejected rows never enter either snapshot. Duplicates are not importer rejections: preserve them so `clean_occurrences` remains the sole authority for duplicate evidence.

#### Snapshot identity and checksums

Calculate `source_sha256` from exact input bytes before parsing. Define:

```text
snapshot_key = <dataset-id>:<first-12-source-sha256-characters>:<mapping-version>
```

Calculate checksums for final occurrence and taxonomy files, store them in the report, then read the files back and verify them before success. Do not self-embed a checksum for the report.

#### Offline taxonomy provider

Implement `LocalSnapshotTaxonomyProvider` against the existing Protocol and select it with:

```text
taxonomy_provider = "local_snapshot"
taxonomy_snapshot_path = "<path-to-taxonomy.json>"
```

Add `taxonomy_snapshot_path: str | None` to `S3Settings` and require it only for this provider.

Resolution rules:

1. normalize with Unicode normalization, trimming, whitespace collapse, and case folding;
2. exact normalized-name matching only;
3. one match returns `success`;
4. multiple matches return `partial`, mark ambiguity, and list all stable matches;
5. no match returns the existing `taxon_not_found` warning;
6. never call a remote service or silently fall back to fixture taxonomy.

Occurrence and taxonomy snapshots must share `dataset_id` and `source_sha256`. Every occurrence `taxon_id` must exactly equal a value present in one taxonomy item's `taxon_ids` mapping; unused taxonomy entries are allowed. Add one shared `validate_local_snapshot_bundle(settings)` helper in `providers/factory.py`, and call it from both provider builders whenever both selected providers are `local_snapshot`. Construction must fail clearly on a mismatch. Preserve the existing ability to use a legacy occurrence-only snapshot with a non-local taxonomy provider.

#### Configuration and use

Extend `config/sources.example.toml` with:

```toml
occurrence_provider = "local_snapshot"
occurrence_snapshot_path = "data/snapshots/example/occurrences.json"
taxonomy_provider = "local_snapshot"
taxonomy_snapshot_path = "data/snapshots/example/taxonomy.json"
```

README must show a complete offline workflow. If `assess` does not accept `--config`, add it and load TOML through `S3Settings.load`; generated snapshots must be usable without custom Python wiring.

#### Tests

All tests must run without networking and without optional `agent` or `api` dependencies.

Unit tests must cover every source profile and field fallback; CSV, TSV, `occurrence.txt`, and canonical JSON; UTF-8 names; empty-to-null mapping; namespacing; generated IDs; partial dates; numeric and Boolean parsing; deterministic ordering and serialization; every fatal and row error; overwrite behavior; duplicate preservation; and Pydantic validation of all outputs.

One integration test must:

1. import synthetic GBIF data for the four TF4 genera;
2. construct both local providers through the factory and TOML settings;
3. submit an `ObservationRequest` containing display names rather than pre-resolved IDs;
4. prove names resolve to IDs used by imported occurrences;
5. run unchanged `run_assessment` logic;
6. verify evidence provenance, licence, query parameters, snapshot key, and cleaning flags;
7. prove malformed rows appear only in the report;
8. prove duplicates are imported and later flagged by the existing cleaner;
9. fail if any network function is called;
10. prove repeated imports create byte-identical occurrence and taxonomy snapshots.

Existing tests must retain their meaning and pass. Add public models to schema export and preserve the deterministic-core import boundary.

#### Acceptance and work record

The builder must run and record actual results for:

```text
pytest
ruff check .
pyright
python scripts/export_json_schemas.py
python -m s3_ecological.cli import-occurrences <synthetic-test-options>
python -m s3_ecological.cli assess --config <generated-test-config> --input <test-request> --output -
```

Append a timestamped `Work.md` entry containing implementation order, files, mappings, decisions, actual test results, usage, limitations, extension instructions, and confirmation that no network, API, LLM, or biological-performance claim was used.

#### Definition of done for Milestone 1.5

- [ ] One documented command imports GBIF-, ALA-, and generic Darwin Core-compatible local tables.
- [ ] No network or credential is required.
- [ ] All three outputs validate against versioned schemas.
- [ ] Occurrence and taxonomy identifiers work together end to end.
- [ ] Generated snapshots work through existing provider Protocols and factory.
- [ ] Evidence retains provenance, licence, checksum, and snapshot identity.
- [ ] Fatal writes are atomic and partial row rejection is transparent.
- [ ] The existing cleaner remains authoritative for ecological usability and duplicates.
- [ ] Profile v0.1 scoring, fusion, thresholds, and risk semantics are unchanged.
- [ ] Offline import-to-assessment integration passes.
- [ ] All pre-existing tests, `ruff`, and `pyright` pass.
- [ ] README, configuration, schemas, data card, and `Work.md` are updated.
- [ ] No large or unapproved real dataset is committed.
- [ ] No result is described as biological validation, absence evidence, or incursion probability.

After completion, proceed to Milestone 2 only if authorised occurrence data and compatible S1 outputs are available. Otherwise record `not_run_missing_authorised_data`; do not substitute synthetic metrics or start threshold calibration.

### 2026-08-29 16:37 Australia/Sydney — Design log separation and rename

- Renamed `Design Change Log` to `Design Suggestion Log`.
- Moved the complete historical log out of `EarlyDesign.md` into the new root-level `DesignSuggestionLog.md` file.
- Preserved all prior entries without changing their meaning, timestamps, authority, or implementation status.
- Established `DesignSuggestionLog.md` as the only append-only location for future design suggestions and design-change records.
- Kept `EarlyDesign.md` as the consolidated normative build specification and added an explicit link to this file.
- This organizational change does not modify S3 code, formulas, thresholds, provider behavior, schemas, or acceptance criteria.

### 2026-08-29 16:49 Australia/Sydney - Work log file rename

- Status: owner-approved non-semantic documentation-organization change.
- Renamed `Work.md` to `WorkLog.md` while preserving all historical content and all existing append-only maintenance requirements.
- Historical entries that mention `Work.md` remain unchanged and refer to the same file before its rename.
- Updated current documentation references to use `WorkLog.md`; all future implementation records must be appended there.
- This rename does not modify any S3 functional requirement, code, schema, formula, threshold, test, provider, or acceptance criterion.
