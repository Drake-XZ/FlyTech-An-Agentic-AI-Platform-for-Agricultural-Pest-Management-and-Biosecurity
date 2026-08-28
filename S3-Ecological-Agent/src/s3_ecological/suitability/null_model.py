"""Null environmental-suitability model (EarlyDesign.md Profile v0.1 fusion
semantics: "set temporal_support=null and environmental_suitability=null in
v0.1 unless a separately tested component is explicitly enabled").

Environmental suitability modelling is Milestone 3 scope. This model keeps
the :class:`SuitabilityModel` Protocol wired into the pipeline now, so a
real implementation can be swapped in later without touching fusion or risk
logic, while guaranteeing v0.1 never fabricates a suitability score.
"""

from __future__ import annotations

from s3_ecological.interfaces.suitability import (
    CandidateSuitability,
    SuitabilityModel,
    SuitabilityRequest,
)
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus


class NullSuitabilityModel(SuitabilityModel):
    """Always reports every candidate as unavailable; never fabricates a score."""

    def estimate(self, request: SuitabilityRequest) -> ToolResult[list[CandidateSuitability]]:
        data = [
            CandidateSuitability(
                candidate_id=candidate.candidate_id,
                taxon_id=candidate.taxon_id,
                suitability=None,
                within_model_support=None,
            )
            for candidate in request.candidate_taxa
        ]
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=data,
            warnings=[
                Issue(
                    code=IssueCode.COMPONENT_UNAVAILABLE,
                    message="Environmental suitability is not implemented in Profile v0.1",
                    component="suitability.null_model",
                    retryable=False,
                )
            ],
        )
