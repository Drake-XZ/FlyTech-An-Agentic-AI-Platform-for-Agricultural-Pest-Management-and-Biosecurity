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

---

## 2026-08-29 00:20 Australia/Sydney

### Scope

Implementation of **Milestone 1.5: offline occurrence snapshot ingestion**,
exactly as specified in the `EarlyDesign.md` design record dated "2026-08-28
22:52 Australia/Sydney — Next implementation increment: offline occurrence
snapshot ingestion." This adds one new CLI subcommand
(`import-occurrences`), one new deterministic-adjacent ingestion module, one
new taxonomy provider, and the schemas/tests/docs needed to convert a
locally-held GBIF/ALA/generic-Darwin-Core occurrence export (or a previously
produced canonical bundle) into an on-disk `occurrences.json` +
`taxonomy.json` + `import-report.json` snapshot bundle that `assess` can
query offline via `occurrence_provider`/`taxonomy_provider = "local_snapshot"`.

Explicitly **out of scope**, and not touched: the Profile v0.1 math
(distance, fusion, risk-policy formulas/thresholds/precedence), the meaning
of any existing golden fixture, and any S1/S2/S4/S5/S6/orchestrator/UI
business logic. No network access, external API call, API key, real LLM
call, or real downloaded dataset was used or is required to run or test this
code; every fixture under `tests/fixtures/importer/` is a small,
hand-written synthetic file, not a real GBIF/ALA/ALA export.

### Modification order

1. Re-read `EarlyDesign.md`'s "offline occurrence snapshot ingestion" design
   record and `Work.md` in full to confirm this was implementing a design
   already recorded, not inventing new scope.
2. Added `schemas/snapshot.py`: `OccurrenceSnapshot`, `TaxonomySnapshotItem`,
   `TaxonomySnapshot`, `ImportRejection`, `OutputFileChecksum`,
   `ImportReport`, `ImportStatus` — all `ConfigDict(extra="forbid")`, mirroring
   the existing `schemas/request.py`/`response.py` style.
3. Added `ingestion/occurrence_snapshot.py` (`import_occurrence_snapshot`,
   `ImportFatalError`): field-mapping tables and `_resolve_format` for
   `gbif`/`ala`/`generic_dwc`, the canonical-JSON re-import path, row parsing
   and rejection, taxonomy-item construction and ambiguity marking, and the
   atomic write/checksum-verify/commit sequence.
4. Added `providers/taxonomy_local_snapshot.py`
   (`LocalSnapshotTaxonomyProvider`) implementing the existing
   `TaxonomyProvider` Protocol, reusing the same
   `interfaces/taxonomy.py::TaxonomyQuery`/`TaxonomyResolution` contract as
   `providers/taxonomy_fixture.py::FixtureTaxonomyProvider`.
5. Extended `providers/factory.py` with `validate_local_snapshot_bundle` and
   wired `taxonomy_provider="local_snapshot"`/`occurrence_provider=
   "local_snapshot"` into `build_taxonomy_provider`/`build_occurrence_provider`
   (the occurrence side, `LocalSnapshotOccurrenceProvider`, already existed
   from Milestone 1 — only the taxonomy side and the cross-bundle
   consistency check are new).
6. Added `S3Settings.taxonomy_snapshot_path` (`settings.py`), mirroring the
   existing `occurrence_snapshot_path`.
7. Added the `import-occurrences` subcommand to `cli.py`, reusing the
   existing `demo`/`assess` argparse structure and offline-only invariants
   documented at the top of that module.
8. Added three synthetic fixtures under `tests/fixtures/importer/`
   (`gbif_small.csv`, `ala_small.tsv`, `malformed_rows.csv`) and the data
   card `docs/data_cards/offline_occurrence_snapshot_v1.md`.
9. Wrote `tests/unit/test_occurrence_snapshot_import.py` (importer unit
   tests) and `tests/integration/test_imported_snapshot_pipeline.py`
   (import → `run_assessment` end-to-end tests), reusing `run_assessment`,
   `build_taxonomy_provider`/`build_occurrence_provider`,
   `NearestDistanceGeoPriorModel`, `NullSuitabilityModel`, and
   `DeterministicRiskPolicy` exactly as the existing golden/safety tests do —
   no scoring, cleaning, or risk logic was duplicated.
10. Registered the six new schema models in
    `scripts/export_json_schemas.py`, and documented the new subcommand and
    package-layout entry in `README.md` and the new `local_snapshot` block
    in `config/sources.example.toml`.
11. Ran the full test suite, found and fixed one genuine pre-existing
    implementation defect (see "Methods and design decisions" below), then
    ran `ruff check .` and `pyright` to a clean baseline, then ran real CLI
    example commands end to end.

### Methods and design decisions

- **Row-level rejection is per-row, not per-error.** A row can fail several
  checks at once (e.g. missing `scientificName` and a non-numeric latitude);
  the importer records exactly one `ImportRejection` per row, joining every
  triggering message with `"; "` and reporting the first error's `code`/
  `field` as primary — so `rejected_record_count` always equals the number of
  distinct bad *rows*, never the number of individual defects.
- **Zero accepted records is fatal, not a valid partial report.** If every
  row in an input file is rejected, `import_occurrence_snapshot` raises
  `ImportFatalError("zero accepted records; nothing to import")` and writes
  no bundle at all, rather than writing an empty-but-"completed" one. This
  matches `EarlyDesign.md`'s documented failure semantics and is exercised
  directly by `test_malformed_rows_all_rejected_is_fatal_and_writes_nothing`
  / `test_malformed_rows_alone_are_all_rejected_and_the_import_is_fatal`.
- **A genuine pre-existing bug was found and fixed in `_import_canonical`,
  and the fix deliberately departs from one literal sentence of the design
  text — this is called out explicitly, not glossed over.**
  `EarlyDesign.md`'s canonical-reimport wording says a canonical file's
  "dataset ID, retrieval time, licence, citation, **and source** must
  exactly match the CLI metadata." Read completely literally, this is
  self-contradictory with the design's own reimport use case: `--source
  canonical` is the CLI selector that is *always* the literal string
  `"canonical"` on this code path, while the file's own `source` field
  correctly records where its records originally came from (e.g. `"gbif"`).
  A prior implementation pass had compared these two directly, so
  re-importing any real gbif/ala/generic_dwc-sourced `occurrences.json`
  always raised `ImportFatalError` — permanently breaking the documented
  reimport workflow, and directly contradicting the pre-existing unit test
  `test_canonical_source_reimports_a_previous_occurrences_json_unchanged`
  (which asserts the reimport succeeds unchanged). Fixed by removing the
  `source` parameter and its comparison from `_import_canonical` entirely;
  only `dataset_id`/`retrieved_at`/`dataset_license`/`citation` are now
  checked against the current command line, and the file's own `source` is
  carried through to every record unchanged. Documented in both the
  function's docstring and
  `docs/data_cards/offline_occurrence_snapshot_v1.md`'s `--source canonical`
  section. `test_canonical_source_rejects_metadata_that_does_not_match_the_
  command_line` (dataset_id mismatch) is unaffected by this change and still
  passes.
- **Taxon-id/name ambiguity is preserved, never silently resolved.** When two
  distinct `taxon_id`s share one normalized scientific name (or a
  `submitted_names` entry), the importer keeps them as two separate
  `TaxonomySnapshotItem`s and marks both `ambiguous=True`
  (`_mark_ambiguous`), rather than merging them or picking a winner;
  `LocalSnapshotTaxonomyProvider.resolve` surfaces this as
  `ToolStatus.PARTIAL` with `candidate_matches` listing every match, exactly
  mirroring how the fixture taxonomy provider and the deterministic pipeline
  already treat ambiguity (`resolved_taxon.ambiguous` feeding
  `review_reasons=["ambiguous_taxonomy"]`) — no new ambiguity-handling logic
  was added to the pipeline itself.
- **Snapshot identity and cross-file consistency are checked at
  settings-build time, not at query time.** `validate_local_snapshot_bundle`
  (called from both `build_taxonomy_provider` and
  `build_occurrence_provider`, only when both providers are
  `"local_snapshot"`) checks matching `dataset_id`/`source_sha256` and that
  every occurrence record's `taxon_id` exists in the taxonomy bundle,
  raising `ValueError` fast rather than letting a half-updated bundle
  produce silent `TAXON_NOT_FOUND` results later.
- **Atomic, deterministic writes.** Each of the three output files is
  serialized with fixed indentation/`ensure_ascii=False`/Pydantic
  field-declaration key order (`_serialize`), written to a same-directory
  temp file (`_write_temp`), read back and SHA-256-verified, then committed
  with `os.replace` (`_verify_and_commit`) — re-running the importer on
  byte-identical input produces byte-identical output, and no failure
  partway through a single file's write can leave a half-written file at
  its final path.
- No Profile v0.1 formula, threshold, fusion weight, or risk-precedence rule
  was read, touched, or reinterpreted by any of this work.

### Resources / frameworks / existing code reused

- `interfaces/taxonomy.py::TaxonomyProvider`/`TaxonomyQuery`/
  `TaxonomyResolution` and `interfaces/occurrence.py::OccurrenceProvider`/
  `RawOccurrenceRecord`/`OccurrenceQuery` — the new provider and importer
  produce/consume these existing types unchanged.
- `providers/occurrence_local_snapshot.py::LocalSnapshotOccurrenceProvider`
  (already existed from Milestone 1) — reused unmodified as the occurrence
  side of the new bundle; only its taxonomy-side counterpart is new.
- `orchestration/pipeline.py::run_assessment`,
  `priors/geo_nearest_distance.py::NearestDistanceGeoPriorModel`,
  `suitability/null_model.py::NullSuitabilityModel`,
  `risk/policy.py::DeterministicRiskPolicy` — used as-is, unmodified, by the
  new integration tests and by the `assess` CLI example run below.
- `schemas/common.py::Issue`/`ToolResult`, `schemas/enums.py::IssueCode`/
  `ToolStatus` — reused by `LocalSnapshotTaxonomyProvider` exactly as
  `taxonomy_fixture.py` uses them.
- Pydantic v2 (`BaseModel`, `ConfigDict(extra="forbid")`, `Field`,
  `field_validator`/`model_validator`), `tomllib`-based `S3Settings.load`
  (unmodified), `argparse` (`cli.py`'s existing subparser pattern).

### Files and components created or modified

Created:

- `src/s3_ecological/schemas/snapshot.py` (171 lines) — snapshot/report
  Pydantic models.
- `src/s3_ecological/ingestion/__init__.py` (7 lines) and
  `src/s3_ecological/ingestion/occurrence_snapshot.py` (805 lines) — the
  importer.
- `src/s3_ecological/providers/taxonomy_local_snapshot.py` (101 lines) —
  `LocalSnapshotTaxonomyProvider`.
- `docs/data_cards/offline_occurrence_snapshot_v1.md` (151 lines) — field
  mappings, rejection codes, snapshot-identity rules, failure semantics,
  known limitations.
- `tests/fixtures/importer/gbif_small.csv`, `ala_small.tsv`,
  `malformed_rows.csv` — small, hand-written synthetic fixtures (6, 4, and 7
  lines respectively including header).
- `tests/unit/test_occurrence_snapshot_import.py` (361 lines, 18 tests).
- `tests/integration/test_imported_snapshot_pipeline.py` (239 lines, 5
  tests).

Modified:

- `src/s3_ecological/settings.py` — added `taxonomy_snapshot_path: str |
  None = None`.
- `src/s3_ecological/providers/factory.py` — added
  `validate_local_snapshot_bundle`; wired `local_snapshot` into
  `build_taxonomy_provider` and cross-checked it from
  `build_occurrence_provider`.
- `src/s3_ecological/cli.py` — added the `import-occurrences` subcommand and
  `_run_import_occurrences`.
- `scripts/export_json_schemas.py` — registered the six new snapshot/report
  models.
- `config/sources.example.toml` — added a commented-out `local_snapshot`
  configuration block.
- `README.md` — documented the new subcommand, its exit codes, the
  `ingestion/` package in the layout diagram, and two new known-limitation
  bullets (synthetic-fixture-only data, exact-name-matching-only
  resolution).

### Functionality added

- **`gbif`/`ala`/`generic_dwc` field mapping** — canonical field ← ordered
  fallback header list, per source, exactly as tabulated in
  `docs/data_cards/offline_occurrence_snapshot_v1.md` (e.g.
  `taxon_id` ← `acceptedTaxonKey`/`taxonKey`/`taxonID` for `gbif`,
  ← `acceptedConceptID`/`taxonConceptID`/`taxonID` for `ala`).
- **`--source canonical`** — re-imports a previously written
  `occurrences.json` unchanged (see the bugfix note above), rebuilding the
  taxonomy bundle by grouping the file's own `(taxon_id,
  scientific_name_raw)` pairs.
- **Six row-rejection codes**: `missing_scientific_name`,
  `missing_taxon_id`, `invalid_numeric_value`,
  `negative_coordinate_uncertainty`, `non_finite_numeric_value`,
  `invalid_record_schema` — one `ImportRejection` per bad row, never per
  individual defect.
- **`taxon_id` namespacing** (`gbif:...`/`ala:...`/`generic_dwc:...`) and
  **deterministic generated record ids**
  (`"generated:" + sha256(sorted header→value JSON)`, independent of row
  order) when no id header is present.
- **Snapshot identity**: `source_sha256` (input file bytes) shared across
  all three output files; `snapshot_key =
  "<dataset-id>:<sha256[:12]>:<mapping-version>"`.
- **Cross-file consistency validation** at settings-build time
  (`validate_local_snapshot_bundle`).
- **`LocalSnapshotTaxonomyProvider`**: exact Unicode-NFKC-normalized,
  case-folded name matching against both `scientific_name` and every
  `submitted_names` entry; zero matches → `TAXON_NOT_FOUND` warning; exactly
  one → `SUCCESS`; more than one → `PARTIAL` with `ambiguous=True` and every
  candidate listed.
- **Atomic, checksum-verified, deterministic output** for all three bundle
  files.

### How to use it

```bash
cd S3-Ecological-Agent
python -m s3_ecological.cli import-occurrences \
  --input tests/fixtures/importer/gbif_small.csv \
  --source gbif \
  --dataset-id demo-gbif-2026 \
  --retrieved-at 2026-08-28T00:00:00+10:00 \
  --dataset-license "CC-BY 4.0" \
  --citation "Example GBIF occurrence download, demo-gbif-2026" \
  --output-dir data/snapshots/example

python -m s3_ecological.cli assess \
  --input <path-to-ObservationRequest.json> \
  --config config/sources.example.toml   # with its local_snapshot block uncommented
```

Exit codes: `0` every row accepted; `2` bundle written but with one or more
row rejections recorded in `import-report.json`; `1` fatal error, no bundle
written. See `README.md`'s new "Offline occurrence snapshot ingestion"
section and `docs/data_cards/offline_occurrence_snapshot_v1.md` for the full
reference.

### Verification performed

All of the following were **actually executed** in this session, from
`S3-Ecological-Agent/`, against Python 3.13.14 (the only interpreter
available in this environment):

- `python -m pytest --cov=s3_ecological --cov-report=term-missing` →
  **130 passed, 2 skipped** (same 2 pre-existing `pydantic_ai`-extra skips
  as before) — **89% overall statement coverage**;
  `ingestion/occurrence_snapshot.py` at 89% (uncovered lines are mostly
  alternate fatal-error branches for conditions not separately unit-tested,
  e.g. a subset of `_load_query_parameters`/`_resolve_format` error
  messages), `providers/taxonomy_local_snapshot.py` at 88%,
  `providers/factory.py` at 91%. `cli.py` remains at 0% direct pytest
  coverage (as in the prior entry) but was exercised manually below.
- `python -m ruff check .` → **All checks passed!** (this pass also fixed
  ~30 pre-existing `E501`/`I001`/`F841` violations in
  `ingestion/occurrence_snapshot.py`,
  `tests/unit/test_occurrence_snapshot_import.py`, and
  `tests/integration/test_imported_snapshot_pipeline.py` that predated ruff
  ever having been run against this new code.)
- `python -m pyright` → **0 errors, 0 warnings, 0 informations** (one real
  finding fixed: `**_COMMAND_METADATA` unpacked directly into
  `import_occurrence_snapshot(...)` in the unit-test file made pyright
  believe a plain `dict[str, str]` could supply *any* keyword argument,
  including the `bool`-typed `overwrite` — fixed by typing
  `_COMMAND_METADATA` as a `TypedDict` with its four actual field names, so
  pyright now knows precisely which keywords it supplies).
- `python scripts/export_json_schemas.py` → exported 20 JSON Schema files
  (up from 14; the 6 new ones are `OccurrenceSnapshot`,
  `TaxonomySnapshotItem`, `TaxonomySnapshot`, `ImportRejection`,
  `OutputFileChecksum`, `ImportReport`) to `json_schemas/` (gitignored) with
  no errors.
- `python -m s3_ecological.cli import-occurrences --input
  tests/fixtures/importer/gbif_small.csv --source gbif --dataset-id
  demo-cli-gbif --retrieved-at 2026-08-29T00:00:00+00:00 --dataset-license
  "CC-BY 4.0" --citation "Demo run, synthetic fixture, not a real dataset."
  --output-dir <scratch-dir>` → exit code **0**; printed `ImportReport` JSON
  with `status: "completed"`, `accepted_record_count: 5`,
  `rejected_record_count: 0`, and one non-fatal `unrecognized_boolean`
  mapping warning (the fixture deliberately includes one unparseable
  `isCaptive` value); wrote `occurrences.json`/`taxonomy.json`/
  `import-report.json` to the scratch directory, verified present on disk.
- `python -m s3_ecological.cli assess --input <request.json> --config
  <settings.toml pointing occurrence_provider/taxonomy_provider =
  "local_snapshot" at the snapshot just written>` → exit code **0**; printed
  a well-formed `AssessmentResult` JSON document with
  `status: "completed_with_warnings"`,
  `resolved_taxon.ambiguous: true` (correctly reflecting the fixture's two
  distinct `taxon_id`s sharing the name "Bactrocera dorsalis"),
  `review_required: true`, `review_reasons: ["ambiguous_taxonomy"]`, and
  `data_snapshot_versions.gbif` equal to the imported bundle's own
  `snapshot_key` — confirming the full import → local-snapshot-providers →
  `run_assessment` path end to end, offline, using no fixture-golden
  shortcut.

No test was reported as passing without being run. No network access,
external API call, API key, or LLM/agent call was used by any command
above. The scratch directories used for the two manual CLI runs
(`D:/tmp_s3_demo/...`) were created and deleted outside the repository and
are not part of this commit.

### Extension and integration guidance

- **A new source format**: add its field-mapping table and a `_map_<source>`
  function in `ingestion/occurrence_snapshot.py`, add its name to
  `SUPPORTED_SOURCES`, and add a fixture + unit test under
  `tests/fixtures/importer/`/`tests/unit/` — no other module needs to
  change.
- **Fuzzy/synonym-aware taxonomy matching**: implement it as a new class
  satisfying `interfaces/taxonomy.py::TaxonomyProvider` (or extend
  `LocalSnapshotTaxonomyProvider` directly) and wire it in via
  `providers/factory.py`; `LocalSnapshotTaxonomyProvider`'s exact-match
  behavior stays available as the offline baseline.
- **Incremental/append import**: not implemented — a re-import always
  writes a fresh trio of files (see "Known limitations" below); a future
  increment could add an `--append` mode that reads the existing bundle via
  the same code path `--source canonical` already uses.
- Every new public Pydantic model under `schemas/` should be added to
  `scripts/export_json_schemas.py`'s `MODELS` list, exactly as the six new
  snapshot models were.

### Maintenance and modification guidance

- Treat this Work.md entry's bugfix note on `_import_canonical` as the
  authoritative account of why the code does not compare `source` on
  canonical reimport — do not "fix" it back to a literal reading of
  `EarlyDesign.md`'s single sentence without first re-reading this note and
  the still-passing
  `test_canonical_source_reimports_a_previous_occurrences_json_unchanged`.
- Run `pytest`, `ruff check .`, and `pyright` before committing any change
  to `src/s3_ecological/ingestion/`, `providers/taxonomy_local_snapshot.py`,
  or `schemas/snapshot.py` — all three are at a clean baseline (130
  passed/2 skipped, 0 ruff violations, 0 pyright errors) as of this entry.
- Keep `ingestion/`, `providers/`, and `schemas/` outside the
  deterministic-core import boundary check's `DETERMINISTIC_PACKAGES` list
  — they are ingestion/provider code, not part of
  `taxonomy/`/`occurrence/`/`priors/`/`suitability/`/`fusion/`/`risk/`/
  `evidence/`, and must stay free to depend on `json`/`hashlib`/`tempfile`/
  filesystem I/O that the deterministic core deliberately avoids.

### Known limitations and deferred work

- Exact-normalized-name matching only; no fuzzy matching, phonetic
  matching, or external synonym database — inherited directly from
  `EarlyDesign.md`'s scope for this milestone, not a shortcut taken here.
- No incremental/append mode: every (re-)import writes a fresh trio of
  files, optionally replacing the previous ones with `--overwrite`.
- `--source canonical` still requires an exact match on
  `dataset_id`/`retrieved_at`/`dataset_license`/`citation` against the
  current command line; it cannot "merge" or partially update one field of
  a previous run.
- No cross-file filesystem transaction: a process kill between the three
  individual atomic commits could still leave the trio partially updated;
  `validate_local_snapshot_bundle` is the guard against consuming such a
  partial bundle, not a mechanism that prevents it from occurring.
- `ingestion/occurrence_snapshot.py` is at 89% branch coverage, not 100% —
  the uncovered lines are alternate fatal-error message branches (e.g.
  additional `_load_query_parameters`/`_resolve_format`/`_read_input` error
  paths) that were reasoned through but not each given a dedicated unit
  test in this pass.
- No real occurrence or taxonomy dataset is included or was used anywhere
  in this work — every fixture under `tests/fixtures/importer/` is
  hand-written and synthetic. This entry makes no claim about real-world
  ecological accuracy, GBIF/ALA API compatibility beyond the documented
  field-mapping tables, or biosecurity decision performance.

### Git record

- Branch: `S3-design-offline-first` (no new branch was created; this is the
  branch that was already checked out at the start of this session).
- Commit message: recorded in the assistant's final report for this
  session (this Work.md entry was written immediately before staging and
  committing, so the hash could not be self-referentially included here).
- Only the S3-Ecological-Agent files listed under "Files and components
  created or modified" above, plus this Work.md entry, were staged and
  committed — the user's own pre-existing untracked `LECTURE/`, `WEEK 4/`,
  `WEEK 5/`, and `.gitignore` were left untouched and unstaged.

---

## 2026-08-29 16:49 Australia/Sydney

### Scope

Renamed the implementation history file from `Work.md` to `WorkLog.md` at the
project owner's request. This is a documentation-organization change only.

### Changes made

- Renamed `Work.md` to `WorkLog.md` without changing or reordering any existing
  historical entry.
- Kept the existing append-only policy, timestamp requirements, record format,
  maintenance rules, and permitted non-semantic correction policy unchanged.
- Updated the active README reference and the current maintenance-policy
  reference in `DesignSuggestionLog.md` to use `WorkLog.md`.
- Preserved historical occurrences of the former filename `Work.md`; they refer
  to this same log before its rename and remain part of the immutable history.
- Added a corresponding rename record to the end of `DesignSuggestionLog.md`.

### Functional and compatibility impact

- S3 source code, configuration, schemas, formulas, thresholds, tests, fixtures,
  CLI behavior, and provider behavior are unchanged.
- Future implementation records must be appended to `WorkLog.md` using the same
  requirements that previously applied to `Work.md`.

### Validation

- Verified that all content from the former `Work.md` is preserved before this
  newly appended entry.
- Verified repository references so current guidance uses the new filename while
  historical log wording remains unchanged.
- No test suite was run because this change only renames and cross-references a
  Markdown documentation file.

---

## 2026-08-29 18:20 Australia/Sydney

### Scope

Implemented the owner-approved "offline pre-Milestone 2 data-readiness and
spatial-split builder", per the `DesignSuggestionLog.md` 2026-08-29 17:16
entry that was marked as an owner-approved implementation requirement. This
is a preparation *gate* for Milestone 2, not any part of Milestone 2 itself:
it never trains a geographic model, never calibrates a fusion weight or risk
threshold, and does not implement S1/S5, environmental suitability, a live
GBIF/ALA client, or an LLM. `EarlyDesign.md` §11.4 and §22 were updated in an
earlier part of this same session to record the approved requirement; this
entry documents the implementation, testing, and validation that followed.

### Modification order

1. Added `schemas/experiment.py` (enums, `AuthorisationDeclaration`,
   `SpatialSplitConfig`, `GeoExperimentConfig`, snapshot-identity models,
   `SplitAssignmentRow`, `ExcludedOccurrenceEntry`, `SpatialSplitManifest`,
   `GeoExperimentReadinessReport`) — the typed contract every other new
   module and test validates against.
2. Added `experiments/spatial_split.py` — pure, file-I/O-free grid/block/
   split logic (`LatitudeLongitudeGridV0` implementing the
   `latitude_longitude_grid_v0.1` formula, `SplitRatios`,
   `OccurrenceForSplit`, deterministic hash-based `assign_records_to_splits`,
   `compute_split_identity`), plus the `SpatialBlockStrategy` `Protocol`
   extension point for future H3/equal-area/state/ecoregion strategies.
3. Added `experiments/readiness.py` — pure status/reason-code derivation
   (authorisation check, S1-input-missing check, taxon-coverage check,
   single-block/empty-split checks) with no file I/O.
4. Added `experiments/prepare.py` — the orchestration module that loads the
   TOML config, loads and cross-checks the Milestone 1.5 bundle via
   `validate_local_snapshot_bundle`, applies `S3Settings`/`clean_occurrences`
   unchanged, calls `spatial_split.py`/`readiness.py`, and performs atomic,
   checksum-verified writes of the two output artifacts. This module was not
   named in the original design-suggestion sketch (which only mentioned
   `readiness.py`/`spatial_split.py`/`schemas/experiment.py`); it was added
   as a thin composition layer so file I/O stays fully separated from the
   pure validation and spatial-split logic, per the engineering requirements
   in the same design-log entry. The deviation is recorded in this module's
   own docstring as well as here.
5. Added the `prepare-geo-experiment` subcommand to `cli.py`, wired to the
   documented exit-code policy (`0`/`1`/`2`).
6. Added `config/geo_experiment.example.toml` and
   `docs/data_cards/geo_experiment_readiness_v0.1.md`.
7. Added `tests/unit/test_spatial_split.py` (grid/hash/split unit tests),
   `tests/unit/test_experiment_readiness.py` (pure readiness-derivation unit
   tests), `tests/unit/test_experiment_schemas.py` (schema validation unit
   tests), and `tests/integration/test_prepare_geo_experiment.py` (12
   end-to-end tests against a real imported Milestone 1.5 bundle, including
   a dedicated AST-based test that no file under `experiments/` imports
   `httpx`/`requests`/`urllib3`/`aiohttp`).
8. Added the 10 new schemas to `scripts/export_json_schemas.py`'s `MODELS`
   list.
9. Ran `pytest`/`ruff`/`pyright`/schema export/a live CLI smoke test, fixed
   every finding (see "Verification performed" below), and re-ran until all
   were clean.

### Methods and design decisions

- **Whole-block, never per-record, split assignment.** Every usable, cleaned
  occurrence is mapped to a `latitude_longitude_grid_v0.1` block id; the
  *block* (not the record) is then assigned to train/validation/test via
  `assign_split_for_unit(hash_unit_interval(seed, block_id), ratios)`. A
  block already assigned is never reassigned, so no block ever spans two
  splits, and the same `(seed, config)` always yields byte-identical output.
- **Pole/antimeridian handling in `latitude_longitude_grid_v0.1`.** Longitude
  is collapsed to `-180.0` exactly at `latitude in (-90.0, 90.0)` (so every
  point at a pole falls in one block regardless of longitude) or at
  `longitude == 180.0` (so the antimeridian doesn't create a spurious extra
  column); latitude index is clamped to the last row
  (`min(latitude_cell_count - 1, floor((latitude+90)/b))`) so `latitude=90.0`
  does not create a size-1 extra row. A near-pole but non-exact latitude
  (e.g. `89.9`) intentionally does *not* get the longitude collapse — this
  was re-derived and confirmed correct, not a bug, while fixing a flawed
  test assumption (see "Verification performed").
- **Protocol extension point uses read-only properties, not attributes.**
  `SpatialBlockStrategy.name`/`.version` are declared as `@property` methods
  rather than plain `str` annotations, specifically so a
  `@dataclass(frozen=True)` implementation (`LatitudeLongitudeGridV0`, whose
  fields are read-only) satisfies the Protocol structurally under pyright.
  A plain-attribute Protocol declaration implies mutability and is
  incompatible with a frozen dataclass's read-only fields.
- **Status precedence is deterministic and gate-like, not a soft warning
  list.** Missing/unauthorised Milestone 1.5 outputs always resolve to
  `not_run_missing_authorised_data` (reason `missing_authorised_s1_outputs`)
  regardless of what else is true about the data; synthetic-fixture data is
  always stamped `engineering_fixture_only` and the report's fixed
  `statement` field ("No model was trained, no fusion weight or risk
  threshold was calibrated, and no biological or biosecurity performance was
  measured by this run.") is always present, so no downstream reader can
  mistake a readiness report for a model-evaluation result.
- **Atomic, checksum-verified writes.** Each output file is written to a
  `tempfile.mkstemp` temp file in the target directory, the temp file is
  read back and its SHA-256 verified against what was intended to be
  written, and only then is it moved into place with `os.replace()` — the
  same pattern already used by the Milestone 1.5 importer, reused unchanged
  in spirit for consistency.

### Resources / frameworks / existing code reused

- `validate_local_snapshot_bundle` (Milestone 1.5, `ingestion/` or
  `providers/` — unchanged) for bundle schema/checksum/identity validation.
- `S3Settings` and `clean_occurrences` (deterministic core — unchanged) for
  cleaning cross-checks; `effective_cleaning_settings` in both output
  artifacts records exactly which settings were applied.
- The Milestone 1.5 atomic-write pattern (`tempfile.mkstemp` → checksum
  verify on readback → `os.replace()`), reused for the two new output files.
- The existing `TypedDict`-for-`**kwargs`-unpacking pattern already used in
  `tests/unit/test_occurrence_snapshot_import.py`, replicated in the new
  integration test file to keep pyright precise about which keyword
  arguments a typed dict literal actually supplies.
- `tests/fixtures/importer/gbif_small.csv` (existing, hand-written,
  synthetic) reused as the integration test's primary input bundle; one new
  hand-written 2-row `generic_dwc` CSV was added inline in the new test file
  for the single-spatial-block test case only.

### Files and components created or modified

- `src/s3_ecological/schemas/experiment.py` (new)
- `src/s3_ecological/experiments/__init__.py`, `spatial_split.py`,
  `readiness.py`, `prepare.py` (new package)
- `src/s3_ecological/cli.py` (added `prepare-geo-experiment` subcommand and
  its exit-code policy; two unrelated line-length reflows found by ruff)
- `config/geo_experiment.example.toml` (new)
- `docs/data_cards/geo_experiment_readiness_v0.1.md` (new)
- `scripts/export_json_schemas.py` (added the 10 new experiment schemas to
  `MODELS`)
- `tests/unit/test_spatial_split.py`, `test_experiment_readiness.py`,
  `test_experiment_schemas.py` (new)
- `tests/integration/test_prepare_geo_experiment.py` (new)
- `DesignSuggestionLog.md`, `EarlyDesign.md` §11.4/§22 (updated earlier in
  this session; not re-modified in this entry's work)
- `README.md` (this entry's own documentation update — see the "Offline
  pre-Milestone 2 data-readiness and spatial-split builder" section)

### How to use it

```bash
python -m s3_ecological.cli prepare-geo-experiment \
  --config config/geo_experiment.example.toml \
  --output-dir data/experiments/<experiment-id>
```

See the README section of the same name and
`docs/data_cards/geo_experiment_readiness_v0.1.md` for the full status/
reason-code vocabulary and configuration reference.

### Verification performed

- `python -m pytest --cov=s3_ecological --cov-report=term-missing` →
  **193 passed, 2 skipped** (the 2 skips are pre-existing, for the optional
  `pydantic_ai` extra, unrelated to this work), **90% overall coverage**;
  `experiments/readiness.py`, `experiments/spatial_split.py`, and
  `schemas/experiment.py` are each at **100%** coverage;
  `experiments/prepare.py` is at **88%** coverage (22 missed lines, all
  defensive/error-path branches such as alternate config-load/snapshot-load
  exception messages, not exercised by the fixture-only test suite). No
  pre-existing test was broken.
- `python -m ruff check .` → **All checks passed!**, after fixing 14
  violations found across this new code (5 auto-fixed by `ruff check . --fix`:
  `.encode("utf-8")` → `.encode()`, `datetime.timezone.utc` →
  `datetime.UTC`; 9 fixed manually by reflowing lines over the 100-character
  limit in `prepare.py`, `spatial_split.py`, `cli.py`, and two test files).
- `python -m pyright` → **0 errors, 0 warnings, 0 informations**, after
  fixing 13 findings: 11 were a single root cause (the `SpatialBlockStrategy`
  Protocol's `name`/`version` declared as plain attributes was incompatible
  with the frozen-dataclass `LatitudeLongitudeGridV0`'s read-only fields;
  fixed once, at the Protocol, by redeclaring them as read-only
  `@property` methods); 2 were in the new integration test file (an
  implicit-Optional default parameter, and a `**kwargs`-unpacked untyped
  dict literal that made pyright check an unrelated `bool` parameter — both
  fixed the same way the existing importer test file already does).
- One test bug was self-caught and fixed before it reached this log: a
  north-pole test originally compared `block_id_for(90.0, 0.0)` against
  `block_id_for(89.9, 0.0)`, which is not a valid comparison because the
  implementation's pole-longitude-collapse applies only at exactly
  `latitude == 90.0`, not at near-pole latitudes — the near-pole point keeps
  its real longitude and lands in a different, non-clamped block. Rewritten
  to assert the pole's exact block id directly
  (`grid.block_id_for(90.0, 5.0) == "grid-v0.1:1.0:179:0"`), isolating the
  latitude-clamp behavior from the separate longitude-collapse rule. This
  was a flaw in the test's assumption, not in the implementation.
- `python scripts/export_json_schemas.py` → succeeded, exported 30 JSON
  Schema files (20 pre-existing + the 10 new experiment models) to
  `json_schemas/` (gitignored; deleted after verification, not part of this
  commit).
- `python -m s3_ecological.cli prepare-geo-experiment --config
  <synthetic-config> --output-dir <scratch-dir>` → live-verified end to end
  using a bundle genuinely produced by the real `import-occurrences` CLI
  subcommand against `tests/fixtures/importer/gbif_small.csv`. Confirmed:
  `Ceratitis` correctly reported in `missing_target_taxa` (its one record is
  excluded during cleaning for missing `coordinate_uncertainty_m`, correctly
  triggering `missing_target_taxon_coverage`); `overall_milestone_2_status`
  and `occurrence_data_status` both `engineering_fixture_only`; the fixed
  `statement` disclaimer present; identical `configuration_digest` in both
  output artifacts; exit code **2** (data-quality reason codes present, no
  fatal error).
- **Determinism check**: ran the same config into two separate scratch
  output directories and diff'd both `spatial-split-manifest.json` and
  `readiness-report.json` byte-for-byte — **identical** in both files,
  confirming determinism at the full CLI/orchestration level, not only at
  the pure-function unit-test level.
- **Overwrite-refusal check**: re-running without `--overwrite` against an
  existing output directory correctly raised `GeoExperimentFatalError` (exit
  code **1**) and wrote nothing; re-running the same config with
  `--overwrite` correctly succeeded (exit code **2**, same residual
  data-quality reason codes as before).
- The scratch directories used for the CLI smoke test
  (`.tmp_cli_smoke/`) and the schema-export output (`json_schemas/`) were
  both deleted after verification and are not part of this commit.

### Extension and integration guidance

- **A new spatial-block strategy** (H3, equal-area, state/ecoregion): add a
  class satisfying `experiments/spatial_split.py::SpatialBlockStrategy`
  (`name`/`version` read-only properties, `block_id_for`,
  `identity_parameters`) and select it in `prepare.py`'s strategy
  construction — `readiness.py`, the CLI, and the output schemas need no
  change.
- **A new readiness reason code**: add the constant and its derivation to
  `experiments/readiness.py`, add it to `cli.py`'s
  `_DATA_QUALITY_REASON_CODES` frozenset if it should map to exit code `2`,
  and add a unit test in `test_experiment_readiness.py`.
- **A future evaluation methodology built on top of this gate** (e.g. an
  actual geographic-model training/evaluation step) should consume
  `spatial-split-manifest.json`'s block-to-split assignment as a read-only
  input and must not weaken the whole-block-never-split-across-splits
  invariant this module guarantees.
- Every new public Pydantic model under `schemas/` should be added to
  `scripts/export_json_schemas.py`'s `MODELS` list, exactly as the 10 new
  experiment models were.

### Maintenance and modification guidance

- Keep `experiments/` outside the deterministic-core import boundary check's
  `DETERMINISTIC_PACKAGES` list, and keep the dedicated
  `test_no_network_client_is_reachable_from_the_experiments_package` AST
  test passing — it is the mechanical guardrail against a future
  contributor adding a live GBIF/ALA/HTTP dependency to this package.
- Do not modify `GeoPriorModel`, the fusion formulas, risk-state precedence,
  Profile v0.1 parameters, or the `AssessmentResult` output contract to
  support this feature — none of that was touched, and none of it should
  need to be for any future extension of this readiness gate.
- Run `pytest`, `ruff check .`, and `pyright` before committing any change to
  `src/s3_ecological/experiments/` or `schemas/experiment.py` — all three are
  at a clean baseline (193 passed/2 skipped/90% coverage, 0 ruff violations,
  0 pyright errors) as of this entry.

### Known limitations and deferred work

- This gate does not implement S1, environmental suitability, or Milestone
  2's geographic model itself; it only prepares and reports on the data a
  future Milestone 2 implementation would need. `not_run_missing_authorised_
  data` is the expected, correct status until S1 exists and produces
  authorised outputs — not a defect in this implementation.
- `latitude_longitude_grid_v0.1` is an equal-angle grid, not equal-area, and
  is not a production ecological-region definition — this is documented in
  both the data card and the strategy's own docstring.
- `experiments/prepare.py` is at 88%, not 100%, branch coverage; the
  uncovered lines are alternate exception-message branches in config/
  snapshot loading and the atomic-write/verify helpers, reasoned through but
  not each given a dedicated unit test in this pass.
- No real GBIF/ALA occurrence or taxonomy dataset was used anywhere in this
  work — every fixture is hand-written and synthetic, and every synthetic
  result is stamped `engineering_fixture_only`. This entry makes no claim
  about real-world ecological or biosecurity accuracy.

### Git record

- Branch: `S3-design-offline-first` (no new branch was created; this is the
  branch that was already checked out at the start of this session).
- Commit message: recorded in the assistant's final report for this session
  (this WorkLog.md entry was written immediately before staging and
  committing, so the hash could not be self-referentially included here).
- Only the S3-Ecological-Agent files listed under "Files and components
  created or modified" above, plus this WorkLog.md entry and the README.md
  update, were staged and committed. The repository root's own untracked
  `.gitignore` (one level above `S3-Ecological-Agent/`) was explicitly left
  untouched and unstaged, per the project owner's standing instruction.
