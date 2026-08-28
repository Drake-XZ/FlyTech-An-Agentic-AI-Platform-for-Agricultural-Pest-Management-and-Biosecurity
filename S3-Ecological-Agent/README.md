# FlyTech S3 Ecological Agent

Offline-first ecological plausibility core for FlyTech's agricultural pest
management platform. This package implements **Milestone 0 + Milestone 1**
and the "core engineering prototype" definition of done from
[`EarlyDesign.md`](EarlyDesign.md) §23.1 — nothing from Milestones 2-4, and
none of the conditional research-validation requirements in §23.2.

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
pip install -e ".[agent]"   # adds pydantic-ai, for PydanticAIAdapter
pip install -e ".[api]"     # adds fastapi/uvicorn, for a future HTTP API
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

## Verify

```bash
pytest
ruff check .
pyright
python scripts/export_json_schemas.py
```

See `Work.md` for the actual commands run against this codebase and their
results.

## Layout

```
src/s3_ecological/
  schemas/        request/response contract models + shared enums
  interfaces/     Protocols for taxonomy, occurrence, geo-prior, suitability,
                  risk-policy, and LLM providers
  providers/      fixture / in-memory / local-snapshot / deferred-live
                  implementations of the provider Protocols
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
  api/            documented stub only - no HTTP API in this prototype
  cli.py          `s3-ecological` demo/assess commands
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
data/, models/    empty placeholders; no real data or model artifact is
                  committed in this prototype
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
- No real occurrence or taxonomy data is committed; only the fixture-backed
  providers under `providers/` and `fixtures/golden/` are used.
- `coordinate_coarsening_decimals` is declared in `S3Settings` but not yet
  wired into any code path in this prototype.
