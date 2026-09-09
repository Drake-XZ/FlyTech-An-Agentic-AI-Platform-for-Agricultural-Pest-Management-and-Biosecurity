"""Integration tests for the real TF4/geo-prior model adapters.

Skipped entirely unless torch is installed AND the local M2 checkpoints are
present on disk - a fresh clone with only the deterministic core installed
must not fail these tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("torch")

from s3_ecological.api import geo_model, s1_model  # noqa: E402
from s3_ecological.api.demo_config import TF4_CLASS_NAMES, load_demo_config  # noqa: E402
from s3_ecological.interfaces.priors import GeoPriorCandidateTaxon, GeoPriorRequest  # noqa: E402
from s3_ecological.schemas.enums import ToolStatus  # noqa: E402

_CONFIG = load_demo_config()

_TF4_AVAILABLE = _CONFIG.tf4_checkpoint_path.exists()
_GEO_PRIOR_AVAILABLE = (
    _CONFIG.geo_prior_checkpoint_path.exists()
    and _CONFIG.geo_prior_selected_configuration_path.exists()
)


@pytest.mark.skipif(not _TF4_AVAILABLE, reason="local TF4 checkpoint not present")
def test_tf4_inference_returns_a_valid_four_way_softmax():
    import io

    from PIL import Image

    image = Image.new("RGB", (32, 32), color=(128, 64, 32))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = s1_model.infer(buffer.getvalue(), config=_CONFIG)

    assert set(result.probabilities) == set(TF4_CLASS_NAMES)
    total = sum(result.probabilities.values())
    assert abs(total - 1.0) < 1e-4
    assert all(0.0 <= value <= 1.0 for value in result.probabilities.values())


@pytest.mark.skipif(not _GEO_PRIOR_AVAILABLE, reason="local geo-prior checkpoint not present")
def test_geo_prior_adapter_returns_scores_in_unit_range():
    model = geo_model.FCNetGeoPriorModel(_CONFIG)
    request = GeoPriorRequest(
        candidate_taxa=[
            GeoPriorCandidateTaxon(
                candidate_id=f"fixture:{name.lower()}", taxon_id=f"fixture:{name.lower()}"
            )
            for name in TF4_CLASS_NAMES
        ],
        latitude=10.0,
        longitude=20.0,
        observed_at=datetime(2024, 5, 1, tzinfo=UTC),
    )

    result = model.estimate(request)

    assert result.status in (ToolStatus.SUCCESS, ToolStatus.PARTIAL)
    assert result.data is not None
    for support in result.data:
        if support.geo_support is not None:
            assert 0.0 <= support.geo_support <= 1.0


@pytest.mark.skipif(not _GEO_PRIOR_AVAILABLE, reason="local geo-prior checkpoint not present")
def test_geo_prior_adapter_never_fabricates_a_date():
    model = geo_model.FCNetGeoPriorModel(_CONFIG)
    request = GeoPriorRequest(
        candidate_taxa=[
            GeoPriorCandidateTaxon(candidate_id="fixture:anastrepha", taxon_id="fixture:anastrepha")
        ],
        latitude=10.0,
        longitude=20.0,
        observed_at=None,
    )

    result = model.estimate(request)

    assert result.data is not None
    assert all(support.geo_support is None for support in result.data)
