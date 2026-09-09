"""Integration tests for the local demo's FastAPI app.

The TF4/geo-prior model adapters are monkeypatched to stub implementations
so these tests never require torch or a local checkpoint - they only
exercise validation, request wiring, safe degradation, and the "never
persist an upload" invariant.
"""

from __future__ import annotations

import io

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from s3_ecological.api import app as app_module  # noqa: E402
from s3_ecological.api import geo_model, s1_model  # noqa: E402
from s3_ecological.api.demo_config import TF4_CLASS_NAMES, DemoConfig  # noqa: E402
from s3_ecological.interfaces.priors import CandidateGeoSupport  # noqa: E402
from s3_ecological.schemas.common import ToolResult  # noqa: E402
from s3_ecological.schemas.enums import EvidenceQuality, ToolStatus  # noqa: E402

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _StubGeoPriorModel:
    def __init__(self, config: DemoConfig, *, geo_support_value: float | None = 0.6):
        self._geo_support_value = geo_support_value

    def estimate(self, request):
        data = [
            CandidateGeoSupport(
                candidate_id=candidate.candidate_id,
                taxon_id=candidate.taxon_id,
                geo_support=self._geo_support_value,
                min_occurrence_distance_km=None,
                usable_occurrence_count=0,
                evidence_quality=(
                    EvidenceQuality.MEDIUM
                    if self._geo_support_value is not None
                    else EvidenceQuality.INSUFFICIENT
                ),
                supporting_evidence_ids=[],
            )
            for candidate in request.candidate_taxa
        ]
        return ToolResult(status=ToolStatus.SUCCESS, data=data)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    config = DemoConfig(
        tf4_checkpoint_path=tmp_path / "missing-tf4.pt",
        geo_prior_checkpoint_path=tmp_path / "missing-geo.pt",
        geo_prior_selected_configuration_path=tmp_path / "missing-config.json",
    )

    def _fake_infer(image_bytes: bytes, *, config):
        probability = 1.0 / len(TF4_CLASS_NAMES)
        return s1_model.VisualInferenceResult(
            probabilities=dict.fromkeys(TF4_CLASS_NAMES, probability),
            model_version="stub-visual-v0",
        )

    monkeypatch.setattr(s1_model, "infer", _fake_infer)
    monkeypatch.setattr(geo_model, "FCNetGeoPriorModel", _StubGeoPriorModel)

    app = app_module.create_app(config)
    return TestClient(app)


def _upload_files():
    return {"image": ("sample.png", io.BytesIO(_PNG_BYTES), "image/png")}


def test_health_endpoint():
    config = DemoConfig()
    client_ = TestClient(app_module.create_app(config))
    response = client_.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["genera"] == list(TF4_CLASS_NAMES)


def test_happy_path_with_location(client):
    response = client.post(
        "/api/assess",
        data={"latitude": "10.0", "longitude": "20.0"},
        files=_upload_files(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assessment"]["reranked_candidates"]
    assert body["assessment"]["missing_evidence"] == []


def test_missing_location_safe_degrade(client):
    response = client.post("/api/assess", data={}, files=_upload_files())
    assert response.status_code == 200
    body = response.json()
    assert "location" in body["assessment"]["missing_evidence"]
    assert body["assessment"]["review_required"] is True
    for candidate in body["assessment"]["reranked_candidates"]:
        assert candidate["geo_support"] is None


def test_missing_date_never_fabricates_a_timestamp(client):
    response = client.post(
        "/api/assess",
        data={"latitude": "10.0", "longitude": "20.0"},
        files=_upload_files(),
    )
    assert response.status_code == 200
    narrative = " ".join(response.json()["narrative"])
    assert "No observation date was provided" in narrative


def test_invalid_coordinates_rejected(client):
    response = client.post(
        "/api/assess",
        data={"latitude": "999.0", "longitude": "20.0"},
        files=_upload_files(),
    )
    assert response.status_code == 400


def test_one_sided_coordinates_rejected(client):
    response = client.post(
        "/api/assess",
        data={"latitude": "10.0"},
        files=_upload_files(),
    )
    assert response.status_code == 400


def test_invalid_image_rejected(client):
    files = {"image": ("bad.txt", io.BytesIO(b"not an image"), "image/png")}
    response = client.post("/api/assess", data={}, files=files)
    assert response.status_code == 400


def test_environmental_fields_echoed_not_modeled(client):
    response = client.post(
        "/api/assess",
        data={
            "latitude": "10.0",
            "longitude": "20.0",
            "host": "guava",
            "trap_type": "mcphail",
            "habitat": "orchard",
            "temperature_c": "24.5",
            "notes": "seen near irrigation canal",
        },
        files=_upload_files(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["context_echo"] == {"notes": "seen near irrigation canal"}
    narrative = " ".join(body["narrative"])
    assert "host" in narrative
    assert "not currently incorporated" in narrative


def test_response_never_contains_unsafe_phrases(client):
    response = client.post(
        "/api/assess",
        data={"latitude": "10.0", "longitude": "20.0"},
        files=_upload_files(),
    )
    body_text = response.text.lower()
    for phrase in ("quarantine cleared", "species confirmation", "confirmed incursion"):
        assert phrase not in body_text


def test_no_file_written_under_data_local(client):
    from pathlib import Path

    data_local = Path("data/local")
    before = set(data_local.rglob("*")) if data_local.exists() else set()

    client.post(
        "/api/assess",
        data={"latitude": "10.0", "longitude": "20.0"},
        files=_upload_files(),
    )

    after = set(data_local.rglob("*")) if data_local.exists() else set()
    assert after == before
