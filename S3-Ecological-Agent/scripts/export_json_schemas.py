"""Export JSON Schemas for every public S3 contract model.

EarlyDesign.md section 23.1 (Definition of Done) requires "validated I/O
models with exportable JSON Schemas". This script is the verification step
for that requirement: it calls ``model_json_schema()`` on each public model
and writes the result to ``json_schemas/`` so a schema failure (an
un-exportable model, a broken ``$ref``) is caught by running this script,
not asserted without evidence.

Run from the ``S3-Ecological-Agent`` directory: ``python scripts/export_json_schemas.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3_ecological.schemas.common import EvidenceReference, Issue, ToolResult  # noqa: E402
from s3_ecological.schemas.request import (  # noqa: E402
    ExternalAgentEvidence,
    Location,
    ObservationContext,
    ObservationRequest,
    VisualCandidate,
)
from s3_ecological.schemas.response import (  # noqa: E402
    AssessmentResult,
    EvidenceRecord,
    RerankedCandidate,
    ResolvedTaxon,
    UncertaintyInfo,
)
from s3_ecological.schemas.snapshot import (  # noqa: E402
    ImportRejection,
    ImportReport,
    OccurrenceSnapshot,
    OutputFileChecksum,
    TaxonomySnapshot,
    TaxonomySnapshotItem,
)
from s3_ecological.settings import S3Settings  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "json_schemas"

MODELS = [
    Location,
    VisualCandidate,
    ObservationContext,
    ExternalAgentEvidence,
    ObservationRequest,
    ResolvedTaxon,
    RerankedCandidate,
    UncertaintyInfo,
    EvidenceRecord,
    AssessmentResult,
    Issue,
    EvidenceReference,
    S3Settings,
    OccurrenceSnapshot,
    TaxonomySnapshotItem,
    TaxonomySnapshot,
    ImportRejection,
    OutputFileChecksum,
    ImportReport,
]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        schema = model.model_json_schema()
        output_path = OUTPUT_DIR / f"{model.__name__}.schema.json"
        output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"wrote {output_path.relative_to(OUTPUT_DIR.parent)}")

    # ToolResult is generic; export one concrete parameterization to confirm
    # the generic envelope itself is schema-exportable.
    concrete_tool_result = ToolResult[ResolvedTaxon]
    schema = concrete_tool_result.model_json_schema()
    output_path = OUTPUT_DIR / "ToolResult_ResolvedTaxon.schema.json"
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"wrote {output_path.relative_to(OUTPUT_DIR.parent)}")

    print(f"Exported {len(MODELS) + 1} JSON Schemas to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
