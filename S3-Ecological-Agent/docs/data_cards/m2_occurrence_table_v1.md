# M2 Occurrence Table v1 (`m2-fruit-fly-occurrences-v1`)

Data card for the derived Milestone 1.5 bundle produced from the committed
GBIF/ALA JSONL resources for Milestone 2 preparation
(DesignSuggestionLog.md "2026-09-08 Australia/Sydney - Suggested next
increment: M2-A authorised occurrence preparation and readiness run").

This is a data-preparation artifact, not a model, not a calibrated
threshold, and not a claim of biological or species-distribution accuracy.
Running `prepare-geo-experiment` against it does not itself authorise, run,
or evaluate a Milestone 2 experiment - see "Readiness result" below.

## Inputs

- `data/external/m2/gbif/{anastrepha,bactrocera,ceratitis,rhagoletis}.jsonl`
  (39,689 records; GBIF occurrence-download API shape)
- `data/external/m2/ala/{anastrepha,bactrocera,ceratitis,rhagoletis}.jsonl`
  (6,018 records; ALA biocache-download JSON shape)

Both are already-committed, bounded snapshots (see
`docs/m2_resource_inventory.md`); this data card covers only what is
*derived* from them. No network request is made anywhere in this pipeline.

## Conversion tool

`scripts/prepare_m2_occurrence_table.py` (`tool_version =
"prepare-m2-occurrence-table-v0.1.0"`, `conversion_profile_version =
"m2-occurrence-conversion-v0.1"`, `dedup_profile_version =
"m2-dedup-v0.1"`). Reads only the committed local JSONL files above, streams
each file line by line, makes no network/model/LLM call, and does not
reimplement `s3_ecological.occurrence.cleaning.clean_occurrences` - that
function remains the sole authority for coordinate-quality/usability
decisions, applied unmodified, later, by `prepare-geo-experiment`.

Reproduce:

```powershell
python scripts/prepare_m2_occurrence_table.py `
  --output-csv data/local/m2/conversion/m2_occurrences.csv `
  --output-report data/local/m2/conversion/m2_conversion_report.json
```

`data/local/` is gitignored; none of this pipeline's real outputs are
committed (see "Storage decision" below).

### Field mapping

| Output column | GBIF source | ALA source |
|---|---|---|
| `occurrenceID` (prefixed `gbif:`/`ala:`) | `occurrenceID` else `gbifID` | `uuid` |
| `taxonID` (prefixed `gbif:`/`ala:`) | `acceptedTaxonKey` else `taxonKey` else `taxonID` | `acceptedConceptID` else `taxonConceptID` else `taxonID` |
| `scientificName` / `acceptedScientificName` | verbatim | verbatim (ALA records here carry no distinct accepted name) |
| `taxonRank` | verbatim | verbatim |
| `decimalLatitude` / `decimalLongitude` / `coordinateUncertaintyInMeters` | verbatim | verbatim |
| `eventDate` | verbatim `eventDate`, else `year`/`month`/`day` | **converted**: ALA's iNaturalist-sourced records store epoch milliseconds; converted to `YYYY-MM-DD` via `datetime(1970,1,1,UTC) + timedelta(milliseconds=value)` (never `datetime.fromtimestamp`, which raises `OSError` for the pre-1970 values present in this dataset on some platforms), else `year`/`month`/`day` |
| `basisOfRecord` | verbatim | verbatim else `raw_basisOfRecord` |
| `license` | verbatim | verbatim |
| `mediaLicense` | first attached image's `media[0].license` | always blank (no such field in the committed ALA records) |
| `isCaptive` | `"wild"` -> `false`; anything else -> blank (never guessed) | always blank (no such field in the committed ALA records) |

**Provider-prefixing is required, not cosmetic.** The Milestone 1.5 importer
(`s3_ecological/ingestion/occurrence_snapshot.py`) namespaces the *taxon id*
it is given with the `--source` value but does **not** namespace
`source_record_id`, and under `--source generic_dwc` every emitted record's
`source` field is set to the literal string `"generic_dwc"` for all rows
regardless of true provider. Since this conversion merges two providers into
one `generic_dwc` import, the original provider is only recoverable via the
`gbif:`/`ala:` string prefix this script embeds into `occurrenceID`/
`taxonID` itself - fully reversible by splitting on the first `:`.

This script performs **no row rejection** of its own for missing/invalid
scientific names, taxon ids, or coordinates (its only self-originated
rejection category is a raw JSONL line that fails to parse as JSON at all,
tracked as `unparseable_line_count`). All content-based row validation
(`missing_scientific_name`, `missing_taxon_id`, `invalid_numeric_value`,
`negative_coordinate_uncertainty`, `non_finite_numeric_value`,
`invalid_record_schema`) remains the importer's, applied unmodified when the
CSV is fed to `import-occurrences`.

### Deduplication (`m2-dedup-v0.1`)

Three explicit tiers, all reported, ambiguous matches never silently
dropped:

1. **Exact** - two rows from the *same* provider share the same provider
   record identity. Only one survives; tie-break is deterministic
   (lexicographically smallest fully-mapped row), independent of input file
   order.
2. **Probable cross-provider** - either (a) a shared iNaturalist observation
   id embedded in both providers' raw `occurrenceID` URLs, or (b) the same
   normalized accepted name plus coordinates rounded to 3 decimal degrees
   (`coordinate_round_decimals = 3`, ~111 m) plus agreeing event dates.
   `canonical_provider_precedence = ["gbif", "ala"]` breaks the tie.
3. **Ambiguous** - same coordinate/name bucket as 2(b) but event dates
   disagree or are missing on one or both sides. **Both rows are kept**; the
   pairing is recorded under
   `duplicate_details.ambiguous_cross_provider_matches` in the conversion
   report for manual review.

Known, disclosed limitation: tier 2(b)/3 matching is an exact-precision
coordinate bucket, not a fuzzy nearest-neighbour search across the full
dataset - a deliberately bounded-cost choice for this offline script,
recorded here as a data-preparation parameter, not a scientific calibration.

## Actual conversion result (2026-09-08 run against the committed data)

```
total_input_records:                        45,707  (39,689 GBIF + 6,018 ALA)
total_unparseable_input_lines:                   0
emitted_records:                            45,610
exact_duplicates_removed (same provider):        14
probable_cross_provider_duplicates_removed:      83
ambiguous_cross_provider_matches_flagged:         0
reconciliation: 45,707 = 45,610 + 14 + 83           (reconciles: true)
```

By provider (emitted): `gbif` 39,675, `ala` 5,935.

By target genus (first whitespace token of the emitted accepted/scientific
name; emitted 45,610 total): Anastrepha 8,321; Bactrocera 13,606; Ceratitis
10,299; Rhagoletis 9,624; **other-genus-token 3,760**.

**Label-contract caveat (see "Taxonomy and label contract" below): all
3,760 "other-genus-token" records are GBIF records whose `scientificName`/
`acceptedScientificName` is a BOLD BIN identifier (e.g. `"BOLD:AAA5439"`),
not a Latin binomial** - confirmed by direct inspection: every one of these
records' own Darwin Core `genus` field correctly says `Anastrepha`/
`Bactrocera`/`Ceratitis`/`Rhagoletis`, but that field is not part of this
conversion's or the importer's CSV/field-mapping contract, and the
downstream `prepare-geo-experiment` gate determines genus by taking the
first whitespace token of the *name*. These rows are therefore genuine
GBIF query-matched occurrences of a target genus that fall outside the
readiness gate's reported target-taxon counts under the existing,
unmodified genus-by-name heuristic. This conversion script does not
fabricate a binomial name to work around this - the name is passed through
exactly as GBIF supplied it - and no off-target contamination was found:
100% of the "other-genus-token" rows are `BOLD:`-prefixed.

Licence values are heterogeneous and preserved exactly, never normalized
(15 distinct strings observed across the two providers, including GBIF's
full CC legalcode URLs and ALA's abbreviated `"CC-BY"`/`"CC-BY 4.0 (Int)"`/
`"CC-BY 3.0 (Au)"` variants). No mapping warnings were emitted for the real
dataset (0 of 45,610 rows).

Determinism: re-running the script against the same inputs, and running it
against the four genus files loaded in reverse order, produce byte-identical
CSV output and identical conversion-report counts (only the `generated_at`
timestamp and the run's own output paths differ) - verified directly.

## Milestone 1.5 bundle

Built via the existing, unmodified importer:

```powershell
python -m s3_ecological.cli import-occurrences `
  --input data/local/m2/conversion/m2_occurrences.csv `
  --source generic_dwc `
  --dataset-id m2-fruit-fly-occurrences-v1 `
  --retrieved-at 2026-09-08T00:00:00Z `
  --dataset-license "Mixed: see per-record license field (GBIF CC-BY/CC-BY-NC/CC0 legalcode URLs; ALA CC-BY/CC-BY-NC/CC0 variants) - not a single dataset-wide license" `
  --citation "GBIF.org occurrence downloads and Atlas of Living Australia (ALA) occurrence records for Anastrepha, Bactrocera, Ceratitis, Rhagoletis, retrieved 2026-09-07, converted via scripts/prepare_m2_occurrence_table.py (m2-occurrence-conversion-v0.1)" `
  --output-dir data/local/m2/bundle
```

Result: `input_record_count = 45,610`, `accepted_record_count = 45,610`,
`rejected_record_count = 0`, 0 mapping warnings, 893 distinct namespaced
taxon ids across the two providers. The bundle was never hand-authored or
patched after generation.

## Taxonomy and label contract

- **Scope**: TF4 genera only (Anastrepha, Bactrocera, Ceratitis,
  Rhagoletis), matching Profile v0.1's `DEFAULT_TARGET_TAXA`.
- **Resolution level**: species-level names are preserved verbatim wherever
  the provider supplied one; provider taxonomy ids (`gbif:<taxonKey>` /
  `ala:<taxonConceptID URL>`) are preserved and namespaced so they remain
  individually recoverable and joinable back to GBIF/ALA. No taxonomic
  synonymisation or renaming is performed by this pipeline beyond what each
  provider's own `acceptedScientificName`/`acceptedTaxonKey`/
  `acceptedConceptID` already encodes.
- **Known non-binomial labels**: see the BOLD-BIN caveat above. These
  records carry a valid provider taxon id but no binomial name; they are
  data-quality/label characteristics of the source GBIF query results, not
  something this conversion invented or can safely resolve offline (doing
  so would require an external taxonomic lookup, which this offline tool
  does not perform).
- **S1 alignment status**: `pending_s1_alignment`. No S1 (visual
  identification) module exists yet in this repository, so there is no
  agreed stable taxonomy-id crosswalk between this occurrence table and any
  S1 output to record here. The `taxon_id` values above
  (`generic_dwc:<provider>:<provider taxon id>`, fully recoverable by
  splitting on the first two `:` separators) are the stable identifiers a
  future S1 evaluation-input schema must key against, per
  DesignSuggestionLog.md's M2-A "S1 input and leakage requirements" section.

## Readiness result

Config: `config/geo_experiment.m2.toml` (schema `1.1.0`, `data_nature =
"real_world_data"`, `authorisation.status = "unknown"`, TF4 target taxa,
`latitude_longitude_grid_v0.1` at `grid_size_degrees = 1.0`, ratios
0.60/0.20/0.20, `seed = 42` - all unmodified Profile v0.1 defaults).

```powershell
python -m s3_ecological.cli prepare-geo-experiment `
  --config config/geo_experiment.m2.toml `
  --output-dir data/local/m2/readiness
```

Actual result (2026-09-08):

- `occurrence_data_status` / `overall_milestone_2_status`:
  **`not_run_missing_authorised_data`**
- `s1_input_status`: `missing`
- `reason_codes`: `authorisation_unknown`, `missing_authorised_s1_outputs`,
  `geographic_scope_not_enforced`
- `missing_target_taxa`: `[]` (all four TF4 genera present)
- `usable_record_count` (post-cleaning, target-taxa-scoped): 18,709
- `excluded_record_count`: 23,141, almost entirely
  `excluded_unknown_coordinate_uncertainty` (22,298) - most committed
  GBIF/ALA records do not report `coordinateUncertaintyInMeters` at all, and
  the existing (unmodified) cleaner conservatively treats missing
  uncertainty as unusable for distance computation; this is expected,
  disclosed existing-cleaner behaviour, not something this data card's
  pipeline alters.
- `counts_by_target_taxon` (usable): Anastrepha 723, Bactrocera 7,059,
  Ceratitis 2,993, Rhagoletis 7,934
- `counts_by_split`: train 11,436, validation 3,242, test 4,031, across
  1,410 distinct spatial blocks; every block is assigned to exactly one
  split (verified directly against `spatial-split-manifest.json`).
- CLI exit code: `0` (missing-S1 is a correctly-reported blocked state, not
  a data-quality reason code, per the documented 0/1/2 exit-code contract).
- Re-running the gate against the same bundle/config produces a
  byte-identical `spatial-split-manifest.json` and (apart from
  `generated_at`) an identical `readiness-report.json` - verified directly.

**This does not reach `ready_for_approved_milestone_2_experiment`.** Two
things are missing, and neither was fabricated to make progress:

1. **A formal experiment-authorisation declaration.** The project owner's
   earlier permission to commit the bounded GBIF/ALA/vendored-source
   snapshot (`docs/m2_resource_inventory.md`) is repository-storage
   authorisation only. It is not the separate declaration this schema
   requires (`authorisation.status = "authorised"` plus non-blank
   `authorisation_reference`/`purpose`/`approving_role`, enforced by a
   Pydantic validator on `AuthorisationDeclaration`). No such declaration
   has been supplied, so `config/geo_experiment.m2.toml` honestly leaves
   `status = "unknown"`.
2. **An authorised S1 evaluation input.** S1 (visual candidate
   identification) is not implemented in this repository. No S1 predictions
   file of any kind - synthetic or real - has been supplied or fabricated
   for this run.

## Storage decision

Real conversion/bundle/readiness output files (`data/local/m2/**`) are
**not** committed to this repository. `data/local/` is gitignored. These
files can carry real, potentially sensitive spatial occurrence coordinates,
and DesignSuggestionLog.md's M2-A entry requires an explicit
repository-storage decision before such outputs are committed - none has
been made, so results are instead documented here (counts, statuses,
checksums) and in `WorkLog.md`. `config/geo_experiment.m2.toml` itself
*is* committed (it contains only paths, ratios, and target-taxa lists - no
occurrence data).

## What this data card does not claim

No model was trained, no fusion weight or risk threshold was calibrated,
and no biological or species-distribution accuracy claim is made anywhere
in this document or by the commands above. `clean_occurrences`,
`assign_records_to_splits`, `prepare_geo_experiment`, the CLI, and every
Prototype Implementation Profile v0.1 numeric default were used unmodified.
