"""Lazy-loaded FCNet geographic-prior adapter for the local demo.

Implements the frozen :class:`~s3_ecological.interfaces.priors.GeoPriorModel`
Protocol exactly as the existing v0.1 nearest-distance baseline does
(``priors/geo_nearest_distance.py``), so fusion and risk logic never change.
Torch is imported lazily inside functions only.

The FCNet architecture and location/date encoding here are a direct,
independent re-implementation of ``scripts/geo_prior_model.py`` (never
imported from ``scripts/``, which relies on script-relative sibling
imports) - kept deliberately small and documented so it can be checked by
inspection against that script.
"""

from __future__ import annotations

import json
import math
import threading
from typing import Any

from ..interfaces.priors import (
    CandidateGeoSupport,
    GeoPriorCandidateTaxon,
    GeoPriorModel,
    GeoPriorRequest,
)
from ..schemas.common import Issue, ToolResult
from ..schemas.enums import EvidenceQuality, IssueCode, ToolStatus
from .demo_config import TF4_CLASS_NAMES, DemoConfig

_lock = threading.Lock()
_cache: dict[str, Any] = {}


class GeoPriorModelUnavailableError(RuntimeError):
    """Raised when the geo-prior checkpoint or configuration is missing/unusable."""


def _build_fcnet(num_inputs: int, num_classes: int, num_filts: int) -> Any:
    """Re-implements ``scripts/geo_prior_model.py``'s ``FCNet``/``ResLayer``.

    ``forward`` returns a raw per-class sigmoid score (not a softmax
    distribution) - this matches ``CandidateGeoSupport.geo_support``'s
    documented per-candidate, independent [0, 1]-ish score semantics.
    """
    import torch
    from torch import nn

    class ResLayer(nn.Module):
        def __init__(self, linear_size: int):
            super().__init__()
            self.w1 = nn.Linear(linear_size, linear_size)
            self.nonlin1 = nn.ReLU()
            self.dropout1 = nn.Dropout()
            self.w2 = nn.Linear(linear_size, linear_size)
            self.nonlin2 = nn.ReLU()

        def forward(self, x: Any) -> Any:
            y = self.w1(x)
            y = self.nonlin1(y)
            y = self.dropout1(y)
            y = self.w2(y)
            y = self.nonlin2(y)
            return x + y

    class FCNet(nn.Module):
        def __init__(self, num_inputs: int, num_classes: int, num_filts: int):
            super().__init__()
            self.class_emb = nn.Linear(num_filts, num_classes, bias=False)
            layers = [nn.Linear(num_inputs, num_filts), nn.ReLU(inplace=True)]
            layers.extend(ResLayer(num_filts) for _ in range(4))
            self.feats = nn.Sequential(*layers)

        def forward(self, x: Any, *, return_feats: bool = False) -> Any:
            loc_emb = self.feats(x)
            if return_feats:
                return loc_emb
            return torch.sigmoid(self.class_emb(loc_emb))

    return FCNet(num_inputs, num_classes, num_filts)


def _encode(
    latitude: float, longitude: float, date_fraction: float | None, *, use_date_feats: bool
) -> Any:
    """Re-implements ``convert_loc_to_tensor``/``encode_loc_time`` inline."""
    import torch

    loc = torch.tensor([[longitude / 180.0, latitude / 90.0]], dtype=torch.float32)
    feats = torch.cat((torch.sin(math.pi * loc), torch.cos(math.pi * loc)), 1)
    if use_date_feats:
        assert date_fraction is not None
        date = torch.tensor([[date_fraction]], dtype=torch.float32)
        date_feats = torch.cat((torch.sin(math.pi * date), torch.cos(math.pi * date)), 1)
        feats = torch.cat((feats, date_feats), 1)
    return feats


def _day_of_year_fraction(observed_at_isoformat: str) -> float:
    """Mirrors ``scripts/train_geo_prior.py::_day_of_year_fraction`` exactly."""
    from datetime import datetime

    parsed = datetime.strptime(observed_at_isoformat[:10], "%Y-%m-%d")
    day_of_year = parsed.timetuple().tm_yday
    return (day_of_year / 365.0) * 2.0 - 1.0


def _load(config: DemoConfig) -> tuple[Any, bool]:
    checkpoint_path = config.geo_prior_checkpoint_path
    if not checkpoint_path.exists() or not config.geo_prior_selected_configuration_path.exists():
        raise GeoPriorModelUnavailableError(
            "The geographic-prior checkpoint is not available on this machine."
        )

    import torch

    try:
        with config.geo_prior_selected_configuration_path.open(encoding="utf-8") as handle:
            selected = json.load(handle)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # noqa: BLE001 - surfaced as a safe, generic message
        raise GeoPriorModelUnavailableError(
            "The geographic-prior checkpoint or configuration could not be loaded."
        ) from exc

    class_names = checkpoint.get("class_names")
    if list(class_names or []) != list(TF4_CLASS_NAMES):
        raise GeoPriorModelUnavailableError(
            "The geographic-prior checkpoint's class order does not match the "
            "expected four-genus configuration for this demo."
        )

    frozen_config = selected.get("frozen_config", {})
    num_filts = int(frozen_config.get("num_filts", checkpoint.get("config", {}).get("num_filts")))
    use_date_feats = bool(
        frozen_config.get("use_date_feats", checkpoint.get("config", {}).get("use_date_feats"))
    )
    num_inputs = int(checkpoint.get("num_inputs", 4 + (2 if use_date_feats else 0)))

    model = _build_fcnet(num_inputs, len(TF4_CLASS_NAMES), num_filts)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model, use_date_feats


def _get_model(config: DemoConfig) -> tuple[Any, bool]:
    key = str(config.geo_prior_checkpoint_path)
    with _lock:
        cached = _cache.get(key)
        if cached is None:
            cached = _load(config)
            _cache[key] = cached
        return cached


def _insufficient(candidate: GeoPriorCandidateTaxon) -> CandidateGeoSupport:
    """No usable evidence: mirrors ``priors/geo_nearest_distance.py``'s convention -
    return ``geo_support=None``, never a substituted zero.
    """
    return CandidateGeoSupport(
        candidate_id=candidate.candidate_id,
        taxon_id=candidate.taxon_id,
        geo_support=None,
        min_occurrence_distance_km=None,
        usable_occurrence_count=0,
        evidence_quality=EvidenceQuality.INSUFFICIENT,
        supporting_evidence_ids=[],
    )


class FCNetGeoPriorModel(GeoPriorModel):
    """Live learned geographic prior for the local demo, implementing GeoPriorModel."""

    def __init__(self, config: DemoConfig):
        self._config = config

    def estimate(self, request: GeoPriorRequest) -> ToolResult[list[CandidateGeoSupport]]:
        try:
            model, use_date_feats = _get_model(self._config)
        except GeoPriorModelUnavailableError as exc:
            data = [_insufficient(candidate) for candidate in request.candidate_taxa]
            return ToolResult(
                status=ToolStatus.PROVIDER_NOT_CONFIGURED,
                data=data,
                errors=[
                    Issue(
                        code=IssueCode.PROVIDER_NOT_CONFIGURED,
                        message=str(exc),
                        component="api.geo_model",
                        retryable=False,
                    )
                ],
            )

        if use_date_feats and request.observed_at is None:
            data = [_insufficient(candidate) for candidate in request.candidate_taxa]
            return ToolResult(
                status=ToolStatus.PARTIAL,
                data=data,
                warnings=[
                    Issue(
                        code=IssueCode.NO_RECORDS,
                        message=(
                            "The geographic-prior model requires an observation date; "
                            "none was provided, so no geographic score was computed."
                        ),
                        component="api.geo_model",
                        retryable=False,
                    )
                ],
            )

        date_fraction = None
        if use_date_feats:
            # Guaranteed non-None here by the early return above.
            assert request.observed_at is not None
            date_fraction = _day_of_year_fraction(request.observed_at.isoformat())
        features = _encode(
            request.latitude, request.longitude, date_fraction, use_date_feats=use_date_feats
        )

        import torch

        with torch.no_grad():
            scores = model(features).squeeze(0).tolist()
        score_by_genus = dict(zip(TF4_CLASS_NAMES, scores, strict=True))
        genus_by_taxon_id = {f"fixture:{name.lower()}": name for name in TF4_CLASS_NAMES}

        results: list[CandidateGeoSupport] = []
        warnings: list[Issue] = []
        for candidate in request.candidate_taxa:
            genus = genus_by_taxon_id.get(candidate.taxon_id)
            if genus is None:
                warnings.append(
                    Issue(
                        code=IssueCode.SCORE_NOT_COMPUTABLE,
                        message=(
                            f"Taxon '{candidate.taxon_id}' is outside the geographic "
                            "prior's four-genus label space."
                        ),
                        component="api.geo_model",
                        retryable=False,
                    )
                )
                results.append(_insufficient(candidate))
                continue
            # EvidenceQuality.MEDIUM: this is a live learned-model score, not the
            # occurrence-count-based tiers the v0.1 baseline uses. MEDIUM keeps the
            # risk policy's LOW-forces-weak-support rule and INSUFFICIENT-means-no-
            # evidence rule both inert here, so the resulting risk state depends only
            # on the actual geo_support value against the configured thresholds.
            # HIGH is reserved for a future validated policy and must not be produced.
            results.append(
                CandidateGeoSupport(
                    candidate_id=candidate.candidate_id,
                    taxon_id=candidate.taxon_id,
                    geo_support=float(score_by_genus[genus]),
                    min_occurrence_distance_km=None,
                    usable_occurrence_count=0,
                    evidence_quality=EvidenceQuality.MEDIUM,
                    supporting_evidence_ids=[],
                )
            )

        status = ToolStatus.PARTIAL if warnings else ToolStatus.SUCCESS
        return ToolResult(status=status, data=results, warnings=warnings)
