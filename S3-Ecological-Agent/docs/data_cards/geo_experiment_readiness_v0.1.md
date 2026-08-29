# Data card: geo-experiment readiness gate and spatial-split manifest (v0.1)

## What this describes

The two on-disk artifacts produced by `s3-ecological prepare-geo-experiment`
(`s3_ecological.experiments.prepare`): `spatial-split-manifest.json` and
`readiness-report.json`, written together into one output directory. This
tool is an **offline pre-Milestone 2 preparation gate**
(`EarlyDesign.md` section 11.4;
`DesignSuggestionLog.md`, "2026-08-29 17:16 Australia/Sydney - Suggested
next increment: offline pre-Milestone 2 data-readiness and spatial-split
builder", approved 2026-08-29 20:05 Australia/Sydney). It reads an
already-imported Milestone 1.5 bundle
(see `docs/data_cards/offline_occurrence_snapshot_v1.md`), reuses the
existing bundle-consistency check and cleaning logic unchanged, and
deterministically assigns whole spatial blocks - never individual records -
to a train/validation/test split.

Public contract versions for this hardening increment are configuration
`1.1.0`, `spatial-split-manifest.json` `1.1.0`, and
`readiness-report.json` `2.0.0`. Unknown versions are rejected.

This is **not** a real dataset, and its outputs are **not** a geographic
model or an evaluation result. No occurrence or taxonomy data is committed
to this repository; the only inputs matching the expected bundle shape under
version control are the small synthetic fixtures in
`tests/fixtures/importer/` used by the automated tests.

## What this tool does NOT do

- It does not train a geographic-prior model, calibrate a soft-fusion
  weight, or calibrate a risk threshold.
- It does not implement S1 (visual identification), S5, an environmental
  suitability model, a live GBIF/ALA client, or an LLM.
- It never reports a synthetic engineering fixture's results as a real
  ecological or biosecurity finding - see "Data nature" below.
- It never moves a record between splits to "fix" a data-quality problem; it
  only reports the problem.

## Required inputs

Three files from one Milestone 1.5 `import-occurrences` run:
`occurrences.json`, `taxonomy.json`, and `import-report.json`. All three are
read as exact bytes and SHA-256 checksummed. The occurrence and taxonomy
digests must match exactly one `import-report.json.output_files` entry found
by logical filename, never by mapping order. The three inputs must agree on
`dataset_id` and source SHA-256; all other identity metadata shared by two or
more schemas must also agree. Every occurrence `taxon_id` must be present in
the taxonomy bundle. Missing checksums, duplicate checksums, tampering, or
identity mismatch are fatal before temporary output files are created, and
no readiness report is written.

## Geographic scope semantics

`geographic_scope` is required to be a non-blank human-readable label. The
only supported mode is `geographic_scope_mode = "label_only"`: the label does
not define a boundary and never filters or excludes a record. Both outputs
record the mode, and the readiness report includes
`geographic_scope_not_enforced`, meaning region-specific readiness remains
unverified. A future boundary-enforced mode requires a separately approved,
versioned profile.

## Genus resolution and in-scope filtering

The genus of each occurrence is the first whitespace-delimited token of its
resolved `TaxonomySnapshotItem.scientific_name` (e.g. `"Bactrocera"` from
`"Bactrocera dorsalis"`). Only records whose genus is in the configured
`target_taxa` list (default: the four TF4 genera - `Anastrepha`,
`Bactrocera`, `Ceratitis`, `Rhagoletis` - see
`WEEK 4/FlyTech_S3_Resource_Map.md` section 3.5) reach cleaning and
splitting; off-target-genus records are dropped before cleaning and are not
counted as "excluded" (they were never in scope).

## Cleaning

In-scope records are cleaned with the existing, unmodified
`s3_ecological.occurrence.cleaning.clean_occurrences` - the same function
`assess` uses. This tool adds no new exclusion rule. A record's quality
flags and cleaning actions are carried unchanged into
`spatial-split-manifest.json`'s `excluded_records` for any record not
`usable_for_distance`.

The readiness report keeps the following summaries distinct:

- `counts_by_quality_flag` counts each distinct quality flag once per
  in-scope record, including usable records;
- `counts_by_cleaning_action` counts each distinct action once per excluded
  record;
- `counts_by_exclusion_flag` is a deprecated one-revision compatibility alias
  whose value is exactly equal to `counts_by_cleaning_action`.

It also reports `counts_by_event_year` for usable records with a valid
four-digit year and `undated_usable_record_count` for usable records without
one. These time summaries are descriptive coverage only; they are not
seasonality, environmental-suitability, or ecological-support evidence.

## Spatial block strategy: `latitude_longitude_grid_v0.1`

Equal-angle grid cells of a configurable `grid_size_degrees` (default `1.0`,
must be in `(0, 10]`). A block id is
`"grid-v0.1:<grid_size_degrees>:<latitude_index>:<longitude_index>"`, where
`latitude_index = floor((latitude + 90) / grid_size_degrees)` (clamped to the
last row at the north pole) and `longitude_index` uses
`floor((longitude + 180) / grid_size_degrees)`, treating `longitude == 180`
and either pole's longitude as `-180` so the antimeridian and the poles each
resolve to one consistent cell rather than splitting across a boundary.

**Known limitation:** these cells are equal-angle, not equal-area - a cell
near the poles covers far less ground area than one near the equator - and
this grid is not a production ecological-region (ecoregion/state/H3)
definition. `SpatialBlockStrategy` (a `Protocol` in
`experiments/spatial_split.py`) exists so a future equal-area, H3, or
administrative-region strategy can be added without changing the readiness
or manifest schemas.

## Deterministic block-to-split assignment

Every distinct block (not every record) is assigned once to `train`,
`validation`, or `test` via `sha256("<seed>:<block_id>")`, truncated to its
first 8 bytes as an unsigned big-endian integer, divided into `[0, 1)`, and
compared against the configured ratios (default `0.60/0.20/0.20`, default
`seed = 42`). A block already assigned is never reassigned, so no spatial
block ever spans more than one split, and re-running with an unchanged
config always reproduces the same assignment.

## Data nature and authorisation (never inferred)

- `data_nature`: `"real_world_data"` or `"synthetic_engineering_fixture"`,
  set explicitly in the config. A synthetic-fixture run's
  `occurrence_data_status` (and therefore `overall_milestone_2_status`) is
  always `engineering_fixture_only`, regardless of how clean or complete the
  data looks - this status can never be upgraded by data quality alone.
- `authorisation.status`: `"authorised"` / `"not_authorised"` / `"unknown"`
  (default). This is the project owner's or an authorised supervisor's
  explicit permission to use one dataset for the stated experiment. A
  dataset's public licence (e.g. a GBIF/ALA open-data licence) is never
  silently converted into this declaration - `status = "authorised"`
  requires `authorisation_reference`, `purpose`, and `approving_role` to all
  be filled in, or the config fails validation.

## Status vocabulary

`occurrence_data_status` / `overall_milestone_2_status` use:
`ready_for_geo_prior_engineering`, `not_run_missing_authorised_data`,
`not_ready_data_quality`, `engineering_fixture_only`,
`ready_for_approved_milestone_2_experiment`. `s1_input_status` uses:
`available_authorised`, `missing`, `unvalidated`, `engineering_fixture_only`
(S1 is not implemented by this tool, so a supplied path is only ever
recorded, never validated). Precedence for `overall_milestone_2_status`:
an engineering fixture always wins first; otherwise, any missing
authorisation or non-authorised S1 input forces
`not_run_missing_authorised_data`; otherwise a data-quality problem forces
`not_ready_data_quality`; only a fully clean, authorised, S1-available run
reaches `ready_for_approved_milestone_2_experiment`.

## Privacy

`spatial-split-manifest.json` records exact coordinates only implicitly, via
each record's assigned `block_id` (at the configured `grid_size_degrees`
resolution) - it does not repeat the raw latitude/longitude. Both output
files may still be sensitive if the source occurrence dataset itself
protects sensitive-species locations; treat these outputs with the same
sensitivity as the input snapshot bundle, and never commit a real run's
outputs to this repository.

## Determinism and atomicity

Both output files use fixed indentation, `ensure_ascii=False`, and
Pydantic's field-declaration key order, so re-running on a byte-identical
bundle and config produces byte-identical output. Both files are serialized
and validated before final paths are touched, staged in the destination
directory, checksum-verified, and committed as one pair. On a replacement or
read-back failure, a new partial pair is removed or an existing pair is
restored byte-for-byte; handled paths leave no temporary/backup files. An
existing `spatial-split-manifest.json`/`readiness-report.json` pair is left
untouched unless `--overwrite` is passed.

## CLI outcome contract

`prepare-geo-experiment` returns `0` for a clean or expected blocked result
without data-quality reason codes, including the honest
`not_run_missing_authorised_data` state while authorised S1 output is absent.
It returns `2` after writing a report with non-fatal data-quality reasons, and
`1` for fatal configuration, input, integrity, or output-commit failures. A
fatal failure writes no new output pair; overwrite failures restore the prior
pair.

## Why the absence of S1 blocks full Milestone 2 evaluation

Milestone 2 (`EarlyDesign.md` section 22) evaluates a soft fusion of the
geographic prior with S1's visual identification. S1 is not implemented yet,
so this gate can prepare data and a spatial split, but it cannot itself
produce a fusion-evaluation result - `overall_milestone_2_status` can reach
`ready_for_approved_milestone_2_experiment` only once an authorised S1
evaluation output also exists.
