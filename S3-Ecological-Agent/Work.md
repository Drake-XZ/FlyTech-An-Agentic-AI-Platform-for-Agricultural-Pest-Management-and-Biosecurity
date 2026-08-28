# S3 Ecological Agent — Implementation Work Log

This file is **append-only**. New work is added as a new dated section at the
end of the file, so this file remains a faithful history of what was done and
verified. Non-semantic corrections to mathematical rendering, spelling,
formatting, or broken links may be applied directly in place when they do not
alter historical claims, decisions, results, or timestamps.

---

## 2026-08-28 19:15 Australia/Sydney

### Scope

Initial implementation of the FlyTech S3 Ecological Agent as a runnable,
tested, offline-first Python package, covering exactly:

- **Milestone 0** (EarlyDesign.md): package skeleton, validated request/
  response schemas with exportable JSON Schema, the `LLMProvider` boundary
  and a deterministic mock provider, and a fixture-backed CLI/library entry
  point.
- **Milestone 1**: occurrence providers (in-memory, local-snapshot,
  deferred-live GBIF/ALA stubs), occurrence cleaning and quality flags, the
  v0.1 deterministic nearest-clean-occurrence geographic baseline, soft-
  fusion re-ranking, the six-rule deterministic risk-state policy, and
  traceable evidence/provenance records.
- **§23.1** "Core engineering prototype definition of done."

Explicitly **out of scope** and not claimed as done: §23.2's conditional
research-validation requirements (no real GBIF/ALA data, no fitted
species-distribution model, no incursion-rule validation), Milestones 2-4,
and any business logic belonging to S1/S2/S4/S5/S6, the orchestrator, or a
UI. No external LLM call, network request, or API credential was used or is
required to run or test this code.

### Modification order

1. Read `EarlyDesign.md` in full and froze **Prototype Implementation
   Profile v0.1** as the normative spec for schemas, thresholds, the
   geographic-baseline formula, fusion formula, and risk-state precedence.
2. Wrote three ADRs (`docs/decisions/0001-0003`) recording the
   TOML-config/argparse-CLI choice, the optional `pydantic-ai`/`fastapi`
   boundary, and shipping golden fixtures inside the installed package.
3. Built the package skeleton (`pyproject.toml`, `src/s3_ecological/`
   layout) and the schema layer (`schemas/enums.py`, `schemas/common.py`,
   `schemas/request.py`, `schemas/response.py`).
4. Defined the provider-facing Protocols (`interfaces/taxonomy.py`,
   `occurrence.py`, `priors.py`, `suitability.py`, `risk.py`, `llm.py`).
5. Implemented the deterministic core: `taxonomy/resolve.py`,
   `occurrence/cleaning.py` + `distance.py`, `priors/geo_nearest_distance.py`,
   `suitability/null_model.py`, `fusion/soft_fusion.py`, `risk/policy.py`,
   `evidence/records.py`.
6. Implemented concrete providers (`providers/taxonomy_fixture.py`,
   `occurrence_memory.py`, `occurrence_local_snapshot.py`,
   `occurrence_live_deferred.py`, `factory.py`) and settings
   (`settings.py`, TOML example files under `config/`).
7. Wired everything together in `orchestration/pipeline.py`
   (`run_assessment`) plus request validation (`orchestration/validation.py`).
8. Implemented the optional agent layer: `agent/mock_provider.py`,
   `agent/tools.py` (typed `ToolResult`-returning wrappers), and the
   guarded-import `agent/pydantic_ai_adapter.py`.
9. Implemented `cli.py` (`demo`, `assess` subcommands) and
   `scripts/export_json_schemas.py`.
10. Built the six golden acceptance fixtures under
    `src/s3_ecological/fixtures/golden/<case>/` and the loader
    (`fixtures/golden_loader.py`).
11. Wrote the full test suite: `tests/unit/`, `tests/integration/`,
    `tests/safety/`, `tests/golden/`.
12. Ran `pyright` and iteratively fixed every reported error (see
    "Methods and design decisions" and "Known limitations" below for what
    each fix was and why).
13. Re-ran the full test suite, `ruff`, the JSON Schema export script, and
    both CLI subcommands to confirm zero regressions from the pyright-driven
    edits.
14. Wrote this Work.md entry, then performed the git add/commit/push.

### Methods and design decisions

- **Stdlib `argparse` CLI, TOML config via `tomllib`, only `pydantic>=2` as a
  hard runtime dependency** — see ADRs 0001-0002. `pydantic-ai` and
  `fastapi` are optional extras (`.[agent]`, `.[api]`); the deterministic
  core (`taxonomy/`, `occurrence/`, `priors/`, `suitability/`, `fusion/`,
  `risk/`, `evidence/`) never imports either, enforced by
  `tests/integration/test_import_boundary.py` parsing each module's AST.
- **Golden fixtures ship inside the installed package**
  (`src/s3_ecological/fixtures/golden/`), not under `tests/`, so both the
  test suite and `cli.py demo --fixture <name>` load the exact same fixture
  data via `importlib.resources` — see ADR 0003.
- **Geographic baseline (Profile v0.1 steps 1-7)**: clean occurrence
  records, take the haversine distance to the nearest usable one, and
  convert it to `geo_support = exp(-distance_km / geo_distance_scale_km)`.
  When there is no usable record, `geo_support` is `None` (never `0.0`) so
  "no evidence" is never confused with "confirmed absent" — a direct
  EarlyDesign.md invariant, not an implementation detail.
- **Environmental suitability is a `NullSuitabilityModel`**: it always
  returns `suitability=None` plus a `component_unavailable` warning. This is
  a deliberate stub per Milestone-1 scope, not a bug.
- **Risk-state precedence** (`risk/policy.py`) implements the six-rule
  ordering from EarlyDesign.md §9 exactly; the potential-incursion rule is
  wired but its trigger condition is hard-coded to never fire in this build
  (no validated rule exists yet), so an out-of-range candidate is always
  reported as `geographic_ood`.
- **Pyright fix pattern**: every one of the 88 initial `pyright` errors (see
  below) was individually triaged as either (a) a genuine, if currently
  dormant, correctness gap — fixed by tightening runtime behaviour, most
  notably `orchestration/pipeline.py`'s candidate construction, which
  previously would have raised a `pydantic.ValidationError` (crashing that
  assessment) if a resolved taxon's `taxon_ids` map lacked the configured
  provider's key; it now excludes that candidate from geo/suitability
  scoring instead, which degrades gracefully rather than crashing, per the
  spec's "must not crash" requirement — or (b) a pure static-analysis
  narrowing limitation on already-correct runtime logic (`Traversable`-to-
  `Path` conversions, dict-typed `**kwargs` unpacking in test helpers,
  `ToolResult.data: T | None` accessed without a guard, `list[T]` invariance
  vs. `Sequence[T]` covariance) — fixed with local variables, walrus-bound
  narrowing, explicit `assert`s documenting a real invariant, or (for one
  deliberately-invalid test input) a scoped `# type: ignore[call-arg]`.
  Nothing was fixed by weakening a Protocol's required-field guarantee or by
  disabling a check globally.
- **`agent/pydantic_ai_adapter.py`'s remaining `pyright` findings** (guarded
  `pydantic_ai` import + the `Agent`/`TestModel` construction that depends on
  it) are suppressed with scoped `# type: ignore[reportMissingImports]` /
  `# type: ignore[reportOptionalCall]` comments rather than any change to
  the guard logic itself — the guarded-import boundary is intentional
  (documented in the module's own docstring) so that this module, and
  everything that imports it, loads whether or not the optional `agent`
  extra is installed.

### Resources / frameworks / existing code

- `EarlyDesign.md` (existing, read-only) — the sole specification source.
- No other existing FlyTech code was reused, since no S1/S2/etc. Python code
  existed in the repository prior to this work; this is greenfield within
  `S3-Ecological-Agent/`.
- Frameworks: `pydantic>=2.6,<3` (hard dependency); `pytest`, `pytest-cov`,
  `ruff`, `pyright` (dev-only); `pydantic-ai` (optional `agent` extra, not
  installed in the development environment — its adapter test is
  self-skipping); no `fastapi`/`uvicorn` code was written (the `api/` package
  is a documented stub only).
- Development environment actually used: Python 3.13.14 (Windows, via the
  existing Anaconda installation) with `pip`, not Python 3.11 or `uv` — the
  package declares `requires-python = ">=3.11"` and contains no 3.13-only
  syntax; `uv` is documented as the preferred tool in `README.md` but was
  not available locally, so `pip install -e ".[dev]"` was the fallback
  actually run.

### Files and components created or modified

All paths below are new in this entry except where noted as "modified in
this pyright fix-up pass":

- `pyproject.toml`, `README.md`, `.gitignore`
- `docs/decisions/0001-toml-config-and-argparse-cli.md`,
  `0002-optional-pydantic-ai-boundary.md`,
  `0003-golden-fixtures-in-package.md`
- `config/sources.example.toml`, `config/thresholds.example.toml`
- `data/README.md`, `data/raw/.gitkeep`, `data/interim/.gitkeep`,
  `data/processed/.gitkeep`, `models/README.md`
- `scripts/export_json_schemas.py`
- `src/s3_ecological/__init__.py`, `settings.py` (settings.py's
  `S3Settings.load()` signature modified in the pyright fix-up pass:
  `config_paths` widened from `list[str | Path] | None` to
  `Sequence[str | Path] | None`)
- `src/s3_ecological/schemas/{enums,common,request,response}.py`
- `src/s3_ecological/interfaces/{taxonomy,occurrence,priors,suitability,risk,llm}.py`
- `src/s3_ecological/providers/{taxonomy_fixture,occurrence_memory,occurrence_local_snapshot,occurrence_live_deferred,factory,fixture_occurrences}.py`
- `src/s3_ecological/taxonomy/resolve.py`
- `src/s3_ecological/occurrence/{cleaning,distance}.py` (cleaning.py's
  coordinate-uncertainty check refactored in the pyright fix-up pass to
  narrow `record.coordinate_uncertainty_m` through a local variable instead
  of a dict/attribute expression pyright could not narrow twice)
- `src/s3_ecological/priors/geo_nearest_distance.py` (a
  `_distance_to_usable_record` helper was added in the pyright fix-up pass,
  with an explicit `assert record.latitude is not None and record.longitude
  is not None` documenting the invariant that `cleaning.py`'s
  `usable_for_distance` filter already enforces at runtime)
- `src/s3_ecological/suitability/null_model.py`
- `src/s3_ecological/fusion/soft_fusion.py`
- `src/s3_ecological/risk/policy.py`
- `src/s3_ecological/evidence/records.py`
- `src/s3_ecological/orchestration/{pipeline,validation}.py` (pipeline.py
  modified in the pyright fix-up pass: introduced an explicit `location`
  local variable narrowed once and reused for both the geo-prior and
  suitability request construction; rewrote the `GeoPriorCandidateTaxon`
  and `SuitabilityCandidateTaxon` list comprehensions to use a walrus-bound
  `taxon_id` filter that skips a candidate gracefully — rather than raising
  a `pydantic.ValidationError` — if its resolved taxon lacks the configured
  taxonomy provider's key; reused a walrus-bound `resolved_taxon` for both
  `taxon_id` and `ambiguous_taxonomy` in the risk-candidate construction)
- `src/s3_ecological/agent/{mock_provider,tools}.py`
- `src/s3_ecological/agent/pydantic_ai_adapter.py` (scoped `# type: ignore`
  comments added in the pyright fix-up pass on the guarded `pydantic_ai`
  imports and the `Agent(...)` construction; no change to the guard logic)
- `src/s3_ecological/api/__init__.py` (documented stub only)
- `src/s3_ecological/cli.py`
- `src/s3_ecological/fixtures/golden_loader.py` (the `Traversable`-returning
  `importlib.resources.files(...)` result modified in the pyright fix-up
  pass to be stringified — `Path(str(resources.files(...)))` — before being
  wrapped in `pathlib.Path`)
- `src/s3_ecological/fixtures/golden/{supported_same_location,geographic_ood_review,no_occurrence_records,provider_not_configured,missing_location,truncated_top_k}/{request,expected}.json`
  (plus `occurrences.json` for the two cases that need a snapshot)
- `tests/unit/test_{schemas,cleaning,distance,fusion,risk_policy,evidence_records,taxonomy_fixture}.py`
  (all seven modified in the pyright fix-up pass: `test_cleaning.py`,
  `test_evidence_records.py`, `test_risk_policy.py` had their
  `**overrides`/`defaults = dict(...)` helper patterns explicitly annotated
  `**overrides: Any` / `defaults: dict[str, Any]`; `test_schemas.py` gained
  one scoped `# type: ignore[call-arg]` on a deliberately-invalid-input
  test; `test_taxonomy_fixture.py` was rewritten in full to guard every
  `ToolResult.data` access with `assert result.data is not None`)
- `tests/integration/test_{agent_offline,import_boundary,provider_swap,pydantic_ai_adapter}.py`
  (`test_agent_offline.py`, `test_import_boundary.py`, `test_provider_swap.py`
  modified in the pyright fix-up pass to add `assert result.data is not
  None` guards, respectively a `Traversable`-to-`Path` stringify fix)
- `tests/safety/test_safety_properties.py`
- `tests/golden/test_golden_cases.py` (modified in the pyright fix-up pass:
  the rerank-score assertion now filters to `c.rerank_score is not None`
  before building its `dict[str, float]`, matching the schema's genuinely
  optional `rerank_score: float | None`)
- `tests/{unit,integration,safety,golden}/__init__.py`, `tests/__init__.py`

### Functionality added

- Validated `ObservationRequest` / `AssessmentResult` (and all nested)
  Pydantic v2 models, each exporting a JSON Schema via
  `scripts/export_json_schemas.py`.
- Fixture-backed taxonomy resolution (`FixtureTaxonomyProvider`) with
  case-insensitive matching, synonym resolution, and ambiguous-match
  handling that never invents a resolution via partial string matching.
- Three occurrence providers behind one `OccurrenceProvider` Protocol:
  in-memory, local JSON snapshot, and deferred-live GBIF/ALA stubs that
  always return `provider_not_configured` rather than crashing or
  fabricating data.
- Occurrence cleaning with explicit quality flags and cleaning-action
  records (duplicate detection, missing/zero/out-of-range coordinates,
  unknown or excessive coordinate uncertainty, invalid dates).
- Haversine nearest-usable-occurrence distance and the v0.1
  `geo_support = exp(-distance/scale)` transformation, with `None` (never
  `0.0`) returned when there is no usable evidence.
- Preserved raw visual-model probabilities alongside the fused
  `combined_log_score` and softmax-normalized `rerank_score`.
- Deterministic six-rule risk-state precedence with structured
  `review_reasons`.
- Structured `Issue` warnings/errors with stable `IssueCode`s and a
  `retryable` flag.
- Evidence records with source, dataset, retrieval time, and a
  content-addressed `evidence_id`, referenced from each reranked candidate's
  `supporting_evidence_ids`.
- Versioned configuration (`S3Settings`, "prototype-v0.1"), profile version,
  model-version and threshold-version reporting on every `AssessmentResult`.
- One deterministic library entry point (`run_assessment`) and one
  `s3-ecological` CLI with `demo --fixture <name>` and
  `assess --input <path> --output <path|->` subcommands.
- An offline `MockLLMProvider` plus typed `ToolResult`-returning tool
  wrappers (`agent/tools.py`) that never call a network or an LLM, and an
  optional, guarded `pydantic_ai` adapter that is inert unless the `agent`
  extra is installed.
- Six golden acceptance fixtures covering: full geographic support,
  geographic out-of-range, no occurrence records, an unconfigured live
  provider, a missing location, and truncated top-k reranking.

### How to use it

```bash
cd S3-Ecological-Agent
pip install -e ".[dev]"

python -m s3_ecological.cli demo --fixture supported_same_location
python -m s3_ecological.cli assess --input <path-to-ObservationRequest.json> --output -
```

Library entry point:

```python
from s3_ecological import S3Settings, run_assessment
```

See `README.md` for the full worked example, install instructions
(including the `uv`-preferred / `pip`-fallback split), package layout, and
known limitations.

### Verification performed

All of the following were **actually executed** in this session, from
`S3-Ecological-Agent/`, against Python 3.13.14 (the only interpreter
available in this development environment; the package targets
`>=3.11` and uses no 3.13-only syntax):

- `python -m pytest --cov=s3_ecological --cov-report=term-missing`
  → **103 passed, 2 skipped** (the 2 skips are
  `tests/integration/test_pydantic_ai_adapter.py`, self-skipping because the
  optional `pydantic_ai` extra is not installed) — **91% overall statement
  coverage**. Lowest-covered modules are `cli.py` (0%, not exercised by
  pytest itself — but exercised manually below via the golden-case
  subprocess test and manual runs) and `agent/pydantic_ai_adapter.py` (56%,
  the guarded-unavailable branch and the never-executed real-package
  branch).
- `python -m ruff check .` → **All checks passed!**
- `python -m pyright` → **0 errors, 0 warnings, 0 informations** (down from
  88 on the first run; every finding was individually triaged and fixed or,
  for the four `agent/pydantic_ai_adapter.py` guarded-import findings,
  suppressed with a scoped, documented `# type: ignore` rather than by
  weakening the guard).
- `python scripts/export_json_schemas.py` → exported 14 JSON Schema files
  to `json_schemas/` (gitignored, generated output) with no errors.
- `python -m s3_ecological.cli demo --fixture supported_same_location` →
  ran to completion, printed a well-formed `AssessmentResult` JSON document
  with `risk_state: "ecologically_supported"`, `review_required: false`.
- `python -m s3_ecological.cli assess --input src/s3_ecological/fixtures/golden/supported_same_location/request.json --output -`
  → ran to completion against default (fixture) providers, printed a
  well-formed `AssessmentResult` JSON document with
  `status: "completed_with_warnings"` (the default fixture occurrence
  provider's records are geographically distant from the default request
  location, correctly producing `geographic_ood` rather than a fabricated
  support score) — confirms the CLI's own default provider wiring, as
  distinct from the golden-fixture-snapshot path exercised by `demo` and by
  the pytest golden-case tests.

No test was reported as passing without being run. No network access or
LLM/API credential was used by any of the above commands.

### Extension and integration guidance

- **Milestone 2 (learned geographic prior)**: implement a new class
  satisfying `interfaces/priors.py::GeoPriorModel` and wire it in via
  `providers/factory.py` / `S3Settings`; `NearestDistanceGeoPriorModel`
  stays available as the v0.1 fallback/reference baseline.
- **Environmental suitability**: implement `interfaces/suitability.py::
  SuitabilityModel` and replace `NullSuitabilityModel` at the call site in
  `orchestration/pipeline.py`; no other module needs to change, since the
  pipeline only depends on the Protocol.
- **Live GBIF/ALA integration**: fill in `providers/occurrence_live_deferred.py`
  behind the existing `OccurrenceProvider` Protocol; `factory.py` already
  routes `occurrence_provider="live_gbif"/"live_ala"` to these classes, so no
  other call site needs to change.
- **A real LLM provider**: implement `interfaces/llm.py::LLMProvider`, or
  install the `agent` extra and enable `agent/pydantic_ai_adapter.py`'s
  `PydanticAIAdapter` with a real model. Per EarlyDesign.md, any such
  provider must only interpret/explain — it must never be given a path to
  override a score, risk state, or evidence record computed by the
  deterministic core.
- **An HTTP API**: `api/__init__.py` is an intentionally empty, documented
  stub; add FastAPI routes there that call `run_assessment` directly, behind
  the `api` optional extra, once justified by an actual integration need.
- **S1/S2/S4/S5/S6/orchestrator integration**: those systems should treat
  `run_assessment` (or the future `api/` HTTP surface) as the sole S3 entry
  point and `schemas/request.py`/`response.py` as the sole contract; no
  other module in this package is intended to be imported directly by an
  external caller.

### Maintenance and modification guidance

- Treat `EarlyDesign.md` and the frozen Prototype Implementation Profile
  v0.1 defaults in `settings.py` as normative; any deviation should be
  recorded as a new ADR under `docs/decisions/`, not made silently.
- The deterministic-core import boundary
  (`tests/integration/test_import_boundary.py`) will fail if any of
  `taxonomy/`, `occurrence/`, `priors/`, `suitability/`, `fusion/`, `risk/`,
  `evidence/` ever imports `pydantic_ai` or `fastapi` — keep it that way.
  Add new deterministic-core subpackages to that test's
  `DETERMINISTIC_PACKAGES` list if the layout grows.
- Golden fixtures are the acceptance contract: if `EarlyDesign.md` §20.3's
  expectations for a case change, update both the fixture JSON under
  `src/s3_ecological/fixtures/golden/<case>/` and the corresponding
  assertions in `tests/golden/test_golden_cases.py` together, and record why
  in a new Work.md entry.
- Every new public Pydantic model should be added to
  `scripts/export_json_schemas.py`'s model list so its schema stays
  exported and reviewable.
- When adding a new required field to any of the four "candidate taxon"
  input models (`GeoPriorCandidateTaxon`, `SuitabilityCandidateTaxon`,
  `CandidateRiskInput`, `FusionInput`), check whether it should be Optional
  the way `taxon_id` deliberately is on the latter two — the asymmetry is
  intentional (see "Methods and design decisions" above) and callers rely on
  it.
- Run `pytest`, `ruff check .`, and `pyright` before committing any change
  to `src/s3_ecological/` or `tests/` — all three are currently at a clean
  baseline (0 pyright errors, 0 ruff violations, 103 passed/2 skipped) and
  should stay that way.

### Known limitations and deferred work

- Environmental suitability is entirely stubbed (`NullSuitabilityModel`) —
  no real model exists yet.
- The potential-incursion risk rule never fires in this build — no
  validated trigger condition has been implemented; an out-of-range
  candidate is always classified `geographic_ood` instead.
- `live_gbif`/`live_ala` occurrence providers are structural stubs only;
  every call returns `provider_not_configured`, never fabricated data.
- No real occurrence or taxonomy dataset is included or was used — only
  synthetic fixtures. This prototype makes no claim about real-world
  ecological accuracy (§23.2 is explicitly not attempted).
- `S3Settings.coordinate_coarsening_decimals` is declared but not wired into
  any code path yet.
- `cli.py` has 0% direct pytest coverage (it is exercised by one
  subprocess-based golden test and by the two manual runs recorded above,
  but not by a dedicated unit test) — a future pass could add
  `CliRunner`-style tests if `cli.py` grows more branching logic.
- `agent/pydantic_ai_adapter.py` was never exercised against a real
  `pydantic_ai` installation in this environment (the extra is not
  installed); its guarded/skippable test
  (`tests/integration/test_pydantic_ai_adapter.py`) is written and will run
  automatically once the extra is present, but that has not been verified
  end-to-end here.
- Development and verification used Python 3.13.14, not Python 3.11 or
  `uv`, because neither was available in this environment; nothing in the
  code depends on a 3.12/3.13-only feature, but this has not been verified
  by actually running the suite under 3.11.

### Git record

- Branch: `codex/s3-design-offline-first`.
- Commit message: `feat(s3): build offline ecological agent prototype`.
- Commit hash and push status: recorded in the assistant's final report for
  this session (this Work.md entry was written immediately before staging
  and committing, so the hash could not be self-referentially included
  here).

---

## 2026-08-28 21:31 Australia/Sydney

### Scope

Documented the exact deterministic mathematical specification currently implemented by the S3 prototype, including symbol definitions, formulas, frozen Profile v0.1 parameter values, state thresholds, expert-review rules, uncertainty rules, and the engineering tests used to evaluate them. No scoring or risk logic was changed in this update.

This entry also establishes the following maintenance rule:

- every future update to `EarlyDesign.md` must add a new timestamped Design Change Log subsection at the physical end of that file;
- every future update to `Work.md` must add a new timestamped work section at the physical end of this file;
- existing historical entries must not be rewritten, reordered, or deleted.

### Source-of-truth code inspected

- `src/s3_ecological/occurrence/distance.py`
- `src/s3_ecological/occurrence/cleaning.py`
- `src/s3_ecological/priors/geo_nearest_distance.py`
- `src/s3_ecological/fusion/soft_fusion.py`
- `src/s3_ecological/risk/policy.py`
- `src/s3_ecological/orchestration/pipeline.py`
- `src/s3_ecological/orchestration/validation.py`
- `src/s3_ecological/settings.py`
- `config/thresholds.example.toml`
- matching unit, integration, safety, and golden tests under `tests/`

### Symbols

| Symbol | Meaning |
|---|---|
| $O=(\phi_o,\lambda_o)$ | Observation latitude and longitude |
| $R_{ij}=(\phi_{ij},\lambda_{ij})$ | Occurrence record $j$ for candidate taxon $i$ |
| $R_E$ | Mean Earth radius in kilometres |
| $V_i$ | Cleaned occurrence records usable for distance for candidate $i$ |
| $n_i=|V_i|$ | Number of usable occurrence records for candidate $i$ |
| $d_{ij}$ | Great-circle distance from the observation to record $j$ |
| $d_i^{\min}$ | Nearest usable occurrence distance for candidate $i$ |
| $D$ | Geographic exponential distance scale |
| $g_i$ | Geographic support score for candidate $i$ |
| $Q_i$ | Evidence-quality category for candidate $i$ |
| $p_i$ | Raw visual probability supplied by S1 for candidate $i$ |
| $e_i$ | Environmental-suitability score, when available |
| $\varepsilon$ | Numerical stabiliser used inside logarithms |
| $w_g,w_e$ | Geographic and environmental fusion weights |
| $s_i$ | Unnormalised combined log score |
| $q_i$ | Within-submitted-set softmax reranking score |
| $\delta$ | Candidate probability-sum tolerance |
| $\tau_s$ | Minimum geographic support for `ecologically_supported` |
| $\tau_o$ | Maximum geographic support for `geographic_ood` |
| $N_o$ | Minimum usable occurrence count required for geographic OOD |
| $L$ | Boolean indicating whether a valid observation location is available |
| $X_i$ | Boolean environmental-conflict flag for candidate $i$ |
| $A_i$ | Boolean ambiguous-taxonomy flag for candidate $i$ |

Latitude and longitude inputs are converted from degrees to radians before the trigonometric distance calculation.

### 1. Occurrence usability

A record belongs to $V_i$ only when it has valid coordinates, known coordinate uncertainty no greater than $U_{\max}$, is not a configured centroid, is not captive/cultivated, and is not an exact duplicate. Missing uncertainty excludes the record from distance scoring. Zero coordinates and implausible event dates are flagged but are not, by themselves, excluded.

Current values:

$$
U_{\max}=50{,}000\ \mathrm{m}
$$

$$
\eta_c=0.0001^\circ
$$

where $\eta_c$ is the configured-centroid matching tolerance. The default configured-centroid list is empty.

### 2. Great-circle distance

For each usable record:

$$
\Delta\phi_{ij}=\phi_{ij}-\phi_o,
\qquad
\Delta\lambda_{ij}=\lambda_{ij}-\lambda_o
$$

$$
a_{ij}=\sin^2\left(\frac{\Delta\phi_{ij}}{2}\right)
+\cos(\phi_o)\cos(\phi_{ij})
\sin^2\left(\frac{\Delta\lambda_{ij}}{2}\right)
$$

$$
d_{ij}=2R_E\,\mathrm{atan2}
\left(\sqrt{a_{ij}},\sqrt{1-a_{ij}}\right)
$$

Current value:

$$
R_E=6371.0088\ \mathrm{km}
$$

The nearest usable distance is:

$$
d_i^{\min}=\min_{j\in V_i}d_{ij}
$$

If $V_i=\varnothing$, the implementation returns `min_occurrence_distance_km=null`, `geo_support=null`, `evidence_quality=insufficient`, and a `no_records` warning. It does not infer species absence.

### 3. Geographic support

When at least one usable occurrence exists:

$$
g_i=\exp\left(-\frac{d_i^{\min}}{D}\right)
$$

Current value:

$$
D=500.0\ \mathrm{km}
$$

Examples under the current profile are:

$$
g_i(0)=1,
\qquad
g_i(500)=e^{-1}\approx0.367879,
\qquad
g_i(1000)=e^{-2}\approx0.135335
$$

### 4. Evidence quality

Define evidence quality as the deterministic function $Q_i=f_Q(n_i;N_o)$:

| First matching condition | $Q_i$ |
|---|---|
| $n_i=0$ | `insufficient` |
| $1\le n_i<N_o$ | `low` |
| $n_i\ge N_o$ | `medium` |

Current value:

$$
N_o=3
$$

Profile v0.1 never produces `evidence_quality=high`; that value is reserved for a future validated policy.

### 5. Visual/ecological soft fusion

The combined score is:

Let $A_i$ be the set of available, enabled ecological components for candidate $i$, and let $x_{ic}$ be component $c$'s score. The implemented fusion can be written as:

$$
s_i=\ln(p_i+\varepsilon)
+\sum_{c\in A_i}w_c\ln(x_{ic}+\varepsilon)
$$

For the current component set, $x_{ig}=g_i$ with weight $w_g$, and $x_{ie}=e_i$ with weight $w_e$.

An unavailable component is omitted from the sum; it is never replaced by zero or one.

Current values:

$$
\varepsilon=10^{-6},
\qquad
w_g=1.0,
\qquad
w_e=0.0
$$

The current `NullSuitabilityModel` returns $e_i=\varnothing$, so the environmental term is absent in Profile v0.1.

### 6. Reranking

Let:

$$
m=\max_j s_j
$$

The numerically stable softmax implemented by the code is:

$$
q_i=\frac{\exp(s_i-m)}{\sum_j\exp(s_j-m)}
$$

Therefore:

$$
\sum_i q_i=1
$$

only across the submitted candidate set. The result is a within-set ranking score, not a posterior probability over all possible taxa. Candidates are sorted by descending $s_i$; exact ties are broken by original S1 order and then by stable resolved taxon identifier, falling back to candidate identifier.

### 7. S1 probability validation

Each submitted visual probability must satisfy:

$$
0\le p_i\le1
$$

When `candidate_set_complete=true`:

$$
\left|\sum_i p_i-1\right|\le\delta
$$

When `candidate_set_complete=false`:

$$
\sum_i p_i\le1+\delta
$$

Current value:

$$
\delta=10^{-6}
$$

`omitted_probability_mass` is validated to lie in $[0,1]$ when supplied, but it does not currently affect fusion, risk-state classification, or expert-review logic.

### 8. Evidence-state thresholds and precedence

Current values:

$$
\tau_s=0.5,
\qquad
\tau_o=0.1,
\qquad
N_o=3
$$

Under $D=500\ \mathrm{km}$, the support thresholds imply:

$$
g_i\ge0.5
\iff
d_i^{\min}\le-500\ln(0.5)
\approx346.574\ \mathrm{km}
$$

$$
g_i\le0.1
\iff
d_i^{\min}\ge-500\ln(0.1)
\approx1151.293\ \mathrm{km}
$$

The first matching rule wins. For candidate state $S_i$:

| Precedence | First matching condition | $S_i$ |
|---:|---|---|
| 1 | No location is available, $g_i$ is unavailable, or $Q_i$ is `insufficient` | `unknown_or_insufficient_evidence` |
| 2 | $X_i$ is `true` | `environmental_conflict` |
| 3 | $n_i\ge N_o$ and $g_i\le\tau_o$ | `geographic_ood` |
| 4 | $Q_i$ is `low`, or $\tau_o<g_i<\tau_s$ | `weak_ecological_support` |
| 5 | $g_i\ge\tau_s$ | `ecologically_supported` |
| 6 | No earlier condition matched | `unknown_or_insufficient_evidence` |

At case level a separately validated potential-incursion rule would precede environmental conflict, but `_potential_incursion_rule_fires` currently always returns `False`, and `incursion_rule_enabled=false` by default. The pipeline currently supplies `environmental_conflict=false`, so neither state is produced by the present Profile v0.1 execution path.

### 9. Expert-review decision

For a successfully processed case, define three Boolean indicators:

$$
r=I_s\lor I_a\lor I_f
$$

where `review_required=true` exactly when $r$ is true:

| Indicator | Becomes true when |
|---|---|
| $I_s$ | The top state is `unknown_or_insufficient_evidence`, `geographic_ood`, `environmental_conflict`, or a future validated `potential_incursion` |
| $I_a$ | At least one submitted candidate has ambiguous taxonomy |
| $I_f$ | Request validation or unexpected internal processing fails |

Failed validation and unexpected internal processing failure also force expert review. `weak_ecological_support`, an unavailable environmental-suitability warning, `candidate_set_complete=false`, and `omitted_probability_mass` do not currently force review.

### 10. Uncertainty level

For the top reranked candidate, the first matching row determines $U$:

| Precedence | First matching condition | $U$ |
|---:|---|---|
| 1 | The top state is `unknown_or_insufficient_evidence` | `high` |
| 2 | The top evidence quality is `low`, or the top state is `weak_ecological_support`, `geographic_ood`, or `environmental_conflict` | `medium` |
| 3 | No earlier condition matched | `low` |

This is a deterministic Profile v0.1 heuristic, not a calibrated uncertainty model or confidence interval.

### 11. Assessment processing status

For a structurally valid assessment that reaches the result builder:

| First matching condition | Assessment status |
|---|---|
| At least one warning, error, or missing-evidence item exists | `completed_with_warnings` |
| Otherwise | `completed` |

Validation failure and unexpected internal failure use the separate statuses `failed_validation` and `failed` and force high uncertainty plus expert review.

### Current Profile v0.1 parameter register

| Symbol / setting | Current value | Meaning |
|---|---:|---|
| $R_E$ / Earth mean radius | `6371.0088 km` | Haversine distance radius |
| $D$ / `geo_distance_scale_km` | `500.0 km` | Geographic exponential decay scale |
| $U_{\max}$ / `max_coordinate_uncertainty_m` | `50000 m` | Maximum usable coordinate uncertainty |
| $\eta_c$ / centroid match tolerance | `0.0001°` | Configured-centroid equality tolerance |
| $N_o$ / `min_occurrences_for_ood` | `3` | Minimum usable records for OOD and medium evidence quality |
| $\tau_s$ / `geo_supported_min` | `0.5` | Ecologically-supported threshold |
| $\tau_o$ / `geo_ood_max` | `0.1` | Geographic-OOD maximum support threshold |
| $\delta$ / `probability_sum_tolerance` | `0.000001` | S1 probability-sum tolerance |
| $\varepsilon$ / `fusion_epsilon` | `0.000001` | Logarithm stabiliser |
| $w_g$ / `fusion_weight_geo` | `1.0` | Geographic fusion weight |
| $w_e$ / `fusion_weight_environment` | `0.0` | Environmental fusion weight |
| `incursion_rule_enabled` | `false` | Potential-incursion policy switch |

These values are reproducible engineering defaults for synthetic fixtures. They are not trained, calibrated, ecological, or regulatory thresholds and must be replaced only through a versioned decision supported by authorised validation data.

### Verification and evaluation currently performed

The repository evaluates these formulas as engineering behavior, not as real biological performance:

- distance unit tests verify identical-point distance, quarter-circle and antipodal arc lengths, symmetry, and non-negativity;
- fusion tests verify the exact log-linear calculation, omission of unavailable components, weight scaling, deterministic ordering, and a softmax sum of one;
- risk-policy boundary tests verify equality at $\tau_s=0.5$, OOD gating at $n_i\ge3$ and $g_i\le0.1$, weak-evidence behavior, ambiguity-driven review, and deterministic top-candidate selection;
- golden fixtures verify same-location full support, distant geographic OOD, no-record behavior, provider-not-configured degradation, missing-location handling, and truncated-top-k reranking;
- safety tests ensure that no records are never interpreted as species absence and that missing evidence forces safe escalation.

No real-data accuracy, calibration, OOD recall, false-alert rate, or incursion performance is claimed. Those evaluations remain conditional on authorised labelled data under `EarlyDesign.md` Section 19 and Section 23.2.

### Files modified

- `EarlyDesign.md`: moved the append-only Design Change Log to the physical end of the file and added the append-only documentation rule.
- `Work.md`: appended this mathematical specification, variable glossary, current parameter register, implementation notes, and evaluation status.

### Future maintenance

- When a formula or threshold changes, update the versioned code/configuration and its tests together.
- Append a new timestamped Design Change Log subsection to the end of `EarlyDesign.md` explaining the requirement change and rationale.
- Append a new timestamped section to the end of `Work.md` describing the implementation order, affected files, validation performed, compatibility impact, and upgrade or rollback guidance.
- Never silently alter historical entries or describe prototype fixture behavior as biological validation.
