# FlyTech S3 Ecological Agent

Offline-first ecological plausibility core for FlyTech's agricultural pest
management platform. This package implements **Milestone 0 + Milestone 1 +
Milestone 1.5 (offline occurrence snapshot ingestion)**, plus an **offline
pre-Milestone 2 data-readiness and spatial-split builder** (see
[`EarlyDesign.md`](EarlyDesign.md) §11.4 and §22), and the "core engineering
prototype" definition of done from `EarlyDesign.md` §23.1 — nothing else from
Milestones 2-4, and none of the conditional research-validation requirements
in §23.2.

It runs with **no external LLM, no API credentials, and no network access**,
using local fixtures and a deterministic geographic baseline. It does not
implement S1/S2/S4/S5/S6, the orchestrator, or any UI — only the S3
ecological-reasoning contracts and their offline reference implementations.

## What this is (and isn't)

- **Is**: a validated request/response contract, a deterministic
  nearest-occurrence geographic-support baseline, soft-fusion re-ranking, a
  six-rule risk-state precedence policy, traceable evidence records, and a
  fixture-backed CLI/library entry point — all runnable and tested offline.
- **Isn't**: a validated species-distribution model, a live GBIF/ALA
  integration, an incursion-detection system, or anything that has been
  checked against real ecological data. Environmental suitability
  (`suitability/null_model.py`) and the incursion rule
  (`risk/policy.py::_potential_incursion_rule_fires`) are explicitly stubbed
  and documented as deferred — see "Known limitations" below.

## Requirements

- Python **3.11+** (the codebase uses `StrEnum`, `tomllib`, and `match`
  statements from 3.10/3.11).
- [`uv`](https://docs.astral.sh/uv/) is the preferred tool for environment
  and dependency management. A plain `pip` fallback is documented below and
  is what was actually used to develop and test this prototype, since `uv`
  was not available in the development environment.

## Install

Preferred (`uv`):

```bash
uv venv
uv pip install -e ".[dev]"
```

Documented fallback (`pip`), actually used during development:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate ; POSIX: source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras (not required for the deterministic core or its tests):

```bash
pip install -e ".[agent]"           # adds pydantic-ai, for PydanticAIAdapter
pip install -e ".[api]"             # adds fastapi/uvicorn/python-multipart/pillow
pip install -e ".[api,demo-ml]"     # also adds torch/torchvision, for the local demo server
```

## Run it

Run one of the six golden acceptance fixtures with no configuration:

```bash
python -m s3_ecological.cli demo --fixture supported_same_location
```

Run an arbitrary `ObservationRequest` JSON file:

```bash
python -m s3_ecological.cli assess --input request.json --output -
```

Or call the library entry point directly:

```python
from datetime import UTC, datetime
from s3_ecological import S3Settings, run_assessment
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider, build_taxonomy_provider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.suitability.null_model import NullSuitabilityModel
from s3_ecological.schemas.request import ObservationRequest, VisualCandidate

settings = S3Settings()
occurrence_provider = build_occurrence_provider(settings)

result = run_assessment(
    ObservationRequest(
        schema_version="1.0.0",
        observation_id="obs-1",
        candidate_set_complete=True,
        visual_candidates=[VisualCandidate(candidate_id="c1", name="Bactrocera", visual_probability=0.9)],
    ),
    settings=settings,
    taxonomy_provider=build_taxonomy_provider(settings),
    occurrence_provider=occurrence_provider,
    geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
    suitability_model=NullSuitabilityModel(),
    risk_policy=DeterministicRiskPolicy(),
    analysis_id="example-1",
    generated_at=datetime.now(UTC),
)
print(result.risk_state, result.review_required)
```

`run_assessment` never raises for a handled input, never calls an LLM, and
never makes a network request.

### Offline occurrence snapshot ingestion (Milestone 1.5)

Convert a locally-held GBIF/ALA/generic Darwin Core export (a CSV/TSV file
you already downloaded - this command never fetches anything itself) into a
local `occurrences.json` + `taxonomy.json` + `import-report.json` bundle:

```bash
python -m s3_ecological.cli import-occurrences \
  --input tests/fixtures/importer/gbif_small.csv \
  --source gbif \
  --dataset-id demo-gbif-2026 \
  --retrieved-at 2026-08-28T00:00:00+10:00 \
  --dataset-license "CC-BY 4.0" \
  --citation "Example GBIF occurrence download, demo-gbif-2026" \
  --output-dir data/snapshots/example
```

Exit code `0` means every row was accepted; `2` means the bundle was still
written but `import-report.json` records one or more row-level rejections;
`1` means a fatal error occurred and no bundle was written. Then point
`assess` at the resulting bundle, either via `config/sources.example.toml`'s
commented-out `local_snapshot` block or directly:

```bash
python -m s3_ecological.cli assess \
  --input request.json \
  --config config/sources.example.toml
```

See [`docs/data_cards/offline_occurrence_snapshot_v1.md`](docs/data_cards/offline_occurrence_snapshot_v1.md)
for the full field-mapping tables, row-rejection codes, and snapshot-identity
rules.

### Offline pre-Milestone 2 data-readiness and spatial-split builder

Given an already-imported Milestone 1.5 bundle, build a deterministic
spatial train/val/test split and a readiness report — a *preparation gate*,
not a model-training or model-evaluation step:

```bash
python -m s3_ecological.cli prepare-geo-experiment \
  --config config/geo_experiment.example.toml \
  --output-dir data/experiments/example-experiment
```

This command:

- authenticates the exact `occurrences.json` and `taxonomy.json` bytes against
  the checksum entries in `import-report.json`, then checks the three files'
  versioned identity metadata before creating temporary outputs;
- reuses the Milestone 1.5 bundle validation (`validate_local_snapshot_bundle`)
  and deterministic-core cleaning rules (`S3Settings` + `clean_occurrences`)
  unchanged, while reporting quality flags separately from cleaning actions;
- checks authorisation declarations, taxonomy-ID resolution, and TF4
  target-genus coverage (`Anastrepha`, `Bactrocera`, `Ceratitis`,
  `Rhagoletis`);
- treats `geographic_scope` as a label only under the required
  `geographic_scope_mode = "label_only"`; it never filters by that label and
  reports `geographic_scope_not_enforced`;
- assigns whole spatial blocks — never individual records — to train/val/test
  using the `latitude_longitude_grid_v0.1` strategy and a seeded hash, so a
  block is never split across two splits and a re-run with unchanged inputs
  produces byte-identical output;
- reports descriptive counts by valid event year and the usable records that
  have no valid year; these are not seasonality or suitability evidence;
- writes and verifies `spatial-split-manifest.json` and
  `readiness-report.json` as one output pair, restoring the exact prior pair
  or removing a partial new pair if commit/read-back verification fails.

The current public contract versions are config `1.1.0`, spatial-split
manifest `1.1.0`, and readiness report `2.0.0`. Unknown versions and blank or
duplicate identity/target-taxon values fail validation.

It **never** trains a geographic model, calibrates a fusion weight or risk
threshold, implements S1/S5 or environmental suitability, calls a live
GBIF/ALA API, or uses an LLM — and it never reports a result built from
synthetic engineering fixtures as a real ecological or biosecurity accuracy
figure (every such report is stamped `engineering_fixture_only`).

Exit code `0` means the report is clean or in an expected blocked state with
no data-quality reason codes; `2` means the report was still written but one
or more non-fatal data-quality reason codes are present (e.g. missing target
taxon coverage, all usable records fall in a single spatial block); `1` means
a fatal error occurred (e.g. a missing/unreadable input file, a
`dataset_id` mismatch between bundle files, or an existing output directory
without `--overwrite`) and no new output pair was written. Missing authorised
S1 output is represented honestly as `not_run_missing_authorised_data`
(reason `missing_authorised_s1_outputs`) and remains a non-fatal, expected
blocked state until S1 is available.

See [`docs/data_cards/geo_experiment_readiness_v0.1.md`](docs/data_cards/geo_experiment_readiness_v0.1.md)
for the full status/reason-code vocabulary, the grid/split formulas, and the
authorisation rules.

## Verify

```bash
pytest
ruff check .
pyright
python scripts/export_json_schemas.py
```

See `WorkLog.md` for the actual commands run against this codebase and their
results.

## Layout

```
src/s3_ecological/
  schemas/        request/response contract models + shared enums
  interfaces/     Protocols for taxonomy, occurrence, geo-prior, suitability,
                  risk-policy, and LLM providers
  providers/      fixture / in-memory / local-snapshot / deferred-live
                  implementations of the provider Protocols
  ingestion/      offline GBIF/ALA/generic-DwC -> local snapshot importer
                  (Milestone 1.5; outside the deterministic-core boundary)
  experiments/    offline pre-Milestone 2 readiness + spatial-split builder
                  (prepare.py orchestration, readiness.py, spatial_split.py;
                  outside the deterministic-core boundary; never trains a
                  model or calibrates fusion/risk parameters)
  taxonomy/       name -> ResolvedTaxon resolution
  occurrence/     cleaning, quality flags, haversine distance
  priors/         v0.1 nearest-clean-occurrence geographic baseline
  suitability/    null (always-unavailable) environmental-suitability model
  fusion/         soft-fusion combined_log_score + rerank_score
  risk/           six-rule deterministic risk-state precedence
  evidence/       traceable, content-addressed evidence records
  orchestration/  run_assessment(): wires the above into one pipeline
  agent/          optional offline mock LLM provider + typed tool wrappers
                  + a guarded, optional pydantic_ai adapter
  api/            local-only research-demo FastAPI app + static UI (below);
                  still not a production HTTP API - see "Local research demo"
  cli.py          demo/assess/import-occurrences/prepare-geo-experiment/
                  serve-demo commands
  settings.py     S3Settings (Prototype Implementation Profile v0.1 defaults)
tests/
  unit/           schemas, cleaning, distance, fusion, risk, evidence, taxonomy
  integration/    provider swap, offline agent tools, import boundary,
                  guarded pydantic_ai adapter
  safety/         no-absence-claim, no-incursion-claim, evidence traceability,
                  provider-failure safe degrade
  golden/         the six EarlyDesign.md section 20.3 acceptance cases
docs/decisions/   ADRs for the non-obvious implementation choices
config/           example TOML configuration files (not loaded by default)
data/, models/    empty placeholders for this prototype's own runtime, plus
                  data/external/m2/ (real, bounded GBIF/ALA occurrence and
                  iNaturalist image data) and data/local/ (gitignored real
                  M2 conversion/bundle/readiness outputs) - see
                  docs/m2_resource_inventory.md and
                  docs/data_cards/m2_occurrence_table_v1.md; no model
                  artifact is committed
```

## Known limitations (v0.1 prototype)

- The geographic baseline (`priors/geo_nearest_distance.py`) is an
  unvalidated nearest-occurrence heuristic, not a fitted species-distribution
  model. It is Milestone 1 scope only.
- `suitability/null_model.py` always reports environmental suitability as
  unavailable; no real suitability model is implemented.
- The incursion rule (`RiskState.POTENTIAL_INCURSION` / rule 2 of the
  risk-state precedence) never fires in this build — no validated rule
  exists yet, so an out-of-range case is always reported as
  `geographic_ood` instead, per EarlyDesign.md §9.
- `live_gbif`/`live_ala` occurrence providers are structurally wired but
  deliberately unimplemented: every query returns `provider_not_configured`.
- The runtime providers used by `demo`/`assess` are still fixture-backed only
  (`providers/` and `fixtures/golden/`), and the Milestone 1.5 importer's own
  test fixtures under `tests/fixtures/importer/` remain hand-written
  synthetic rows. A bounded, real GBIF/ALA occurrence dataset for the TF4
  genera *is* committed for Milestone 2 preparation, under
  `data/external/m2/` (see `docs/m2_resource_inventory.md`); it is not wired
  into the `demo`/`assess` runtime path, and committing it is a
  repository-storage decision only, not an experiment authorisation. See
  `docs/data_cards/m2_occurrence_table_v1.md` and
  `config/geo_experiment.m2.toml` for the M2-A occurrence-table conversion,
  import, and readiness-run commands built on top of it.
- The offline importer's name resolution (`import-occurrences` and
  `LocalSnapshotTaxonomyProvider`) is exact-normalized-name matching only -
  no fuzzy matching, no synonym database beyond what the input file itself
  states via `acceptedScientificName`.
- `coordinate_coarsening_decimals` is declared in `S3Settings` but not yet
  wired into any code path in this prototype.
- `prepare-geo-experiment` only builds a spatial train/val/test split and a
  readiness report; it does not implement S1, environmental suitability, or
  Milestone 2's geographic model itself, and it does not calibrate fusion
  weights or risk thresholds — those remain out of scope until S1 exists and
  the design-log's evaluation methodology is implemented separately.
- The `latitude_longitude_grid_v0.1` spatial-block strategy is equal-angle,
  not equal-area, and is not a production ecological-region definition; the
  `SpatialBlockStrategy` Protocol exists specifically so an H3, equal-area, or
  state/ecoregion strategy can be substituted later without changing the
  readiness-reporting or CLI code.

## M2-B temporary S1 evaluation input

The authorised M2 readiness gate now accepts a validated, external temporary
S1 bundle produced from a reproduced TF4 EfficientNet-B2 baseline. It is
strictly an offline research utility, not an S3 runtime provider and not the
original paper checkpoint. Its images, weights, prediction outputs, and
readiness artifacts remain in gitignored `data/local/`; the committed
provenance, validation logic, and limitations are in
`docs/model_cards/tf4_visual_baseline_v0.1.md`.

## M2-C geographic-prior reproduction and locked spatial-test evaluation

The geographic-prior (Mac Aodha, Cole & Perona) presence-only model has now
been reproduced, fit on the spatial `train` split only, and selected on the
spatial `validation` split only (`scripts/train_geo_prior.py`); the frozen
configuration was then evaluated exactly once on the locked spatial `test`
split via the unmodified fixed-fusion formula
(`src/s3_ecological/fusion/soft_fusion.py`, Prototype Implementation Profile
v0.1 constants unchanged). This is a single, experimental research
measurement, not a production-readiness or biosecurity/biological-efficacy
claim. Full method, frozen configuration, and separately-reported S1-only /
geographic-only / fixed-fusion metrics are in
`docs/model_cards/geo_prior_baseline_v0.1.md` and
`docs/m2c_evaluation_report.md`. All training data, checkpoints, and the
locked evaluation report remain in gitignored `data/local/`.

## M2-D geographic-prior robustness, ablation, and generalisation audit

M2-C's locked result remains the single primary confirmatory measurement,
unchanged and re-run by nothing below. M2-D is a separately labelled
robustness study that repeats the same frozen training recipe and evaluation
protocol, unmodified, on four additional pre-declared spatial partitions
(grid sizes 0.5°/1.0°/2.0°, seeds 7/42/123) plus a location-only (no-date)
ablation on M2-C's own reference partition, using M2-C's own already-trained
candidate read-only. Fixed fusion outperformed both S1-only and geographic-
only on every partition tested, while the geographic-only method's own
standalone accuracy varied more across partitions than either single-source
figure alone. Full per-partition results, the ablation comparison, and an
explicit list of conclusions this audit does not and cannot establish (no
out-of-distribution, calibration, incursion, or biosecurity-efficacy claim;
no new best-model or threshold selection) are in
`docs/m2d_robustness_report.md`. As with M2-C, all training data,
checkpoints, and evaluation reports remain in gitignored `data/local/`.

## Local research demo (image + geo upload -> fused visualization)

**This is a local research demo only. It is not a production system, not a
quarantine/inspection decision tool, and not a biosecurity decision system.**
It exists to let someone see what M2's reproduced TF4 visual model and
geo-prior model, combined through S3's existing fixed-fusion and risk logic,
actually output for one uploaded image plus a location - nothing more.

The visual model recognizes exactly **four genera** in a closed-set softmax
(`Anastrepha`, `Bactrocera`, `Ceratitis`, `Rhagoletis`); the four
probabilities sum to 1, but that does not mean these are the only taxa that
exist - there is no unknown-class detection. The geographic-prior score and
fusion result are the same unvalidated research-reproduction results
described above (M2-C/M2-D); this demo does not add, change, or recalibrate
any of them. Environmental fields you type in (host, trap type, habitat,
temperature, notes) are recorded and echoed back for context only - the
current model does not consume them.

### Install and run

```bash
pip install -e ".[api,demo-ml]"
s3-ecological serve-demo --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in a browser. If the required local M2
checkpoints (`data/local/m2/s1/training/fold-0/tf4_efficientnet_b2_best.pt`
and `data/local/m2/geo_prior/training/filts256_dateTrue/checkpoint.pt`) are
not present on the machine, `/api/health` reports them as unavailable and
`/api/assess` returns a clear, friendly error rather than crashing or
substituting a fabricated result.

### What the page does

1. Upload one image (PNG/JPEG/WebP; kept in memory only, never written to
   disk) or click "use sample image" to load the bundled synthetic
   placeholder (`api/static/sample_specimen.png` - a generated gradient, not
   a real specimen photo).
2. Enter a required latitude/longitude; optionally an observation date and
   environmental notes.
3. Click "Run Analysis." The server validates the input, runs the local TF4
   checkpoint for closed-set visual probabilities, calls the existing S3
   geo-prior/fusion/risk pipeline (`run_assessment`) unmodified, and returns
   the real `AssessmentResult` plus a small explanation sidecar built only
   from that result's own fields.
4. The results page shows: (A) a summary card with the closed-set/research
   framing; (B) a per-genus comparison table (visual probability, geographic
   support or "unavailable", and the fused rerank score labeled explicitly as
   a within-set ranking score, not a posterior); (C) a plain-language
   explanation; (D) a collapsible evidence/limitations panel with model
   versions, missing-evidence flags, and the fixed limitations list.

No coordinates are inferred beyond what you typed, no map service is called,
no red/green verdict is ever shown, and nothing about a missing date or
missing location is silently filled in - the pipeline's existing safe-
degradation path (`missing_evidence`, `review_required`) is used unchanged.

### Data handling

Uploaded images and submitted coordinates are held in memory for the
duration of one request only and are never written to disk or logged; server
logs record only a coarse (one-decimal) coordinate, the top genus, and the
risk state. Nothing under `data/local/` is created or modified by this demo.

### What this demo intentionally does not implement

- No Grad-CAM or other morphological/visual explanation - the reasoning
  panel always shows a fixed sentence stating this instead of fabricating
  one.
- No environmental-suitability model - `NullSuitabilityModel` (always
  "unavailable") is used unchanged, same as the rest of S3.
- No external API, LLM, online map service, GBIF, or ALA call of any kind.
- No species-level confirmation, pest-quarantine conclusion, incursion
  confirmation, or absence claim, in any wording on the page.
