"""Frozen M2-C reference values (DesignSuggestionLog.md "M2-D robustness,
ablation, and generalisation audit").

M2-C's single locked spatial-test evaluation (grid 1.0 degrees, seed 42,
frozen ``filts256_dateTrue`` recipe) is the project's primary confirmatory
result. M2-D is an independently labelled robustness study; it must never
overwrite, re-tune, or supersede this result. The constants and helpers
below let any M2-D code or test re-verify that the M2-C artifacts are still
exactly what they were when M2-C was reported, without re-deriving anything
from scratch.

``M2C_REPORT_SHA256`` is checked against the *committed* doc, so it can be
verified on any machine, in any environment, with no local data. The
checkpoint / spatial-split-identity / S1-bundle hashes below refer to
real-data artifacts that live only under gitignored ``data/local/`` and are
therefore only checked when present locally.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

M2C_REPORT_RELATIVE_PATH = "docs/m2c_evaluation_report.md"
M2C_REPORT_SHA256 = "ff77b67dec947070c95987df863d663bea60f288d2fdd25ec48208e61f623263"

M2C_FROZEN_CONFIG_ID = "filts256_dateTrue"
M2C_CHECKPOINT_SHA256 = "952d81008184f18888d22de54b3557f7c5429b35ed28782aabd6914707e61086"
M2C_SPATIAL_SPLIT_IDENTITY = "59014aec1786e0cb7d4c2d9db0a091fa8c0a7a797c918185516d41d81f670183"
M2C_S1_BUNDLE_MANIFEST_SHA256 = "017014a2fe218249739908130d93343ca0b16c8100120eba2c1a4088332ad289"

M2C_SELECTED_CONFIGURATION_PATH = "data/local/m2/geo_prior/training/selected_configuration.json"
M2C_LOCKED_TEST_REPORT_PATH = "data/local/m2/geo_prior/evaluation/m2c_locked_test_report.json"

# Primary result values as reported in docs/m2c_evaluation_report.md. These
# are the confirmatory numbers M2-D must never be used to replace.
M2C_PRIMARY_RESULT: dict[str, dict[str, float | int]] = {
    "s1_only": {
        "accuracy": 0.8991507430997877,
        "macro_f1": 0.792731572983687,
        "observation_count": 942,
    },
    "geo_only": {
        "accuracy": 0.8996763754045307,
        "macro_f1": 0.8782186279356277,
        "observation_count": 927,
    },
    "fusion": {
        "accuracy": 0.9501061571125266,
        "macro_f1": 0.9252195090362658,
        "observation_count": 942,
    },
}
M2C_GEO_ONLY_EXCLUDED_MISSING_DATE = 15


class M2CReferenceError(RuntimeError):
    """Raised when a live M2-C artifact no longer matches its frozen value."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_m2c_report_hash(repo_root: Path) -> None:
    """Always runnable: the M2-C report is a committed file, present on
    every checkout. Raises if it was ever edited after being frozen."""
    report_path = repo_root / M2C_REPORT_RELATIVE_PATH
    if not report_path.is_file():
        raise M2CReferenceError(f"M2-C reference report is missing: {report_path}")
    actual = _sha256_file(report_path)
    if actual != M2C_REPORT_SHA256:
        raise M2CReferenceError(
            "M2-C evaluation report has changed since it was frozen for M2-D "
            f"(expected {M2C_REPORT_SHA256}, got {actual}); M2-C's primary "
            "result must never be edited by a later milestone."
        )


def verify_m2c_local_artifacts(repo_root: Path) -> list[str]:
    """Best-effort check of the gitignored, real-data M2-C artifacts. Only
    checks files that are actually present locally (they are absent on a
    fresh checkout or CI machine without the real M2 data) and returns the
    list of relative paths it actually verified. Raises if a present
    artifact's recorded value no longer matches its frozen constant."""
    verified: list[str] = []

    selected_configuration_path = repo_root / M2C_SELECTED_CONFIGURATION_PATH
    if selected_configuration_path.is_file():
        payload: dict[str, Any] = json.loads(
            selected_configuration_path.read_text(encoding="utf-8")
        )
        if payload.get("frozen_config_id") != M2C_FROZEN_CONFIG_ID:
            raise M2CReferenceError(
                "M2-C selected_configuration.json's frozen_config_id has changed"
            )
        if payload.get("checkpoint_sha256") != M2C_CHECKPOINT_SHA256:
            raise M2CReferenceError(
                "M2-C selected_configuration.json's checkpoint_sha256 has changed"
            )
        if payload.get("spatial_split_identity") != M2C_SPATIAL_SPLIT_IDENTITY:
            raise M2CReferenceError(
                "M2-C selected_configuration.json's spatial_split_identity has changed"
            )
        verified.append(M2C_SELECTED_CONFIGURATION_PATH)

    locked_test_report_path = repo_root / M2C_LOCKED_TEST_REPORT_PATH
    if locked_test_report_path.is_file():
        report: dict[str, Any] = json.loads(
            locked_test_report_path.read_text(encoding="utf-8")
        )
        if report.get("spatial_split_identity") != M2C_SPATIAL_SPLIT_IDENTITY:
            raise M2CReferenceError(
                "M2-C locked test report's spatial_split_identity has changed"
            )
        if report.get("s1_bundle_manifest_sha256") != M2C_S1_BUNDLE_MANIFEST_SHA256:
            raise M2CReferenceError(
                "M2-C locked test report's s1_bundle_manifest_sha256 has changed"
            )
        for method, expected in M2C_PRIMARY_RESULT.items():
            actual_block = report.get(method) or {}
            for field, expected_value in expected.items():
                if actual_block.get(field) != expected_value:
                    raise M2CReferenceError(
                        f"M2-C locked test report's {method}.{field} has changed "
                        f"(expected {expected_value}, got {actual_block.get(field)})"
                    )
        if report.get("geo_only_excluded_missing_date") != M2C_GEO_ONLY_EXCLUDED_MISSING_DATE:
            raise M2CReferenceError(
                "M2-C locked test report's geo_only_excluded_missing_date has changed"
            )
        verified.append(M2C_LOCKED_TEST_REPORT_PATH)

    return verified
