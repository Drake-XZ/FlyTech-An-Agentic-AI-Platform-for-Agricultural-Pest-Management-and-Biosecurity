# Data card: offline occurrence snapshot bundle (v1)

## What this describes

The on-disk bundle produced by `s3-ecological import-occurrences`
(`s3_ecological.ingestion.occurrence_snapshot`, Milestone 1.5): three files
written together into one output directory -
`occurrences.json` + `taxonomy.json` + `import-report.json` - plus the
`local_snapshot` providers (`providers/occurrence_local_snapshot.py`,
`providers/taxonomy_local_snapshot.py`) that read them back for `assess`.

This is **not** a real dataset. No occurrence or taxonomy data is committed
to this repository; this document describes a *format*, and the only files
matching it under version control are the small synthetic fixtures in
`tests/fixtures/importer/` used by the automated tests.

## Inputs accepted

| `--source`    | File shape                              | Delimiter |
|---------------|------------------------------------------|-----------|
| `gbif`        | GBIF occurrence download (`.csv`)        | `,`       |
| `ala`         | ALA occurrence download (`.tsv`/`occurrence.txt`) | `\t` |
| `generic_dwc` | Any Darwin Core-ish export (`.csv`/`.tsv`/`occurrence.txt`) | by extension |
| `canonical`   | A previously produced `occurrences.json` (`.json`) | n/a (JSON) |

The delimiter is chosen from the file extension alone; it is never sniffed
from file content.

## Field mapping (delimited sources -> `RawOccurrenceRecord`)

Each canonical field takes the first present, non-empty header from its
ordered fallback list.

| Canonical field | `gbif` | `ala` | `generic_dwc` |
|---|---|---|---|
| `source_record_id` | `occurrenceID`, `gbifID` | `occurrenceID`, `id` | `occurrenceID`, `id` |
| `scientific_name_raw` | `scientificName` | `scientificName` | `scientificName` |
| accepted name (taxonomy only) | `acceptedScientificName`, `scientificName` | same | same |
| `taxon_id` (before namespacing) | `acceptedTaxonKey`, `taxonKey`, `taxonID` | `acceptedConceptID`, `taxonConceptID`, `taxonID` | `taxonID` |
| `rank` (taxonomy only) | `taxonRank` | `taxonRank` | `taxonRank` |
| `latitude` | `decimalLatitude` | same | same |
| `longitude` | `decimalLongitude` | same | same |
| `coordinate_uncertainty_m` | `coordinateUncertaintyInMeters` | same | same |
| `event_date` | `eventDate`, else `year`/`year-month`/`year-month-day` | same | same |
| `basis_of_record` | `basisOfRecord` | same | same |
| `license` | `license`, else the run's `--dataset-license` | same | same |
| `media_license` | `mediaLicense` | same | same |
| `is_captive_or_cultivated` | `isCaptive`, `isCultivated` | same | same |

If `source_record_id` is absent, one is generated deterministically:
`"generated:" + sha256(sorted, trimmed header -> trimmed value-or-null JSON)`.
It never encodes the row's position, so re-ordering an input file never
changes a generated id.

`taxon_id` is namespaced with the import source as a prefix (`gbif:...`,
`ala:...`, `generic_dwc:...`), unless the raw value is already prefixed that
way.

## `--source canonical`

Re-imports a previously exported `occurrences.json` unchanged (it must
already validate as `OccurrenceSnapshot`), after checking that
`dataset_id`/`retrieved_at`/`dataset_license`/`citation` in the file match
the command-line metadata exactly. The file's own `source` field (e.g.
`"gbif"`) is *not* compared against the CLI's `--source canonical` selector
and is carried through unchanged on every record - `--source canonical` only
picks the canonical-JSON code path, it does not claim the data originated
from a source literally named "canonical". No delimited-format field
mapping applies; the taxonomy bundle is rebuilt by grouping the file's own
`(taxon_id, scientific_name_raw)` pairs, keyed by the id's own namespace
prefix.

## Row-level rejection codes

One rejected row produces exactly one `ImportRejection` (multiple failing
checks on the same row are joined into one `message`, but the row is still
counted once):

- `missing_scientific_name` - `scientificName` absent or empty.
- `missing_taxon_id` - no supported source taxon-id header has a value.
- `invalid_numeric_value` - latitude/longitude/uncertainty is present but not numeric.
- `negative_coordinate_uncertainty` - `coordinateUncertaintyInMeters` parses but is negative.
- `non_finite_numeric_value` - a numeric field parses to `NaN`/`Infinity`.
- `invalid_record_schema` - the row's field count does not match the header, or the assembled record fails `RawOccurrenceRecord` validation.

An unrecognized (non-empty) boolean spelling for `isCaptive`/`isCultivated`
is **not** a row rejection: it is recorded as a non-fatal entry in
`ImportReport.mapping_warnings` and the field is left `null`.

## Snapshot identity and cross-file consistency

- `source_sha256` = SHA-256 of the raw input file's bytes, shared by
  `occurrences.json`, `taxonomy.json`, and `import-report.json`.
- `snapshot_key` = `"<dataset-id>:<first 12 hex chars of source_sha256>:<mapping-version>"`.
- `providers.factory.validate_local_snapshot_bundle()` checks, whenever both
  `occurrence_provider` and `taxonomy_provider` are `"local_snapshot"`, that
  the two files share `dataset_id` and `source_sha256`, and that every
  occurrence record's `taxon_id` appears in the taxonomy bundle - so a
  half-updated bundle fails fast at settings-build time rather than
  producing silent `TAXON_NOT_FOUND` results at query time.

## Taxonomy resolution (`LocalSnapshotTaxonomyProvider`)

Matching is exact, on a Unicode-normalized name (NFKC, trim, collapse
whitespace, casefold) against both `scientific_name` and every
`submitted_names` entry of every `taxonomy.json` item:

- zero matches -> `PARTIAL` + `TAXON_NOT_FOUND` warning, `resolved_taxon=None`.
- exactly one match -> `SUCCESS`.
- more than one match -> `PARTIAL`, `resolved_taxon.ambiguous=True` (best
  guess is the lowest-sorted-`taxon_id` candidate), `candidate_matches`
  lists every matching accepted name.

There is never a network fallback. `TaxonomySnapshotItem.taxon_ids` is
re-keyed from the import-source name it was written under (e.g. `"gbif"`) to
the runtime provider name (`"local_snapshot"`) when handed to the pipeline
as a `ResolvedTaxon`, mirroring how `FixtureTaxonomyProvider` keys its own
entries by `"fixture"`.

## Failure semantics (raises `ImportFatalError`, no bundle written)

Missing/unreadable/non-UTF-8 input; unsupported extension/source
combination; a missing required header (`scientificName`, or every taxon-id
fallback for the chosen source); empty `--dataset-id`/`--dataset-license`/
`--citation`; an invalid or timezone-naive `--retrieved-at`; a
`--query-parameters-json` file that is not a single JSON object or that
contains a secret-like key (`token`, `password`, `apikey`/`api_key`,
`secret`); a canonical-JSON schema or metadata mismatch; an existing output
file without `--overwrite`; an unwritable output directory; zero accepted
records; or a post-write checksum-verification failure.

## Determinism and atomicity

Output JSON uses fixed indentation, `ensure_ascii=False`, and Pydantic's
field-declaration key order, so re-running the importer on byte-identical
input produces byte-identical output. Each of the three output files is
written to a same-directory temp file, read back and checksum-verified, then
committed with `os.replace`; a failure partway through never leaves a
half-written file at the final path (though, with no cross-file filesystem
transaction, a process kill between the three individual commits can still
leave the trio partially updated - `validate_local_snapshot_bundle` is the
guard against consuming such a partial bundle).

## Known limitations

- Exact-name matching only; no fuzzy matching, phonetic matching, or
  external synonym database.
- `--source canonical` requires an exact metadata match to the current
  command line; it cannot "merge" or "update" one field of a previous run.
- No incremental/append mode: a re-import writes a fresh set of three files
  (optionally replacing the previous ones with `--overwrite`).
