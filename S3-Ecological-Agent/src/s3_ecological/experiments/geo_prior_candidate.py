"""Read-only extraction of an already-trained geo_prior candidate from an
existing ``candidate_table.json`` (DesignSuggestionLog.md "M2-D robustness,
ablation, and generalisation audit").

M2-D's reference-partition location-only ablation compares M2-C's frozen
``filts256_dateTrue`` result against the ``filts256_dateFalse`` candidate
that M2-C *already trained* as part of its own 4-config grid search on the
same reference train split and seed. That checkpoint must never be
retrained: this module only reads the existing ``candidate_table.json`` and
re-verifies the chosen candidate's checkpoint hash, emitting a
``selected_configuration.json``-shaped payload usable directly by
``scripts/evaluate_geo_prior_m2c.py --selected-configuration``.

Torch-free: this module never imports torch and never touches checkpoint
contents, only the checkpoint file's bytes (for hashing).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODEL_NAME = "geo_prior_fcnet"
MODEL_VERSION = "flytech-reproduced-geo-prior-fcnet-v0.1"
UPSTREAM_REPOSITORY = "https://github.com/macaodha/geo_prior"
UPSTREAM_COMMIT = "257dc7e30f3cc6bf02fbec55ee878724d077fe61"


class GeoPriorCandidateError(RuntimeError):
    """Raised when a requested candidate is missing or its checkpoint hash
    no longer matches the value recorded at training time."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_candidate(
    candidate_table_path: Path,
    config_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Read an already-trained candidate out of ``candidate_table.json`` and
    re-verify its checkpoint hash, without retraining anything.

    ``repo_root`` resolves a relative ``checkpoint_path`` recorded in the
    candidate table (defaults to the current working directory, matching how
    ``train_geo_prior.py`` records paths when run from the repo root).
    """
    repo_root = repo_root if repo_root is not None else Path.cwd()
    candidate_table = json.loads(candidate_table_path.read_text(encoding="utf-8"))

    candidates = candidate_table.get("candidates", [])
    matches = [candidate for candidate in candidates if candidate.get("config_id") == config_id]
    if not matches:
        known_ids = [candidate.get("config_id") for candidate in candidates]
        raise GeoPriorCandidateError(
            f"config_id {config_id!r} not found in {candidate_table_path} "
            f"(known ids: {known_ids})"
        )
    candidate = matches[0]

    checkpoint_path = Path(candidate["checkpoint_path"])
    resolved_checkpoint_path = (
        checkpoint_path if checkpoint_path.is_absolute() else repo_root / checkpoint_path
    )
    if not resolved_checkpoint_path.is_file():
        raise GeoPriorCandidateError(
            f"checkpoint for config_id {config_id!r} is missing on disk: "
            f"{resolved_checkpoint_path}"
        )
    actual_checkpoint_sha256 = _sha256_file(resolved_checkpoint_path)
    if actual_checkpoint_sha256 != candidate["checkpoint_sha256"]:
        raise GeoPriorCandidateError(
            f"checkpoint for config_id {config_id!r} has changed since training "
            f"(expected {candidate['checkpoint_sha256']}, got {actual_checkpoint_sha256}); "
            "the M2-D ablation reuses this checkpoint read-only and must not proceed "
            "against a modified file."
        )

    dataset_report = candidate_table.get("dataset_report") or {}
    selected_configuration: dict[str, Any] = {
        "schema_version": "1.0.0",
        "identity": (
            "FlyTech reproduced geo_prior FCNet; not the original Mac Aodha et al. checkpoint "
            "(none is published upstream). Extracted read-only from an existing "
            "candidate_table.json for the M2-D location-only ablation; not retrained."
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": UPSTREAM_COMMIT,
        "frozen_config": candidate["config"],
        "frozen_config_id": candidate["config_id"],
        "checkpoint_path": candidate["checkpoint_path"],
        "checkpoint_sha256": candidate["checkpoint_sha256"],
        "selection_rationale": (
            "Not a validation-macro-F1 selection: this candidate was extracted for the M2-D "
            "location-only ablation because it is M2-C's own already-trained "
            "use_date_feats=False counterpart to the frozen filts256_dateTrue configuration."
        ),
        "validation_result": {
            "best_epoch": candidate.get("best_epoch"),
            "best_validation_macro_f1": candidate.get("best_validation_macro_f1"),
            "best_validation_accuracy": candidate.get("best_validation_accuracy"),
            "train_count": candidate.get("train_count"),
            "validation_count": candidate.get("validation_count"),
        },
        "seed": candidate_table.get("seed"),
        "train_manifest_sha256": candidate_table.get("train_manifest_sha256"),
        "validation_manifest_sha256": candidate_table.get("validation_manifest_sha256"),
        "spatial_split_identity": dataset_report.get("spatial_split_identity"),
    }
    return selected_configuration
