"""Extract an already-trained geo_prior candidate from an existing
``candidate_table.json`` and write it as a ``selected_configuration.json``
file, without retraining anything.

Used by the M2-D robustness audit's reference-partition location-only
ablation: M2-C already trained ``filts256_dateFalse`` on the reference
train split as part of its own 4-config grid search. This script reads that
result read-only, re-verifies its checkpoint's SHA-256, and writes it in the
same shape ``scripts/evaluate_geo_prior_m2c.py --selected-configuration``
expects.

Torch-free: run via the main venv, not the dedicated S1/torch venv.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from s3_ecological.experiments.geo_prior_candidate import extract_candidate


def extract(args: argparse.Namespace) -> dict:
    selected_configuration = extract_candidate(
        args.candidate_table,
        args.config_id,
        repo_root=Path.cwd(),
    )
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "selected_configuration.json"
    output_path.write_text(
        json.dumps(selected_configuration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"selected_configuration": str(output_path)}, sort_keys=True))
    return selected_configuration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-table",
        type=Path,
        default=Path("data/local/m2/geo_prior/training/candidate_table.json"),
    )
    parser.add_argument("--config-id", type=str, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    extract(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
