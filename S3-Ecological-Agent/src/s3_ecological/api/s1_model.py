"""Lazy-loaded TF4 EfficientNet-B2 visual inference for the local demo.

Torch, torchvision, and Pillow are imported lazily inside functions so that
importing this module (and the rest of ``s3_ecological.api``) never forces
those optional dependencies onto users of the deterministic core. This
module is only exercised when the demo server actually receives an image.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .demo_config import TF4_CLASS_NAMES, TF4_MODEL_VERSION, DemoConfig

if TYPE_CHECKING:
    import torch

_lock = threading.Lock()
_cache: dict[str, Any] = {}


class ModelUnavailableError(RuntimeError):
    """Raised when the TF4 checkpoint is missing, unreadable, or unusable."""


@dataclass(frozen=True)
class VisualInferenceResult:
    probabilities: dict[str, float]
    model_version: str


def _load_model(config: DemoConfig) -> Any:
    checkpoint_path = config.tf4_checkpoint_path
    if not checkpoint_path.exists():
        raise ModelUnavailableError(
            "The visual model checkpoint is not available on this machine. "
            "This demo requires a local TF4 checkpoint under data/local/m2/s1/ "
            "to run visual inference."
        )

    import torch
    from torch import nn
    from torchvision.models import efficientnet_b2

    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # noqa: BLE001 - surfaced as a safe, generic message
        raise ModelUnavailableError(
            "The visual model checkpoint could not be loaded."
        ) from exc

    class_names = checkpoint.get("class_names")
    if list(class_names or []) != list(TF4_CLASS_NAMES):
        raise ModelUnavailableError(
            "The visual model checkpoint's class order does not match the "
            "expected four-genus configuration for this demo."
        )

    model = efficientnet_b2()
    # nn.Module.__getattr__'s generic stub return type obscures that this is
    # always an int for a real Linear layer.
    in_features = cast(int, model.classifier[-1].in_features)
    model.classifier[-1] = nn.Linear(in_features, len(TF4_CLASS_NAMES))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


def _get_model(config: DemoConfig) -> Any:
    key = str(config.tf4_checkpoint_path)
    with _lock:
        model = _cache.get(key)
        if model is None:
            model = _load_model(config)
            _cache[key] = model
        return model


def infer(image_bytes: bytes, *, config: DemoConfig) -> VisualInferenceResult:
    model = _get_model(config)

    import torch
    from PIL import Image, UnidentifiedImageError
    from torchvision import transforms

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ModelUnavailableError(
            "The uploaded image could not be decoded for visual inference."
        ) from exc

    transform = transforms.Compose(
        [
            transforms.Resize((260, 260)),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )
    # Compose's overload stub resolves to the PIL-Image overload here even
    # though ToTensor/Normalize make the actual runtime result a Tensor.
    tensor = cast("torch.Tensor", transform(image)).unsqueeze(0)

    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0).tolist()

    return VisualInferenceResult(
        probabilities=dict(zip(TF4_CLASS_NAMES, probabilities, strict=True)),
        model_version=TF4_MODEL_VERSION,
    )
