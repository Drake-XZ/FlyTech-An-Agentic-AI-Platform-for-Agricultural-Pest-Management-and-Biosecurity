"""FastAPI app for the local research demo.

A thin wrapper only: this module validates input, runs the two local model
adapters, builds an ``ObservationRequest``, and calls
``s3_ecological.run_assessment`` unmodified. It never re-implements,
duplicates, or bypasses fusion, risk, or validation logic.

Not a production service. Not a quarantine/inspection decision tool. Not a
biosecurity decision system. Local-only: no external API, LLM, map service,
GBIF, or ALA call is made by this module.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..orchestration.pipeline import run_assessment
from ..providers.factory import build_occurrence_provider, build_taxonomy_provider
from ..risk.policy import DeterministicRiskPolicy
from ..schemas.request import Location, ObservationContext, ObservationRequest, VisualCandidate
from ..settings import S3Settings
from ..suitability.null_model import NullSuitabilityModel
from .demo_config import (
    GEO_PRIOR_MODEL_VERSION,
    TF4_CLASS_NAMES,
    TF4_MODEL_VERSION,
    DemoConfig,
    load_demo_config,
)
from .validation import (
    DemoValidationError,
    validate_coordinates,
    validate_image_bytes,
    validate_observed_at,
)

_logger = logging.getLogger("s3_ecological.api.demo")

_DEMO_NOTICE = (
    "Local research demo only - not a production system, not a "
    "quarantine/inspection decision tool, and not a biosecurity decision "
    "system. The visual model recognizes exactly four genera in a "
    "closed-set softmax; it has no unknown-class detection."
)


def _tf4_available(config: DemoConfig) -> bool:
    return config.tf4_checkpoint_path.exists()


def _geo_prior_available(config: DemoConfig) -> bool:
    return (
        config.geo_prior_checkpoint_path.exists()
        and config.geo_prior_selected_configuration_path.exists()
    )


def create_app(config: DemoConfig | None = None):
    demo_config = config or load_demo_config()
    settings = S3Settings()
    taxonomy_provider = build_taxonomy_provider(settings)
    occurrence_provider = build_occurrence_provider(settings)

    static_dir = Path(__file__).resolve().parent / "static"

    app = FastAPI(title="S3 Ecological Reasoning - Local Research Demo")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "tf4_available": _tf4_available(demo_config),
            "geo_prior_available": _geo_prior_available(demo_config),
            "tf4_model_version": TF4_MODEL_VERSION,
            "geo_prior_model_version": GEO_PRIOR_MODEL_VERSION,
            "genera": list(TF4_CLASS_NAMES),
            "notice": _DEMO_NOTICE,
        }

    @app.post("/api/assess")
    async def assess(
        image: UploadFile = File(...),  # noqa: B008 - standard FastAPI dependency-default idiom
        latitude: float | None = Form(default=None),
        longitude: float | None = Form(default=None),
        observed_at: str | None = Form(default=None),
        host: str | None = Form(default=None),
        trap_type: str | None = Form(default=None),
        habitat: str | None = Form(default=None),
        notes: str | None = Form(default=None),
        temperature_c: float | None = Form(default=None),
    ) -> JSONResponse:
        try:
            image_bytes = await image.read()
            validate_image_bytes(image_bytes, image.content_type)
            validate_coordinates(latitude, longitude)
            parsed_observed_at = validate_observed_at(observed_at)
        except DemoValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

        from . import s1_model
        from .geo_model import FCNetGeoPriorModel

        try:
            visual_result = s1_model.infer(image_bytes, config=demo_config)
        except s1_model.ModelUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

        location = (
            Location(latitude=latitude, longitude=longitude)
            if latitude is not None and longitude is not None
            else None
        )

        context = None
        if any([host, trap_type, habitat, temperature_c is not None]):
            context = ObservationContext(
                host=host or None,
                trap_type=trap_type or None,
                habitat=habitat or None,
                environmental_covariates=(
                    {"temperature_c": temperature_c} if temperature_c is not None else None
                ),
            )

        visual_candidates = [
            VisualCandidate(
                candidate_id=f"fixture:{genus.lower()}",
                name=genus,
                rank="genus",
                visual_probability=visual_result.probabilities[genus],
                model_version=visual_result.model_version,
            )
            for genus in TF4_CLASS_NAMES
        ]

        request = ObservationRequest(
            schema_version="1.0.0",
            observation_id=str(uuid.uuid4()),
            source="s3-local-demo-upload",
            candidate_set_complete=True,
            omitted_probability_mass=0.0,
            observed_at=parsed_observed_at,
            location=location,
            visual_candidates=visual_candidates,
            context=context,
        )

        result = run_assessment(
            request,
            settings=settings,
            taxonomy_provider=taxonomy_provider,
            occurrence_provider=occurrence_provider,
            geo_prior_model=FCNetGeoPriorModel(demo_config),
            suitability_model=NullSuitabilityModel(),
            risk_policy=DeterministicRiskPolicy(),
            analysis_id=f"demo-{uuid.uuid4()}",
            generated_at=datetime.now(UTC),
        )

        from .explain import build_narrative

        narrative = build_narrative(request, result)

        top_name = (
            result.reranked_candidates[0].submitted_name if result.reranked_candidates else None
        )
        _logger.info(
            "demo assess: lat=%s lon=%s top=%s risk_state=%s review_required=%s",
            round(latitude, 1) if latitude is not None else None,
            round(longitude, 1) if longitude is not None else None,
            top_name,
            result.risk_state,
            result.review_required,
        )

        return JSONResponse(
            {
                "assessment": result.model_dump(mode="json"),
                "narrative": narrative,
                "warnings": [issue.message for issue in result.warnings],
                "context_echo": {"notes": notes} if notes else {},
                "notice": _DEMO_NOTICE,
            }
        )

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app
