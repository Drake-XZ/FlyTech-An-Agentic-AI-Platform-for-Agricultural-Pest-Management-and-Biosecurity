"""``s3-ecological`` command-line entry point (EarlyDesign.md section 23.1:
"one deterministic library entry point and one fixture-backed CLI command").

Three subcommands:

- ``demo --fixture <name>``: runs one of the six golden acceptance cases
  (see ``s3_ecological.fixtures.golden_loader``) end to end with no
  configuration and prints the resulting ``AssessmentResult`` as JSON.
- ``assess --input <path> --output <path|->``: runs an arbitrary
  ``ObservationRequest`` JSON file through the deterministic pipeline using
  the default (fixture-backed) providers, optionally layering TOML
  configuration files with ``--config``.
- ``import-occurrences``: converts a locally-held GBIF/ALA/generic Darwin
  Core export (or a canonical JSON snapshot) into a local occurrence +
  taxonomy snapshot bundle that ``assess`` can then query with
  ``occurrence_provider``/``taxonomy_provider = "local_snapshot"``
  (Milestone 1.5, EarlyDesign.md "offline occurrence snapshot ingestion").
- ``prepare-geo-experiment``: builds a deterministic spatial train/val/test
  split and a readiness report from an already-imported Milestone 1.5
  bundle. This is a pre-Milestone 2 preparation gate (EarlyDesign.md
  section 11.4 and 22) - it never trains a model, calibrates a fusion
  weight or risk threshold, or implements S1.

All subcommands are offline: no network access and no LLM call is made.
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

from s3_ecological.experiments.prepare import GeoExperimentFatalError, prepare_geo_experiment
from s3_ecological.experiments.readiness import (
    REASON_EMPTY_REQUIRED_SPLIT,
    REASON_MISSING_TARGET_TAXON_COVERAGE,
    REASON_NO_USABLE_OCCURRENCE_RECORDS,
    REASON_SINGLE_BLOCK_ONLY,
)
from s3_ecological.fixtures.golden_loader import GOLDEN_CASE_NAMES, load_golden_case
from s3_ecological.ingestion.occurrence_snapshot import (
    ImportFatalError,
    import_occurrence_snapshot,
)
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
    if args.command == "import-occurrences":
        return _run_import_occurrences(args)
    if args.command == "prepare-geo-experiment":
        return _run_prepare_geo_experiment(args)

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

    import_parser = subparsers.add_parser(
        "import-occurrences",
        help=(
            "convert an offline GBIF/ALA/generic Darwin Core export (or a canonical "
            "JSON snapshot) into a local occurrence + taxonomy snapshot bundle"
        ),
    )
    import_parser.add_argument(
        "--input",
        required=True,
        help="path to the source .csv/.tsv/occurrence.txt file, or a canonical .json snapshot",
    )
    import_parser.add_argument(
        "--source", required=True, choices=["gbif", "ala", "generic_dwc", "canonical"]
    )
    import_parser.add_argument("--dataset-id", required=True)
    import_parser.add_argument(
        "--retrieved-at", required=True, help="ISO-8601 timestamp with a timezone offset or 'Z'"
    )
    import_parser.add_argument("--dataset-license", required=True)
    import_parser.add_argument("--citation", required=True)
    import_parser.add_argument(
        "--query-parameters-json",
        default=None,
        help="path to a JSON file containing a single JSON object (default: {})",
    )
    import_parser.add_argument("--output-dir", required=True)
    import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing occurrences.json/taxonomy.json/import-report.json",
    )

    prepare_parser = subparsers.add_parser(
        "prepare-geo-experiment",
        help=(
            "build a deterministic spatial train/val/test split and readiness report "
            "from an already-imported Milestone 1.5 bundle (pre-Milestone 2 gate)"
        ),
    )
    prepare_parser.add_argument(
        "--config", required=True, help="path to a geo-experiment TOML config"
    )
    prepare_parser.add_argument("--output-dir", required=True)
    prepare_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing spatial-split-manifest.json/readiness-report.json",
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


def _run_import_occurrences(args: argparse.Namespace) -> int:
    try:
        report = import_occurrence_snapshot(
            input_path=args.input,
            source=args.source,
            dataset_id=args.dataset_id,
            retrieved_at=args.retrieved_at,
            dataset_license=args.dataset_license,
            citation=args.citation,
            query_parameters_path=args.query_parameters_json,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
        )
    except ImportFatalError as exc:
        print(f"import-occurrences: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 2 if report.rejected_record_count else 0


_DATA_QUALITY_REASON_CODES = frozenset(
    {
        REASON_NO_USABLE_OCCURRENCE_RECORDS,
        REASON_MISSING_TARGET_TAXON_COVERAGE,
        REASON_SINGLE_BLOCK_ONLY,
        REASON_EMPTY_REQUIRED_SPLIT,
    }
)


def _run_prepare_geo_experiment(args: argparse.Namespace) -> int:
    try:
        report = prepare_geo_experiment(
            config_path=args.config, output_dir=args.output_dir, overwrite=args.overwrite
        )
    except GeoExperimentFatalError as exc:
        print(f"prepare-geo-experiment: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.model_dump(mode="json"), indent=2))
    if _DATA_QUALITY_REASON_CODES.intersection(report.reason_codes):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
