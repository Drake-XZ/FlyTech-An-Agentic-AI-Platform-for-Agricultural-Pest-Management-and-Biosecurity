# data/

Local, offline data used by S3 providers. Nothing in this directory is
required to run the prototype's default fixture-backed providers or the
golden acceptance tests — those use in-package fixture data under
`src/s3_ecological/fixtures/`.

- `raw/` — unmodified snapshot files (e.g. a GBIF/ALA occurrence export)
  intended for `LocalSnapshotOccurrenceProvider` via
  `occurrence_provider = "local_snapshot"` and `occurrence_snapshot_path`.
- `interim/` — intermediate, partially cleaned data, if a future milestone
  needs a caching or pre-processing step.
- `processed/` — data ready for direct provider consumption.

No real occurrence data is committed in this prototype. Do not commit
credentials, API keys, or any data subject to a redistribution restriction
into this directory.
