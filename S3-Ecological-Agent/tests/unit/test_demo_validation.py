"""Unit tests for the local demo's torch-free input validation."""

from __future__ import annotations

import pytest

from s3_ecological.api.validation import (
    DemoValidationError,
    validate_coordinates,
    validate_image_bytes,
    validate_observed_at,
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_JPEG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 16
_WEBP_MAGIC = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8


def test_validate_coordinates_accepts_both_none():
    validate_coordinates(None, None)


def test_validate_coordinates_rejects_one_missing():
    with pytest.raises(DemoValidationError):
        validate_coordinates(1.0, None)
    with pytest.raises(DemoValidationError):
        validate_coordinates(None, 1.0)


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
def test_validate_coordinates_rejects_out_of_range(lat, lon):
    with pytest.raises(DemoValidationError):
        validate_coordinates(lat, lon)


def test_validate_coordinates_accepts_valid_range():
    validate_coordinates(-90.0, -180.0)
    validate_coordinates(90.0, 180.0)
    validate_coordinates(12.3, 45.6)


def test_validate_observed_at_none_for_blank_input():
    assert validate_observed_at(None) is None
    assert validate_observed_at("") is None
    assert validate_observed_at("   ") is None


def test_validate_observed_at_never_fabricates_a_date():
    # A date-only string parses to midnight of that date rather than "now" -
    # confirming no fabrication happens for blank input above is the key
    # invariant; here we confirm a partial date is parsed as given.
    parsed = validate_observed_at("2024-05-01")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2024, 5, 1)


def test_validate_observed_at_accepts_full_iso8601():
    parsed = validate_observed_at("2024-05-01T09:30:00")
    assert parsed is not None
    assert parsed.hour == 9 and parsed.minute == 30


def test_validate_observed_at_rejects_unparseable_input():
    with pytest.raises(DemoValidationError):
        validate_observed_at("not a date")


def test_validate_image_bytes_rejects_empty():
    with pytest.raises(DemoValidationError):
        validate_image_bytes(b"", "image/png")


def test_validate_image_bytes_rejects_oversized():
    from s3_ecological.api.demo_config import MAX_UPLOAD_BYTES

    oversized = _PNG_MAGIC + b"\x00" * MAX_UPLOAD_BYTES
    with pytest.raises(DemoValidationError):
        validate_image_bytes(oversized, "image/png")


def test_validate_image_bytes_rejects_disallowed_content_type():
    with pytest.raises(DemoValidationError):
        validate_image_bytes(_PNG_MAGIC, "application/octet-stream")


def test_validate_image_bytes_rejects_non_image_payload():
    with pytest.raises(DemoValidationError):
        validate_image_bytes(b"not an image at all", "image/png")


@pytest.mark.parametrize("data", [_PNG_MAGIC, _JPEG_MAGIC, _WEBP_MAGIC])
def test_validate_image_bytes_accepts_supported_formats(data):
    validate_image_bytes(data, None)


def test_validation_error_messages_avoid_unsafe_phrases():
    unsafe_phrases = ["absence", "confirmed incursion", "quarantine cleared"]
    checks = [
        lambda: validate_coordinates(91.0, 0.0),
        lambda: validate_coordinates(1.0, None),
        lambda: validate_observed_at("not a date"),
        lambda: validate_image_bytes(b"", "image/png"),
        lambda: validate_image_bytes(b"not an image", "image/png"),
    ]
    for check in checks:
        with pytest.raises(DemoValidationError) as excinfo:
            check()
        message = str(excinfo.value).lower()
        for phrase in unsafe_phrases:
            assert phrase not in message
