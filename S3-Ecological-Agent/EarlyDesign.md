# S3 Ecological Agent - Early Design and Build Requirements

**Document status:** Early design specification for implementation agents<br>
**Prepared from:** FlyTech Week 4 materials<br>
**Last updated:** 26 August 2026<br>
**Primary target:** A testable proof-of-concept for fruit-fly identification and biosecurity decision support

## 1. Purpose of This Document

This document is the implementation brief for any agent or developer building the FlyTech S3 Ecological Agent. It converts the Week 4 project material into explicit product, data, model, interface, testing, and safety requirements.

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

The PPTX under `WEEK 4/backup/` contains the same slide content as the main deck. Its differences are limited to Office document properties and view metadata, so it is not a separate design source.

If this document conflicts with later written instructions from the project owner or supervisor, the later instruction wins. Record the decision in a design log rather than silently changing behavior.

## 3. Mission

S3 must answer the following question:

> Given visual candidate taxa and an observation context, how ecologically plausible is each candidate, what evidence supports or conflicts with it, and should the case be trusted, questioned, treated as out-of-distribution, or escalated as a possible incursion?

S3 is an ecological reasoning and evidence agent. It is not a replacement for visual identification, taxonomy experts, surveillance programs, or official biosecurity decisions.

The first testable research question is:

> Can ecological distribution priors improve candidate reranking and flag potential incursions without becoming overconfident?

## 4. System Context

FlyTech is an orchestrated, modular platform. The central orchestrator coordinates specialist agents through shared interfaces.

- **S1 Visual Agent:** produces image- and morphology-based candidate taxa and calibrated probabilities.
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
- rerank candidates with a transparent, calibrated soft-fusion method;
- return evidence, uncertainty, missing-data flags, and a review-oriented risk state;
- run without live APIs by using recorded fixtures for tests;
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

1. normalize the observation and candidate probabilities;
2. resolve names and synonyms;
3. choose relevant occurrence sources and geographic bounds;
4. query or load cached ecological records;
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
  "observation_id": "obs-123",
  "source": "flytech-app",
  "observed_at": "2026-08-26T10:30:00+10:00",
  "location": {
    "latitude": -35.2809,
    "longitude": 149.1300,
    "coordinate_uncertainty_m": 100
  },
  "visual_candidates": [
    {
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

- latitude must be in `[-90, 90]` and longitude in `[-180, 180]`;
- probabilities must be finite and in `[0, 1]`;
- preserve the raw candidate name as well as the resolved name;
- do not silently infer an exact date, location, host, or coordinate precision;
- distinguish missing time from an explicitly date-free request;
- reject impossible dates and malformed identifiers with structured errors;
- allow partial analysis when non-essential fields are missing.

## 9. Output Contract

S3 must return structured evidence and risk, not only a label.

```json
{
  "observation_id": "obs-123",
  "analysis_id": "s3-run-uuid",
  "status": "completed_with_warnings",
  "reranked_candidates": [
    {
      "submitted_name": "Bactrocera",
      "resolved_taxon": {
        "scientific_name": "Bactrocera",
        "rank": "genus",
        "taxon_ids": {"gbif": "...", "ala": "..."}
      },
      "visual_probability": 0.82,
      "geo_support": 0.61,
      "temporal_support": null,
      "environmental_suitability": null,
      "combined_score": 0.73,
      "evidence_quality": "medium",
      "conflicts": [],
      "supporting_evidence_ids": ["evidence-1"]
    }
  ],
  "risk_state": "ecologically_supported",
  "review_required": false,
  "uncertainty": {
    "level": "medium",
    "reasons": ["environmental covariates unavailable"]
  },
  "missing_evidence": ["host", "environmental_covariates"],
  "evidence": [],
  "model_versions": {},
  "threshold_versions": {},
  "generated_at": "2026-08-26T00:00:00Z"
}
```

Required risk states:

| State | Meaning | Expected action |
|---|---|---|
| `ecologically_supported` | Visual candidate is supported by usable ecological evidence | Keep candidate; report evidence and uncertainty |
| `weak_ecological_support` | Evidence is sparse, old, imprecise, or only mildly supportive | Keep candidate; lower confidence; consider more evidence |
| `geographic_ood` | Observation is outside well-supported sampled range | Do not reject candidate; flag distribution conflict |
| `environmental_conflict` | Available covariates are inconsistent with the fitted suitability model | Do not reject candidate; report model scope and uncertainty |
| `potential_incursion` | Candidate is visually plausible and outside known range but location appears suitable, or another validated rule is triggered | Require expert or biosecurity review |
| `unknown_or_insufficient_evidence` | Candidate set or evidence cannot support a reliable conclusion | Request more evidence or defer |
| `conflicting_multimodal_evidence` | Specialist agents materially disagree | Route to orchestrator and expert review |

`potential_incursion` must never be presented as `confirmed_incursion`.

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

Start with bounded genus-level queries. Save query parameters and raw responses before transforming them. Prefer batch downloads for large GBIF or iNaturalist-derived datasets and normal API calls only for bounded interactive lookups.

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

## 12. Modelling Requirements

### 12.1 Baseline A: occurrence-distance heuristic

Implement a simple, explainable baseline before a neural geographic prior. Examples include distance to quality-filtered records, kernel density, or region-level frequency with smoothing. Its purpose is to validate interfaces and evaluation, not to claim ecological truth.

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
combined_score(s) = log(p_visual(s) + eps)
                  + w_geo * log(p_geo(s | location, time) + eps)
                  + w_env * log(p_env(s | environment) + eps)
```

Requirements:

- learn or select `w_geo` and `w_env` only on validation data;
- define `eps` and all transformations in configuration;
- handle unavailable ecological components explicitly instead of substituting false certainty;
- normalize scores for candidate reranking where appropriate;
- preserve component scores in the output;
- compare fused performance against S1-only, geographic-only, and environment-only ablations;
- calibrate final risk decisions rather than interpreting raw combined scores as probabilities.

## 13. Datasets and Data Platforms

The following resources may be used. The builder must read each licence and terms before downloading or redistributing data.

### 13.1 P0 - required for the first prototype

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
    schemas/
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
- tests must not depend on live APIs by default;
- logs must avoid unnecessary precise-location disclosure;
- model and data artefacts must not be committed if their licences or size make that inappropriate;
- use data cards and model cards for all material snapshots and trained models.

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

Live API tests must be optional and clearly marked.

### 20.3 Safety tests

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

### Milestone 1 - traceable occurrence MVP

- Implement taxonomy and GBIF/ALA adapters.
- Build a small, licensed, genus-level occurrence snapshot.
- Implement cleaning, caching, provenance, and an occurrence-distance baseline.
- Return evidence-bearing risk results without a learned model.

### Milestone 2 - geographic reranking experiment

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

The first S3 agent is complete only when all of the following are true:

- [ ] A validated request with S1 candidates, location, and optional date can be processed end to end.
- [ ] The S1 request used by standalone tests is a fixture or schema-compatible external payload; no S1 implementation is required.
- [ ] Taxon names are resolved with raw and accepted forms preserved.
- [ ] At least one GBIF or ALA occurrence adapter works, and the other can be added through the same interface.
- [ ] Live data is cached and tests run offline with fixtures.
- [ ] Occurrence records retain source IDs, query details, coordinate precision, dates, licences, and cleaning flags.
- [ ] A simple geographic baseline produces candidate support scores.
- [ ] S1 and ecological scores are combined through documented soft fusion.
- [ ] Output contains reranked candidates, component scores, evidence, uncertainty, missing evidence, versions, and risk state.
- [ ] No-data and provider-failure cases return safe partial results.
- [ ] A spatial holdout evaluation compares S1-only against S1-plus-S3.
- [ ] Calibration and OOD metrics are reported where labels permit.
- [ ] Potential-incursion cases require review and are never presented as confirmed incursions.
- [ ] Unit, integration, and safety tests pass without network access.
- [ ] A README explains setup, demo commands, configuration, data acquisition, and limitations.
- [ ] Relevant data cards, model cards, licence notes, and experiment records exist.
- [ ] Versioned interface schemas and examples exist for all external-module boundaries used by S3.
- [ ] Tests pass with mocks or fixtures when S1, S2, S4, S5, S6, and the orchestrator are unavailable.
- [ ] No non-S3 agent logic, orchestrator routing logic, application logic, or expert-workflow implementation has been added to the S3 repository.

## 24. Questions That Require Project-Owner or Supervisor Confirmation

The builder should not block the basic fixture-based MVP on these questions, but must request decisions before treating them as production requirements:

1. Is genus-level TF4 coverage sufficient for the first demo, or are particular fruit-fly species required?
2. Which Australian jurisdictions, ecoregions, crops, hosts, and surveillance programs are in scope?
3. Will S1 provide calibrated probabilities and a stable taxonomy identifier, or only display names?
4. What data, baseline models, and HPC resources will the project team provide?
5. Which locations are sensitive and require coordinate coarsening or access control?
6. What operational action follows each risk state?
7. Who is the authorised expert reviewer, and how should feedback reach S5?
8. Which labelled incursion or quarantine records may be used for evaluation?
9. What false-alert and missed-alert trade-off is acceptable?
10. Is deployment local, sovereign cloud, university HPC, or another environment?

Until these are answered, use configuration placeholders and clearly labelled assumptions.

## 25. Final Instruction to Any Implementation Agent

Build the smallest evidence-grounded system that can answer the first testable question. Begin with transparent data, a simple baseline, spatially honest evaluation, and safe uncertainty behavior. Do not hide ecological assumptions inside an LLM prompt, do not overclaim from presence-only records, and do not expand to large multimodal datasets until the geographic-prior MVP produces reproducible evidence of value.
