"""Tests for the frozen M2-C reference values (DesignSuggestionLog.md
"M2-D robustness, ablation, and generalisation audit"). These guard M2-C's
primary confirmatory result against ever being silently edited by later
milestone work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from s3_ecological.experiments import m2c_reference

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_m2c_report_hash_matches_frozen_constant():
    m2c_reference.verify_m2c_report_hash(REPO_ROOT)


def test_verify_m2c_report_hash_rejects_a_changed_report(tmp_path: Path):
    fake_root = tmp_path
    docs_dir = fake_root / "docs"
    docs_dir.mkdir()
    (docs_dir / "m2c_evaluation_report.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(m2c_reference.M2CReferenceError, match="changed"):
        m2c_reference.verify_m2c_report_hash(fake_root)


def test_verify_m2c_report_hash_rejects_a_missing_report(tmp_path: Path):
    with pytest.raises(m2c_reference.M2CReferenceError, match="missing"):
        m2c_reference.verify_m2c_report_hash(tmp_path)


def test_verify_m2c_local_artifacts_is_a_noop_when_absent(tmp_path: Path):
    assert m2c_reference.verify_m2c_local_artifacts(tmp_path) == []


def test_verify_m2c_local_artifacts_checks_present_files_when_available():
    """Best-effort: only asserts something when the real gitignored M2-C
    local artifacts happen to be present on this machine; otherwise this is
    equivalent to the no-op case above and always passes."""
    verified = m2c_reference.verify_m2c_local_artifacts(REPO_ROOT)
    assert isinstance(verified, list)
