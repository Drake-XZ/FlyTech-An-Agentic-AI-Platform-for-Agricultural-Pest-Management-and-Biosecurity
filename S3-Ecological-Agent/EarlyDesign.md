# S3 Ecological Agent - Early Design and Build Requirements

**Document status:** Early design specification for implementation agents<br>
**Prepared from:** FlyTech Week 4 materials<br>
**Last updated:** 29 August 2026<br>
**Primary target:** A testable proof-of-concept for fruit-fly identification and biosecurity decision support

## 1. Purpose of This Document

This document is the implementation brief for any agent or developer building the FlyTech S3 Ecological Agent. It converts the Week 4 project material into explicit product, data, model, interface, testing, and safety requirements.

Everything described here is currently a **prototype requirement**, not a production deployment claim. The prototype must be deliberately small and runnable, while its boundaries, schemas, configuration, tests, and documentation must make later replacement, extension, maintenance, and production hardening possible without rewriting the ecological core. A prototype shortcut is acceptable only when it is isolated behind an interface, clearly documented, safe, and covered by a test; shortcuts must not become hidden coupling or permanent business logic.

The builder must treat the following distinction as authoritative:

- **Project requirements** come directly from the FlyTech introduction and S3 early-design presentation.
- **Recommended implementation choices** are practical proposals derived from the Week 4 resource map. They may be changed if an experiment shows a better option, but the reason and evidence must be documented.
- **Research resources** are inputs, baselines, or evaluation references. They are not automatically approved production dependencies and are not one combined S3 training dataset.

## 2. Source Material and Authority

Read these files before changing the design or implementing the agent:

1. [FlyTech introduction](../WEEK%204/FlyTech%20introduction.pdf) - project background, system modules, orchestration model, human-in-the-loop requirement, and deployment goals.
2. [S3 Ecological Agent presentation](../WEEK%204/S3_Ecological_Agent.pdf) - S3 role, reasoning loop, evidence flow, candidate reranking, risk output, and first testable question.
3. [S3 Ecological Agent source deck](../WEEK%204/S3_Ecological_Agent.pptx) - editable source equivalent of the S3 presentation.
4. [S3 resource map](../WEEK%204/FlyTech_S3_Resource_Map.md) - detailed datasets, papers, repositories, limitations, and proposed MVP sequence.
5. [Design Suggestion Log](DesignSuggestionLog.md) - append-only design history, suggestions, approvals, and implementation-increment records.

The PPTX under `WEEK 4/backup/` contains the same slide content as the main deck. Its differences are limited to Office document properties and view metadata, so it is not a separate design source.

If this document conflicts with later written instructions from the project owner or supervisor, the later instruction wins. Record the decision in [DesignSuggestionLog.md](DesignSuggestionLog.md) rather than silently changing behavior.

## 3. Mission

S3 must answer the following question:

> Given visual candidate taxa and an observation context, how ecologically plausible is each candidate, what evidence supports or conflicts with it, and should the case be trusted, questioned, treated as out-of-distribution, or escalated as a possible incursion?

S3 is an ecological reasoning and evidence agent. It is not a replacement for visual identification, taxonomy experts, surveillance programs, or official biosecurity decisions.

The first testable research question is:

> Can ecological distribution priors improve candidate reranking and flag potential incursions without becoming overconfident?

## 4. System Context

FlyTech is an orchestrated, modular platform. The central orchestrator coordinates specialist agents through shared interfaces.

- **S1 Visual Agent:** produces image- and morphology-based candidate taxa and probability or confidence scores; S3 must not assume those scores are calibrated until the interface owner confirms it.
- **S2 Bioacoustic Agent:** contributes audio or wingbeat evidence where available.
- **S3 Ecological Agent:** contributes distribution priors, temporal plausibility, environmental suitability, evidence conflicts, and incursion risk.
- **S4 Resistance Predictor:** contributes DNA and insecticide-resistance evidence.
- **S5 Feedback and Alignment:** records expert confirmation, correction, deferral, and threshold feedback.
- **S6 Robustness and Trust:** evaluates confidence, open-set behavior, adversarial robustness, and baseline comparisons.
- **Orchestrator:** decides which agents or tools to call, fuses specialist evidence, and routes uncertain cases to the application or an expert.

S3 must therefore be callable as a specialist service or tool. It must not assume that it owns the final system decision.

### 4.1 Ownership boundary

The owner of this work is responsible for **S3 only**. References to other FlyTech agents describe integration context, not additional implementation scope.

- S3 must define and document the inputs it expects from S1, S2, S4, the orchestrator, or another approved producer.
- S3 must define and document the outputs that S5, S6, the orchestrator, an application, or an expert-review workflow may consume.
- S3 may provide JSON examples, schemas, mocks, fixtures, test doubles, and adapter interfaces for those boundaries.
- S3 must not implement, train, repair, deploy, or take ownership of S1, S2, S4, S5, S6, the central orchestrator, the user application, or an expert-review system.
- Integration tests must use mocks or contract fixtures unless the owner of another module supplies a compatible implementation.
- A missing external agent must not block standalone S3 development. The S3 core must run through a CLI, library call, or S3-owned API using fixture inputs.
- Any change required in another module must be recorded as an external dependency or interface request and handed to that module's owner.

The S3 repository may contain compatibility schemas for external modules, but it must not contain their business logic.

## 5. Required Design Principles

The implementation must follow all of these principles:

1. **Ecological evidence is a soft prior, never a hard taxon filter.** Lack of a record is not evidence of absence.
2. **Presence-only data must be represented honestly.** GBIF, ALA, and iNaturalist records are affected by observer effort, sampling programs, roads, cities, institutions, and reporting practices.
3. **Evidence must be traceable.** Every material claim must identify its source, query, retrieval time, quality flags, and model version.
4. **Uncertainty must be explicit.** S3 must be able to say that evidence is missing, conflicting, stale, spatially imprecise, or outside model support.
5. **Potential incursion is a review state, not a confirmed diagnosis.** Official confirmation remains a human and regulatory responsibility.
6. **Agent behavior must be reproducible.** Remote data should be cached or snapshot-tested, models and thresholds versioned, and deterministic fixtures available.
7. **The architecture must remain modular.** Taxonomy, occurrence, geographic-prior, suitability, fusion, and explanation components need replaceable interfaces.
8. **Privacy and sovereignty matter.** Do not expose precise sensitive locations or user data beyond what is required by the approved deployment.
9. **Ask for more evidence when needed.** Missing coordinates, observation time, image quality, host, trap, or environmental context should generate a request, not fabricated certainty.
10. **Human feedback must be preserved.** Expert corrections and deferrals must be recordable for later calibration through S5.

## 6. Scope

### 6.1 MVP scope

The first implementation should support fruit flies and begin at genus level with the four TF4 genera:

- `Anastrepha`
- `Bactrocera`
- `Ceratitis`
- `Rhagoletis`

The MVP must:

- receive S1 top-k candidates and observation context;
- resolve submitted taxon names to stable identifiers and known synonyms;
- retrieve and clean occurrence evidence from GBIF and/or ALA;
- estimate a geographic and optional temporal support score;
- rerank candidates with a transparent soft-fusion method; calibration is required only when an authorised labelled validation set is available;
- return evidence, uncertainty, missing-data flags, and a review-oriented risk state;
- run end to end without any live API, credential, or network access by using local snapshots, synthetic fixtures, and test doubles;
- support spatial holdout evaluation;
- expose enough logging to reproduce every result.

### 6.2 Post-MVP scope

After the geographic-prior MVP is validated, add:

- environmental suitability using EcoCommons layers and MaxEnt-style species distribution modelling;
- seasonal or month-aware priors;
- open-set and geographic OOD evaluation based on Open-Insect protocols;
- schema-only multimodal evidence hooks for externally owned S2 and S4 implementations;
- richer evidence retrieval and explanation;
- threshold calibration from imported, authorised expert-feedback records;
- optional S3 service/API deployment and contract-level orchestrator integration.

### 6.3 Non-goals for the first build

Do not make the first implementation responsible for:

- training or replacing the S1 image classifier;
- building or modifying S1, S2, S4, S5, S6, the central orchestrator, the application, or the expert-review platform;
- implementing cross-agent fusion that belongs to the orchestrator;
- collecting expert feedback through an S5 user interface or workflow; S3 only exports and imports the agreed record schema;
- waiting for another agent to exist before providing a standalone S3 demo with fixtures;
- declaring a species absent because no public record was returned;
- making an official quarantine, eradication, or pesticide decision;
- downloading BIOSCAN-5M or another multi-million-item image collection before a small metadata experiment justifies it;
- scraping iNaturalist at high volume through its interactive API;
- automatically incorporating unreviewed expert feedback into production weights;
- using a general-purpose LLM as the numeric ecological model;
- treating suitability, occurrence support, or visual similarity as a true incursion probability without labelled calibration data.

### 6.4 Offline-first implementation and deferred APIs

Live external APIs are **not required for the current prototype**. The project owner may provide API details, credentials, approved endpoints, quotas, or datasets later. The builder must continue now by implementing the S3 code and must not block on GBIF, ALA, EcoCommons, iNaturalist, or another remote service.

Current implementation requirements:

- define the complete provider interfaces and configuration schemas now;
- implement an in-memory provider and a local-file/snapshot provider for development and tests;
- create small synthetic or legally reusable fixtures that exercise normal, empty, malformed, duplicate, low-quality, timeout-equivalent, and provider-unavailable cases;
- make fixture or local-snapshot mode the default development and demonstration mode;
- place provider selection behind dependency injection or a factory so a live adapter can be added later without changing taxonomy, cleaning, fusion, risk, evidence, or API layers;
- allow live-provider configuration fields to remain unset and return a clear `provider_not_configured` status rather than failing startup;
- do not request, invent, hard-code, commit, or log API keys, tokens, account details, or private endpoints;
- document the expected authentication fields and endpoint settings using empty examples only;
- retain representative raw-response fixture shapes and provenance fields so later live responses can be mapped into the existing domain schema;
- mark unimplemented network adapters explicitly as deferred integration work, not as completed providers;
- ensure every automated test and the main prototype demo succeed with networking disabled.

When API access is provided later, the integration task should be limited to implementing and validating the relevant adapter, mapping remote responses to the existing domain model, adding optional live tests, and recording rate-limit, licence, caching, retry, and credential-handling behavior.

### 6.5 Prototype Implementation Profile v0.1

This profile is the normative, directly implementable default for Milestones 0 and 1. It removes choices that would otherwise cause two builder agents to produce incompatible prototypes. It does **not** claim that the numeric defaults are scientifically calibrated. Future profiles must be added through a new dated change-log entry and decision record; do not silently change v0.1 behavior.

#### Runtime and delivery defaults

- use Python 3.11 for the first implementation;
- use a `pyproject.toml` package with a `src/` layout;
- prefer `uv` for environment and lock-file management, but document an ordinary `pip` fallback;
- use Pydantic v2 models as the source for exported JSON Schemas;
- keep PydanticAI in an optional `agent` dependency group;
- keep FastAPI in an optional `api` dependency group;
- use `pytest`, `ruff`, and `pyright` in a development dependency group;
- expose one deterministic library entry point and one fixture-backed CLI command before adding an HTTP API;
- set `S3_LLM_ENABLED=false`, fixture/local providers, and network-disabled behavior as the default profile.

The console entry point must be named `s3-ecological` and support at least:

```text
uv run s3-ecological demo --fixture supported_same_location
uv run s3-ecological assess --input request.json --output -
uv run pytest
uv run ruff check .
uv run pyright
```

#### S1 top-k probability semantics

- preserve every supplied `visual_probability` exactly as `visual_probability_raw`;
- do not renormalize a truncated top-k candidate list and do not imply that it contains all probability mass;
- accept `candidate_set_complete: bool` and optional `omitted_probability_mass` at request level;
- require `omitted_probability_mass` to be in `[0, 1]` when supplied;
- when `candidate_set_complete=true`, require the candidate probabilities to sum to 1 within a configurable floating-point tolerance;
- when `candidate_set_complete=false`, allow the sum to be less than or equal to 1 and report whether omitted mass is known;
- reject duplicate candidate identifiers after deterministic taxonomy resolution;
- a normalized `rerank_score` may sum to 1 across the submitted candidates, but it must be labelled as a **within-candidate-set ranking score**, not a full posterior probability.

#### Deterministic geographic baseline

The v0.1 engineering baseline is nearest-clean-occurrence distance. It exists to prove the contracts and decision path before a learned geographic prior is available.

1. Clean occurrence records using Section 11.
   A record is usable for the v0.1 distance score only when taxonomy is resolved, coordinates are valid, known coordinate uncertainty is less than or equal to `max_coordinate_uncertainty_m`, and no configured centroid, captive/cultivated, duplicate, or geocoding-artifact exclusion applies. Retain excluded and unknown-uncertainty records as traceable evidence with flags, but do not use them in the distance calculation.
2. Calculate great-circle distance with the haversine formula and Earth mean radius `6371.0088 km`.
3. For each candidate, let `d_min_km` be the distance to the nearest usable record.
4. Calculate:

```text
geo_support = exp(-d_min_km / geo_distance_scale_km)
```

5. If no usable records exist, return `geo_support=null`, `evidence_quality=insufficient`, and a `no_records` warning. Do not return zero and do not infer absence.
6. With one or two usable records, return the score with `evidence_quality=low`, but do not classify the case as geographic OOD or potential incursion.
7. With at least three usable records, use `evidence_quality=medium` and the prototype may apply the configured geographic state thresholds below. Reserve `high` for a later, validated evidence-quality policy.

The frozen fixture-profile defaults are:

```yaml
profile_version: "0.1"
configuration_version: "prototype-v0.1"
geo_distance_scale_km: 500.0
max_coordinate_uncertainty_m: 50000
min_occurrences_for_ood: 3
geo_supported_min: 0.5
geo_ood_max: 0.1
probability_sum_tolerance: 0.000001
fusion_epsilon: 0.000001
fusion_weight_geo: 1.0
fusion_weight_environment: 0.0
incursion_rule_enabled: false
```

These values are engineering defaults for reproducible fixtures, not ecological or regulatory thresholds. Production-like experiments must select and version replacements using authorised validation data.

#### v0.1 fusion semantics

- calculate `combined_log_score` from `visual_probability_raw` and every available enabled ecological component;
- omit an unavailable component and emit a warning instead of substituting zero, one, or fabricated evidence;
- calculate `rerank_score` by applying softmax to `combined_log_score` across the submitted candidate set;
- preserve `visual_probability_raw`, `geo_support`, every other component score, `combined_log_score`, and `rerank_score` in the response;
- break an exact score tie by the original S1 candidate order, then by stable resolved taxon identifier;
- set `temporal_support=null` and `environmental_suitability=null` in v0.1 unless a separately tested component is explicitly enabled;
- do not enable `potential_incursion` in the default profile. Until a validated rule is approved, an out-of-range case must remain `geographic_ood` with `review_required=true`.

## 7. Observe-Reason-Act-Learn Loop

S3 should implement the decision loop described in the Week 4 design.

### 7.1 Observe

Receive and validate:

- observation identifier;
- S1 top-k candidates and probabilities;
- latitude and longitude;
- coordinate uncertainty, if known;
- observation date and local timezone, if known;
- optional season, host plant, trap type, land cover, climate, elevation, habitat, and source metadata;
- optional, schema-valid evidence produced by other specialist agents; S3 treats it as external input and does not implement those producers.

If essential information is missing or invalid, continue only with the evidence that is available and return explicit missing-evidence flags.

### 7.2 Reason

Create a short internal plan based on available evidence:

1. validate and normalize the observation structure, preserve supplied candidate probabilities, and derive only the separately labelled reranking normalization defined in Profile v0.1;
2. resolve names and synonyms;
3. choose relevant occurrence sources and geographic bounds;
4. load ecological records from the configured fixture, local snapshot, cache, or later live provider through the same interface;
5. evaluate record quality and spatial support;
6. optionally estimate environmental suitability;
7. compare visual and ecological evidence;
8. calculate uncertainty and risk state;
9. decide whether more evidence or expert review is required.

Numeric scoring must be done by deterministic code or a versioned statistical model. An LLM may plan tool calls and summarize evidence, but it must not invent records, coordinates, taxa, scores, citations, or thresholds.

### 7.3 Act

Call only the tools required for the current case. Candidate tool functions are:

```text
resolve_taxonomy(name, rank=None)
query_occurrences(taxon_id, region, time_range=None, quality_filters=None)
estimate_geo_prior(candidate_taxa, latitude, longitude, observed_at=None)
estimate_environmental_suitability(candidate_taxa, latitude, longitude, covariates=None)
explain_distribution_evidence(candidate_taxon, observation_context)
flag_out_of_range_or_unknown(candidate_scores, evidence_quality, thresholds)
```

Tool calls require timeouts, bounded retries, caching, and structured errors. A failed external service must degrade to an evidence-unavailable result instead of crashing the full workflow.

For the current prototype, these tool functions are contracts and callable interfaces. They must have fixture-backed or local implementations. Network-backed implementations may remain unconfigured or explicitly deferred until the project owner provides the required API access.

Every tool must return a typed `ToolResult[T]` equivalent to:

```python
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    status: ToolStatus
    data: T | None
    warnings: list[Issue] = Field(default_factory=list)
    errors: list[Issue] = Field(default_factory=list)
    provenance: list[EvidenceReference] = Field(default_factory=list)
```

Required tool statuses are:

| Tool status | Meaning | Retryable by default |
|---|---|---:|
| `success` | Valid result returned | No |
| `no_records` | Query succeeded but returned no usable occurrence records; this is not evidence of absence | No |
| `partial` | Some valid data returned with explicit limitations | No |
| `provider_not_configured` | A real provider was requested without required configuration | No |
| `timeout` | Provider exceeded the configured deadline | Yes |
| `rate_limited` | Provider rejected the request because of rate limits | Yes |
| `unavailable` | Provider or local dependency was unavailable | Yes |
| `invalid_response` | Provider response could not be validated or mapped safely | No |

Initial typed tool contracts:

| Tool | Input model | Output data model |
|---|---|---|
| `resolve_taxonomy` | `TaxonomyQuery` | `TaxonomyResolution` |
| `query_occurrences` | `OccurrenceQuery` | `list[OccurrenceRecord]` |
| `estimate_geo_prior` | `GeoPriorRequest` | `list[CandidateGeoSupport]` |
| `estimate_environmental_suitability` | `SuitabilityRequest` | `list[CandidateSuitability]` |
| `explain_distribution_evidence` | `ExplanationRequest` | `EvidenceExplanation` derived only from validated evidence |
| `flag_out_of_range_or_unknown` | `RiskPolicyRequest` | `RiskPolicyResult` |

Each public model must be documented and exported as JSON Schema. Fixture adapters must implement exactly the same contract as future live adapters.

### 7.4 Learn

Record, but do not blindly apply:

- expert-confirmed taxon;
- expert correction;
- request for additional evidence;
- deferred or unresolved case;
- confirmed false alert or missed alert;
- threshold and model version used for the original decision.

Any later learning or recalibration pipeline must use versioned datasets and approval gates.

S3's responsibility ends at emitting an exportable feedback request/result record and accepting authorised feedback records in an agreed schema. Building S5, collecting feedback from users, and managing the expert workflow remain outside S3 scope.

## 8. Input Contract

Use a framework-neutral schema. Pydantic models and JSON Schema are recommended for a Python implementation.

```json
{
  "schema_version": "1.0.0",
  "observation_id": "obs-123",
  "source": "flytech-app",
  "candidate_set_complete": false,
  "omitted_probability_mass": 0.18,
  "observed_at": "2026-08-26T10:30:00+10:00",
  "location": {
    "latitude": -35.2809,
    "longitude": 149.1300,
    "coordinate_uncertainty_m": 100
  },
  "visual_candidates": [
    {
      "candidate_id": "s1-candidate-1",
      "name": "Bactrocera",
      "rank": "genus",
      "visual_probability": 0.82,
      "model_version": "s1-example"
    }
  ],
  "context": {
    "host": null,
    "trap_type": null,
    "habitat": null,
    "environmental_covariates": null
  },
  "other_agent_evidence": []
}
```

Validation requirements:

- `schema_version`, `observation_id`, `candidate_set_complete`, and at least one visual candidate are required for an assessment attempt;
- latitude must be in `[-90, 90]` and longitude in `[-180, 180]`;
- probabilities must be finite and in `[0, 1]`;
- apply the candidate-set and omitted-mass rules in Prototype Implementation Profile v0.1;
- candidate IDs must be unique within a request and must be preserved in every output candidate;
- preserve the raw candidate name as well as the resolved name;
- do not silently infer an exact date, location, host, or coordinate precision;
- distinguish missing time from an explicitly date-free request;
- reject impossible dates and malformed identifiers with structured errors;
- allow partial analysis when non-essential fields are missing.

Every `other_agent_evidence` item must use a versioned, framework-neutral `ExternalAgentEvidence` contract containing at least `evidence_id`, `schema_version`, `producer_agent`, `evidence_type`, `status`, optional `candidate_id`, typed `value` and `unit` fields where applicable, `provenance_refs`, and `generated_at`. Standalone S3 validates and preserves these items as integration context but does not implement their producer, reinterpret unknown payloads, or perform final cross-agent fusion.

## 9. Output Contract

S3 must return structured evidence and risk, not only a label.

```json
{
  "schema_version": "1.0.0",
  "observation_id": "obs-123",
  "analysis_id": "s3-run-uuid",
  "status": "completed",
  "reranked_candidates": [
    {
      "submitted_name": "Bactrocera",
      "candidate_id": "s1-candidate-1",
      "resolved_taxon": {
        "scientific_name": "Bactrocera",
        "rank": "genus",
        "taxon_ids": {"gbif": "...", "ala": "..."}
      },
      "visual_probability_raw": 0.82,
      "geo_support": 0.61,
      "min_occurrence_distance_km": 247.2,
      "usable_occurrence_count": 12,
      "temporal_support": null,
      "environmental_suitability": null,
      "combined_log_score": -0.693,
      "rerank_score": 1.0,
      "ecological_state": "ecologically_supported",
      "evidence_quality": "medium",
      "conflicts": [],
      "supporting_evidence_ids": ["evidence-1"]
    }
  ],
  "risk_state": "ecologically_supported",
  "review_required": false,
  "review_reasons": [],
  "uncertainty": {
    "level": "medium",
    "reasons": ["environmental covariates unavailable"]
  },
  "missing_evidence": ["host", "environmental_covariates"],
  "requested_evidence": [],
  "evidence": [
    {
      "evidence_id": "evidence-1",
      "source": "fixture",
      "source_record_id": "fixture-occurrence-1",
      "dataset_id": "fixture-occurrences-v0.1",
      "source_url": "fixture://occurrences/fixture-occurrence-1",
      "retrieved_at": "2026-08-26T00:00:00Z",
      "scientific_name_raw": "Bactrocera",
      "taxon_id": "fixture:bactrocera",
      "latitude": -35.1,
      "longitude": 146.4,
      "coordinate_uncertainty_m": 100,
      "event_date": "2026-08-01",
      "basis_of_record": "synthetic_fixture",
      "license": "CC0-1.0",
      "media_license": null,
      "quality_flags": [],
      "cleaning_actions": [],
      "query_parameters": {"taxon_id": "fixture:bactrocera"},
      "snapshot_or_cache_key": "fixture-occurrences-v0.1"
    }
  ],
  "warnings": [],
  "errors": [],
  "profile_version": "0.1",
  "configuration_version": "prototype-v0.1",
  "model_versions": {"geo": "nearest-distance-v0.1"},
  "threshold_versions": {"risk": "fixture-thresholds-v0.1"},
  "data_snapshot_versions": {"occurrence": "fixture-occurrences-v0.1"},
  "explanation": "The submitted candidate is supported by nearby fixture occurrence evidence; environmental suitability was not evaluated.",
  "generated_at": "2026-08-26T00:00:00Z"
}
```

Top-level `status` is separate from ecological risk and must be one of:

| Status | Meaning |
|---|---|
| `completed` | All enabled components completed without a warning; components intentionally disabled by the selected profile do not create a warning unless the request explicitly required them |
| `completed_with_warnings` | A valid partial or complete assessment exists, but one or more components were missing, disabled, degraded, or inconclusive |
| `failed_validation` | The request could not be assessed because required structure or values were invalid |
| `failed` | No safe assessment could be returned because of an internal processing failure; return a redacted typed error and log the trace outside the public response |

Warnings and errors must use the shared shape `{code, message, component, retryable, details?}`. Do not expose credentials, raw stack traces, or sensitive configuration in `details`.

Minimum `IssueCode` values are `invalid_input`, `unsupported_schema_version`, `unsupported_profile`, `duplicate_candidate`, `ambiguous_taxonomy`, `no_records`, `component_unavailable`, `provider_not_configured`, `timeout`, `rate_limited`, `unavailable`, `invalid_response`, and `score_not_computable`. Extensions must be documented and backward-compatible within the same schema major version.

Required risk states:

| State | Meaning | Expected action |
|---|---|---|
| `ecologically_supported` | Visual candidate is supported by usable ecological evidence | Keep candidate; report evidence and uncertainty |
| `weak_ecological_support` | Evidence is sparse, old, imprecise, or only mildly supportive | Keep candidate; lower confidence; consider more evidence |
| `geographic_ood` | Observation is outside well-supported sampled range | Do not reject candidate; flag distribution conflict |
| `environmental_conflict` | Available covariates are inconsistent with the fitted suitability model | Do not reject candidate; report model scope and uncertainty |
| `potential_incursion` | Candidate is visually plausible and outside known range but location appears suitable, or another validated rule is triggered | Require expert or biosecurity review |
| `unknown_or_insufficient_evidence` | Candidate set or evidence cannot support a reliable conclusion | Request more evidence or defer |
| `conflicting_multimodal_evidence` | Reserved integration state supplied or derived by the external orchestrator when specialist agents materially disagree | S3 may preserve the flag in an integration response but must not compute cross-agent fusion |

`potential_incursion` must never be presented as `confirmed_incursion`.

#### Risk-state ownership and deterministic precedence

- `ecological_state` is calculated per candidate; top-level `risk_state` describes the case using the highest-ranked candidate after reranking;
- candidate `ecological_state` is limited to `ecologically_supported`, `weak_ecological_support`, `geographic_ood`, `environmental_conflict`, or `unknown_or_insufficient_evidence`; case-level `risk_state` may additionally use a validated `potential_incursion` or externally supplied `conflicting_multimodal_evidence` state;
- retain every candidate's state so the orchestrator can inspect alternatives;
- standalone S3 must never generate `conflicting_multimodal_evidence`; cross-agent conflict detection and final fusion belong to the orchestrator;
- an externally supplied conflict flag may be validated and echoed as integration context, but it must not change S3 component scores;
- `failed_validation` is a processing status, not a risk state.

For v0.1, apply the following first-match precedence:

1. `unknown_or_insufficient_evidence` when no valid candidate can be assessed, location is unavailable for every enabled ecological check, or the top-ranked candidate has no usable ecological evidence;
2. `potential_incursion` only when `incursion_rule_enabled=true` and a separately documented, versioned, validated rule fires;
3. `environmental_conflict` when an enabled suitability component reports a versioned conflict for the top candidate and no potential-incursion rule fired;
4. `geographic_ood` when the top candidate has at least `min_occurrences_for_ood` usable records and `geo_support <= geo_ood_max`;
5. `weak_ecological_support` when evidence quality is low or `geo_ood_max < geo_support < geo_supported_min`;
6. `ecologically_supported` when `geo_support >= geo_supported_min` and no higher-precedence condition fired.

`review_required` must be true for `potential_incursion`, `environmental_conflict`, `geographic_ood`, `unknown_or_insufficient_evidence`, ambiguous taxonomy, and any externally supplied multimodal-conflict flag. Threshold equality must follow the operators shown above and be covered by boundary tests.

## 10. Evidence and Provenance Model

Each occurrence or derived evidence item should retain at least:

| Field | Requirement |
|---|---|
| `evidence_id` | Stable identifier within the S3 run |
| `source` | GBIF, ALA, EcoCommons, model, expert, or other named source |
| `source_record_id` | `occurrenceID`, record ID, or equivalent |
| `dataset_id` | `datasetKey` or equivalent dataset identifier |
| `source_url` | Human-auditable record, query, or dataset link |
| `retrieved_at` | UTC retrieval timestamp |
| `scientific_name_raw` | Name supplied by source |
| `taxon_id` | Stable source taxonomy identifier |
| `latitude`, `longitude` | Coordinates used in analysis |
| `coordinate_uncertainty_m` | Preserve missing values; do not assume zero |
| `event_date` | Observation or collection time if known |
| `basis_of_record` | Observation, specimen, trap, eDNA, or other type |
| `license` | Record/data licence |
| `media_license` | Separate media licence if an image is used |
| `quality_flags` | Coordinate, date, taxonomy, duplicate, centroid, captive/cultivated, and other flags |
| `cleaning_actions` | What was changed or excluded and why |
| `query_parameters` | Reproducible source query |
| `snapshot_or_cache_key` | Exact cached response or dataset snapshot |

Never discard raw identifiers when producing a cleaned table.

## 11. Data Acquisition and Cleaning Pipeline

### 11.1 Taxonomy resolution

1. Preserve the submitted name.
2. Resolve it against source taxonomies.
3. store accepted name, rank, synonym relationship, and source-specific ID;
4. flag ambiguous or higher-rank matches;
5. do not silently merge taxa when the match is uncertain.

### 11.2 Occurrence retrieval

For the current prototype, start with a small genus-level local snapshot or synthetic fixture. Save the intended query parameters, source name, fixture version, and representative raw response before transforming it. The same provider interface must later support bounded live queries. After API access is supplied, prefer batch downloads for large GBIF or iNaturalist-derived datasets and normal API calls only for bounded interactive lookups.

### 11.3 Minimum cleaning checks

- remove exact duplicate source records while preserving a duplicate map;
- detect duplicated coordinates and records aggregated through more than one platform;
- reject impossible coordinates and dates;
- flag zero coordinates, country/state centroids, institutions, and obvious geocoding artefacts;
- filter or weight records by coordinate uncertainty appropriate to the spatial resolution;
- retain `basisOfRecord` and dataset provenance;
- inspect captive/cultivated or non-wild flags where available;
- normalize time to a consistent representation without inventing missing day/month values;
- record every exclusion reason;
- review sample density and spatial bias before modelling.

### 11.4 Data splits

Random row splits are insufficient. At minimum, implement spatial blocks, geographic regions, or state/ecoregion holdouts. Where enough time coverage exists, add temporal holdout. Prevent leakage from the same occurrence, photographer, locality, source dataset, or near-duplicate image across splits.

**Offline pre-Milestone 2 readiness gate (normative, approved 29 August 2026; see `DesignSuggestionLog.md`).** Before any Milestone 2 geographic-prior experiment is trained, run the offline `prepare-geo-experiment` command:

```
python -m s3_ecological.cli prepare-geo-experiment \
  --config config/geo_experiment.example.toml \
  --output-dir data/experiments/<experiment-id>
```

This command is a data-readiness and spatial-split builder, not a modelling step. It reuses the existing Milestone 1.5 `occurrences.json`/`taxonomy.json`/`import-report.json` bundle, `validate_local_snapshot_bundle`, `S3Settings`, and `clean_occurrences` as the sole cleaning authority; validates the explicit data-authorisation declaration, schema, checksums, snapshot identity, and taxonomy IDs; resolves coverage of the four TF4 genera (`Anastrepha`, `Bactrocera`, `Ceratitis`, `Rhagoletis`); assigns whole spatial blocks (never individual records) to deterministic train/validation/test splits using the `latitude_longitude_grid_v0.1` profile:

```
longitude_for_index = -180 if longitude == 180 or latitude in (-90, 90) else longitude
latitude_cell_count  = ceil(180 / b)
latitude_index       = min(latitude_cell_count - 1, floor((latitude + 90) / b))
longitude_index      = floor((longitude_for_index + 180) / b)
block_id             = "grid-v0.1:<b>:<latitude_index>:<longitude_index>"
```

with `b` finite and in `(0, 10]`, and each block deterministically assigned to a split by hashing `"<seed>:<block_id>"` (SHA-256, first 8 bytes as an unsigned 64-bit integer divided by 2^64) against configured `train_ratio`/`validation_ratio`/`test_ratio` (defaults 0.60/0.20/0.20, `seed=42`, uncalibrated reproducibility defaults). It writes `spatial-split-manifest.json` and `readiness-report.json` with the status vocabulary `ready_for_geo_prior_engineering`, `not_run_missing_authorised_data`, `not_ready_data_quality`, `engineering_fixture_only`, and `ready_for_approved_milestone_2_experiment`. When Milestone 1's S1 identification outputs are absent, `overall_milestone_2_status` must be `not_run_missing_authorised_data` with reason code `missing_authorised_s1_outputs`, regardless of occurrence-data readiness. This tool must not train a geographic model, calibrate fusion weights or risk thresholds, or implement S1, S5, an environmental suitability model, live GBIF/ALA access, or an LLM, and synthetic engineering fixtures must be reported as `engineering_fixture_only`, never as a real ecological or biosecurity accuracy result.

## 12. Modelling Requirements

### 12.1 Baseline A: occurrence-distance heuristic

Implement the nearest-clean-occurrence method frozen in Prototype Implementation Profile v0.1 before a neural geographic prior. Kernel density or region-level frequency with smoothing may be added later only as separately named, versioned adapters. The v0.1 method exists to validate interfaces and evaluation, not to claim ecological truth.

### 12.2 Baseline B: presence-only geographic prior

Use the Mac Aodha et al. method and `geo_prior` repository as the reference design. Replace its original species data with a small, cleaned GBIF/ALA fruit-fly occurrence table. The model should map location and optional time to candidate support.

Do not copy an old environment blindly. Reproduce the demo first, document dependency issues, and isolate legacy code behind an adapter if necessary.

### 12.3 Baseline C: environmental suitability

After the geographic baseline works, use MaxEnt-style species distribution modelling. Candidate tools are `elapid` in Python or `biomod2` in R. Inputs should include quality-controlled occurrence points, a justified background region, background or pseudoabsence samples, and documented environmental covariates.

Potential covariates include temperature, rainfall, elevation, land cover, habitat, and host availability. Variable selection must be justified; correlated variables, spatial resolution, temporal mismatch, extrapolation, and sampling bias must be examined.

Suitability is not occurrence probability and is not incursion probability.

### 12.4 Soft fusion

Start with an interpretable log-linear fusion:

```text
combined_log_score(s) = log(visual_probability_raw(s) + eps)
                      + w_geo * log(p_geo(s | location, time) + eps)
                      + w_env * log(p_env(s | environment) + eps)

rerank_score(candidate_set) = softmax(combined_log_score(candidate_set))
```

Requirements:

- learn or select `w_geo` and `w_env` only on validation data;
- define `eps` and all transformations in configuration;
- handle unavailable ecological components explicitly instead of substituting false certainty;
- normalize scores for candidate reranking where appropriate;
- preserve component scores in the output;
- preserve the unnormalised `combined_log_score` and the within-candidate-set `rerank_score` as different fields;
- compare fused performance against S1-only, geographic-only, and environment-only ablations;
- calibrate final risk decisions when authorised labelled validation data are available; never interpret either score as an incursion probability.

## 13. Datasets and Data Platforms

The following resources may be used. The builder must read each licence and terms before downloading or redistributing data.

### 13.1 P0 - target sources for the first prototype; live access may be deferred

| Resource | Role | How to use it | Do not use it as |
|---|---|---|---|
| [GBIF occurrence data](https://www.gbif.org/) and [Occurrence API](https://techdocs.gbif.org/en/openapi/v1/occurrence) | Global occurrence, taxonomy, date, coordinates, dataset provenance | Query target genera; retain IDs and quality fields; build a cleaned snapshot; use for geographic support and spatial evaluation | A reliable absence database or uniform survey |
| [Atlas of Living Australia](https://www.ala.org.au/) | Australia-focused occurrence and taxonomy evidence | Use as the regional priority source; filter by location and quality; compare with GBIF while preserving source provenance | An automatically authoritative identification |
| TF4 from [Shen et al.](https://pubmed.ncbi.nlm.nih.gov/38061169/) | Fruit-fly/open-set task definition covering four genera | Reproduce class and open-set definitions; recover location/date only from licensed original records or author-provided data; start genus-level S3 experiments | A dataset that can be redistributed without confirming access and media licences |

### 13.2 P1 - required for the second experiment or evaluation

| Resource | Role | How to use it | Do not use it as |
|---|---|---|---|
| [EcoCommons](https://www.ecocommons.org.au/) | Australian environmental layers and reproducible species-distribution workflows | Select documented covariates and produce location-level suitability; retain layer versions, resolution, CRS, and scenario | Direct proof that a species is present |
| [iNaturalist research-grade data via GBIF](https://www.gbif.org/dataset/50c9509d-22c7-4a22-a47d-8c48425ef4a7) and [iNaturalist Open Data](https://github.com/inaturalist/inaturalist-open-data) | Linked images, taxonomy, place, and time | Build licensed image-location examples; keep observation URL, observer/source, quality grade, data licence, and media licence; prefer bulk exports | A source to scrape at high volume or a substitute for quarantine identification |
| [Open-Insect](https://github.com/RolnickLab/Open-Insect) | Open-set, geographic OOD, and novel-species evaluation | Reuse its benchmark concepts and evaluation code; validate methods on a resized subset; migrate protocols to fruit flies | Direct fruit-fly training data |

### 13.3 P2 - optional future extensions

| Resource | Role | How to use it | Constraint |
|---|---|---|---|
| [BIOSCAN-1M](https://github.com/bioscan-ml/BIOSCAN-1M) / [BIOSCAN-5M](https://github.com/bioscan-ml/BIOSCAN-5M) | Image, DNA barcode/BIN, taxonomy, and geography schema | Begin with metadata and a Tephritidae-relevant subset; use for multimodal schema and cross-checking | High storage and compute cost; licences may differ by modality |
| [IP102](https://github.com/xpwu95/IP102) | S1 visual baseline and long-tail pest examples | Use its model output to exercise the S1-to-S3 candidate interface | Mainly an S1 resource; academic-use restrictions apply |

## 14. Code Repositories and Their Intended Use

| Repository | Priority | Intended use in S3 | Integration requirement |
|---|---:|---|---|
| [macaodha/geo_prior](https://github.com/macaodha/geo_prior) | P0 | Reproduce the location-to-class prior demo and use it as the first learned reranking baseline | Wrap legacy code behind a stable adapter; record commit and environment |
| [AtlasOfLivingAustralia/galah-python](https://github.com/AtlasOfLivingAustralia/galah-python) | P0 | Query ALA taxonomy and occurrence records into pandas tables | Cache responses; request only needed columns; record filters and source URLs |
| [earth-chris/elapid](https://github.com/earth-chris/elapid) | P1 | Python MaxEnt-style SDM, raster annotation, background sampling, and spatial CV | Keep modelling configuration explicit; validate Windows compatibility or use an approved isolated environment |
| [RolnickLab/Open-Insect](https://github.com/RolnickLab/Open-Insect) | P1 | Reuse open-set and geographic OOD evaluation logic | Start with metadata/resized data; port evaluation rather than insect-specific weights |
| [biomodhub/biomod2](https://github.com/biomodhub/biomod2) | P2 | R-based multi-model and ensemble SDM comparison | Define a versioned file/API boundary between R outputs and S3 |
| [inaturalist/inaturalist-open-data](https://github.com/inaturalist/inaturalist-open-data) | P1 | Bulk metadata and image-location-taxonomy schema | Separate record and media licences; avoid high-volume interactive API calls |
| [bioscan-ml/BIOSCAN-1M](https://github.com/bioscan-ml/BIOSCAN-1M) / [BIOSCAN-5M](https://github.com/bioscan-ml/BIOSCAN-5M) | P2 | Metadata processing and future multimodal schema | Subset first; do not make the full corpus an MVP dependency |
| [xpwu95/IP102](https://github.com/xpwu95/IP102) | P2 | S1 candidate generator and interface test data | Keep visual class frequency separate from ecological support |

Before adopting any repository, record:

- upstream URL and exact commit;
- licence and redistribution constraints;
- last successful local reproduction;
- required runtime and dependency lock;
- data files downloaded and their checksums;
- modifications made by FlyTech;
- which outputs S3 consumes.

## 15. Papers and How They Guide the Build

| Paper | What to learn | Required implementation action |
|---|---|---|
| Shen et al., [An open set model for pest identification](https://pubmed.ncbi.nlm.nih.gov/38061169/) | TF4 task, Tephritid genera, known/unknown distinction, pest open-set context | Align the initial taxa and evaluation vocabulary; compare ecology-aware reranking with the visual baseline |
| Mac Aodha, Cole, and Perona, [Presence-Only Geographical Priors for Fine-Grained Image Classification](https://arxiv.org/abs/1906.05272) | Presence-only geographic/temporal priors and visual-prior fusion | Implement or reproduce the first learned geographic-prior baseline and use spatial evaluation |
| Elith et al., [A statistical explanation of MaxEnt for ecologists](https://doi.org/10.1111/j.1472-4642.2010.00725.x) | Statistical meaning and assumptions of MaxEnt | Document background choice, regularisation, feature selection, and output interpretation |
| Phillips, Anderson, and Schapire, [Maximum entropy modeling of species geographic distributions](https://www.sciencedirect.com/science/article/abs/pii/S030438000500267X) | Classic presence-only distribution modelling | Provide a transparent traditional suitability baseline |
| Chen et al., [Open-Insect](https://arxiv.org/abs/2503.01691) | Novel-species, geographic OOD, and open-set evaluation | Adapt spatial holdout, local/non-local OOD, AUROC, and FPR95 evaluation concepts |
| Wang et al., [DeepTaxon](https://arxiv.org/abs/2604.24029) | Retrieval-augmented multimodal evidence and explicit novelty | Use as a design reference for evidence cards and insufficient-evidence behavior; do not assume an official code dependency |
| Shi et al., [PestMA](https://arxiv.org/abs/2504.09855) | Retriever, validator, and orchestrator roles in pest-management agents | Use as an architecture reference for retrieval validation and evidence conflict handling |

The builder must not claim that a paper's reported accuracy transfers to FlyTech. All performance statements must be measured on FlyTech-defined splits.

## 16. Recommended Software Architecture

Unless an established repository standard supersedes it, prefer a Python package with framework-neutral core logic and an optional HTTP layer.

```text
S3-Ecological-Agent/
  EarlyDesign.md
  README.md
  pyproject.toml
  config/
    sources.example.yaml
    thresholds.example.yaml
  src/s3_ecological/
    agent/
    schemas/
    interfaces/
    providers/
    taxonomy/
    occurrence/
    priors/
    suitability/
    fusion/
    risk/
    evidence/
    orchestration/
    api/
  tests/
    fixtures/
    unit/
    integration/
    evaluation/
  data/
    README.md
    raw/.gitkeep
    interim/.gitkeep
    processed/.gitkeep
  models/
    README.md
  scripts/
  docs/
    decisions/
    data-cards/
    model-cards/
```

Architecture requirements:

- domain logic must run without HTTP;
- each external data provider must implement a common adapter interface;
- provider-specific fields must be retained in raw evidence;
- configuration must control source selection, bounds, quality rules, weights, and thresholds;
- secrets must come from environment or an approved secret store and must never be committed;
- the default prototype configuration must require no secrets and must use fixture or local-snapshot providers;
- tests must not depend on live APIs by default;
- logs must avoid unnecessary precise-location disclosure;
- model and data artefacts must not be committed if their licences or size make that inappropriate;
- use data cards and model cards for all material snapshots and trained models.

### 16.1 Prototype agent framework and optional LLM boundary

The recommended prototype stack is **Python, Pydantic, PydanticAI, pytest, and an optional FastAPI transport layer**. PydanticAI is the preferred first agent framework because it supports typed tools, dependency injection, validated structured outputs, test models, and replaceable model providers. This is an implementation recommendation, not a permanent platform dependency: if later project evidence favours the OpenAI Agents SDK, LangGraph, another framework, or a centrally supplied FlyTech runtime, S3 must be able to replace the agent adapter without rewriting ecological domain logic.

The stack is recommended for the following concrete S3 reasons:

- S3 inputs and outputs require explicit, validated data structures for taxa, locations, observation times, environmental variables, visual and ecological scores, evidence, provenance, missing values, and uncertainty;
- PydanticAI provides typed tools, dependency injection, and validated structured outputs, which supports the prototype's readability, maintainability, testability, and later extension;
- its provider abstraction can support OpenAI, Anthropic, Google, Ollama, and other compatible model providers, so S3 must select the provider through configuration rather than become locked to one API vendor;
- the absence of an API key must not block the build: use PydanticAI's offline test model or an S3-owned mock provider to test the agent loop, tool contracts, dependency injection, and output validation before enabling a real model.

The prototype must follow these boundaries:

- the S3 ecological core must run and be fully testable **without an LLM**, network access, credentials, HTTP, or PydanticAI;
- Pydantic models and exported JSON Schema are the canonical request, response, evidence, error, and external-agent contracts;
- PydanticAI may be used only in `agent/` as a thin orchestration and interaction layer over typed S3 tools;
- FastAPI, if added, is a transport adapter rather than the owner of S3 business logic;
- framework SDK objects, chat messages, and provider response objects must not cross into `taxonomy/`, `occurrence/`, `priors/`, `suitability/`, `fusion/`, `risk/`, or `evidence/`;
- the LLM may interpret a request, select an allowed tool, identify missing inputs, request clarification, and explain already-computed results;
- deterministic Python code or a separately versioned statistical or machine-learning model must perform taxonomy validation, occurrence cleaning, ecological scoring, fusion, threshold checks, and risk-state assignment;
- the LLM must never generate or override occurrence records, taxa, coordinates, component scores, thresholds, risk states, citations, provenance, or model versions;
- an LLM-generated explanation must be derived only from the validated S3 result and evidence objects, and the structured result remains authoritative if prose and data disagree;
- a deterministic orchestration path must remain available for batch evaluation, regression tests, debugging, and deployments that disable generative AI;
- the default demo must use a mock or framework-provided test model and must not require a real model API key.

Define an S3-owned model boundary using a small `Protocol` or equivalent interface. The exact names may change, but the dependency direction must remain equivalent to:

```python
class LLMProvider(Protocol):
    async def generate(self, request: AgentRequest) -> AgentResponse:
        """Return a validated orchestration or explanation result."""
        ...
```

The first implementation should provide:

- `MockLLMProvider` or PydanticAI's offline test model for deterministic development and tests;
- configuration that disables the LLM by default and selects providers without code changes;
- a deferred adapter location for a future OpenAI or other approved provider;
- a typed tool registry containing only S3-owned capabilities;
- an explicit allow-list so the agent cannot call arbitrary code, shell commands, network endpoints, or tools belonging to S1, S2, S4, S5, S6, or the orchestrator.

Suggested configuration semantics:

```text
S3_LLM_ENABLED=false
S3_LLM_PROVIDER=mock
S3_LLM_MODEL=
```

Configuration names may follow repository conventions, but disabled or unconfigured LLM mode must start successfully. A missing credential must produce a typed `provider_not_configured` result only when the real provider is requested; it must not prevent deterministic S3 analysis.

The current prototype does not require multi-agent conversations, autonomous long-running execution, or graph-based workflow persistence. Do not introduce AutoGen, LangGraph, a vector database, or another orchestration platform until a documented S3 use case and evaluation justify the extra dependency. Knowledge retrieval may later use LlamaIndex or another RAG component behind an S3-owned evidence-retriever interface, but retrieval output must still pass provenance validation before it affects an assessment.

### 16.2 Configuration contract

Represent runtime configuration with a validated, typed `S3Settings` model and publish an empty-secret example. Reject unknown fields so configuration mistakes do not silently change ecological behavior.

Configuration precedence, from highest to lowest, is:

1. explicit constructor or CLI arguments;
2. environment variables;
3. the selected versioned YAML/TOML configuration file;
4. Prototype Implementation Profile v0.1 defaults.

The configuration must cover:

- `configuration_version` and `profile_version`;
- taxonomy and occurrence provider selection;
- snapshot paths and checksums;
- geographic bounds and cleaning rules;
- baseline parameters, fusion weights, and risk thresholds;
- cache location, TTL, timeouts, and bounded retry policy;
- privacy and coordinate-coarsening policy;
- LLM enabled flag, provider, model, and safe limits;
- logging level and redaction behavior.

Secrets are never valid configuration-file values in committed examples. Real-provider credentials must come from environment variables or an approved secret store. Invalid configuration must fail before analysis with a typed message that identifies the field but never echoes secret values.

### 16.3 Code readability, maintainability, and extensibility

These are hard requirements for the prototype, not optional cleanup work. Code that produces the expected output but is difficult to understand, test, modify, or extend does not satisfy this design.

#### Readability

- use descriptive domain names such as `occurrence_records`, `geo_support`, and `coordinate_uncertainty_m` rather than unexplained abbreviations;
- keep functions and classes focused on one responsibility and avoid deeply nested control flow;
- separate data retrieval, validation, cleaning, scoring, risk classification, and presentation instead of combining them in one workflow function;
- add type hints to public functions, service boundaries, schemas, adapter methods, and non-trivial internal functions;
- use validated domain models instead of passing unstructured dictionaries through the core logic;
- use consistent terminology from this document for risk states, evidence quality, taxon identity, and uncertainty;
- avoid duplicated transformations or scoring logic; extract shared behavior only when its responsibility is clear;
- prefer straightforward code over clever or compressed expressions;
- include units in names or schemas where ambiguity is possible, for example metres, degrees, UTC timestamps, and probabilities.

#### Maintainability

- keep ecological domain logic independent from HTTP, CLI, database, and provider SDK code;
- isolate each remote provider behind an adapter and translate provider failures into typed S3 errors;
- keep thresholds, weights, geographic bounds, quality filters, and retry settings in versioned configuration rather than magic numbers;
- use explicit dependency injection or factories so tests can replace live providers, caches, clocks, and models with fixtures;
- use structured logging with analysis IDs and safe context, while avoiding unnecessary precise-location disclosure;
- pin or lock direct dependencies and document why each material dependency is required;
- provide one documented developer workflow, such as project scripts or equivalent commands, for formatting, linting, type checking, testing, and running the fixture demo;
- keep architectural decisions that affect interfaces, data meaning, modelling assumptions, or dependencies in `docs/decisions/`;
- delete dead code and stale compatibility paths instead of leaving multiple undocumented implementations;
- do not silence type, lint, or test failures without a local explanation and a documented follow-up.

#### Extensibility

- define small interfaces or Python `Protocol`/abstract base classes for taxonomy providers, occurrence providers, geographic-prior models, suitability models, caches, and risk policies;
- adding a new occurrence provider should normally require a new adapter and configuration entry, not changes to fusion or risk logic;
- adding a new prior or suitability model should preserve the same versioned input/output contract and component-score semantics;
- keep provider-specific fields in raw evidence, but do not leak provider-specific response objects into domain logic;
- version public schemas and document backward-incompatible changes;
- make supported taxa, data sources, scoring components, and thresholds configuration-driven where scientifically valid;
- document extension points with one minimal example or test double;
- avoid speculative generalisation: introduce an abstraction only when it protects a known boundary or supports a planned alternative.

#### Comments and documentation inside the code

- add concise comments or docstrings where they explain **why** a choice exists, not merely what the next line does;
- comment ecological assumptions, presence-only limitations, background-sampling choices, coordinate-quality rules, score transformations, threshold precedence, extrapolation checks, and non-obvious edge cases;
- document public classes, functions, schemas, adapters, and configuration fields with their inputs, outputs, units, failure modes, and important side effects;
- place a short rationale next to any unavoidable workaround, compatibility branch, or non-obvious performance optimisation;
- do not over-comment obvious assignments or repeat the code in prose;
- update or remove comments when behavior changes; incorrect comments are defects;
- use actionable TODOs that describe the missing work and its reason; do not use vague TODOs as permanent placeholders.

#### Code-quality gates

The selected toolchain may follow repository standards. For a new Python implementation, `ruff` or an equivalent formatter/linter, `pyright` or `mypy` for static type checking, and `pytest` are recommended. The prototype must have:

- no formatter, linter, type-checker, or test errors in S3-owned code;
- meaningful unit coverage for schemas, cleaning, fusion, risk policies, and error handling, with a target of at least 80 percent line coverage for core deterministic modules;
- an import-boundary test or equivalent architectural check showing that deterministic domain modules do not depend on PydanticAI, FastAPI, or a model-provider SDK;
- tests that demonstrate a provider or model can be replaced with a fixture through its interface;
- tests that demonstrate the same validated ecological assessment can be produced with the LLM disabled;
- code review evidence that an additional occurrence provider can be added without rewriting the core decision pipeline;
- a readable fixture-based example that a new developer or agent can run from the README without live credentials.

## 17. External Integration Contract

S3 must publish a stable contract that an externally owned orchestrator can use. Implementing that orchestrator is not part of this project. The contract must have these behaviors:

1. S3 accepts S1 candidates even when some context is missing.
2. S3 returns partial results and structured warnings when a provider is unavailable.
3. S3 identifies what additional evidence would most improve the decision.
4. S3 preserves candidate identity so an external orchestrator can combine S1, S2, S3, and S4 evidence.
5. S3 provides `review_required`, reasons, and evidence links.
6. S3 returns machine-readable values and a short human-readable explanation derived from those values.
7. S3 never changes the final candidate to a taxon that was neither supplied nor explicitly introduced as a separately labelled retrieval suggestion.
8. Every response includes analysis, model, threshold, data-snapshot, and schema versions.

Recommended service operations:

```text
POST /v1/ecological-assessments
GET  /v1/ecological-assessments/{analysis_id}
GET  /v1/evidence/{evidence_id}
GET  /health
GET  /version
```

An in-process tool interface is acceptable for the MVP if it uses the same schemas.

Contract-boundary requirements:

- provide versioned request and response JSON Schemas owned by S3;
- provide example payloads for S1 candidates, optional external-agent evidence, orchestrator requests, and S5-compatible feedback records;
- provide mocks or fixtures for every external producer and consumer used in S3 tests;
- use consumer/provider contract tests where practical;
- do not import implementation code from another agent merely to make an S3 test pass;
- do not place cross-agent routing, final multi-agent fusion, UI behavior, or expert-workflow logic inside S3;
- return clear compatibility errors when an external payload uses an unsupported schema version;
- document external interface requests separately so the responsible module owner can implement them.

## 18. Uncertainty, Thresholds, and Escalation

Thresholds must be versioned configuration, never hidden literals. At minimum distinguish:

- insufficient occurrence sample size;
- unacceptable coordinate uncertainty;
- source-query failure;
- weak geographic support;
- high disagreement between visual and ecological evidence;
- outside training covariate range;
- model ensemble disagreement;
- open-set or novelty score requiring review.

Expert review should be required when:

- a possible incursion rule is triggered;
- high visual confidence conflicts strongly with ecological evidence;
- multimodal agents disagree materially;
- taxonomy resolution is ambiguous;
- critical evidence has poor provenance;
- the observation is outside model geographic or environmental support;
- the decision would be used for an operational biosecurity action.

The explanation must identify which threshold fired and which version defined it.

## 19. Evaluation Plan

This section defines research evaluation once authorised, appropriately labelled data and compatible S1 outputs are available. It must not block the fixture-backed engineering prototype. Synthetic fixtures may validate evaluation code paths, but their metrics must never be reported as biological, identification, calibration, OOD, or incursion performance.

### 19.1 Required comparisons

Evaluate at least:

1. S1 visual predictions only;
2. geographic prior only;
3. S1 plus geographic prior;
4. environmental suitability only, when available;
5. S1 plus geographic prior plus suitability;
6. the same systems with and without calibration.

### 19.2 Required splits

- spatial block or region holdout;
- Australia-focused state/ecoregion holdout where data allows;
- temporal holdout where coverage allows;
- known taxa versus unseen near-neighbour taxa;
- local OOD versus non-local OOD inspired by Open-Insect;
- fixture-based integration cases for missing and conflicting evidence.

### 19.3 Required metrics

- candidate top-1 and top-k accuracy where labels are valid;
- macro F1 for known classes;
- change in correct-candidate rank after S3;
- unknown/OOD AUROC and FPR95;
- expected calibration error and/or Brier score;
- potential-incursion review recall on expert-validated cases;
- false-alert rate;
- percentage of cases escalated to experts;
- remote query latency, cache hit rate, and failure rate;
- evidence completeness and provenance coverage.

Report confidence intervals or repeated-split variation when sample size allows. Do not optimize only for closed-set accuracy.

## 20. Testing Requirements

### 20.1 Unit tests

Cover:

- coordinate and date validation;
- probability validation and normalization;
- taxonomy synonym and ambiguity handling;
- occurrence cleaning and duplicate detection;
- missing coordinate uncertainty;
- score behavior when one or more components are unavailable;
- threshold boundary conditions;
- risk-state precedence;
- evidence serialization and schema stability.

### 20.2 Integration tests

Use recorded or synthetic fixtures for:

- successful GBIF/ALA responses;
- no records returned;
- rate limit, timeout, server error, and malformed response;
- duplicated GBIF/ALA records;
- stale cache and source refresh;
- conflicting source taxonomy;
- orchestrator request and response round trip.
- deterministic end-to-end analysis with `S3_LLM_ENABLED=false`;
- mock/test-model agent tool selection without network access;
- validation that agent prose cannot mutate the authoritative component scores, risk state, evidence, or provenance.

Live API and real-LLM tests must be optional, clearly marked, excluded from the default test command, and safe to skip when credentials are absent.

### 20.3 Golden acceptance fixtures

Store versioned request, provider-response, and expected-result files under `tests/fixtures/golden/`. The default test command must run all golden cases with networking and the LLM disabled. Assert exact enum, flag, warning, version, and ordering values; use documented floating-point tolerances for calculated scores.

The minimum v0.1 golden cases are:

| Fixture | Synthetic setup | Required result |
|---|---|---|
| `supported_same_location` | Observation at `(0, 0)`; top candidate has three valid occurrence records at `(0, 0)`, `(0, 0.1)`, and `(0, -0.1)` | `geo_support=1.0`; candidate remains first; `risk_state=ecologically_supported`; `review_required=false` |
| `geographic_ood_review` | Observation at `(0, 0)`; top candidate has at least three valid records whose nearest point is around `(0, 20)`; incursion rule disabled | `geo_support < geo_ood_max`; `risk_state=geographic_ood`; `review_required=true`; never `potential_incursion` or `confirmed_incursion` |
| `no_occurrence_records` | Occurrence query succeeds with no records for every candidate | `geo_support=null`; tool status `no_records`; case status `completed_with_warnings`; `risk_state=unknown_or_insufficient_evidence`; no absence claim |
| `provider_not_configured` | A live provider is explicitly selected without its required configuration | Typed `provider_not_configured` issue; no startup crash; any fixture-backed components may still return a safe partial result |
| `missing_location` | Structurally valid request omits location | Case status `completed_with_warnings`; no occurrence-distance calculation; `risk_state=unknown_or_insufficient_evidence`; `requested_evidence` asks for location |
| `truncated_top_k` | `candidate_set_complete=false`; raw probabilities `0.6` and `0.3`; omitted mass `0.1`; candidates have equal ecological support | Raw probabilities and omitted mass remain unchanged; rerank scores are approximately `0.666667` and `0.333333`, sum to 1 only across submitted candidates, and are not labelled as a posterior |

Each expected result must include `schema_version`, `profile_version`, `configuration_version`, model, threshold, and data-snapshot versions. Golden fixtures are engineering acceptance evidence only and must not be reported as biological performance.

### 20.4 Safety tests

Verify that S3:

- never translates `no records` into `species absent`;
- never returns `confirmed_incursion`;
- never hides missing location or date;
- cannot produce untraceable evidence links;
- escalates configured high-risk conflicts;
- redacts or coarsens precise sensitive locations when configured;
- behaves safely when all external providers fail.

## 21. Reproducibility and Data Governance

For every experiment, save:

- code commit;
- configuration and random seed;
- source query and retrieval date;
- raw snapshot checksum;
- cleaning report and exclusion counts;
- taxonomy mapping version;
- train/validation/test split manifest;
- model artefact checksum;
- metric definitions and output;
- known limitations;
- licences and citation requirements.

Do not commit API keys, restricted data, large raw datasets, or media without verified redistribution rights. A record licence and an image/media licence are separate concerns.

## 22. Delivery Sequence for the Builder Agent

### Milestone 0 - repository and design confirmation

- Inspect the repository and later project instructions.
- Create the package skeleton, configuration examples, and decision log.
- Convert the input/output contracts in this document into validated schemas.
- Add a minimal CLI or callable function using synthetic fixtures.
- Add the deterministic orchestration path first, with no dependency on an LLM.
- Add the PydanticAI adapter, typed S3 tool wrappers, and mock/test-model configuration as a replaceable outer layer.
- Define the `LLMProvider` boundary and deferred real-provider configuration without requiring credentials.
- Configure and document formatting, linting, static type checking, tests, and the fixture-demo command.
- Add the provider/model interfaces and at least one test double before connecting a live API.

### Milestone 1 - traceable occurrence MVP

- Implement taxonomy and occurrence provider interfaces, plus in-memory and local-snapshot adapters.
- Add explicit configuration placeholders or deferred stubs for future GBIF/ALA live adapters without requiring credentials or network access.
- Build a small synthetic or legally reusable genus-level occurrence snapshot.
- Implement cleaning, caching, provenance, and an occurrence-distance baseline.
- Return evidence-bearing risk results without a learned model.

### Milestone 2 - geographic reranking experiment

- Before training, run the offline `prepare-geo-experiment` readiness gate (section 11.4) and confirm `overall_milestone_2_status` is not `not_run_missing_authorised_data` or `not_ready_data_quality`; this gate prepares data and spatial splits only and does not itself satisfy this milestone.
- Reproduce `geo_prior` on its example data.
- Train or adapt a fruit-fly geographic prior.
- Implement soft fusion with S1 outputs.
- Evaluate S1-only versus S1-plus-geography on spatial holdouts.

### Milestone 3 - suitability and open-set evaluation

- Add justified environmental covariates and a MaxEnt-style baseline.
- Add model-scope and extrapolation checks.
- Add Open-Insect-inspired OOD evaluation.
- Calibrate escalation thresholds with validation data.

### Milestone 4 - S3 interface hardening and external handoff

- Expose the stable service/tool interface.
- Define S5-compatible expert-feedback import/export records without implementing S5.
- Add contract tests with mocked S1, orchestrator, S5, and other external-module payloads.
- Test S3's evidence-conflict, request-more-evidence, and escalation outputs without implementing the downstream workflow.
- Produce data cards, model cards, and an evaluation report.

Do not begin a later milestone until the previous milestone has a runnable demo and documented test results.

## 23. Definition of Done for the First Testable S3 Agent

### 23.1 Core engineering prototype definition of done

The first fixture-backed S3 engineering prototype is complete only when all of the following are true:

- [ ] A validated request with S1 candidates, location, and optional date can be processed end to end.
- [ ] The S1 request used by standalone tests is a fixture or schema-compatible external payload; no S1 implementation is required.
- [ ] Taxon names are resolved with raw and accepted forms preserved.
- [ ] In-memory and local-snapshot occurrence adapters work through the same interface intended for future GBIF/ALA adapters.
- [ ] The prototype starts, demonstrates its full workflow, and passes tests without API credentials, live providers, or network access.
- [ ] The same core ecological assessment can run with `S3_LLM_ENABLED=false`, and the default prototype does not require an external LLM.
- [ ] PydanticAI, if present, is confined to the agent adapter and can be replaced without modifying deterministic ecological modules.
- [ ] A mock or offline test model exercises typed agent tools and validated outputs without making a model API call.
- [ ] Real LLM providers are configuration-selected adapters; no provider SDK or model name is hard-coded into domain logic.
- [ ] Agent-generated prose cannot override the authoritative structured scores, risk state, thresholds, evidence, or provenance.
- [ ] Unconfigured live providers return an explicit safe status and do not prevent other S3 functions from running.
- [ ] Future GBIF/ALA integration can be added as an adapter without changing the core cleaning, fusion, risk, evidence, or public-schema logic.
- [ ] Occurrence records retain source IDs, query details, coordinate precision, dates, licences, and cleaning flags.
- [ ] A simple geographic baseline produces candidate support scores.
- [ ] S1 and ecological scores are combined through documented soft fusion.
- [ ] Output contains reranked candidates, component scores, evidence, uncertainty, missing evidence, versions, and risk state.
- [ ] No-data and provider-failure cases return safe partial results.
- [ ] All v0.1 golden acceptance fixtures pass through the documented CLI and library entry point.
- [ ] Potential-incursion cases require review and are never presented as confirmed incursions.
- [ ] Unit, integration, and safety tests pass without network access.
- [ ] Formatting, linting, and static type checks pass for all S3-owned code.
- [ ] Core deterministic modules meet the documented coverage target, or an explicit evidence-based exception is recorded.
- [ ] Public interfaces and non-obvious ecological or scoring decisions have accurate docstrings or concise rationale comments.
- [ ] A provider and a model can each be replaced by a fixture or test double without changing the core decision pipeline.
- [ ] Import-boundary checks show that the core does not depend on PydanticAI, FastAPI, or an external LLM SDK.
- [ ] The implementation contains no unexplained magic thresholds, duplicated scoring logic, provider objects leaking into domain logic, or vague permanent TODOs.
- [ ] A README explains setup, demo commands, configuration, data acquisition, and limitations.
- [ ] Relevant data cards, model cards, licence notes, and experiment records exist.
- [ ] Versioned interface schemas and examples exist for all external-module boundaries used by S3.
- [ ] Tests pass with mocks or fixtures when S1, S2, S4, S5, S6, and the orchestrator are unavailable.
- [ ] No non-S3 agent logic, orchestrator routing logic, application logic, or expert-workflow implementation has been added to the S3 repository.

### 23.2 Conditional research-validation definition of done

These items become required only after the project owner or supervisor supplies or approves suitable data, S1 outputs, labels, and evaluation scope. Their absence must not block completion of the engineering prototype.

- [ ] The evaluation dataset has an approved licence, provenance, checksum, taxonomy mapping, and split manifest.
- [ ] Real or authorised recorded S1 candidate outputs are available; synthetic visual probabilities are not used to claim identification performance.
- [ ] A spatial holdout evaluation compares S1-only, geographic-only, and S1-plus-S3 results.
- [ ] Temporal, local-OOD, and non-local-OOD splits are evaluated where the available data support them.
- [ ] Calibration and OOD metrics are reported only where valid labels permit.
- [ ] Potential-incursion and false-alert metrics use expert-validated or authorised regulatory labels rather than inferred public-record absence.
- [ ] Confidence intervals or repeated-split variation are reported where sample size permits.
- [ ] The evaluation report clearly separates engineering fixture results from biological research results.

If these inputs are unavailable, record the research-validation status as `not_run_missing_authorised_data` with the missing dependency; do not fabricate data, labels, metrics, or completion evidence.

## 24. Questions That Require Project-Owner or Supervisor Confirmation

The builder should not block the basic fixture-based MVP on these questions, but must request decisions before treating them as production requirements:

1. Is genus-level TF4 coverage sufficient for the first demo, or are particular fruit-fly species required?
2. Which Australian jurisdictions, ecoregions, crops, hosts, and surveillance programs are in scope?
3. Will S1 provide calibrated probabilities and a stable taxonomy identifier, or only display names?
4. What API access, approved data snapshots, baseline models, and HPC resources will the project team provide later?
5. Which locations are sensitive and require coordinate coarsening or access control?
6. What operational action follows each risk state?
7. Who is the authorised expert reviewer, and how should feedback reach S5?
8. Which labelled incursion or quarantine records may be used for evaluation?
9. What false-alert and missed-alert trade-off is acceptable?
10. Is deployment local, sovereign cloud, university HPC, or another environment?

Until these are answered, use configuration placeholders and clearly labelled assumptions.

## 25. Final Instruction to Any Implementation Agent

Build the smallest evidence-grounded system that can answer the first testable question. Begin with transparent data, a simple baseline, spatially honest evaluation, and safe uncertainty behavior. Do not hide ecological assumptions inside an LLM prompt, do not overclaim from presence-only records, and do not expand to large multimodal datasets until the geographic-prior MVP produces reproducible evidence of value.
