"""Versioned S3 runtime configuration (EarlyDesign.md section 16.2).

Precedence, highest to lowest:

1. explicit constructor/CLI keyword arguments (``overrides``);
2. environment variables (``S3_<FIELD_NAME_UPPER>``);
3. the selected TOML configuration file(s);
4. Prototype Implementation Profile v0.1 defaults (the field defaults below).

Unknown fields are rejected (``extra="forbid"``) so a configuration typo
cannot silently change ecological behavior. Nothing in this module ever
stores a secret value - live-provider credentials are named by environment
variable (see ``gbif_api_key_env_var`` / ``ala_api_key_env_var``) and read
from ``os.environ`` only inside the live-provider adapter at call time.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Fields that map to boolean environment values; every other field is parsed
# with its annotated type via a best-effort constructor call.
_BOOL_FIELDS = frozenset({"llm_enabled", "incursion_rule_enabled"})


class S3Settings(BaseModel):
    """Validated, typed runtime configuration for the S3 ecological core."""

    model_config = ConfigDict(extra="forbid")

    # --- Versioning -----------------------------------------------------
    configuration_version: str = "prototype-v0.1"
    profile_version: str = "0.1"

    # --- Deterministic geographic baseline (Profile v0.1, frozen) -------
    geo_distance_scale_km: float = 500.0
    max_coordinate_uncertainty_m: float = 50000.0
    min_occurrences_for_ood: int = 3
    geo_supported_min: float = 0.5
    geo_ood_max: float = 0.1
    probability_sum_tolerance: float = 0.000001

    # --- Soft fusion (Profile v0.1, frozen) ------------------------------
    fusion_epsilon: float = 0.000001
    fusion_weight_geo: float = 1.0
    fusion_weight_environment: float = 0.0
    incursion_rule_enabled: bool = False

    # --- Occurrence cleaning ---------------------------------------------
    known_centroid_coordinates: list[tuple[float, float]] = Field(default_factory=list)

    # --- Provider selection (EarlyDesign.md section 6.4) -----------------
    # "fixture" and "in_memory" are fully implemented. "local_snapshot" reads
    # a JSON snapshot file. "live_gbif" / "live_ala" are deferred adapters
    # that always return provider_not_configured until credentials and an
    # approved endpoint are supplied - selecting them never crashes startup.
    occurrence_provider: str = "fixture"
    occurrence_snapshot_path: str | None = None
    taxonomy_provider: str = "fixture"
    # Required only when taxonomy_provider == "local_snapshot" - points at a
    # taxonomy.json bundle produced by `import-occurrences` (Milestone 1.5).
    taxonomy_snapshot_path: str | None = None

    # --- Deferred live-provider configuration (names only, never secrets) -
    gbif_base_url: str | None = None
    gbif_api_key_env_var: str | None = None
    ala_base_url: str | None = None
    ala_api_key_env_var: str | None = None

    # --- Caching, timeouts, retries ---------------------------------------
    cache_ttl_seconds: int = 3600
    request_timeout_seconds: float = 5.0
    max_retries: int = 2

    # --- Privacy ------------------------------------------------------------
    # Number of decimal degrees to round coordinates to before they leave S3
    # in logs; None disables coarsening. ~0.01 deg is ~1.1 km at the equator.
    coordinate_coarsening_decimals: int | None = None

    # --- Optional LLM boundary (EarlyDesign.md section 16.1) ---------------
    llm_enabled: bool = False
    llm_provider: str = "mock"
    llm_model: str | None = None

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"

    @classmethod
    def load(
        cls,
        config_paths: Sequence[str | Path] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> S3Settings:
        """Build settings by merging TOML file(s), environment, then overrides.

        ``config_paths`` may list one or more TOML files (e.g. the
        ``sources.example.toml`` and ``thresholds.example.toml`` templates in
        ``config/``); later files take precedence over earlier ones. Omitting
        it keeps the prototype in its default, file-free demonstration mode.
        """
        merged: dict[str, Any] = {}
        for path in config_paths or []:
            with open(path, "rb") as handle:
                merged.update(tomllib.load(handle))

        for field_name in cls.model_fields:
            env_name = f"S3_{field_name.upper()}"
            if env_name in os.environ:
                merged[field_name] = _coerce_env_value(field_name, os.environ[env_name])

        merged.update(overrides or {})
        return cls(**merged)


def _coerce_env_value(field_name: str, raw_value: str) -> Any:
    """Coerce a raw environment-variable string into a JSON-ish scalar.

    Only booleans and numbers need coercion; every other field stays a plain
    string, which Pydantic then validates against the field's declared type.
    """
    if field_name in _BOOL_FIELDS:
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return raw_value
