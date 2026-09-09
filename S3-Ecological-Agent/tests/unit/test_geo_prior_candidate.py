"""Tests for read-only geo_prior candidate extraction from an existing
candidate_table.json (DesignSuggestionLog.md "M2-D robustness, ablation, and
generalisation audit"). Torch-free - no model is trained or loaded here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from s3_ecological.experiments.geo_prior_candidate import (
    GeoPriorCandidateError,
    extract_candidate,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_candidate_table(tmp_path: Path) -> tuple[Path, str]:
    checkpoint_bytes = b"fake-checkpoint-bytes"
    checkpoint_dir = tmp_path / "filts256_dateFalse"
    checkpoint_dir.mkdir()
    checkpoint_path = checkpoint_dir / "checkpoint.pt"
    checkpoint_path.write_bytes(checkpoint_bytes)
    checkpoint_sha256 = _sha256_bytes(checkpoint_bytes)

    candidate_table = {
        "schema_version": "1.0.0",
        "seed": 42,
        "train_manifest_sha256": "train-sha",
        "validation_manifest_sha256": "validation-sha",
        "dataset_report": {"spatial_split_identity": "split-id"},
        "selection_rule": "highest best_validation_macro_f1",
        "candidates": [
            {
                "config": {"num_filts": 256, "use_date_feats": False},
                "config_id": "filts256_dateFalse",
                "checkpoint_path": str(checkpoint_path),
                "checkpoint_sha256": checkpoint_sha256,
                "best_epoch": 65,
                "best_validation_macro_f1": 0.8010,
                "best_validation_accuracy": 0.8936,
                "train_count": 11436,
                "validation_count": 3242,
            },
            {
                "config": {"num_filts": 256, "use_date_feats": True},
                "config_id": "filts256_dateTrue",
                "checkpoint_path": str(tmp_path / "filts256_dateTrue" / "checkpoint.pt"),
                "checkpoint_sha256": "unused-in-this-test",
                "best_epoch": 65,
                "best_validation_macro_f1": 0.8041,
                "best_validation_accuracy": 0.9054,
                "train_count": 11403,
                "validation_count": 3215,
            },
        ],
        "selected_config_id": "filts256_dateTrue",
    }
    candidate_table_path = tmp_path / "candidate_table.json"
    candidate_table_path.write_text(json.dumps(candidate_table), encoding="utf-8")
    return candidate_table_path, checkpoint_sha256


def test_extract_candidate_returns_selected_configuration_shaped_payload(tmp_path: Path):
    candidate_table_path, checkpoint_sha256 = _write_candidate_table(tmp_path)
    result = extract_candidate(candidate_table_path, "filts256_dateFalse", repo_root=tmp_path)

    assert result["frozen_config_id"] == "filts256_dateFalse"
    assert result["frozen_config"] == {"num_filts": 256, "use_date_feats": False}
    assert result["checkpoint_sha256"] == checkpoint_sha256
    assert result["seed"] == 42
    assert result["spatial_split_identity"] == "split-id"
    assert result["validation_result"]["best_epoch"] == 65
    assert result["validation_result"]["best_validation_macro_f1"] == pytest.approx(0.8010)


def test_extract_candidate_raises_on_unknown_config_id(tmp_path: Path):
    candidate_table_path, _ = _write_candidate_table(tmp_path)
    with pytest.raises(GeoPriorCandidateError, match="not found"):
        extract_candidate(candidate_table_path, "does_not_exist", repo_root=tmp_path)


def test_extract_candidate_raises_when_checkpoint_hash_no_longer_matches(tmp_path: Path):
    candidate_table_path, _ = _write_candidate_table(tmp_path)
    tampered_checkpoint = tmp_path / "filts256_dateFalse" / "checkpoint.pt"
    tampered_checkpoint.write_bytes(b"tampered-bytes")
    with pytest.raises(GeoPriorCandidateError, match="has changed since training"):
        extract_candidate(candidate_table_path, "filts256_dateFalse", repo_root=tmp_path)


def test_extract_candidate_raises_when_checkpoint_is_missing(tmp_path: Path):
    candidate_table_path, _ = _write_candidate_table(tmp_path)
    (tmp_path / "filts256_dateFalse" / "checkpoint.pt").unlink()
    with pytest.raises(GeoPriorCandidateError, match="missing on disk"):
        extract_candidate(candidate_table_path, "filts256_dateFalse", repo_root=tmp_path)
