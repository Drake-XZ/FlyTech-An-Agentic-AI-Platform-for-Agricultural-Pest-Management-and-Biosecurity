"""``s3-ecological`` command-line entry point (EarlyDesign.md section 23.1:
"one deterministic library entry point and one fixture-backed CLI command").

Two subcommands:

- ``demo --fixture <name>``: runs one of the six golden acceptance cases
  (see ``s3_ecological.fixtures.golden_loader``) end to end with no
  configuration and prints the resulting ``AssessmentResult`` as JSON.
- ``assess --input <path> --output <path|->``: runs an arbitrary
  ``ObservationRequest`` JSON file through the deterministic pipeline using
  the default (fixture-backed) providers, optionally layering TOML
  configuration files with ``--config``.

Both subcommands are offline: no network access and no LLM call is made.
``analysis_id``/``generated_at`` are generated here, at the process
boundary, and nowhere inside the deterministic pipeline itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from s3_ecological.fixtures.golden_loader import GOLDEN_CASE_NAMES, load_golden_case
from s3_ecological.orchestration.pipeline import run_assessment
from s3_ecological.priors.geo_nearest_distance import NearestDistanceGeoPriorModel
from s3_ecological.providers.factory import build_occurrence_provider, build_taxonomy_provider
from s3_ecological.risk.policy import DeterministicRiskPolicy
from s3_ecological.schemas.request import ObservationRequest
from s3_ecological.settings import S3Settings
from s3_ecological.suitability.null_model import NullSuitabilityModel


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        return _run_demo(args.fixture)
    if args.command == "assess":
        return _run_assess(args.input, args.output, args.config)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="s3-ecological")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser(
        "demo", help="run one golden acceptance fixture with no configuration"
    )
    demo_parser.add_argument(
        "--fixture", choices=GOLDEN_CASE_NAMES, default="supported_same_location"
    )

    assess_parser = subparsers.add_parser(
        "assess", help="run an ObservationRequest JSON file through the deterministic pipeline"
    )
    assess_parser.add_argument(
        "--input", required=True, help="path to an ObservationRequest JSON file"
    )
    assess_parser.add_argument(
        "--output", default="-", help="output path, or '-' for stdout (default)"
    )
    assess_parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="path to a TOML configuration file; may be given more than once",
    )

    return parser


def _run_demo(fixture_name: str) -> int:
    case = load_golden_case(fixture_name)
    result = run_assessment(
        case.request,
        settings=case.settings,
        taxonomy_provider=case.taxonomy_provider,
        occurrence_provider=case.occurrence_provider,
        geo_prior_model=case.geo_prior_model,
        suitability_model=case.suitability_model,
        risk_policy=case.risk_policy,
        analysis_id=f"demo-{fixture_name}-{uuid.uuid4()}",
        generated_at=datetime.now(UTC),
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0


def _run_assess(input_path: str, output_path: str, config_paths: list[str]) -> int:
    request = ObservationRequest.model_validate_json(Path(input_path).read_text(encoding="utf-8"))
    settings = S3Settings.load(config_paths=config_paths or None)
    occurrence_provider = build_occurrence_provider(settings)

    result = run_assessment(
        request,
        settings=settings,
        taxonomy_provider=build_taxonomy_provider(settings),
        occurrence_provider=occurrence_provider,
        geo_prior_model=NearestDistanceGeoPriorModel(occurrence_provider, settings),
        suitability_model=NullSuitabilityModel(),
        risk_policy=DeterministicRiskPolicy(),
        analysis_id=str(uuid.uuid4()),
        generated_at=datetime.now(UTC),
    )
    payload = json.dumps(result.model_dump(mode="json"), indent=2)

    if output_path == "-":
        print(payload)
    else:
        Path(output_path).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
