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

### 2026-08-29 17:16 Australia/Sydney - Suggested next increment: offline pre-Milestone 2 data-readiness and spatial-split builder

**Status:** Owner-requested design suggestion; not yet implemented. This entry does not amend the normative requirements in `EarlyDesign.md` and does not authorise learned-model training, threshold calibration, or biological-performance claims.

#### Decision boundary

The next proposed engineering increment is a **pre-Milestone 2 readiness tool**, not Milestone 2 model training. It prepares an authorised local occurrence bundle for a later geographic-prior experiment and reports exactly why the experiment is ready or blocked.

This increment is deliberately allowed to run without S1 or any other FlyTech agent. It must preserve the existing rule that full Milestone 2 evaluation cannot proceed until both authorised occurrence data and compatible S1 outputs are available. When S1 outputs are absent, the tool may complete data preparation but must set `overall_milestone_2_status = "not_run_missing_authorised_data"` and include the more specific reason code `missing_authorised_s1_outputs`.

Do not implement an environmental-suitability model, live GBIF/ALA provider, external API call, LLM workflow, S1 model, S5 workflow, learned geographic prior, fusion-weight calibration, risk-threshold calibration, or incursion classifier in this increment.

#### Objective

Implement one deterministic offline command that:

1. validates an existing Milestone 1.5 occurrence/taxonomy snapshot bundle;
2. records the project owner's data-authorisation declaration without inferring authorisation from public availability;
3. applies the existing occurrence-cleaning rules;
4. summarizes usable data for the four genus-level TF4 targets;
5. assigns usable records to non-overlapping spatial blocks and deterministic train, validation, and test splits;
6. writes versioned, machine-readable split and readiness artifacts; and
7. reports missing authorised data, missing scope decisions, or missing S1 outputs without inventing substitutes.

The target genera remain `Anastrepha`, `Bactrocera`, `Ceratitis`, and `Rhagoletis`. Supporting a configurable subset is acceptable for engineering tests, but the report must state which target genera are absent.

#### Required local inputs

The command must accept a TOML configuration and local paths only:

- the existing `occurrences.json` snapshot;
- the matching `taxonomy.json` snapshot;
- the matching `import-report.json`;
- a declared target-taxon list, defaulting to the four TF4 genera;
- a declared geographic scope such as `australia`, `global`, or an owner-defined region identifier;
- a data-authorisation status;
- spatial-block and split settings;
- an explicit RFC 3339 `generated_at` timestamp used for both artifact time fields so identical inputs can be reproduced; and
- an optional path reserved for future S1 evaluation inputs.

Load all cleaning-related configuration through the existing `S3Settings` model. Record the effective cleaning settings and a canonical configuration digest in both output artifacts; do not duplicate or silently override Profile v0.1 cleaning thresholds in the experiment package.

Use these authorisation values:

- `authorised`: the project owner or an authorised supervisor has approved this dataset for the stated prototype experiment;
- `not_authorised`: use is explicitly disallowed;
- `unknown`: approval has not been confirmed.

An `authorised` declaration must include a non-empty `authorisation_reference`, the declared purpose, and the approving role or source. The software records this declaration but does not certify its legal correctness. A public licence alone must never be silently converted to project authorisation.

For every input file, retain its path-independent SHA-256 digest, schema version, dataset ID, snapshot key, source digest, licence, citation, retrieval time, and mapping version where available. Reuse `validate_local_snapshot_bundle(settings)`; do not create a competing snapshot-consistency implementation.

#### Proposed command

Expose the workflow through a command shaped as follows:

```text
python -m s3_ecological.cli prepare-geo-experiment \
  --config config/geo_experiment.example.toml \
  --output-dir data/experiments/<experiment-id>
```

The command must perform no network access and require no API key, external agent, LLM, image model, or remote service. Exit codes must be:

- `0`: artifacts were written and all engineering validations completed, including a valid blocked status;
- `1`: fatal configuration, schema, checksum, I/O, or bundle-consistency failure prevented trustworthy artifacts;
- `2`: artifacts were written, but one or more non-fatal data-quality readiness checks failed.

A blocked status such as missing S1 outputs is an expected result and is not by itself a process crash.

#### Processing sequence

The implementation must perform these steps in this order:

1. parse and validate configuration with Pydantic;
2. load the three local bundle files and verify their checksums and shared identity;
3. verify the authorisation declaration and requested study scope;
4. resolve the target genera through the local taxonomy snapshot;
5. reuse the existing occurrence cleaner as the sole authority for ecological usability and duplicate flags;
6. exclude unusable records from split assignment while counting and explaining every exclusion;
7. assign each usable record to one spatial block;
8. assign whole blocks, never individual rows, to train, validation, or test;
9. calculate per-taxon, per-source, per-time-range, per-quality-flag, per-block, and per-split summaries;
10. evaluate the readiness rules without training or scoring a model;
11. write all artifacts atomically; and
12. read the artifacts back through their Pydantic schemas before returning success.

Do not mutate, rewrite, append to, or coarsen the original snapshot files. Any future privacy transformation must create a separately identified derived artifact.

#### Spatial split Profile v0.1

Provide a replaceable `SpatialBlockStrategy` interface. The first implementation is `latitude_longitude_grid_v0.1`, a transparent engineering baseline.

For a configured grid size `b` in decimal degrees, first canonicalize the antimeridian and poles, then calculate:

```text
longitude_for_index = -180
  if longitude == 180 or latitude == -90 or latitude == 90
  else longitude
latitude_cell_count = ceil(180 / b)
latitude_index      = min(latitude_cell_count - 1, floor((latitude + 90) / b))
longitude_index     = floor((longitude_for_index + 180) / b)
block_id            = "grid-v0.1:<b>:<latitude_index>:<longitude_index>"
```

Requirements:

- `b` must be finite and in `(0, 10]`;
- the example configuration may use `b = 1.0` as an explicitly uncalibrated engineering default;
- all records with the same `block_id` must remain in the same split;
- the same block must never occur in more than one split;
- changing the block method, block size, split ratios, or seed creates a different split identity;
- the report must warn that equal-angle cells have unequal physical area and are not a production ecological-region definition.

Assign blocks deterministically. Compute SHA-256 over UTF-8 text `"<seed>:<block_id>"`, interpret the first eight digest bytes as an unsigned integer, and divide by `2^64` to obtain `u` in `[0,1)`. Under the default engineering ratios:

```text
train_ratio      = 0.60
validation_ratio = 0.20
test_ratio       = 0.20
seed             = 42
```

assign the block to train when `u < 0.60`, validation when `0.60 <= u < 0.80`, and test otherwise. Ratios must be configurable, finite, non-negative, and sum to exactly `1.0` within a documented tolerance of `1e-9`.

These numeric values are reproducibility defaults, not scientifically validated choices. Do not move individual records between splits to improve class balance. Instead, report missing or sparse taxa in each split so a later approved experiment can choose a different versioned block profile.

#### Required output artifacts

Write exactly these primary artifacts:

1. `spatial-split-manifest.json`;
2. `readiness-report.json`.

The split manifest must contain at least:

- `schema_version`;
- `experiment_id`;
- `created_at`;
- all input digests and snapshot identities;
- canonical configuration digest and effective cleaning settings;
- target taxa and geographic scope;
- block strategy name and version;
- block size, split ratios, seed, and split identity;
- one row per usable occurrence containing `source`, `source_record_id`, `taxon_id`, `block_id`, and `split`;
- excluded-record identifiers with existing cleaning flags or exclusion reasons; and
- deterministic ordering by split, block ID, taxon ID, source, and source record ID.

Do not copy full coordinates into the manifest unless a later approved requirement needs them. The original versioned snapshot remains the coordinate source.

The readiness report must contain at least:

- `schema_version`;
- `experiment_id`;
- `generated_at`;
- `occurrence_data_status`;
- `s1_input_status`;
- `overall_milestone_2_status`;
- stable machine-readable reason codes;
- authorisation declaration and reference;
- snapshot, taxonomy, licence, citation, and checksum summary;
- usable and excluded record counts;
- counts by target taxon, source, block, and split;
- earliest and latest usable event dates when present;
- missing target taxa;
- empty-split and single-block warnings;
- a statement that no model was trained and no biological performance was measured; and
- the path and SHA-256 digest of the split manifest. The readiness report must not embed its own digest; the CLI may print that digest after the final file is written.

Use these minimum status semantics:

- `ready_for_geo_prior_engineering`: occurrence data is authorised and structurally ready for an approved geo-only engineering experiment;
- `not_run_missing_authorised_data`: the required overall status whenever authorised occurrence data, compatible authorised S1 outputs, or authorised evaluation labels are missing; stable reason codes must identify the specific missing dependency;
- `not_ready_data_quality`: artifacts were produced but validation found empty required splits, unresolved target taxonomy, sparse or missing target coverage, or another non-fatal declared readiness failure;
- `engineering_fixture_only`: synthetic fixtures exercised the workflow and must not be presented as research readiness.
- `ready_for_approved_milestone_2_experiment`: all required authorised inputs are structurally present, while still making no scientific-performance claim.

`occurrence_data_status` may be `ready_for_geo_prior_engineering` while `overall_milestone_2_status` remains `not_run_missing_authorised_data`. `s1_input_status` must independently distinguish `available_authorised`, `missing`, `unvalidated`, and `engineering_fixture_only`.

If more than one condition applies, preserve all reason codes. The overall status must use the safest applicable result; it must never report `ready_for_approved_milestone_2_experiment` while S1 outputs or authorised evaluation labels are absent.

#### S1 boundary

Do not implement S1. The optional S1 path is only a future-facing validation boundary. When no path is supplied:

- set `s1_input_status = "missing"`;
- include reason `missing_authorised_s1_outputs`; and
- set `overall_milestone_2_status = "not_run_missing_authorised_data"`.

A future S1 bundle must contain versioned `ObservationRequest`-compatible candidate lists plus a separate authorised ground-truth label manifest keyed by `observation_id`. Candidate probabilities without confirmed labels may test interface plumbing but cannot support accuracy, calibration, or reranking-effect claims.

Synthetic S1 candidates may be used only in automated tests. Their reports must use `engineering_fixture_only`.

#### Code structure and extension requirements

Keep this preprocessing workflow outside the deterministic ecological core. A suggested layout is:

```text
src/s3_ecological/
  experiments/
    readiness.py
    spatial_split.py
  schemas/
    experiment.py
config/
  geo_experiment.example.toml
docs/data_cards/
  geo_experiment_readiness_v0.1.md
```

Requirements:

- expose narrow Protocols for the spatial blocker and future split strategies;
- use typed Pydantic input/output models with `extra="forbid"`;
- add public models to JSON Schema export;
- isolate file I/O from pure validation and split-assignment functions;
- use deterministic serialization and atomic replacement;
- require an explicit overwrite option before replacing artifacts;
- keep functions small, names explicit, and comments focused on rationale;
- do not introduce dependencies on PydanticAI, FastAPI, an LLM SDK, or a live data client;
- do not modify `GeoPriorModel`, existing fusion formulas, risk-state precedence, Profile v0.1 thresholds, provider semantics, or assessment output contracts.

The spatial-block interface must allow a later H3, equal-area, state, ecoregion, or supervisor-approved grouping strategy without rewriting readiness reporting.

#### Tests

All tests must run offline. Add unit tests for:

- configuration validation and ratio tolerance;
- every authorisation state;
- bundle mismatch and checksum failure;
- target-taxon coverage;
- reuse of existing cleaning outcomes;
- the exact block-index formula at coordinate boundaries;
- deterministic hash assignment;
- no block shared across splits;
- deterministic ordering and byte-identical repeated outputs when the explicit generation timestamp is unchanged;
- empty, single-block, sparse-taxon, missing-date, and missing-S1 cases;
- stable reason codes and safest-status precedence;
- atomic writes and overwrite refusal; and
- Pydantic validation of both output artifacts.

Add one integration test that imports a synthetic local GBIF/ALA-compatible fixture through the existing Milestone 1.5 importer, builds the readiness artifacts, proves there is no network call, proves all records from one block stay in one split, and receives `engineering_fixture_only` rather than a research-performance claim.

Existing tests must retain their meaning and pass.

#### Documentation and work record

Update README with the offline command, input files, output meanings, exit codes, and a clear distinction between engineering readiness and scientific validation. Add a data card explaining spatial bias, presence-only limitations, unequal grid-cell area, authorisation declarations, privacy considerations, and why absence of S1 blocks full Milestone 2 evaluation.

After implementation, append a timestamped entry to `WorkLog.md` describing implementation order, files, algorithms, exact defaults, actual commands and results, limitations, maintenance guidance, and confirmation that no external API, LLM, S1 agent, trained geographic model, calibration, or biological-performance claim was used.

#### Definition of done for this suggested increment

- [ ] One offline command validates a local snapshot bundle and writes both versioned artifacts.
- [ ] Data authorisation is explicit and never inferred.
- [ ] The four TF4 genera are summarized and missing coverage is visible.
- [ ] Existing cleaning logic remains authoritative.
- [ ] Spatial blocks are deterministic and never cross splits.
- [ ] Split parameters and identities are fully recorded.
- [ ] Missing S1 produces overall status `not_run_missing_authorised_data` with reason `missing_authorised_s1_outputs`.
- [ ] Synthetic tests produce `engineering_fixture_only`.
- [ ] No model is trained and no threshold is calibrated.
- [ ] No network, external agent, API key, or LLM is required.
- [ ] Existing scoring, fusion, risk, provider, and response behavior is unchanged.
- [ ] All new schemas are exported and documented.
- [ ] Tests, Ruff, Pyright, schema export, and CLI smoke tests pass.
- [ ] README, data card, and `WorkLog.md` are updated.
- [ ] No real dataset, generated experiment bundle, or sensitive coordinate file is committed.

#### Consistency with existing design

This suggestion is compatible with the existing delivery sequence because it is a preparation gate before Milestone 2, not a replacement for Milestone 2. It preserves the requirement to reproduce or adapt `geo_prior`, train a fruit-fly prior, fuse it with S1, and evaluate spatial holdouts only after the required authorised inputs are available.

It also preserves the earlier rule to record `not_run_missing_authorised_data` rather than fabricate results. The more specific `missing_authorised_s1_outputs` reason code identifies which dependency is absent without changing the required overall status or claiming Milestone 2 completion. If this suggestion is approved as a normative implementation requirement, copy its current requirements into the appropriate sections of `EarlyDesign.md`, update that document's `Last updated` date, and append a separate approval entry here before implementation begins.

### 2026-08-29 20:05 Australia/Sydney - Approval: offline pre-Milestone 2 data-readiness and spatial-split builder

**Status:** Owner-approved implementation requirement. The project owner's implementation instruction confirms the suggestion recorded above (`2026-08-29 17:16 Australia/Sydney - Suggested next increment: offline pre-Milestone 2 data-readiness and spatial-split builder`) is approved for implementation exactly as written there, with no changes to its scope, decision boundary, formulas, status vocabulary, or "must not" list.

**Action taken:** Per that entry's closing instruction, its requirements have been copied into `EarlyDesign.md` (section 11.4 "Data splits" and the Milestone 2 entry in section 22 "Delivery Sequence for the Builder Agent"), and the "Last updated" date at the top of `EarlyDesign.md` has been advanced to 29 August 2026. No existing record in this log or in `EarlyDesign.md` was modified, deleted, or reordered, and no new Change Log section was added to `EarlyDesign.md`.

**Scope confirmation:** This approval authorises only the pre-Milestone 2 readiness/spatial-split tool described in the 17:16 entry (the `prepare-geo-experiment` CLI command, `spatial-split-manifest.json`, `readiness-report.json`, and the `latitude_longitude_grid_v0.1` block/split profile). It does not authorise training a geographic model, calibrating fusion weights or risk thresholds, implementing S1/S5, an environmental suitability model, live GBIF/ALA API access, or an LLM, and it does not change any existing scoring, fusion, risk-state precedence, or Profile v0.1 threshold. Implementation, tests, and documentation follow in this same change.
