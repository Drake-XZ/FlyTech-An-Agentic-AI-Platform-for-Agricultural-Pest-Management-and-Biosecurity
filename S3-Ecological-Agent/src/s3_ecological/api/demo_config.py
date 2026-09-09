"""Runtime configuration for the local research demo (torch-free).

Checkpoint paths default to the locations documented in
``docs/model_cards/tf4_visual_baseline_v0.1.md`` and
``docs/model_cards/geo_prior_baseline_v0.1.md``, and are overridable via
environment variable so a different machine's local M2 artifacts can be
pointed at without editing code. This module never imports torch, FastAPI,
or Pillow - it only describes where things live.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

TF4_CLASS_NAMES: tuple[str, ...] = ("Anastrepha", "Bactrocera", "Ceratitis", "Rhagoletis")
TF4_MODEL_VERSION = "flytech-reproduced-tf4-efficientnet-b2-v0.1"
GEO_PRIOR_MODEL_VERSION = "flytech-reproduced-geo-prior-fcnet-v0.1"

# src/s3_ecological/api/demo_config.py -> parents[3] is the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_TF4_CHECKPOINT_PATH = (
    _REPO_ROOT / "data/local/m2/s1/training/fold-0/tf4_efficientnet_b2_best.pt"
)
DEFAULT_GEO_PRIOR_CHECKPOINT_PATH = (
    _REPO_ROOT / "data/local/m2/geo_prior/training/filts256_dateTrue/checkpoint.pt"
)
DEFAULT_GEO_PRIOR_SELECTED_CONFIGURATION_PATH = (
    _REPO_ROOT / "data/local/m2/geo_prior/training/selected_configuration.json"
)

# 8 MiB is generous for a single specimen photo while keeping the demo's
# in-memory decode step bounded.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


@dataclass(frozen=True)
class DemoConfig:
    """Local paths the demo reads from. Never a place to store uploads."""

    tf4_checkpoint_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("S3_DEMO_TF4_CHECKPOINT", str(DEFAULT_TF4_CHECKPOINT_PATH))
        )
    )
    geo_prior_checkpoint_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("S3_DEMO_GEO_PRIOR_CHECKPOINT", str(DEFAULT_GEO_PRIOR_CHECKPOINT_PATH))
        )
    )
    geo_prior_selected_configuration_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "S3_DEMO_GEO_PRIOR_CONFIG",
                str(DEFAULT_GEO_PRIOR_SELECTED_CONFIGURATION_PATH),
            )
        )
    )


def load_demo_config() -> DemoConfig:
    return DemoConfig()
