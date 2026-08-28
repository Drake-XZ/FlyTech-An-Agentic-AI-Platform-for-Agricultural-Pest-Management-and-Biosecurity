"""Loader for the six golden acceptance cases (EarlyDesign.md section 20.3).

Each case lives under ``fixtures/golden/<name>/`` as:

- ``request.json`` - a serialized :class:`ObservationRequest`.
- ``expected.json`` - ``{"settings_overrides": {...}, "expect": {...}}``.
  ``settings_overrides`` are merged over the frozen Profile v0.1 defaults;
  ``expect`` is documentation-only for this loader (the actual assertions
  live in the pytest tests, which is where a wrong expectation would be
  caught by a failing test rather than silently trusted).
- ``occurrences.json`` - optional. When present, occurrences are served from
  this snapshot via :class:`LocalSnapshotOccurrenceProvider`; otherwise the
  provider named by ``settings.occurrence_provider`` is built normally (this
  is how ``no_occurrence_records`` gets an empty ``in_memory`` provider and
  ``provider_not_configured`` gets an unconfigured live adapter).

This module is imported by both the test suite and the CLI's
``demo --fixture <name>`` command so the two never drift apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from s3_ecological.interfaces.occurrence import OccurrenceProvider
from s3_ecological.interfaces.priors import GeoPriorModel
from s3_ecological.interfaces.risk import RiskPolicy
from s3_ecological.interfaces.suitability import SuitabilityModel
from s3_ecological.interfaces.taxonomy import TaxonomyProvider
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider
from s3_ecological.providers.occurrence_local_snapshot import LocalSnapshotOccurrenceProvider
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.request import ObservationRequest
from s3_ecological.settings import S3Settings
from s3_ecological.suitability.null_model import NullSuitabilityModel

GOLDEN_CASE_NAMES: tuple[str, ...] = (
    "supported_same_location",
    "geographic_ood_review",
    "no_occurrence_records",
    "provider_not_configured",
    "missing_location",
    "truncated_top_k",
)


def golden_case_dir(name: str) -> Path:
    if name not in GOLDEN_CASE_NAMES:
        raise ValueError(f"Unknown golden case '{name}'; known cases are {GOLDEN_CASE_NAMES}")
    return Path(str(resources.files("s3_ecological.fixtures"))) / "golden" / name


@dataclass(frozen=True)
class GoldenCase:
    """Everything needed to run one golden case through ``run_assessment``."""

    name: str
    request: ObservationRequest
    settings: S3Settings
    expect: dict
    taxonomy_provider: TaxonomyProvider
    occurrence_provider: OccurrenceProvider
    geo_prior_model: GeoPriorModel
    suitability_model: SuitabilityModel
    risk_policy: RiskPolicy


def load_golden_case(name: str) -> GoldenCase:
    case_dir = golden_case_dir(name)
    request = ObservationRequest.model_validate(
        json.loads((case_dir / "request.json").read_text(encoding="utf-8"))
    )
    expected_payload = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    settings = S3Settings(**expected_payload.get("settings_overrides", {}))

    occurrences_path = case_dir / "occurrences.json"
    occurrence_provider: OccurrenceProvider
    if occurrences_path.exists():
        occurrence_provider = LocalSnapshotOccurrenceProvider(occurrences_path)
    else:
        occurrence_provider = build_occurrence_provider(settings)

    return GoldenCase(
        name=name,
        request=request,
        settings=settings,
        expect=expected_payload.get("expect", {}),
        taxonomy_provider=FixtureTaxonomyProvider(),
        occurrence_provider=occurrence_provider,
        geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
        suitability_model=NullSuitabilityModel(),
        risk_policy=DeterministicRiskPolicy(),
    )
