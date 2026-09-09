"""Torch-free input validation for the local research demo.

Every error message is written in careful, non-decisive language. This demo
must never phrase a validation failure (or anything else) in terms of
"absence", "confirmed incursion", "quarantine cleared", or similar
biosecurity-decision language - it is a research visualization only.
"""

from __future__ import annotations

from datetime import datetime

from .demo_config import ALLOWED_IMAGE_CONTENT_TYPES, MAX_UPLOAD_BYTES


class DemoValidationError(ValueError):
    """Raised for any user-input problem; message is always safe to display."""


def validate_coordinates(latitude: float | None, longitude: float | None) -> None:
    if latitude is None and longitude is None:
        return
    if latitude is None or longitude is None:
        raise DemoValidationError(
            "Please provide both latitude and longitude, or leave both blank."
        )
    if not (-90.0 <= latitude <= 90.0):
        raise DemoValidationError("Latitude must be between -90 and 90 degrees.")
    if not (-180.0 <= longitude <= 180.0):
        raise DemoValidationError("Longitude must be between -180 and 180 degrees.")


def validate_observed_at(raw_value: str | None) -> datetime | None:
    """Parse an optional observation date/time. Never fabricates a value."""
    if raw_value is None or not raw_value.strip():
        return None
    text = raw_value.strip()
    for candidate in (text, text + "T00:00:00"):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    raise DemoValidationError(
        "The observation date could not be understood. Use a format like "
        "2024-05-01 or 2024-05-01T09:30:00, or leave it blank."
    )


def _looks_like_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def _looks_like_jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff")


def _looks_like_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"


def validate_image_bytes(data: bytes, content_type: str | None) -> None:
    if not data:
        raise DemoValidationError("The uploaded image appears to be empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DemoValidationError(
            f"The uploaded image is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
        )
    if content_type is not None and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise DemoValidationError(
            "Please upload a PNG, JPEG, or WebP image."
        )
    if not (_looks_like_png(data) or _looks_like_jpeg(data) or _looks_like_webp(data)):
        raise DemoValidationError(
            "The uploaded file does not look like a PNG, JPEG, or WebP image."
        )
